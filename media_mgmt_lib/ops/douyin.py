"""Douyin ops: named endpoints + raw api + legacy parse/download providers."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops import api7899
from media_mgmt_lib.providers.douyin.provider import DouyinProvider, DouyinRequest


def _base(cfg: dict[str, Any]) -> str:
    return api7899.base_url(cfg, "douyin")


def _timeout(params: dict[str, Any], cfg: dict[str, Any]) -> float:
    conf = section(cfg, "douyin")
    return float(params.get("timeout") or conf.get("timeout") or 60)


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.capabilities(api7899.DOUYIN_NAMED, "douyin")


def op_api(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    p = api7899.normalize_params_for_service("douyin", params)
    return api7899.call_raw_api(_base(cfg), p, timeout=_timeout(params, cfg))


def _named(op: str):
    def _fn(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        p = api7899.normalize_params_for_service("douyin", params)
        # convenience: if video op and only url, try get_aweme_id first? leave to hybrid_video
        if op in {"hybrid_video", "download"} and not p.get("url") and p.get("link"):
            p["url"] = p["link"]
        result = api7899.call_named(api7899.DOUYIN_NAMED, op, p, base=_base(cfg), timeout=_timeout(params, cfg))
        result.setdefault("service", "douyin")
        result.setdefault("op", op)
        return result

    return _fn


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """High-level parse via provider (hybrid video_data + normalized fields)."""
    conf = section(cfg, "douyin")
    url = params.get("url") or params.get("link")
    if not url:
        return {"success": False, "error": "missing_param", "need": ["url"]}
    req = DouyinRequest(
        url=str(url),
        action="parse",
        api_base_url=_base(cfg),
        timeout=_timeout(params, cfg),
    )
    result = asyncio.run(DouyinProvider().run(req))
    from dataclasses import asdict

    out = asdict(result)
    out["success"] = bool(result.success)
    out["service"] = "douyin"
    out["op"] = "parse"
    return out


def op_download_provider(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Provider download (saves under download_dir with nice filename). Prefer this for '帮我下下来'."""
    conf = section(cfg, "douyin")
    url = params.get("url") or params.get("link")
    if not url:
        return {"success": False, "error": "missing_param", "need": ["url"]}
    download_dir = params.get("download_dir") or conf.get("download_dir")
    req = DouyinRequest(
        url=str(url),
        action="download",
        download_dir=Path(str(download_dir)) if download_dir else None,
        api_base_url=_base(cfg),
        timeout=_timeout(params, cfg),
    )
    result = asyncio.run(DouyinProvider().run(req))
    from dataclasses import asdict

    out = asdict(result)
    if out.get("file_path"):
        out["file_path"] = str(out["file_path"])
    out["success"] = bool(result.success)
    out["service"] = "douyin"
    out["op"] = "download"
    return out


def op_intent(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Given a link + natural intent keywords, suggest/execute the right op."""
    url = params.get("url") or params.get("link") or ""
    intent = str(params.get("intent") or params.get("q") or params.get("want") or "解析").lower()
    # route table
    if any(k in intent for k in ("下载", "保存", "download", "下下来")):
        return op_download_provider(svc, cfg, params)
    if any(k in intent for k in ("评论", "comment")):
        # need aweme_id — try extract
        if url and not params.get("aweme_id"):
            ext = api7899.call_named(
                api7899.DOUYIN_NAMED,
                "get_aweme_id",
                {"url": url},
                base=_base(cfg),
                timeout=_timeout(params, cfg),
            )
            # best-effort dig
            data = ext.get("data") if isinstance(ext, dict) else None
            aweme = None
            if isinstance(data, dict):
                aweme = data.get("aweme_id") or data.get("data") or data.get("id")
                if isinstance(aweme, dict):
                    aweme = aweme.get("aweme_id")
            if aweme:
                params = {**params, "aweme_id": aweme}
        return _named("comments")(svc, cfg, params)
    if any(k in intent for k in ("用户", "主页", "博主", "profile")):
        return _named("get_sec_user_id")(svc, cfg, {**params, "url": url}) if url else _named("user_profile")(svc, cfg, params)
    # default parse
    return op_parse(svc, cfg, params)


# register
register_op("douyin", "capabilities", op_capabilities)
register_op("douyin", "api", op_api)
register_op("douyin", "intent", op_intent)
register_op("douyin", "parse", op_parse)
register_op("douyin", "download", op_download_provider)
for _name in api7899.DOUYIN_NAMED:
    if _name in {"download"}:
        # keep provider download as primary 'download'; expose stream as download_stream
        register_op("douyin", "download_stream", _named("download"))
        continue
    if _name == "hybrid_video":
        register_op("douyin", "hybrid_video", _named("hybrid_video"))
        continue
    register_op("douyin", _name, _named(_name))
