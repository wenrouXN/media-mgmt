"""Catch-up plan: download aired missing eps; subscribe for unreleased."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, mp, ok
from media_mgmt_lib.workflows import subscribe as w_subscribe
from media_mgmt_lib.workflows import watch as w_watch


def _ep_key(season: int | None, episode: int | None) -> str:
    return f"S{int(season or 1):02d}E{int(episode or 0):02d}"


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Plan (and optionally execute) catch-up.

    Logic:
      1. identify / media_detail + TMDB schedule (aired vs upcoming)
      2. library missing episodes
      3. download_candidates = missing ∩ aired
      4. subscribe_needed if any upcoming still missing (or show unfinished)
      5. if execute=true: watch each aired missing (or first N), optionally create subscribe

    params:
      title | tmdbid
      season (default 1)
      execute / yes: actually download + subscribe
      max_download: max episodes to download this run (default 3)
      dry_run: force plan only
      as_of: YYYY-MM-DD for schedule tests
      subscribe: force subscribe create when execute
    """
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    season = int(params.get("season") or 1)
    execute = str(params.get("execute") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    if dry_run:
        execute = False
    max_download = int(params.get("max_download") or 3)

    # schedule
    schedule = mp(
        "schedule",
        title=title,
        tmdbid=tmdbid,
        media_type=params.get("media_type") or params.get("mtype"),
        season=season,
        as_of=params.get("as_of"),
    )
    if not schedule.get("success"):
        return fail("schedule_failed", detail=schedule)
    media = schedule.get("media") or {}
    title = media.get("title") or title
    tmdbid = media.get("tmdb_id") or tmdbid
    aired = {int(e["episode"]): e for e in (schedule.get("aired") or []) if e.get("episode") is not None}
    upcoming = {int(e["episode"]): e for e in (schedule.get("upcoming") or []) if e.get("episode") is not None}

    # library missing
    missing_res = mp(
        "missing_episodes",
        title=title,
        tmdbid=tmdbid,
        media_type=media.get("type") or params.get("media_type") or "电视剧",
    )
    missing_eps: list[int] = []
    if isinstance(missing_res, dict) and missing_res.get("success"):
        for item in missing_res.get("missing_episodes") or []:
            if int(item.get("season") or season) != season:
                continue
            if item.get("episode") is not None:
                missing_eps.append(int(item["episode"]))
    missing_eps = sorted(set(missing_eps))

    # if missing API empty but we have seasons map, treat none missing as fully present
    download_candidates = []
    wait_subscribe = []
    for ep in missing_eps:
        if ep in aired:
            download_candidates.append(
                {
                    "season": season,
                    "episode": ep,
                    "air_date": aired[ep].get("air_date"),
                    "action": "download",
                    "reason": "aired_and_missing",
                }
            )
        elif ep in upcoming:
            wait_subscribe.append(
                {
                    "season": season,
                    "episode": ep,
                    "air_date": upcoming[ep].get("air_date"),
                    "action": "subscribe",
                    "reason": "not_aired_yet",
                }
            )
        else:
            # missing but not in schedule tables — still try download (might be special)
            download_candidates.append(
                {
                    "season": season,
                    "episode": ep,
                    "air_date": None,
                    "action": "download",
                    "reason": "missing_unknown_air_date",
                }
            )

    # if library reports no missing but upcoming exists and user wants show — still suggest subscribe
    subscribe_needed = bool(wait_subscribe) or (
        bool(upcoming) and (missing_eps or str(media.get("status") or "").lower() in {"returning series", "in production"})
    )
    # if no missing data at all, still list upcoming as subscribe-only plan
    if not missing_eps and upcoming:
        for ep, meta in sorted(upcoming.items()):
            wait_subscribe.append(
                {
                    "season": season,
                    "episode": ep,
                    "air_date": meta.get("air_date"),
                    "action": "subscribe",
                    "reason": "upcoming_not_in_library_gap",
                }
            )
        # dedupe
        seen = set()
        deduped = []
        for w in wait_subscribe:
            k = w["episode"]
            if k in seen:
                continue
            seen.add(k)
            deduped.append(w)
        wait_subscribe = deduped
        subscribe_needed = True

    plan = {
        "download_now": download_candidates,
        "subscribe_for": wait_subscribe,
        "skip_search_unreleased": True,
    }

    actions: dict[str, Any] = {"downloaded": [], "subscribe": None, "nf_fill": []}
    prefer = str(params.get("prefer") or "auto").lower()
    if execute:
        # CEO: NF fill first (netdisk → PT-from-NF → MP only if needed), unless prefer=pt
        from media_mgmt_lib.workflows.nf_fill import fill_missing

        for item in download_candidates[:max_download]:
            if prefer in {"pt", "torrent"}:
                wr = w_watch.run(
                    {
                        "title": title,
                        "tmdbid": tmdbid,
                        "season": season,
                        "episode": item["episode"],
                        "yes": True,
                        "skip_hdhive": True,
                        "prefer": "pt",
                    }
                )
                actions["downloaded"].append(
                    {
                        "episode": item["episode"],
                        "path": "pt",
                        "success": bool(wr.get("success")),
                        "result": wr,
                    }
                )
                continue

            fr = fill_missing(
                {
                    "title": title,
                    "tmdbid": tmdbid,
                    "media_type": media.get("type") or params.get("media_type") or "tv",
                    "season": season,
                    "episode": item["episode"],
                    "dry_run": False,
                    "prefer": prefer,
                    "force_mp_search": params.get("force_mp_search"),
                    "resolution": params.get("resolution"),
                    "require_chinese": params.get("require_chinese"),
                    "hdr_mode": params.get("hdr_mode"),
                }
            )
            actions["nf_fill"].append({"episode": item["episode"], "result": fr})
            if fr.get("success"):
                actions["downloaded"].append(
                    {
                        "episode": item["episode"],
                        "path": fr.get("path"),
                        "success": True,
                        "result": fr,
                    }
                )
            else:
                # last resort watch PT
                wr = w_watch.run(
                    {
                        "title": title,
                        "tmdbid": tmdbid,
                        "season": season,
                        "episode": item["episode"],
                        "yes": True,
                        "skip_hdhive": True,
                        "prefer": "pt",
                    }
                )
                actions["downloaded"].append(
                    {
                        "episode": item["episode"],
                        "path": "pt_fallback",
                        "success": bool(wr.get("success")),
                        "result": wr,
                        "nf_fill_error": fr.get("error"),
                    }
                )
        if subscribe_needed or str(params.get("subscribe") or "").lower() in {"1", "true", "yes"}:
            actions["subscribe"] = w_subscribe.run(
                {
                    "title": title,
                    "tmdbid": tmdbid,
                    "media_type": media.get("type") or "电视剧",
                    "season": season,
                    "action": "create",
                    "fill": False,  # already filled above per-ep
                }
            )

    summary_parts = [
        f"《{title}》S{season}",
        f"已播可下 {len(download_candidates)} 集",
        f"未播改订阅 {len(wait_subscribe)} 集",
    ]
    if execute:
        ok_n = sum(1 for x in actions["downloaded"] if x.get("success"))
        summary_parts.append(f"已执行下载 {ok_n}/{min(len(download_candidates), max_download)}")
        if actions.get("subscribe"):
            summary_parts.append("已处理订阅")
    else:
        summary_parts.append("仅计划（execute=true 才下/订）")

    return ok(
        {
            "workflow": "catchup",
            "media": media,
            "season": season,
            "today": schedule.get("today"),
            "schedule_summary": schedule.get("summary"),
            "next_episode_to_air": schedule.get("next_episode_to_air"),
            "next_upcoming": schedule.get("next_upcoming"),
            "library_missing": missing_eps,
            "plan": plan,
            "subscribe_needed": subscribe_needed,
            "execute": execute,
            "actions": actions if execute else None,
            "summary": "；".join(summary_parts),
            "next": {
                "execute": f"run catchup --param tmdbid={tmdbid} --param title={title} --param execute=true",
                "download_one": f"run watch --param tmdbid={tmdbid} --param episode=N --param yes=true",
                "subscribe_only": f"run subscribe --param tmdbid={tmdbid} --param action=create",
            },
        }
    )
