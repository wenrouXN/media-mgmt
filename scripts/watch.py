#!/usr/bin/env python3
"""One-shot watch pipeline for media-mgmt.

Flow: identify → (optional HDHive) → PT search fallback matrix → pick → download → status.

Agent should prefer this over hand-assembled MoviePilot JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from media_mgmt_lib.config import load_json_config, moviepilot_credentials  # noqa: E402
from media_mgmt_lib.torrent_pick import pick_torrent, summarize_candidate  # noqa: E402

import scripts.mp_api as mp_api  # noqa: E402


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _title_variants(title: str, media: dict[str, Any] | None = None, *, limit: int = 6) -> list[str]:
    """Return a small high-signal title set. Avoid exploding on media.names (can be 20+ locales)."""
    variants: list[str] = []

    def add(val: Any) -> None:
        if not val:
            return
        text = str(val).strip()
        if not text or text in variants:
            return
        if len(text) > 80:
            return
        variants.append(text)

    add(title)
    if media:
        for key in ("title", "en_title", "original_title", "original_name", "name"):
            add(media.get(key))
        for name in media.get("names") or []:
            text = str(name).strip()
            if not text or len(text) > 40:
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in text) or any("\uac00" <= ch <= "\ud7a3" for ch in text) or text.isascii():
                add(text)
            if len(variants) >= limit:
                break
    return variants[:limit]


def _episode_keywords(season: int | None, episode: int | None) -> list[str]:
    if episode is None:
        return []
    keys = [f"E{episode:02d}", f"E{episode}", f"EP{episode:02d}", f"第{episode}集", f"第{episode:02d}集"]
    if season is not None:
        keys.extend(
            [
                f"S{season:02d}E{episode:02d}",
                f"S{season}E{episode:02d}",
                f"S{season:02d}E{episode}",
            ]
        )
    return keys


def identify_media(title: str, media_type: str | None, year: str | None, tmdbid: int | None) -> dict[str, Any]:
    if tmdbid:
        mtype = mp_api.normalize_mtype(media_type or "tv") or "电视剧"
        detail = mp_api.request(
            "GET",
            f"/api/v1/media/tmdb:{tmdbid}",
            params={"type_name": mtype, "title": title, "year": year},
        )
        if isinstance(detail, dict) and detail:
            return detail
        # fallback recognize
        rec = mp_api.request("GET", "/api/v1/media/recognize", params={"title": title})
        if isinstance(rec, dict) and isinstance(rec.get("media_info"), dict):
            return rec["media_info"]
        raise SystemExit(json.dumps({"success": False, "error": "identify_failed", "tmdbid": tmdbid}, ensure_ascii=False))

    # Prefer recognize (returns full media_info incl. names/category)
    rec = mp_api.request("GET", "/api/v1/media/recognize", params={"title": title})
    if isinstance(rec, dict) and isinstance(rec.get("media_info"), dict) and rec["media_info"].get("tmdb_id"):
        media = rec["media_info"]
        if year and str(media.get("year") or "") not in {"", str(year)}:
            pass  # keep but continue with search refine
        else:
            return media

    results = mp_api.request("GET", "/api/v1/media/search", params={"title": title, "type": "media", "page": 1, "count": 10})
    selected = mp_api._pick_media_search_result(results, title=title, media_type=media_type, year=year)
    if not selected:
        raise SystemExit(json.dumps({"success": False, "error": "media_not_found", "title": title}, ensure_ascii=False))
    tmdb_id = selected.get("tmdb_id") or selected.get("tmdbid")
    mtype = mp_api.normalize_mtype(media_type or selected.get("type") or "tv") or "电视剧"
    if tmdb_id:
        detail = mp_api.request(
            "GET",
            f"/api/v1/media/tmdb:{tmdb_id}",
            params={"type_name": mtype, "title": selected.get("title") or title, "year": selected.get("year") or year},
        )
        if isinstance(detail, dict) and detail.get("tmdb_id"):
            return detail
    # recognize with selected title
    rec2 = mp_api.request("GET", "/api/v1/media/recognize", params={"title": selected.get("title") or title})
    if isinstance(rec2, dict) and isinstance(rec2.get("media_info"), dict):
        return rec2["media_info"]
    return selected


def search_pt_resources(
    media: dict[str, Any],
    season: int | None,
    episode: int | None,
    sites: str | None,
    *,
    enough: int = 5,
) -> list[dict[str, Any]]:
    """Search PT with early-exit. Avoid N titles x M episode keywords explosion."""
    tmdb_id = media.get("tmdb_id") or media.get("tmdbid")
    mtype = mp_api.normalize_mtype(media.get("type") or "tv")
    title = media.get("title") or media.get("en_title") or media.get("original_title") or ""
    year = media.get("year")
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_items(items: Any, source: str) -> int:
        added = 0
        if not isinstance(items, list):
            if isinstance(items, dict):
                maybe = items.get("data")
                if isinstance(maybe, list):
                    items = maybe
                else:
                    return 0
            else:
                return 0
        for it in items:
            if not isinstance(it, dict):
                continue
            ti = it.get("torrent_info") if isinstance(it.get("torrent_info"), dict) else it
            key = str((ti or {}).get("enclosure") or (ti or {}).get("page_url") or (ti or {}).get("title") or id(it))
            if key in seen:
                continue
            seen.add(key)
            wrapped = it if "torrent_info" in it else {"torrent_info": it, "source_query": source}
            if "source_query" not in wrapped:
                wrapped = {**wrapped, "source_query": source}
            collected.append(wrapped)
            added += 1
        return added

    def episode_hits() -> int:
        if episode is None:
            return len(collected)
        from media_mgmt_lib.torrent_pick import matches_episode

        return sum(1 for it in collected if matches_episode(it, season=season, episode=episode))

    # 1) media id search
    if tmdb_id:
        try:
            res = mp_api.request(
                "GET",
                f"/api/v1/search/media/{urllib.parse.quote(f'tmdb:{tmdb_id}', safe=':')}",
                params={"mtype": mtype, "title": title, "year": year, "season": season, "sites": sites},
            )
            add_items(res, f"media:tmdb:{tmdb_id}")
        except SystemExit:
            pass
        if episode_hits() >= enough:
            return collected

    variants = _title_variants(title, media, limit=4)
    # 2) plain title variants first (broad net)
    for base in variants:
        try:
            res = mp_api.request("GET", "/api/v1/search/title", params={"keyword": base, "page": 0, "sites": sites})
            add_items(res, f"title:{base}")
        except SystemExit:
            continue
        if episode_hits() >= enough:
            return collected

    # 3) precise episode keywords only on top 2 titles, top 3 episode forms
    ep_keys = _episode_keywords(season, episode)[:3]
    for base in variants[:2]:
        for ek in ep_keys:
            kw = f"{base} {ek}"
            try:
                res = mp_api.request("GET", "/api/v1/search/title", params={"keyword": kw, "page": 0, "sites": sites})
                add_items(res, f"title:{kw}")
            except SystemExit:
                continue
            if episode_hits() >= enough:
                return collected

    return collected


def try_hdhive(media: dict[str, Any], season: int | None, episode: int | None) -> dict[str, Any] | None:
    tmdb_id = media.get("tmdb_id") or media.get("tmdbid")
    if not tmdb_id:
        return None
    mtype_raw = str(media.get("type") or "")
    kind = "movie" if mtype_raw in {"电影", "movie"} else "tv"
    script = repo_root / "scripts" / "hdhive.py"
    if not script.exists():
        return {"success": False, "error": "hdhive_script_missing"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "tmdb", kind, str(tmdb_id)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_exec_failed", "detail": str(e)}
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    payload: Any
    try:
        payload = json.loads(out) if out else {"stdout": out, "stderr": err, "code": proc.returncode}
    except json.JSONDecodeError:
        payload = {"stdout": out, "stderr": err, "code": proc.returncode}
    return {
        "success": proc.returncode == 0,
        "code": proc.returncode,
        "result": payload,
        "note": "HDHive path returns candidates/unlock URLs; watch.py currently reports and continues to PT unless --hdhive-only.",
        "season": season,
        "episode": episode,
    }


def ensure_clients() -> list[dict[str, Any]]:
    clients = mp_api.request("GET", "/api/v1/download/clients") or []
    if not isinstance(clients, list) or not clients:
        raise SystemExit(
            json.dumps(
                {
                    "success": False,
                    "error": "no_download_clients",
                    "hint": "Configure qBittorrent/Transmission in MoviePilot. Do not confuse with empty GET /download/ task list.",
                },
                ensure_ascii=False,
            )
        )
    return clients


def download_selected(
    media: dict[str, Any],
    selected: dict[str, Any],
    *,
    downloader: str | None,
    save_path: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    torrent_in = selected.get("torrent_info") if isinstance(selected.get("torrent_info"), dict) else selected
    missing = mp_api.validate_torrent_info(torrent_in)
    missing_media = mp_api.validate_media_info(media, require_full=True)
    if missing or missing_media:
        return {
            "success": False,
            "error": "validation_failed",
            "missing_torrent_fields": missing,
            "missing_media_fields": missing_media,
        }
    resolved = None
    if not save_path:
        paths = mp_api.request("GET", "/api/v1/download/paths") or []
        category_config = mp_api.request("GET", "/api/v1/media/category/config")
        resolved = mp_api.choose_download_path(media, paths, category_config)
        save_path = resolved.get("save_path")
    if not save_path:
        return {"success": False, "error": "save_path_missing"}
    body = {"media_in": media, "torrent_in": torrent_in, "downloader": downloader, "save_path": save_path}
    if dry_run:
        return {
            "dry_run": True,
            "endpoint": "/api/v1/download/",
            "save_path": save_path,
            "resolved_path": resolved,
            "selected_summary": summarize_candidate(selected),
            "downloader": downloader,
        }
    try:
        result = mp_api.request("POST", "/api/v1/download/", body=body)
    except SystemExit as e:
        # mp_api.request already JSON-encoded errors into SystemExit message
        msg = str(e)
        try:
            return json.loads(msg)
        except json.JSONDecodeError:
            return {"success": False, "error": "download_failed", "detail": msg}
    if isinstance(result, dict) and result.get("success") is False:
        return {
            **result,
            "hint": "Check clients, enclosure/cookie completeness, and retry with another candidate.",
            "selected_summary": summarize_candidate(selected),
        }
    return {"success": True, "result": result, "save_path": save_path, "selected_summary": summarize_candidate(selected)}


def status_snapshot(media: dict[str, Any], episode: int | None) -> dict[str, Any]:
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    args = argparse.Namespace(title=media.get("title"), tmdbid=int(tmdbid) if tmdbid else None, episode=episode, count=20)
    # reuse mp_api status logic without printing
    active = mp_api.request("GET", "/api/v1/download/") or []
    if not isinstance(active, list):
        active = []
    transfers = mp_api.request("GET", "/api/v1/history/transfer", params={"page": 1, "count": 20}) or {}
    transfer_list: list[Any] = []
    if isinstance(transfers, dict):
        data = transfers.get("data")
        if isinstance(data, dict):
            transfer_list = data.get("list") or []
        elif isinstance(data, list):
            transfer_list = data
    matched_active = []
    for item in active:
        if not isinstance(item, dict):
            continue
        m = item.get("media") or {}
        if tmdbid and int(m.get("tmdbid") or m.get("tmdb_id") or 0) == int(tmdbid):
            if episode is None or f"E{int(episode):02d}" in str(m.get("episode") or "").upper() or str(episode) in str(m.get("episode") or ""):
                matched_active.append(item)
    matched_transfers = []
    for item in transfer_list:
        if not isinstance(item, dict):
            continue
        if tmdbid and int(item.get("tmdbid") or 0) == int(tmdbid):
            if episode is None or f"E{int(episode):02d}" in str(item.get("episodes") or "").upper() or str(episode) in str(item.get("episodes") or ""):
                matched_transfers.append(item)
    state = "downloading" if matched_active else ("transferred" if matched_transfers else "unknown")
    return {"state": state, "active": matched_active, "transfers": matched_transfers[:5]}


def maybe_subscribe(media: dict[str, Any], season: int | None, dry_run: bool) -> dict[str, Any] | None:
    # Only suggest/create when clearly unfinished
    status = str(media.get("status") or "").lower()
    unfinished = status in {"returning series", "in production", "planned", "continuing"} or not media.get("number_of_episodes")
    if not unfinished:
        return None
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    body = {
        "name": media.get("title"),
        "type": mp_api.normalize_mtype(media.get("type") or "tv"),
        "year": media.get("year"),
        "tmdbid": int(tmdbid) if tmdbid else None,
        "season": season or 1,
    }
    if dry_run:
        return {"dry_run": True, "would_subscribe": body}
    # Default: do not auto-create unless --subscribe
    return {"suggested_subscribe": body}


def cmd_watch(args: argparse.Namespace) -> int:
    media = identify_media(args.title, args.media_type, args.year, args.tmdbid)
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
    if args.prefer in {"hdhive", "auto"} and not args.skip_hdhive:
        hdhive_result = try_hdhive(media, args.season, args.episode)
        report["hdhive"] = hdhive_result
        if args.hdhive_only:
            print_json(report)
            return 0 if hdhive_result and hdhive_result.get("success") else 1

    if args.prefer == "hdhive" and hdhive_result and hdhive_result.get("success") and not args.force_pt:
        # For now HDHive success still needs unlock/transfer workflow; fall through unless only.
        report["note"] = "HDHive candidates found; continuing PT unless --hdhive-only."

    clients = ensure_clients()
    report["clients"] = clients

    items = search_pt_resources(media, args.season, args.episode, args.sites)
    report["search_count"] = len(items)
    if not items:
        report["success"] = False
        report["error"] = "no_resources"
        report["hint"] = "Resource may be too new / not indexed. Consider subscription."
        if args.subscribe:
            report["subscribe"] = maybe_subscribe(media, args.season, args.dry_run)
        print_json(report)
        return 4

    site_priority = [s.strip() for s in (args.site_priority or "").split(",") if s.strip()] or None
    picked = pick_torrent(
        items,
        season=args.season,
        episode=args.episode,
        prefer_resolution=args.resolution or "1080p",
        site_priority=site_priority,
        require_chinese=bool(getattr(args, "require_chinese", False)),
        hdr_mode=str(getattr(args, "hdr_mode", "any") or "any"),
        top_n=args.top,
    )
    report["candidates"] = [summarize_candidate(x) for x in picked.get("candidates") or []]
    selected = picked.get("selected")
    if not selected:
        report["success"] = False
        report["error"] = "pick_failed"
        print_json(report)
        return 5

    if args.pick_index is not None:
        cands = picked.get("candidates") or []
        idx = args.pick_index
        if idx < 0 or idx >= len(cands):
            report["success"] = False
            report["error"] = "pick_index_out_of_range"
            print_json(report)
            return 5
        selected = cands[idx]

    report["selected"] = summarize_candidate(selected)
    if not args.yes and not args.dry_run and not args.auto:
        report["success"] = False
        report["error"] = "confirmation_required"
        report["hint"] = "Re-run with --yes to download selected candidate, or --pick-index N --yes."
        print_json(report)
        return 6

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
        print_json(report)
        return 0

    if not dl.get("success"):
        report["success"] = False
        print_json(report)
        return 7

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
    print_json(report)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    media: dict[str, Any]
    if args.tmdbid:
        media = {"tmdb_id": args.tmdbid, "title": args.title}
    elif args.title:
        media = identify_media(args.title, args.media_type, args.year, None)
    else:
        raise SystemExit("status requires --title or --tmdbid")
    snap = status_snapshot(media, args.episode)
    clients = mp_api.request("GET", "/api/v1/download/clients") or []
    print_json(
        {
            "media": {
                "title": media.get("title") or args.title,
                "tmdb_id": media.get("tmdb_id") or media.get("tmdbid") or args.tmdbid,
            },
            **snap,
            "clients": clients,
            "note": "Empty active list means no running tasks, not missing downloaders.",
        }
    )
    return 0


def build_watch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-shot watch pipeline for media-mgmt")
    parser.add_argument("title", nargs="?", help="Title to watch")
    parser.add_argument("--tmdbid", type=int)
    parser.add_argument("--media-type", dest="media_type", help="movie/tv")
    parser.add_argument("--year")
    parser.add_argument("--season", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--prefer", choices=["auto", "pt", "hdhive"], default="auto", help="Resource preference")
    parser.add_argument("--skip-hdhive", action="store_true")
    parser.add_argument("--hdhive-only", action="store_true")
    parser.add_argument("--force-pt", action="store_true")
    parser.add_argument("--sites", help="comma-separated site ids")
    parser.add_argument("--resolution", default="1080p")
    parser.add_argument("--require-chinese", action="store_true", help="Prefer/require Chinese audio/subs signals in title")
    parser.add_argument("--hdr-mode", choices=["any","sdr","hdr"], default="any")
    parser.add_argument("--site-priority", help="comma-separated preferred site names")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--pick-index", type=int, help="Choose candidate index from ranked list")
    parser.add_argument("--downloader", help="QB/TR/...")
    parser.add_argument("--save-path")
    parser.add_argument("--yes", action="store_true", help="Download without interactive confirmation")
    parser.add_argument("--auto", action="store_true", help="Alias of --yes for agent automation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait", type=int, default=0, help="Seconds to poll status after download")
    parser.add_argument("--subscribe", action="store_true", help="Suggest/create subscription when unfinished")
    return parser


def build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check download/transfer status")
    parser.add_argument("--title")
    parser.add_argument("--tmdbid", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--media-type", dest="media_type")
    parser.add_argument("--year")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "status":
        args = build_status_parser().parse_args(argv[1:])
        return cmd_status(args)
    parser = build_watch_parser()
    args = parser.parse_args(argv)
    if not args.title and not args.tmdbid:
        parser.error("title or --tmdbid is required")
    if not args.title:
        args.title = f"tmdb:{args.tmdbid}"
    return cmd_watch(args)


if __name__ == "__main__":
    raise SystemExit(main())
