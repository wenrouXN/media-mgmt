from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows import library as lib_wf
from media_mgmt_lib.workflows._util import fail, mp, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    lib = lib_wf.run(params)
    missing = lib.get("missing") if isinstance(lib, dict) else None
    has_update = bool(isinstance(missing, dict) and missing.get("has_update"))
    media = (lib or {}).get("media") or {}
    tid = media.get("tmdb_id") or tmdbid
    sub = mp(
        "subscribe",
        action="get",
        tmdbid=tid,
        title=media.get("title") or title,
        season=params.get("season") or 1,
    )
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

    schedule = mp(
        "schedule",
        title=media.get("title") or title,
        tmdbid=tid,
        media_type=media.get("type") or params.get("media_type"),
        season=params.get("season") or 1,
    )
    try:
        from media_mgmt_lib.workflows import catchup as catchup_wf

        catchup = catchup_wf.run(
            {
                "title": media.get("title") or title,
                "tmdbid": tid,
                "season": params.get("season") or 1,
                "media_type": media.get("type") or params.get("media_type"),
                "dry_run": True,
            }
        )
    except Exception as e:  # noqa: BLE001
        catchup = {"success": False, "error": str(e)}

    next_up = None
    if isinstance(schedule, dict):
        next_up = schedule.get("next_upcoming") or schedule.get("next_episode_to_air")

    download_now = ((catchup or {}).get("plan") or {}).get("download_now") or []
    subscribe_for = ((catchup or {}).get("plan") or {}).get("subscribe_for") or []

    summary = (
        f"《{media.get('title') or title}》"
        + ("有更新/缺集" if has_update else "未见缺集")
        + (f"：缺 {[e.get('episode') for e in eps[:10]]}" if eps else "")
        + (f"；订阅缺 {sub_info.get('lack_episode')} 集" if sub_info and sub_info.get("lack_episode") else "")
    )
    if download_now:
        summary += f"；已播可下 {[x.get('episode') for x in download_now[:8]]}"
    if subscribe_for:
        summary += f"；未播改订 {[x.get('episode') for x in subscribe_for[:8]]}"
    if isinstance(next_up, dict) and (next_up.get("air_date") or next_up.get("episode") or next_up.get("episode_number")):
        summary += (
            f"；下集 E{next_up.get('episode') or next_up.get('episode_number')} @ {next_up.get('air_date')}"
        )

    return ok(
        {
            "workflow": "updates",
            "media": media,
            "exists_in_library": lib.get("exists"),
            "has_update": has_update,
            "missing_episodes": eps,
            "missing_raw": missing,
            "subscription": sub_info,
            "library": lib,
            "schedule": schedule if isinstance(schedule, dict) and schedule.get("success") else schedule,
            "catchup_plan": catchup,
            "download_now": download_now,
            "subscribe_for": subscribe_for,
            "summary": summary,
            "next": (
                "run catchup --param execute=true"
                if download_now or subscribe_for
                else ("watch / subscribe" if has_update else "nothing")
            ),
        }
    )
