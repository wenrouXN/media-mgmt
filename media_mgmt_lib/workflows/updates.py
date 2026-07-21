"""Updates / missing diagnosis: dual library + dual subscribe + optional NF fill plan."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows import library as lib_wf
from media_mgmt_lib.workflows._util import fail, mp, ok


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes"}


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    lib = lib_wf.run(params)
    missing = lib.get("missing") if isinstance(lib, dict) else None
    has_update = bool(isinstance(missing, dict) and missing.get("has_update"))
    media = (lib or {}).get("media") or {}
    tid = media.get("tmdb_id") or tmdbid
    season = params.get("season") or 1

    # dual subscribe read
    sub = mp(
        "subscribe",
        action="get",
        tmdbid=tid,
        title=media.get("title") or title,
        season=season,
    )
    nf_sub = None
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if call_op("nextfind", "health", {}).get("success"):
            mtype = "tv"
            raw = str(media.get("type") or params.get("media_type") or "").lower()
            if raw in {"movie", "电影", "film"}:
                mtype = "movie"
            nf_sub = call_op("nextfind", "subscribe_info", {"tmdbid": tid, "media_type": mtype})
    except Exception as e:  # noqa: BLE001
        nf_sub = {"success": False, "error": str(e)}

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
        season=season,
    )
    try:
        from media_mgmt_lib.workflows import catchup as catchup_wf

        catchup = catchup_wf.run(
            {
                "title": media.get("title") or title,
                "tmdbid": tid,
                "season": season,
                "media_type": media.get("type") or params.get("media_type"),
                "dry_run": True,
                "prefer": params.get("prefer") or "auto",
            }
        )
    except Exception as e:  # noqa: BLE001
        catchup = {"success": False, "error": str(e)}

    next_up = None
    if isinstance(schedule, dict):
        next_up = schedule.get("next_upcoming") or schedule.get("next_episode_to_air")

    download_now = ((catchup or {}).get("plan") or {}).get("download_now") or []
    subscribe_for = ((catchup or {}).get("plan") or {}).get("subscribe_for") or []

    # optional fill plan (dry) for first missing ep / movie
    fill_plan = None
    if _truthy(params.get("fill_plan") if params.get("fill_plan") is not None else True):
        try:
            from media_mgmt_lib.workflows.nf_fill import fill_missing

            fill_params: dict[str, Any] = {
                "title": media.get("title") or title,
                "tmdbid": tid,
                "media_type": media.get("type") or params.get("media_type") or "tv",
                "season": season,
                "dry_run": True,
                "prefer": params.get("prefer") or "auto",
                "force_mp_search": params.get("force_mp_search"),
            }
            if eps and isinstance(eps[0], dict) and eps[0].get("episode") is not None:
                fill_params["episode"] = eps[0].get("episode")
            elif download_now:
                fill_params["episode"] = download_now[0].get("episode")
            fill_plan = fill_missing(fill_params)
        except Exception as e:  # noqa: BLE001
            fill_plan = {"success": False, "error": str(e)}

    summary = (
        f"《{media.get('title') or title}》"
        + ("有更新/缺集" if has_update else "未见缺集")
        + (f"：缺 {[e.get('episode') for e in eps[:10]]}" if eps else "")
        + (f"；订阅缺 {sub_info.get('lack_episode')} 集" if sub_info and sub_info.get("lack_episode") else "")
    )
    if lib.get("authority"):
        summary += f"；有没有={lib.get('authority')}"
    if lib.get("has_transfer_record"):
        summary += "；MP有整理记录"
    elif lib.get("moviepilot_organize") is not None:
        summary += "；MP无整理记录"
    if download_now:
        summary += f"；已播可下 {[x.get('episode') for x in download_now[:8]]}"
    if subscribe_for:
        summary += f"；未播改订 {[x.get('episode') for x in subscribe_for[:8]]}"
    if isinstance(next_up, dict) and (next_up.get("air_date") or next_up.get("episode") or next_up.get("episode_number")):
        summary += (
            f"；下集 E{next_up.get('episode') or next_up.get('episode_number')} @ {next_up.get('air_date')}"
        )
    if isinstance(fill_plan, dict) and fill_plan.get("path"):
        summary += f"；fill_plan path={fill_plan.get('path')} ok={fill_plan.get('success')}"

    next_hint = "nothing"
    if download_now or subscribe_for:
        next_hint = "run catchup --param execute=true  # NF fill first then PT"
    elif has_update:
        next_hint = "watch / subscribe"

    return ok(
        {
            "workflow": "updates",
            "media": media,
            "exists_in_library": lib.get("exists"),
            "authority": lib.get("authority"),
            "exists_nf": lib.get("exists_nf"),
            "has_transfer_record": lib.get("has_transfer_record"),
            "moviepilot_organize": lib.get("moviepilot_organize"),
            "has_update": has_update,
            "missing_episodes": eps,
            "missing_raw": missing,
            "subscription": sub_info,
            "subscription_nf": nf_sub,
            "library": lib,
            "schedule": schedule if isinstance(schedule, dict) and schedule.get("success") else schedule,
            "catchup_plan": catchup,
            "download_now": download_now,
            "subscribe_for": subscribe_for,
            "fill_plan": fill_plan,
            "summary": summary,
            "next": next_hint,
        }
    )
