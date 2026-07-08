"""CLI entrypoint for douyin provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

from media_mgmt_lib.config import DEFAULT_CONFIG_PATH, load_json_config, merge_config_sources, section
from media_mgmt_lib.providers.douyin.provider import DouyinProvider, DouyinRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Douyin video parser and downloader")
    parser.add_argument("action", nargs="?", default="parse", choices=["parse", "download"], help="Action to perform")
    parser.add_argument("url", help="Douyin video URL")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output result as JSON")
    parser.add_argument("--download-dir", help="Directory to save downloaded video")
    parser.add_argument("--api-base-url", help="API base URL (default: http://localhost:7899)")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument("--config", help="Optional JSON config file")
    return parser


def load_defaults(config_path: str | None = None) -> dict[str, Any]:
    cfg = section(load_json_config(config_path or DEFAULT_CONFIG_PATH), "douyin")
    return {
        "api_base_url": cfg.get("api_base_url", "http://localhost:7899"),
        "download_dir": cfg.get("download_dir"),
        "timeout": cfg.get("timeout", 60),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        defaults = load_defaults(args.config)
        merged = merge_config_sources(
            {
                "api_base_url": args.api_base_url,
                "download_dir": args.download_dir,
                "timeout": args.timeout,
            },
            defaults,
        )

        provider = DouyinProvider()
        request = DouyinRequest(
            url=args.url,
            action=args.action,
            download_dir=Path(merged["download_dir"]) if merged.get("download_dir") else None,
            api_base_url=str(merged.get("api_base_url", "http://localhost:7899")),
            timeout=float(merged.get("timeout", 60)),
        )

        result = asyncio.run(provider.run(request))

        if args.json_output:
            from dataclasses import asdict
            out = asdict(result)
            if out.get("file_path"):
                out["file_path"] = str(out["file_path"])
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if not result.success:
                print(f"Error: {result.error}", file=sys.stderr)
                return 1
            if result.action == "parse":
                print(f"标题: {result.title}")
                print(f"作者: {result.author}")
                print(f"描述: {result.description[:200]}")
                if result.stats:
                    print(f"统计: {result.stats}")
                if result.tags:
                    print(f"标签: {', '.join(result.tags)}")
                if result.duration:
                    m, s = divmod(result.duration // 1000, 60)
                    print(f"时长: {m}:{s:02d}")
                if result.music_title:
                    print(f"音乐: {result.music_title}")
            else:
                print(f"下载完成: {result.file_path}")
                print(f"文件大小: {result.file_size / 1024 / 1024:.1f} MB")

        return 0
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
