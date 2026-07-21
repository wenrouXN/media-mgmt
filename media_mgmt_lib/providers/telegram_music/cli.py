"""CLI entrypoint for telegram_music provider."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from media_mgmt_lib.config import DEFAULT_CONFIG_PATH, load_json_config, merge_config_sources, section
from media_mgmt_lib.provider_base import ProviderRunRequest
from media_mgmt_lib.provider_registry import get_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Telegram music bot, click inline result, download returned audio/file"
    )
    parser.add_argument("--config", help="Optional JSON config file with defaults")
    parser.add_argument("--api-id", type=int, help="Telegram API ID")
    parser.add_argument("--api-hash", help="Telegram API hash")
    parser.add_argument("--session-string", help="Telegram StringSession")
    parser.add_argument("--session-name", help="Telegram session file/name")
    parser.add_argument("--bot", help="Telegram bot username, e.g. @music_v1bot")
    parser.add_argument("--query", help="Search text to send")
    parser.add_argument("--button-index", type=int, help="1-based inline button index to click")
    parser.add_argument("--button-text", default="", help="Exact button text to click instead of index")
    parser.add_argument("--download-dir", help="Directory to save returned media")
    parser.add_argument("--search-timeout", type=float, default=None, help="Seconds to wait for search-result message")
    parser.add_argument("--download-timeout", type=float, default=None, help="Seconds to wait for returned file")
    parser.add_argument("--poll-interval", type=float, default=None, help="Polling interval in seconds")
    return parser


def load_default_config() -> dict[str, Any]:
    telegram = section(load_json_config(DEFAULT_CONFIG_PATH), "telegram_music")
    return {
        "api_id": telegram.get("api_id"),
        "api_hash": telegram.get("api_hash"),
        "session_string": telegram.get("session_string"),
        "session_name": telegram.get("session_name"),
        "bot": telegram.get("bot"),
        "download_dir": telegram.get("download_dir"),
        "button_index": telegram.get("button_index"),
        "button_text": telegram.get("button_text", ""),
        "search_timeout": telegram.get("search_timeout"),
        "download_timeout": telegram.get("download_timeout"),
        "poll_interval": telegram.get("poll_interval"),
    }


def normalize_override_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept either a telegram_music section or direct provider keys."""
    if not raw:
        return {}
    telegram = section(raw, "telegram_music")
    if not telegram:
        return dict(raw)
    return {
        "api_id": telegram.get("api_id"),
        "api_hash": telegram.get("api_hash"),
        "session_string": telegram.get("session_string"),
        "session_name": telegram.get("session_name"),
        "bot": telegram.get("bot"),
        "download_dir": telegram.get("download_dir"),
        "button_index": telegram.get("button_index"),
        "button_text": telegram.get("button_text"),
        "search_timeout": telegram.get("search_timeout"),
        "download_timeout": telegram.get("download_timeout"),
        "poll_interval": telegram.get("poll_interval"),
    }


def resolve_runtime_settings(args: argparse.Namespace) -> dict[str, Any]:
    # Defaults may inject workspace credentials. Explicit --config file values must win
    # over credentials for fields present in that file (load without inject).
    defaults = load_default_config()
    override: dict[str, Any] = {}
    if args.config:
        override = normalize_override_config(load_json_config(args.config, inject=False))
    cfg = merge_config_sources(override, defaults)
    merged = merge_config_sources(
        {
            "bot": args.bot,
            "api_id": args.api_id,
            "api_hash": args.api_hash,
            "session_string": args.session_string,
            "session_name": args.session_name,
            "query": args.query,
            "button_index": args.button_index,
            "button_text": args.button_text,
            "download_dir": args.download_dir,
            "search_timeout": args.search_timeout,
            "download_timeout": args.download_timeout,
            "poll_interval": args.poll_interval,
        },
        cfg,
    )
    if not merged.get("button_index"):
        merged["button_index"] = 1
    if not merged.get("button_text"):
        merged["button_text"] = ""
    if not merged.get("search_timeout"):
        merged["search_timeout"] = 20.0
    if not merged.get("download_timeout"):
        merged["download_timeout"] = 30.0
    if not merged.get("poll_interval"):
        merged["poll_interval"] = 1.0

    has_creds = bool(merged.get("api_id") and merged.get("api_hash") and (merged.get("session_string") or merged.get("session_name")))
    missing = [name for name in ("bot", "query", "download_dir") if not merged.get(name)]
    if not has_creds:
        missing.append("api_id/api_hash/session_string or session_name")
    if missing:
        raise SystemExit(f"Missing required settings: {', '.join(missing)}")
    return merged


def build_request(settings: dict[str, Any]) -> ProviderRunRequest:
    return ProviderRunRequest(
        bot=settings["bot"],
        query=settings["query"],
        download_dir=Path(settings["download_dir"]),
        api_id=int(settings["api_id"]) if settings.get("api_id") else None,
        api_hash=str(settings.get("api_hash") or ""),
        session_string=str(settings.get("session_string") or ""),
        session_name=str(settings.get("session_name") or ""),
        button_index=int(settings["button_index"]),
        button_text=str(settings.get("button_text") or ""),
        search_timeout=float(settings["search_timeout"]),
        download_timeout=float(settings["download_timeout"]),
        poll_interval=float(settings["poll_interval"]),
    )


async def run_with_args(args: argparse.Namespace):
    settings = resolve_runtime_settings(args)
    provider = get_provider("telegram_music")
    return await provider.run(build_request(settings))


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        asyncio.run(run_with_args(args))
        return 0
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
