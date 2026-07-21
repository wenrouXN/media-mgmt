#!/usr/bin/env python3
"""One-shot watch CLI — thin wiring over media_mgmt_lib.watch_*."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from media_mgmt_lib.watch_stages import STAGES as _STAGES  # noqa: E402
from media_mgmt_lib.watch_identify import (  # noqa: E402
    identify_media,
    _media_shell_usable,
    _fetch_tmdb_detail,
    _title_match_score,
    _score_tmdb_detail,
    _title_variants,
    _episode_keywords,
)
from media_mgmt_lib.watch_search import search_pt_resources  # noqa: E402
from media_mgmt_lib.watch_actions import (  # noqa: E402
    try_hdhive,
    ensure_clients,
    download_selected,
    status_snapshot,
    maybe_subscribe,
)
from media_mgmt_lib.watch_run import run_watch_pipeline  # noqa: E402
import scripts.mp_api as mp_api  # noqa: E402


def print_json(value: Any) -> None:
    if isinstance(value, dict) and _STAGES and "stages" not in value:
        value = {**value, "stages": list(_STAGES)}
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_watch(args: argparse.Namespace) -> int:
    code, report = run_watch_pipeline(args)
    print_json(report)
    return code


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
    parser.add_argument(
        "--prefer",
        choices=["auto", "pt", "hdhive", "nextfind", "nf"],
        default="auto",
        help="Resource preference (hdhive/nextfind/nf = netdisk OpenAPI first)",
    )
    parser.add_argument("--skip-hdhive", action="store_true")
    parser.add_argument("--hdhive-only", action="store_true")
    parser.add_argument("--force-pt", action="store_true")
    parser.add_argument("--sites", help="comma-separated site ids")
    parser.add_argument("--resolution", default=None)
    parser.add_argument("--require-chinese", action="store_true")
    parser.add_argument("--no-require-chinese", action="store_true")
    parser.add_argument("--allow-disc", action="store_true")
    parser.add_argument("--no-fx-sub", action="store_true")
    parser.add_argument("--hdr-mode", choices=["any", "sdr", "hdr"], default=None)
    parser.add_argument("--site-priority", help="comma-separated preferred site names")
    parser.add_argument("--site-name", help="Hard-lock torrent site")
    parser.add_argument("--title-contains")
    parser.add_argument("--page-url")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--pick-index", type=int, help="0-based index into ranked candidates")
    parser.add_argument("--max-age-days", type=float, default=None)
    parser.add_argument("--ignore-freshness", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--downloader")
    parser.add_argument("--save-path")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait", type=int, default=0)
    parser.add_argument("--subscribe", action="store_true")
    parser.add_argument("--hdhive-timeout", type=float, default=90)
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
