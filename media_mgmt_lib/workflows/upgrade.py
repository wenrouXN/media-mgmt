"""Upgrade library quality: prefer HDHive→115, then PT with quality filters."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.quality_pref import parse_quality_params
from media_mgmt_lib.workflows._util import fail, mp, ok
from media_mgmt_lib.workflows import duplicates as w_duplicates
from media_mgmt_lib.workflows import library as w_library
from media_mgmt_lib.workflows import watch as w_watch


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Re-acquire better quality version.

    Default preference order (user policy):
      1) HDHive → unlock 115 → MoviePilot transfer_share
      2) PT torrent download with quality filters

    params:
      title | tmdbid
      episode / season
      resolution (default 2160p for upgrade intent)
      require_chinese / lang=zh
      hdr_mode=sdr|hdr|any (default sdr for upgrade intent when user said 4k sdr)
      prefer: hdhive|pt|auto (default hdhive)
      execute / yes: actually download/transfer
      dry_run: plan only
      force: download even if needs_confirm
    """
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    qpref = parse_quality_params(params)
    # upgrade defaults: 4K + Chinese-friendly + SDR unless explicitly set
    if not qpref.get("resolution") and params.get("resolution") is None:
        # only apply default when user didn't pass resolution key at all
        if "resolution" not in params and "prefer_resolution" not in params:
            qpref["resolution"] = "2160p"
    if "hdr_mode" not in params and "hdr" not in params:
        qpref["hdr_mode"] = qpref.get("hdr_mode") or "sdr"
    if (
        "require_chinese" not in params
        and "chinese" not in params
        and "lang" not in params
        and "language" not in params
    ):
        # default require chinese for upgrade quality complaints
        qpref["require_chinese"] = True if params.get("require_chinese") is None else qpref["require_chinese"]
        if params.get("no_chinese") in (True, "true", "1", "yes"):
            qpref["require_chinese"] = False
        elif str(params.get("require_chinese", "true")).lower() not in {"false", "0", "no"}:
            # if user said 没有中文 / 要中文, default true
            if params.get("require_chinese") is None:
                qpref["require_chinese"] = True

    prefer = str(params.get("prefer") or "hdhive").lower()  # user: HDHive 115 first
    if prefer in {"hidive", "hd"}:  # common typo for hdhive
        prefer = "hdhive"
    execute = str(params.get("execute") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    if dry_run:
        execute = False
    force = str(params.get("force") or "").lower() in {"1", "true", "yes"}
    season = params.get("season")
    episode = params.get("episode")

    # identify
    identified = mp(
        "identify",
        title=title,
        tmdbid=tmdbid,
        media_type=params.get("media_type") or params.get("mtype"),
        year=params.get("year"),
    )
    media = identified.get("selected") if isinstance(identified, dict) else None
    if not isinstance(media, dict):
        return fail("identify_failed", detail=identified)
    title = media.get("title") or title
    tmdbid = media.get("tmdb_id") or media.get("tmdbid") or tmdbid
    mtype = media.get("type") or params.get("media_type") or "电视剧"

    # current library snapshot
    lib = w_library.run(
        {
            "title": title,
            "tmdbid": tmdbid,
            "media_type": mtype,
            "season": season,
        }
    )
    dup = None
    try:
        dup = w_duplicates.run({"title": title, "tmdbid": tmdbid, "count": 50})
    except Exception as e:  # noqa: BLE001
        dup = {"success": False, "error": str(e)}

    plan: dict[str, Any] = {
        "prefer": prefer,
        "quality": qpref,
        "steps": [
            "hdhive_115" if prefer in {"hdhive", "auto"} else "pt",
            "pt_fallback" if prefer in {"hdhive", "auto"} else None,
            "duplicates_compare",
        ],
        "note": "不自动删除旧版本；成功后用 duplicates 建议保留哪条",
    }
    plan["steps"] = [s for s in plan["steps"] if s]

    actions: dict[str, Any] = {}
    hdhive_result = None
    pt_result = None
    needs_confirm = False
    chosen_source = None
    probe = str(params.get("probe") or "").lower() in {"1", "true", "yes"}
    # dry_run without probe: only build plan (no HDHive browser / PT search) — fast & safe
    live = execute or probe

    # 1) HDHive first (user preference: 115 transfer)
    if live and prefer in {"hdhive", "auto"}:
        hdhive_params = {
            "q": title,
            "tmdbid": tmdbid,
            "media_type": mtype,
            "transfer": bool(execute),
            "resolution": qpref.get("resolution"),
            "require_chinese": qpref.get("require_chinese"),
            "hdr_mode": qpref.get("hdr_mode"),
            "select": params.get("select") or 1,
        }
        from media_mgmt_lib.ops import call_op
        import media_mgmt_lib.ops.bootstrap  # noqa: F401

        hdhive_result = call_op("hdhive", "grab", hdhive_params)
        actions["hdhive"] = hdhive_result
        if hdhive_result.get("success"):
            chosen_source = "hdhive_115"
        else:
            plan["hdhive_fail"] = hdhive_result.get("error") or hdhive_result.get("detail")
    elif not live and prefer in {"hdhive", "auto"}:
        actions["hdhive"] = {
            "skipped": True,
            "reason": "dry_run_no_probe",
            "hint": "execute=true 才会 HDHive→115；probe=true 可在不下的情况下探测",
        }

    # 2) PT fallback / primary
    do_pt = prefer == "pt" or (
        prefer in {"hdhive", "auto"} and (not hdhive_result or not hdhive_result.get("success"))
    )
    if live and do_pt:
        search = mp("search", title=title, tmdbid=tmdbid)
        items = []
        if isinstance(search, dict):
            for key in ("data", "results", "items"):
                if isinstance(search.get(key), list):
                    items = search[key]
                    break
        from media_mgmt_lib.torrent_pick import pick_torrent, summarize_candidate

        site_priority = None
        if params.get("site_priority"):
            site_priority = [s.strip() for s in str(params["site_priority"]).split(",") if s.strip()]
        picked = pick_torrent(
            items if isinstance(items, list) else [],
            season=int(season) if season is not None else None,
            episode=int(episode) if episode is not None else None,
            prefer_resolution=qpref.get("resolution") or "2160p",
            site_priority=site_priority,
            require_chinese=bool(qpref.get("require_chinese")),
            hdr_mode=str(qpref.get("hdr_mode") or "sdr"),
            hard_filter=True,
            top_n=int(params.get("top") or 5),
        )
        needs_confirm = bool(picked.get("needs_confirm"))
        actions["pt_pick"] = {
            "search_count": len(items) if isinstance(items, list) else 0,
            "selected": summarize_candidate(picked["selected"]) if picked.get("selected") else None,
            "candidates": [summarize_candidate(x) for x in (picked.get("candidates") or [])],
            "quality": picked.get("quality"),
            "needs_confirm": needs_confirm,
            "reason": picked.get("reason"),
        }
        if picked.get("selected") and execute and (not needs_confirm or force):
            pt_result = w_watch.run(
                {
                    "title": title,
                    "tmdbid": tmdbid,
                    "season": season,
                    "episode": episode,
                    "yes": True,
                    "prefer": "pt",
                    "skip_hdhive": True,
                    "resolution": qpref.get("resolution") or "2160p",
                    "require_chinese": qpref.get("require_chinese"),
                    "hdr_mode": qpref.get("hdr_mode"),
                }
            )
            actions["pt_download"] = pt_result
            if pt_result.get("success"):
                chosen_source = "pt"
        elif picked.get("selected") and not execute:
            chosen_source = "pt_candidate"
        elif not picked.get("selected"):
            plan["pt_fail"] = "no_quality_match"
    elif not live and do_pt:
        actions["pt_pick"] = {
            "skipped": True,
            "reason": "dry_run_no_probe",
            "quality_filter": qpref,
        }

    # if hdhive success and execute, transfer already attempted inside grab
    if execute and prefer in {"hdhive", "auto"} and hdhive_result and hdhive_result.get("success"):
        # re-run with transfer true already done when execute
        if not hdhive_result.get("transfer") and hdhive_result.get("share_url"):
            # unlock-only path: transfer now
            tr = mp("transfer_share", share_url=hdhive_result.get("share_url"))
            actions["transfer_share"] = tr
            if tr.get("success") is not False:
                chosen_source = "hdhive_115"

    summary_bits = [
        f"升级《{title}》",
        f"质量={qpref}",
        f"优先={prefer}",
    ]
    if chosen_source:
        summary_bits.append(f"命中源={chosen_source}")
    if needs_confirm and not force:
        summary_bits.append("PT 多候选需确认")
    if not execute:
        summary_bits.append("仅计划 dry_run" + ("+probe" if probe else "（未探测源）"))
    else:
        summary_bits.append("已执行")

    success = True
    if execute:
        success = chosen_source in {"hdhive_115", "pt"} or bool(
            (pt_result or {}).get("success") or (hdhive_result or {}).get("success")
        )
    else:
        success = bool(
            (hdhive_result and (hdhive_result.get("success") or hdhive_result.get("best_resource")))
            or (actions.get("pt_pick") or {}).get("selected")
        ) or True  # plan always returns success with empty candidates flagged

    return ok(
        {
            "workflow": "upgrade",
            "success": success if execute else True,
            "media": {
                "title": title,
                "tmdb_id": tmdbid,
                "type": mtype,
                "year": media.get("year"),
            },
            "library": {
                "exists": lib.get("exists"),
                "summary": lib.get("summary"),
            },
            "duplicates": {
                "duplicate_group_count": (dup or {}).get("duplicate_group_count"),
                "summary": (dup or {}).get("summary"),
            },
            "quality": qpref,
            "prefer": prefer,
            "plan": plan,
            "needs_confirm": needs_confirm and not force,
            "chosen_source": chosen_source,
            "actions": actions,
            "execute": execute,
            "summary": "；".join(summary_bits),
            "next": {
                "execute": (
                    f"run upgrade --param tmdbid={tmdbid} --param title={title}"
                    + (f" --param episode={episode}" if episode is not None else "")
                    + " --param execute=true"
                    + f" --param resolution={qpref.get('resolution')}"
                    + f" --param hdr_mode={qpref.get('hdr_mode')}"
                    + (" --param require_chinese=true" if qpref.get("require_chinese") else "")
                ),
                "force_pt_pick": "run upgrade --param ... --param prefer=pt --param pick_index=N --param execute=true --param force=true",
                "after": "run duplicates 对比新旧版本，确认后再删旧源",
            },
        }
    )
