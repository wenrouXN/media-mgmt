#!/usr/bin/env python3
"""CLI: parse public playlist URL → JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from media_mgmt_lib.playlist_parse import (  # noqa: E402
    SUPPORTED_PLATFORMS,
    PlaylistParseError,
    parse_playlist,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Parse public music playlist metadata")
    p.add_argument("--url", required=True, help="Public playlist URL")
    p.add_argument("--proxy", default=None, help="Optional proxy URL")
    p.add_argument("--limit", type=int, default=None, help="Max tracks to return")
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()
    try:
        parsed = parse_playlist(
            args.url,
            proxy_url=args.proxy,
            limit=args.limit,
            timeout=args.timeout,
        )
        print(json.dumps(parsed.to_result(), ensure_ascii=False, indent=2))
        return 0
    except PlaylistParseError as e:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": e.code,
                    "detail": str(e),
                    "supported_platforms": list(SUPPORTED_PLATFORMS),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    except Exception as e:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "parse_failed",
                    "detail": str(e),
                    "supported_platforms": list(SUPPORTED_PLATFORMS),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
