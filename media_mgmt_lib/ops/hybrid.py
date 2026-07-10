"""Hybrid link ops: one entry for douyin/tiktok/bilibili URLs."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops import api7899
from media_mgmt_lib.config import section


def _base(cfg: dict[str, Any]) -> str:
    return api7899.base_url(cfg, "douyin")


def _timeout(params: dict[str, Any], cfg: dict[str, Any]) -> float:
    conf = section(cfg, "douyin")
    return float(params.get("timeout") or conf.get("timeout") or 60)


def detect_platform(url: str) -> str:
    u = (url or "").lower()
    if "bilibili.com" in u or "b23.tv" in u:
        return "bilibili"
    if "tiktok.com" in u or "vt.tiktok.com" in u:
        return "tiktok"
    if "douyin.com" in u or "iesdouyin.com" in u or "v.douyin.com" in u:
        return "douyin"
    return "unknown"


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.capabilities(api7899.HYBRID_NAMED, "hybrid")


def op_api(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.call_raw_api(_base(cfg), params, timeout=_timeout(params, cfg))


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    p = dict(params)
    if not p.get("url") and p.get("link"):
        p["url"] = p["link"]
    if not p.get("url"):
        return {"success": False, "error": "missing_param", "need": ["url"]}
    result = api7899.call_named(api7899.HYBRID_NAMED, "video_data", p, base=_base(cfg), timeout=_timeout(params, cfg))
    result["platform"] = detect_platform(str(p.get("url")))
    result.setdefault("service", "hybrid")
    result.setdefault("op", "parse")
    return result


def op_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    p = dict(params)
    if not p.get("url") and p.get("link"):
        p["url"] = p["link"]
    # prefer save_path; else use platform download_dir + generic name via stream
    if not p.get("save_path"):
        conf = section(cfg, "douyin")
        ddir = conf.get("download_dir") or "/tmp"
        p["save_path"] = str(Path_safe(ddir) / "hybrid_download.bin")
    result = api7899.call_named(api7899.HYBRID_NAMED, "download", p, base=_base(cfg), timeout=_timeout(params, cfg))
    result["platform"] = detect_platform(str(p.get("url") or ""))
    return result


def Path_safe(p: str):
    from pathlib import Path
    return Path(p)


def op_intent(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = str(params.get("url") or params.get("link") or "")
    intent = str(params.get("intent") or params.get("q") or params.get("want") or "解析")
    platform = detect_platform(url)
    # route to specialized service intent when known
    if platform == "douyin":
        from media_mgmt_lib.ops import douyin as douyin_ops

        return douyin_ops.op_intent(svc, cfg, params)
    if platform == "bilibili":
        from media_mgmt_lib.ops import bilibili as bili_ops

        return bili_ops.op_intent(svc, cfg, params)
    if platform == "tiktok":
        from media_mgmt_lib.ops import tiktok as tt_ops

        return tt_ops.op_intent(svc, cfg, params)
    if any(k in intent for k in ("下载", "download", "保存")):
        return op_download(svc, cfg, params)
    return op_parse(svc, cfg, params)


register_op("hybrid", "capabilities", op_capabilities)
register_op("hybrid", "api", op_api)
register_op("hybrid", "parse", op_parse)
register_op("hybrid", "download", op_download)
register_op("hybrid", "intent", op_intent)
register_op("hybrid", "video_data", op_parse)
register_op("hybrid", "update_cookie", lambda svc, cfg, params: api7899.call_named(
    api7899.HYBRID_NAMED, "update_cookie", params, base=_base(cfg), timeout=_timeout(params, cfg)
))
