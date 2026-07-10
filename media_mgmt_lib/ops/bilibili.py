"""Bilibili ops: named endpoints + raw api + provider parse/download."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops import api7899
from media_mgmt_lib.providers.bilibili.provider import BilibiliProvider, BilibiliRequest


def _base(cfg: dict[str, Any]) -> str:
    return api7899.base_url(cfg, "bilibili")


def _timeout(params: dict[str, Any], cfg: dict[str, Any]) -> float:
    conf = section(cfg, "bilibili")
    return float(params.get("timeout") or conf.get("timeout") or 120)


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.capabilities(api7899.BILIBILI_NAMED, "bilibili")


def op_api(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    p = api7899.normalize_params_for_service("bilibili", params)
    return api7899.call_raw_api(_base(cfg), p, timeout=_timeout(params, cfg))


def _named(op: str):
    def _fn(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        p = api7899.normalize_params_for_service("bilibili", params)
        if op in {"hybrid_video", "download"} and not p.get("url") and p.get("link"):
            p["url"] = p["link"]
        result = api7899.call_named(api7899.BILIBILI_NAMED, op, p, base=_base(cfg), timeout=_timeout(params, cfg))
        result.setdefault("service", "bilibili")
        result.setdefault("op", op)
        return result

    return _fn


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "bilibili")
    url = params.get("url") or params.get("link")
    if not url and params.get("bv_id"):
        url = f"https://www.bilibili.com/video/{params['bv_id']}"
    if not url:
        return {"success": False, "error": "missing_param", "need": ["url|bv_id"]}
    req = BilibiliRequest(
        url=str(url),
        action="parse",
        api_base_url=_base(cfg),
        quality=int(params.get("quality") or conf.get("quality") or 80),
        timeout=_timeout(params, cfg),
    )
    result = asyncio.run(BilibiliProvider().run(req))
    from dataclasses import asdict

    out = asdict(result)
    out["success"] = bool(result.success)
    out["service"] = "bilibili"
    out["op"] = "parse"
    return out


def op_download_provider(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "bilibili")
    url = params.get("url") or params.get("link")
    if not url and params.get("bv_id"):
        url = f"https://www.bilibili.com/video/{params['bv_id']}"
    if not url:
        return {"success": False, "error": "missing_param", "need": ["url|bv_id"]}
    download_dir = params.get("download_dir") or conf.get("download_dir")
    req = BilibiliRequest(
        url=str(url),
        action="download",
        download_dir=Path(str(download_dir)) if download_dir else None,
        api_base_url=_base(cfg),
        quality=int(params.get("quality") or conf.get("quality") or 80),
        timeout=_timeout(params, cfg),
    )
    result = asyncio.run(BilibiliProvider().run(req))
    from dataclasses import asdict

    out = asdict(result)
    if out.get("file_path"):
        out["file_path"] = str(out["file_path"])
    out["success"] = bool(result.success)
    out["service"] = "bilibili"
    out["op"] = "download"
    return out


def op_intent(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("link") or ""
    intent = str(params.get("intent") or params.get("q") or params.get("want") or "解析").lower()
    if any(k in intent for k in ("下载", "保存", "download", "下下来")):
        return op_download_provider(svc, cfg, params)
    if any(k in intent for k in ("弹幕", "danmaku")):
        # need cid from parse first
        parsed = op_parse(svc, cfg, params)
        if parsed.get("success") and parsed.get("cid"):
            return _named("danmaku")(svc, cfg, {**params, "cid": parsed["cid"]})
        return parsed
    if any(k in intent for k in ("评论", "comment")):
        p = api7899.normalize_params_for_service("bilibili", params)
        return _named("comments")(svc, cfg, p)
    if any(k in intent for k in ("分p", "分P", "多p", "parts")):
        p = api7899.normalize_params_for_service("bilibili", params)
        return _named("parts")(svc, cfg, p)
    if any(k in intent for k in ("播放", "清晰度", "playurl")):
        parsed = op_parse(svc, cfg, params)
        if parsed.get("success") and parsed.get("bvid") and parsed.get("cid"):
            return _named("playurl")(svc, cfg, {**params, "bv_id": parsed["bvid"], "cid": parsed["cid"]})
        return parsed
    if any(k in intent for k in ("直播", "live")):
        p = api7899.normalize_params_for_service("bilibili", params)
        if p.get("room_id"):
            return _named("live_room")(svc, cfg, p)
    return op_parse(svc, cfg, params)


register_op("bilibili", "capabilities", op_capabilities)
register_op("bilibili", "api", op_api)
register_op("bilibili", "intent", op_intent)
register_op("bilibili", "parse", op_parse)
register_op("bilibili", "download", op_download_provider)
for _name in api7899.BILIBILI_NAMED:
    if _name == "download":
        register_op("bilibili", "download_stream", _named("download"))
        continue
    register_op("bilibili", _name, _named(_name))
