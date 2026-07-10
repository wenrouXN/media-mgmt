from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp
from media_mgmt_lib.workflows import library as lib_wf

def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    lib = lib_wf.run(params)
    missing = lib.get("missing") if isinstance(lib, dict) else None
    has_update = bool(isinstance(missing, dict) and missing.get("has_update"))
    # subscription progress if any
    media = (lib or {}).get("media") or {}
    tid = media.get("tmdb_id") or tmdbid
    sub = mp("subscribe", action="get", tmdbid=tid, title=media.get("title") or title, season=params.get("season") or 1)
    sub_info = None
    if isinstance(sub, dict) and sub.get("id"):
        sub_info = {
            "id": sub.get("id"),
            "name": sub.get("name"),
            "season": sub.get("season"),
            "total_episode": sub.get("total_episode"),
            "completed_episode": sub.get("completed_episode"),
            "lack_episode": sub.get("lack_episode"),
        }
        if sub.get("lack_episode"):
            has_update = True
    eps = (missing or {}).get("missing_episodes") if isinstance(missing, dict) else []
    return ok({
        "workflow": "updates",
        "media": media,
        "exists_in_library": lib.get("exists"),
        "has_update": has_update,
        "missing_episodes": eps,
        "missing_raw": missing,
        "subscription": sub_info,
        "library": lib,
        "summary": (
            f"《{media.get('title') or title}》"
            + ("有更新/缺集" if has_update else "未见缺集")
            + (f"：缺 {[e.get('episode') for e in eps[:10]]}" if eps else "")
            + (f"；订阅缺 {sub_info.get('lack_episode')} 集" if sub_info and sub_info.get("lack_episode") else "")
        ),
        "next": "watch / subscribe" if has_update else "nothing",
    })
