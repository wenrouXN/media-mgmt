"""Hongguo ops: parse/info/list_episodes/download + intent router."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.providers.hongguo.provider import HongguoProvider, HongguoRequest


def _timeout(params: dict[str, Any], cfg: dict[str, Any]) -> float:
    conf = section(cfg, "hongguo")
    return float(params.get("timeout") or conf.get("timeout") or 30)


def _proxy(cfg: dict[str, Any]) -> str | None:
    conf = section(cfg, "hongguo")
    return conf.get("proxy") or None


def _download_dir(params: dict[str, Any], cfg: dict[str, Any]) -> Path | None:
    conf = section(cfg, "hongguo")
    d = params.get("download_dir") or conf.get("download_dir")
    return Path(d) if d else None


def _run(params: dict[str, Any], cfg: dict[str, Any], action: str) -> dict[str, Any]:
    url = params.get("url") or params.get("link")
    if not url:
        return {"success": False, "error": "missing_param", "need": ["url"]}
    req = HongguoRequest(
        url=str(url),
        action=action,
        download_dir=_download_dir(params, cfg),
        episode=params.get("episode"),
        proxy=_proxy(cfg),
        timeout=_timeout(params, cfg),
    )
    result = HongguoProvider().run(req)
    from dataclasses import asdict

    out = asdict(result)
    if out.get("file_path"):
        out["file_path"] = str(out["file_path"])
    out["success"] = result.success
    out["service"] = "hongguo"
    out["op"] = action
    return out


def op_health(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Simple HTTP probe to hongguoduanju.com."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            "https://hongguoduanju.com",
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
        ok = 200 <= code < 400
        return {
            "success": ok,
            "service": "hongguo",
            "op": "health",
            "status_code": code,
            "status": "ok" if ok else "degraded",
        }
    except urllib.error.HTTPError as e:
        return {"success": False, "service": "hongguo", "op": "health", "status_code": e.code, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "service": "hongguo", "op": "health", "error": str(e)}


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "service": "hongguo",
        "ops": [
            {"op": "parse", "desc": "Parse series metadata from URL"},
            {"op": "info", "desc": "Alias for parse"},
            {"op": "list_episodes", "desc": "List episodes with accessibility"},
            {"op": "download", "desc": "Download episode(s) as MP4"},
            {"op": "intent", "desc": "Intent-based routing"},
            {"op": "capabilities", "desc": "This"},
            {"op": "health", "desc": "Probe hongguoduanju.com"},
        ],
    }


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(params, cfg, "parse")


def op_info(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(params, cfg, "info")


def op_list_episodes(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(params, cfg, "list_episodes")


def op_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(params, cfg, "download")


def op_intent(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Intent-based routing: parse / info / download / list_episodes."""
    intent = str(params.get("intent") or params.get("q") or params.get("want") or "解析").lower()
    if any(k in intent for k in ("下载", "download", "保存", "下下来")):
        return op_download(svc, cfg, params)
    if any(k in intent for k in ("列表", "集数", "episodes", "有哪些集")):
        return op_list_episodes(svc, cfg, params)
    if any(k in intent for k in ("信息", "info", "详情", "介绍")):
        return op_info(svc, cfg, params)
    return op_parse(svc, cfg, params)


# Register all ops
register_op("hongguo", "health", op_health)
register_op("hongguo", "capabilities", op_capabilities)
register_op("hongguo", "parse", op_parse)
register_op("hongguo", "info", op_info)
register_op("hongguo", "list_episodes", op_list_episodes)
register_op("hongguo", "download", op_download)
register_op("hongguo", "intent", op_intent)
