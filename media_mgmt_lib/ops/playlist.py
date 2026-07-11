"""Public playlist ops: parse metadata only."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.playlist_parse import (
    SUPPORTED_PLATFORMS,
    PlaylistParseError,
    parse_playlist,
)


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "service": "playlist",
        "platforms": list(SUPPORTED_PLATFORMS),
        "unsupported": ["spotify"],
        "ops": ["parse", "capabilities"],
        "params": {
            "url": "public playlist URL (netease/qq/kuwo/kugou)",
            "limit": "optional max tracks returned",
            "proxy": "optional http(s)/socks proxy",
            "timeout": "optional seconds (default 30)",
        },
        "note": "Parse-only. Download individual tracks via run listen with queries[].",
    }


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("link") or params.get("playlist_url")
    if not url:
        return {
            "success": False,
            "error": "missing_param",
            "need": "url",
            "supported_platforms": list(SUPPORTED_PLATFORMS),
        }
    conf = section(cfg, "playlist") if cfg else {}
    proxy = params.get("proxy") or conf.get("proxy") or None
    if proxy in ("", "null", "None"):
        proxy = None
    timeout = float(params.get("timeout") or conf.get("timeout") or 30)
    limit = params.get("limit")
    if limit is None:
        limit = conf.get("default_limit")
    try:
        parsed = parse_playlist(
            str(url),
            proxy_url=str(proxy) if proxy else None,
            limit=int(limit) if limit not in (None, "") else None,
            timeout=timeout,
        )
        result = parsed.to_result()
        result["service"] = "playlist"
        result["op"] = "parse"
        return result
    except PlaylistParseError as e:
        return {
            "success": False,
            "error": getattr(e, "code", None) or "parse_failed",
            "detail": str(e),
            "supported_platforms": list(SUPPORTED_PLATFORMS),
            "service": "playlist",
            "op": "parse",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error": "parse_failed",
            "detail": str(e),
            "supported_platforms": list(SUPPORTED_PLATFORMS),
            "service": "playlist",
            "op": "parse",
        }


register_op("playlist", "capabilities", op_capabilities)
register_op("playlist", "parse", op_parse)
