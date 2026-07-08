"""CLI entrypoint for bilibili provider."""

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
from media_mgmt_lib.providers.bilibili.provider import BilibiliProvider, BilibiliRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bilibili video parser and downloader")
    parser.add_argument("action", nargs="?", default="parse", choices=["parse", "download"], help="Action to perform")
    parser.add_argument("url", help="Bilibili video URL (bilibili.com or b23.tv)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output result as JSON")
    parser.add_argument("--download-dir", help="Directory to save downloaded video")
    parser.add_argument("--api-base-url", help="API base URL (default: http://localhost:7899)")
    parser.add_argument("--quality", type=int, help="Video quality: 120=4K, 116=1080P60, 80=1080P, 64=720P, 32=480P, 16=360P")
    parser.add_argument("--timeout", type=float, help="Request timeout in seconds")
    parser.add_argument("--config", help="Optional JSON config file")
    return parser


def load_defaults(config_path: str | None = None) -> dict[str, Any]:
    cfg = section(load_json_config(config_path or DEFAULT_CONFIG_PATH), "bilibili")
    return {
        "api_base_url": cfg.get("api_base_url", "http://localhost:7899"),
        "download_dir": cfg.get("download_dir"),
        "quality": cfg.get("quality", 80),
        "timeout": cfg.get("timeout", 120),
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        defaults = load_defaults(args.config)
        merged = merge_config_sources(
            {
                "api_base_url": args.api_base_url,
                "download_dir": args.download_dir,
                "quality": args.quality,
                "timeout": args.timeout,
            },
            defaults,
        )

        provider = BilibiliProvider()
        request = BilibiliRequest(
            url=args.url,
            action=args.action,
            download_dir=Path(merged["download_dir"]) if merged.get("download_dir") else None,
            api_base_url=str(merged.get("api_base_url", "http://localhost:7899")),
            quality=int(merged.get("quality", 80)),
            timeout=float(merged.get("timeout", 120)),
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
                print(f"UP主: {result.author}")
                print(f"描述: {result.description[:200]}")
                if result.bvid:
                    print(f"BV号: {result.bvid}")
                if result.stats:
                    print(f"统计: 播放 {result.stats.get('view', '?')} | 弹幕 {result.stats.get('danmaku', '?')} | "
                          f"点赞 {result.stats.get('like', '?')} | 投币 {result.stats.get('coin', '?')} | "
                          f"收藏 {result.stats.get('favorite', '?')} | 分享 {result.stats.get('share', '?')}")
                if result.duration:
                    m, s = divmod(result.duration, 60)
                    print(f"时长: {m}:{s:02d}")
                if result.pages and len(result.pages) > 1:
                    print(f"分P: {len(result.pages)}P")
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
