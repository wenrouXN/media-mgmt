"""CLI entrypoint for hongguo provider."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from media_mgmt_lib.config import DEFAULT_CONFIG_PATH, load_json_config, merge_config_sources, section
from media_mgmt_lib.providers.hongguo.provider import HongguoProvider, HongguoRequest
from media_mgmt_lib.providers.hongguo import parser as hg


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Hongguo short-drama parser/downloader "
            "(hongguoduanju.com / novelquickapp.com share links; "
            "default download_dir: /vol02/1000-0-8501d321/torrents/TV/短剧)"
        ),
    )
    p.add_argument(
        "action", nargs="?", default="parse",
        choices=["parse", "info", "list_episodes", "download"],
        help="Action to perform (default: parse)",
    )
    p.add_argument("url", help="Hongguo detail or player URL")
    p.add_argument("--json", dest="json_output", action="store_true", help="JSON output")
    p.add_argument("--episode", "-e", type=int, help="Episode number (1-indexed); omit for all accessible")
    p.add_argument("--download-dir", help="Directory to save downloaded video(s)")
    p.add_argument("--proxy", help="HTTP(S) proxy")
    p.add_argument("--timeout", type=float, help="Request timeout in seconds")
    p.add_argument("--config", help="Optional JSON config file")
    return p


def load_defaults(config_path: str | None = None) -> dict[str, Any]:
    cfg = section(load_json_config(config_path or DEFAULT_CONFIG_PATH), "hongguo")
    return {
        "download_dir": cfg.get("download_dir"),
        "proxy": cfg.get("proxy"),
        "timeout": cfg.get("timeout", hg.DEFAULT_TIMEOUT),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        defaults = load_defaults(args.config)
        merged = merge_config_sources(
            {
                "download_dir": args.download_dir,
                "proxy": args.proxy,
                "timeout": args.timeout,
            },
            defaults,
        )

        provider = HongguoProvider()
        req = HongguoRequest(
            url=args.url,
            action=args.action,
            download_dir=Path(merged["download_dir"]) if merged.get("download_dir") else None,
            episode=args.episode,
            proxy=merged.get("proxy"),
            timeout=float(merged.get("timeout", 30)),
        )

        result = provider.run(req)

        if args.json_output:
            out = asdict(result)
            if out.get("file_path"):
                out["file_path"] = str(out["file_path"])
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if not result.success:
                print(f"Error: {result.error}", file=sys.stderr)
                return 1
            if result.action == "parse" or result.action == "info":
                print(f"Series: {result.title} ({result.series_id})")
                print(f"Episodes: {result.episode_count} (accessible: {result.accessible_episode_count})")
                if result.tags:
                    print(f"Tags: {', '.join(result.tags)}")
                if result.intro:
                    print(f"Intro: {result.intro[:120]}")
            elif result.action == "list_episodes":
                print(f"Series: {result.title} ({result.series_id})")
                for ep in result.episodes:
                    tag = "✅" if ep.get("accessible") else "🔒"
                    print(f"  E{ep['index']:02d}  vid={ep['vid']}  {tag}")
            elif result.action == "download":
                if result.file_path:
                    sz = f" ({result.file_size} bytes)" if result.file_size else ""
                    print(f"Downloaded: {result.file_path}{sz}")
                else:
                    print("No file downloaded", file=sys.stderr)
                    return 1
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Fatal: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
