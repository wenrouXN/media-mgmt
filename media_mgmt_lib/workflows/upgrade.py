"""Upgrade library quality: NF fill (netdisk→PT-from-NF) first, then PT watch."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.quality_pref import parse_quality_params
from media_mgmt_lib.workflows import duplicates as w_duplicates
from media_mgmt_lib.workflows import library as w_library
from media_mgmt_lib.workflows import watch as w_watch
from media_mgmt_lib.workflows._util import fail, mp, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Re-acquire better quality version.

    Default preference order (CEO 2026-07-20):
      1) nf_fill (NextFind resources once: netdisk grab, then PT rows from same result)
      2) PT via watch with skip_hdhive (only if netdisk/NF path fails or prefer=pt)

    params:
      title | tmdbid
      episode / season
      resolution (default 2160p for upgrade intent)
      require_chinese / lang=zh
      hdr_mode=sdr|hdr|any
      prefer: hdhive|nextfind|pt|auto
      execute / yes / dry_run / probe / force
      force_mp_search: allow MP re-search inside fill when NF empty
    """
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    qpref = parse_quality_params(params)
    if not qpref.get("resolution") and params.get("resolution") is None:
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
        qpref["require_chinese"] = True
        if params.get("no_chinese") in (True, "true", "1", "yes"):
            qpref["require_chinese"] = False

    prefer = str(params.get("prefer") or "hdhive").lower()
    if prefer in {"hidive", "hd", "nextfind", "nf", "openapi", "netdisk"}:
        prefer = "hdhive"
    execute = str(params.get("execute") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    if dry_run:
        execute = False
    force = str(params.get("force") or "").lower() in {"1", "true", "yes"}
    season = params.get("season")
    episode = params.get("episode")
    probe = str(params.get("probe") or "").lower() in {"1", "true", "yes"}
    live = execute or probe

    # identify: prefer NF via library helper path / nextfind identify
    media = None
    identify_path = "moviepilot"
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if call_op("nextfind", "health", {}).get("success"):
            idr = call_op(
                "nextfind",
                "identify",
                {
                    "title": title,
                    "q": title,
                    "tmdbid": tmdbid,
                    "media_type": params.get("media_type") or params.get("mtype"),
                    "year": params.get("year"),
                    "select": params.get("select") or 1,
                },
            )
            if idr.get("success") and isinstance(idr.get("selected"), dict):
                media = idr["selected"]
                identify_path = "nextfind_openapi"
    except Exception:  # noqa: BLE001
        pass
    if not isinstance(media, dict):
        identified = mp(
            "identify",
            title=title,
            tmdbid=tmdbid,
            media_type=params.get("media_type") or params.get("mtype"),
            year=params.get("year"),
        )
        media = identified.get("selected") if isinstance(identified, dict) else None
        identify_path = "moviepilot"
    if not isinstance(media, dict):
        return fail("identify_failed", detail="no selected media")

    title = media.get("title") or title
    tmdbid = media.get("tmdb_id") or media.get("tmdbid") or tmdbid
    mtype = media.get("type") or media.get("media_type") or params.get("media_type") or "电视剧"

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
        "identify_path": identify_path,
        "steps": [
            "nf_fill" if prefer in {"hdhive", "auto"} else "pt",
            "pt_fallback" if prefer in {"hdhive", "auto"} else None,
            "duplicates_compare",
        ],
        "note": "不自动删除旧版本；成功后用 duplicates 建议保留哪条",
    }
    plan["steps"] = [s for s in plan["steps"] if s]

    actions: dict[str, Any] = {}
    fill_result = None
    hdhive_result = None
    pt_result = None
    needs_confirm = False
    chosen_source = None

    # 1) NF fill (shared helper) — probe or execute
    if live and prefer in {"hdhive", "auto"}:
        from media_mgmt_lib.workflows.nf_fill import fill_missing

        fill_params: dict[str, Any] = {
            "title": title,
            "tmdbid": tmdbid,
            "media_type": mtype,
            "season": season,
            "episode": episode,
            "dry_run": (not execute) or dry_run,
            "transfer": bool(execute),
            "prefer": "auto" if prefer == "auto" else "netdisk",
            "resolution": qpref.get("resolution"),
            "require_chinese": qpref.get("require_chinese"),
            "hdr_mode": qpref.get("hdr_mode"),
            "force_mp_search": params.get("force_mp_search"),
            "select": params.get("select") or 1,
        }
        fill_result = fill_missing(fill_params)
        actions["nf_fill"] = {
            "success": fill_result.get("success"),
            "path": fill_result.get("path"),
            "error": fill_result.get("error"),
            "stage": fill_result.get("stage"),
            "steps": fill_result.get("steps"),
            "best": fill_result.get("best") or fill_result.get("slug"),
            "summary": fill_result.get("summary"),
        }
        # alias for older consumers
        hdhive_result = {
            "success": fill_result.get("success"),
            "source": "nextfind_openapi" if fill_result.get("path") in {"netdisk", "nextfind_openapi"} else fill_result.get("path"),
            "path": fill_result.get("path"),
            "slug": (fill_result.get("best") or {}).get("slug") if isinstance(fill_result.get("best"), dict) else fill_result.get("slug"),
            "detail": fill_result,
        }
        actions["hdhive"] = hdhive_result
        if fill_result.get("success"):
            path = str(fill_result.get("path") or "")
            if path in {"netdisk", "nextfind_openapi"}:
                chosen_source = "nextfind_openapi"
            elif path in {"pt", "pt_from_nf", "moviepilot"}:
                chosen_source = "pt" if execute else "pt_candidate"
            else:
                chosen_source = path or "nextfind_openapi"
        else:
            plan["nf_fill_fail"] = fill_result.get("error") or fill_result.get("stage")
    elif not live and prefer in {"hdhive", "auto"}:
        actions["nf_fill"] = {
            "skipped": True,
            "reason": "dry_run_no_probe",
            "hint": "execute=true 才会真转存；probe=true 可探测 fill 路径",
        }
        actions["hdhive"] = actions["nf_fill"]

    # 2) PT fallback / primary (watch with skip netdisk)
    do_pt = prefer == "pt" or (
        prefer in {"hdhive", "auto"}
        and (not fill_result or not fill_result.get("success"))
    )
    # If fill already chose pt path with success under dry, still report
    if fill_result and fill_result.get("success") and str(fill_result.get("path") or "").startswith("pt"):
        do_pt = False if execute else do_pt  # already handled by fill when execute+pt download

    if live and do_pt:
        search = mp("search", title=title, tmdbid=tmdbid)
        items: list[Any] = []
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

    def _netdisk_ok(src: str | None) -> bool:
        if not src:
            return False
        return src in {"hdhive_115", "nextfind_openapi"} or str(src).startswith("nextfind") or str(src).startswith("hdhive")

    summary_bits = [
        f"升级《{title}》",
        f"质量={qpref}",
        f"优先={prefer}",
        f"identify={identify_path}",
    ]
    if chosen_source:
        summary_bits.append(f"命中源={chosen_source}")
    if needs_confirm and not force:
        summary_bits.append("PT 多候选需确认")
    if not execute:
        summary_bits.append("仅计划 dry_run" + ("+probe" if probe else "（未探测源）"))
    else:
        summary_bits.append("已执行")

    if execute:
        success = (
            _netdisk_ok(chosen_source)
            or chosen_source == "pt"
            or bool((pt_result or {}).get("success") or (fill_result or {}).get("success"))
        )
    else:
        success = True

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
            "identify_path": identify_path,
            "library": {
                "exists": lib.get("exists"),
                "authority": lib.get("authority"),
                "exists_nf": lib.get("exists_nf"),
                "has_transfer_record": lib.get("has_transfer_record"),
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
                "probe": "run upgrade --param title=… --param probe=true  # NF fill dry path",
                "force_pt_pick": "run upgrade --param ... --param prefer=pt --param execute=true --param force=true",
                "after": "run duplicates 对比新旧版本，确认后再删旧源",
            },
        }
    )
