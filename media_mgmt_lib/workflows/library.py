from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    mtype = params.get("mtype") or params.get("media_type") or "电视剧"
    # identify for normalized title
    media = None
    if title or tmdbid:
        identified = mp("identify", title=title, tmdbid=tmdbid, media_type=mtype)
        media = identified.get("selected") if isinstance(identified, dict) else None
        if isinstance(media, dict):
            title = media.get("title") or title
            tmdbid = media.get("tmdb_id") or media.get("tmdbid") or tmdbid
            mtype = media.get("type") or mtype
    # title match is more reliable for Emby in this env
    exists_title = mp("library_exists", title=title, mtype=mtype, season=params.get("season")) if title else None
    exists_tmdb = mp("library_exists", tmdbid=tmdbid, mtype=mtype, title=title, season=params.get("season")) if tmdbid else None
    exists = bool((exists_title or {}).get("exists") or (exists_tmdb or {}).get("exists"))
    item = (exists_title or {}).get("item") or (exists_tmdb or {}).get("item")
    missing = None
    if str(mtype) in {"电视剧", "tv", "TV", "动漫"} or (media or {}).get("type") in {"电视剧", "tv"}:
        missing = mp("missing_episodes", title=title, tmdbid=tmdbid, media_type=mtype, media=media)
    return ok({
        "workflow": "library",
        "media": {"title": title, "tmdb_id": tmdbid, "type": mtype},
        "exists": exists,
        "library_item": item,
        "exists_by_title": exists_title,
        "exists_by_tmdb": exists_tmdb,
        "missing": missing,
        "summary": (
            f"库中{'有' if exists else '无'}《{title}》"
            + (f"；{missing.get('summary')}" if isinstance(missing, dict) and missing.get("summary") else "")
        ),
    })
