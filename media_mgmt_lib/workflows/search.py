from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    identified = mp("identify", title=title, tmdbid=tmdbid, media_type=params.get("media_type"))
    media = identified.get("selected") if isinstance(identified, dict) else None
    search = mp("search", title=title or (media or {}).get("title"), tmdbid=tmdbid or (media or {}).get("tmdb_id") or (media or {}).get("tmdbid"))
    # try pick if results present
    items = []
    if isinstance(search, dict):
        for key in ("data", "results", "items"):
            if isinstance(search.get(key), list):
                items = search[key]
                break
        if not items and isinstance(search.get("data"), dict):
            # sometimes nested
            pass
    picked = None
    if items:
        import json, tempfile
        from pathlib import Path
        p = Path("/tmp/media-mgmt-search-results.json")
        p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        from media_mgmt_lib.ops._runner import run_mp_api
        args = ["pick", "--results-json", str(p)]
        if params.get("episode") is not None:
            args += ["--episode", str(params["episode"])]
        if params.get("season") is not None:
            args += ["--season", str(params["season"])]
        picked = run_mp_api(args)
    count = len(items) if isinstance(items, list) else None
    return ok({
        "workflow": "search",
        "media": media,
        "result_count": count,
        "search": search if count is None or (count or 0) <= 5 else {"truncated": True, "result_count": count, "sample": (items or [])[:3]},
        "pick": picked,
        "summary": f"search '{title or tmdbid}': {count if count is not None else '?'} candidates",
    })
