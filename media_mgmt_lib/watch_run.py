"""Orchestrate full watch pipeline (no argparse, no print)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

from media_mgmt_lib.torrent_pick import summarize_candidate
from media_mgmt_lib.watch_actions import (
    download_selected,
    ensure_clients,
    maybe_subscribe,
    status_snapshot,
    try_hdhive,
)
from media_mgmt_lib.watch_identify import identify_media
from media_mgmt_lib.watch_pipeline import pick_for_watch
from media_mgmt_lib.watch_search import search_pt_resources
from media_mgmt_lib.watch_stages import clear_stages, stage as _stage, stages_snapshot


def params_to_args(params: dict[str, Any]) -> SimpleNamespace:
    """Map workflow params to CLI-like namespace."""
    pick_n = params.get("pick_n")
    if pick_n is None:
        pick_n = params.get("pick")
    pick_index = params.get("pick_index")
    if pick_n is not None and str(pick_n).strip() != "" and pick_index is None:
        n = int(pick_n)
        if n < 1:
            raise ValueError("pick_n is 1-based (第一个=1)")
        pick_index = n - 1

    def b(key: str, default: bool = False) -> bool:
        v = params.get(key)
        if v is None:
            return default
        return str(v).lower() in {"1", "true", "yes", "on"}

    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    title = params.get("title") or params.get("q")
    if not title and tmdbid:
        title = f"tmdb:{tmdbid}"
    # Workflow: dry_run => no download; else default yes for agent
    dry = b("dry_run")
    yes = b("yes") or b("auto") or not dry
    return SimpleNamespace(
        title=title,
        media_type=params.get("media_type") or params.get("mtype"),
        year=params.get("year"),
        tmdbid=int(tmdbid) if tmdbid not in (None, "") else None,
        season=int(params["season"]) if params.get("season") not in (None, "") else None,
        episode=int(params["episode"]) if params.get("episode") not in (None, "") else None,
        prefer=str(params.get("prefer") or "auto"),
        skip_hdhive=b("skip_hdhive"),
        hdhive_only=b("hdhive_only"),
        force_pt=b("force_pt"),
        sites=params.get("sites"),
        resolution=params.get("resolution"),
        require_chinese=b("require_chinese") or b("chinese"),
        no_require_chinese=b("no_require_chinese"),
        allow_disc=b("allow_disc"),
        no_fx_sub=b("no_fx_sub"),
        hdr_mode=params.get("hdr_mode"),
        site_priority=params.get("site_priority") or "",
        site_name=params.get("site_name"),
        title_contains=params.get("title_contains"),
        page_url=params.get("page_url"),
        top=int(params.get("top") or 3),
        pick_index=int(pick_index) if pick_index is not None else None,
        max_age_days=float(params["max_age_days"]) if params.get("max_age_days") not in (None, "") else None,
        ignore_freshness=b("ignore_freshness"),
        force=b("force"),
        downloader=params.get("downloader"),
        save_path=params.get("save_path"),
        yes=yes,
        auto=b("auto"),
        dry_run=dry,
        wait=int(params.get("wait") or 0),
        subscribe=b("subscribe"),
        hdhive_timeout=float(params.get("hdhive_timeout") or 90),
    )


def run_watch_pipeline(args: Any) -> tuple[int, dict[str, Any]]:
    """Execute watch; return (exit_code, report). Does not print."""
    clear_stages()
    media = identify_media(
        args.title,
        args.media_type,
        args.year,
        args.tmdbid,
        episode=args.episode,
    )
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    report: dict[str, Any] = {
        "media": {
            "title": media.get("title"),
            "year": media.get("year"),
            "type": media.get("type"),
            "tmdb_id": tmdbid,
            "original_title": media.get("original_title") or media.get("original_name"),
            "category": media.get("category"),
        },
        "request": {
            "title": args.title,
            "season": args.season,
            "episode": args.episode,
            "prefer": args.prefer,
            "dry_run": args.dry_run,
        },
    }

    hdhive_result = None
    hdhive_timeout = float(getattr(args, "hdhive_timeout", 90) or 90)
    if args.prefer in {"hdhive", "auto", "nextfind", "nf"} and not args.skip_hdhive:
        hdhive_result = try_hdhive(media, args.season, args.episode, timeout=hdhive_timeout)
        report["hdhive"] = hdhive_result
        if args.hdhive_only:
            report["stages"] = stages_snapshot()
            _code = 0 if hdhive_result and hdhive_result.get("success") else 1
            return _code, report

        # Full netdisk success (NextFind transfer or legacy unlock+transfer) can short-circuit PT.
        if (
            hdhive_result
            and hdhive_result.get("success")
            and not args.force_pt
            and not args.dry_run
        ):
            report["success"] = True
            report["source"] = hdhive_result.get("source") or hdhive_result.get("path") or "nextfind_openapi"
            report["note"] = f"Netdisk grab succeeded ({report['source']}); skipped PT."
            try:
                report["status"] = status_snapshot(media, args.episode)
            except Exception:  # noqa: BLE001
                report["status"] = None
            report["stages"] = stages_snapshot()
            return 0, report

        if hdhive_result and not hdhive_result.get("success"):
            report["note"] = (
                "Netdisk grab failed ("
                + str((hdhive_result.get("result") or {}).get("error") or hdhive_result.get("error") or "unknown")
                + "); continuing PT."
            )

    _stage("clients_check")
    clients = ensure_clients()
    report["clients"] = clients
    _stage("clients_ok", count=len(clients) if isinstance(clients, list) else 0)

    items = search_pt_resources(media, args.season, args.episode, args.sites)
    report["search_count"] = len(items)
    if not items:
        report["success"] = False
        report["error"] = "no_resources"
        report["hint"] = "Resource may be too new / not indexed. Prefer run updates/subscribe; do not invent mp_api flags."
        if args.subscribe:
            report["subscribe"] = maybe_subscribe(media, args.season, args.dry_run)
        report["stages"] = stages_snapshot()
        return 4, report

    # Lock + quality + rank via pure pipeline (testable)
    lock_site = (getattr(args, "site_name", None) or "").strip() or None
    lock_title = (getattr(args, "title_contains", None) or "").strip() or None
    lock_url = (getattr(args, "page_url", None) or "").strip() or None
    site_priority = [s.strip() for s in (args.site_priority or "").split(",") if s.strip()] or None
    max_age_days = getattr(args, "max_age_days", None)
    _stage("pick_start", search_count=len(items))
    picked = pick_for_watch(
        items,
        media=media,
        media_type=args.media_type or media.get("type"),
        season=args.season,
        episode=args.episode,
        media_year=media.get("year") or args.year,
        resolution=args.resolution,
        hdr_mode=getattr(args, "hdr_mode", None),
        require_chinese=bool(getattr(args, "require_chinese", False)),
        no_require_chinese=bool(getattr(args, "no_require_chinese", False)),
        allow_disc=bool(getattr(args, "allow_disc", False)),
        no_fx_sub=bool(getattr(args, "no_fx_sub", False)),
        site_name=lock_site,
        title_contains=lock_title,
        page_url=lock_url,
        site_priority=site_priority,
        pick_index=args.pick_index,
        prefer_fresh=not bool(getattr(args, "ignore_freshness", False)),
        max_age_days=max_age_days,
        top_n=args.top,
    )
    if picked.get("lock"):
        report["lock"] = picked["lock"]
        _stage(
            "lock_filter",
            site=lock_site,
            title_contains=lock_title,
            matched=(picked["lock"] or {}).get("matched"),
            before=(picked["lock"] or {}).get("before"),
        )
    if picked.get("error") == "lock_no_match":
        report["success"] = False
        report["error"] = "lock_no_match"
        report["hint"] = (
            "No torrent matched site_name/title_contains/page_url lock. "
            "Re-run search without lock, or fix site alias (e.g. 彩虹岛/chdbits)."
        )
        report["candidates"] = picked.get("candidates") or []
        report["stages"] = stages_snapshot()
        return 4, report
    if picked.get("error") == "pick_index_out_of_range":
        report["success"] = False
        report["error"] = "pick_index_out_of_range"
        report["candidates"] = picked.get("candidates") or []
        report["stages"] = stages_snapshot()
        return 5, report

    report["quality_policy"] = picked.get("quality_policy")
    report["candidates"] = picked.get("candidates") or []
    report["pick_meta"] = {
        **(picked.get("pick_meta") or {}),
        "needs_confirm": bool(picked.get("needs_confirm")),
        "confirm_reasons": picked.get("confirm_reasons") or [],
        "max_age_days": max_age_days,
    }
    selected = picked.get("selected_raw") or None
    if selected is None and picked.get("selected"):
        # fall back: re-resolve from candidates not available; keep summary only path
        selected = None
    _stage("pick_done", selected=bool(picked.get("selected")), candidates=len(report["candidates"]))
    if not picked.get("selected") and not selected:
        report["success"] = False
        report["error"] = picked.get("error") or "pick_failed"
        report["hint"] = "Search returned items but none matched season/episode/year filter. Resource may not be out yet."
        report["stages"] = stages_snapshot()
        return 5, report

    # Prefer raw item for download; summary for report
    if selected is None:
        # download needs raw torrent dict — apply_lock_and_pick stores selected_raw
        selected = picked.get("selected_raw")
    report["selected"] = picked.get("selected") or summarize_candidate(selected)
    force_confirm_risk = bool(picked.get("needs_confirm")) and not bool(getattr(args, "force", False))
    # When agent passes --yes/--auto but pick is risky (year/pubdate/low seeders), block unless --force.
    if force_confirm_risk and (args.yes or args.auto) and not args.dry_run:
        report["success"] = False
        report["error"] = "safety_confirmation_required"
        report["hint"] = (
            "Selected torrent looks risky (year/pubdate/seeders). "
            "Show candidates to user, then re-run with --force --yes, or --pick-index N --force --yes. "
            "If already downloaded wrong one: media_ctl run cancel."
        )
        report["stages"] = stages_snapshot()
        return 6, report
    if not args.yes and not args.dry_run and not args.auto:
        report["success"] = False
        report["error"] = "confirmation_required"
        report["hint"] = "Re-run with --yes to download selected candidate, or --pick-index N --yes."
        report["stages"] = stages_snapshot()
        return 6, report

    downloader = args.downloader
    if not downloader and clients:
        # Prefer QB if present
        names = [c.get("name") for c in clients if isinstance(c, dict)]
        downloader = "QB" if "QB" in names else names[0]

    dl = download_selected(
        media,
        selected,
        downloader=downloader,
        save_path=args.save_path,
        dry_run=args.dry_run,
    )
    report["download"] = dl

    if args.dry_run:
        report["success"] = True
        report["stages"] = stages_snapshot()
        return 0, report

    if not dl.get("success"):
        report["success"] = False
        report["stages"] = stages_snapshot()
        return 7, report

    if args.wait > 0:
        deadline = time.time() + args.wait
        last = None
        while time.time() < deadline:
            last = status_snapshot(media, args.episode)
            if last.get("state") in {"transferred", "downloading"}:
                if last.get("state") == "transferred":
                    break
            time.sleep(min(5, max(1, args.wait // 6 or 1)))
        report["status"] = last or status_snapshot(media, args.episode)
    else:
        report["status"] = status_snapshot(media, args.episode)

    if args.subscribe:
        report["subscribe"] = maybe_subscribe(media, args.season, dry_run=False) if not args.dry_run else maybe_subscribe(media, args.season, True)

    report["success"] = True
    report["stages"] = stages_snapshot()
    return 0, report


