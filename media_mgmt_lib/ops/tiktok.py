"""TikTok ops via 7899 API."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops import api7899


def _base(cfg: dict[str, Any]) -> str:
    # reuse douyin base by default
    return api7899.base_url(cfg, "douyin")


def _timeout(params: dict[str, Any], cfg: dict[str, Any]) -> float:
    conf = section(cfg, "douyin")
    return float(params.get("timeout") or conf.get("timeout") or 60)


def op_capabilities(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.capabilities(api7899.TIKTOK_NAMED, "tiktok")


def op_api(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return api7899.call_raw_api(_base(cfg), params, timeout=_timeout(params, cfg))


def _named(op: str):
    def _fn(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        p = dict(params)
        if not p.get("url") and p.get("link"):
            p["url"] = p["link"]
        result = api7899.call_named(api7899.TIKTOK_NAMED, op, p, base=_base(cfg), timeout=_timeout(params, cfg))
        result.setdefault("service", "tiktok")
        result.setdefault("op", op)
        return result

    return _fn


def op_intent(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    intent = str(params.get("intent") or params.get("q") or "解析").lower()
    if any(k in intent for k in ("下载", "download", "保存")):
        return _named("download")(svc, cfg, params)
    if any(k in intent for k in ("评论", "comment")):
        return _named("comments")(svc, cfg, params)
    return _named("hybrid_video")(svc, cfg, params)


register_op("tiktok", "capabilities", op_capabilities)
register_op("tiktok", "api", op_api)
register_op("tiktok", "intent", op_intent)
register_op("tiktok", "parse", _named("hybrid_video"))
for _name in api7899.TIKTOK_NAMED:
    register_op("tiktok", _name, _named(_name))
