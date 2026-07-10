"""Telegram music ops: search candidates + policy download."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.provider_base import ProviderRunRequest
from media_mgmt_lib.provider_registry import get_provider


def _request(cfg: dict[str, Any], params: dict[str, Any]) -> ProviderRunRequest:
    conf = section(cfg, "telegram_music")
    query = params.get("q") or params.get("query") or params.get("title")
    if not query:
        raise ValueError("missing_param:q")
    download_dir = params.get("download_dir") or conf.get("download_dir") or "/tmp"
    return ProviderRunRequest(
        bot=str(params.get("bot") or conf.get("bot") or "@music_v1bot"),
        query=str(query),
        download_dir=Path(str(download_dir)),
        api_id=int(conf["api_id"]) if conf.get("api_id") else None,
        api_hash=str(conf.get("api_hash") or ""),
        session_string=str(conf.get("session_string") or ""),
        session_name=str(conf.get("session_name") or ""),
        button_index=int(params.get("button_index") or conf.get("button_index") or 1),
        button_text=str(params.get("button_text") or conf.get("button_text") or ""),
        search_timeout=float(params.get("search_timeout") or conf.get("search_timeout") or 20),
        download_timeout=float(params.get("download_timeout") or conf.get("download_timeout") or 30),
        poll_interval=float(params.get("poll_interval") or conf.get("poll_interval") or 1),
    )


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    try:
        req = _request(cfg, params)
    except ValueError as e:
        return {"success": False, "error": "missing_param", "need": "q", "detail": str(e)}
    try:
        provider = get_provider("telegram_music")
        return asyncio.run(provider.search_candidates(req))
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "telegram_music_search_failed", "detail": str(e)}


def op_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "telegram_music")
    if not (params.get("download_dir") or conf.get("download_dir")):
        return {"success": False, "error": "missing_config", "need": "telegram_music.download_dir"}
    try:
        req = _request(cfg, params)
    except ValueError as e:
        return {"success": False, "error": "missing_param", "need": "q", "detail": str(e)}
    # require explicit choice when ambiguous path is desired
    if not params.get("button_index") and not params.get("button_text"):
        return {
            "success": False,
            "error": "missing_param",
            "need": "button_index|button_text",
            "hint": "Use search first, then download with chosen index/text",
        }
    try:
        provider = get_provider("telegram_music")
        return asyncio.run(provider.download_choice(req))
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "telegram_music_download_failed", "detail": str(e)}


def op_search_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Policy: high confidence auto-download; otherwise return candidates for confirm."""
    conf = section(cfg, "telegram_music")
    force = str(params.get("force") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    # explicit choice always downloads
    if params.get("button_index") or params.get("button_text"):
        if not (params.get("download_dir") or conf.get("download_dir")):
            return {"success": False, "error": "missing_config", "need": "telegram_music.download_dir"}
        try:
            req = _request(cfg, params)
            provider = get_provider("telegram_music")
            result = asyncio.run(provider.download_choice(req))
            result["policy"] = "explicit_choice"
            return result
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": "telegram_music_failed", "detail": str(e)}

    # 1) search + score
    searched = op_search(svc, cfg, params)
    if not searched.get("success"):
        return searched
    decision = searched.get("decision") or {}
    suggested = decision.get("suggested") or {}

    if decision.get("auto") or force:
        if not (params.get("download_dir") or conf.get("download_dir")):
            return {
                "success": False,
                "error": "missing_config",
                "need": "telegram_music.download_dir",
                "search": searched,
            }
        idx = int(suggested.get("index") or 1)
        try:
            req = _request(cfg, {**params, "button_index": idx})
            provider = get_provider("telegram_music")
            dl = asyncio.run(provider.download_choice(req))
            return {
                "success": bool(dl.get("success")),
                "query": params.get("q") or params.get("query") or params.get("title"),
                "path": dl.get("path"),
                "auto_downloaded": True,
                "forced": force and not decision.get("auto"),
                "decision": decision,
                "candidates": searched.get("candidates"),
                "chosen": dl.get("chosen"),
                "caption": dl.get("caption"),
                "policy": "auto_high_confidence" if decision.get("auto") else "force",
            }
        except Exception as e:  # noqa: BLE001
            return {
                "success": False,
                "error": "telegram_music_download_failed",
                "detail": str(e),
                "decision": decision,
                "candidates": searched.get("candidates"),
            }

    # needs confirm — do not download
    return {
        "success": True,
        "downloaded": False,
        "needs_confirm": True,
        "query": searched.get("query"),
        "candidates": searched.get("candidates"),
        "decision": decision,
        "suggested": suggested,
        "policy": "confirm_required",
        "summary": (
            f"多候选需确认（confidence={decision.get('confidence')}, reason={decision.get('reason')}）；"
            f"建议 #{suggested.get('index')}: {suggested.get('text')}"
        ),
        "next": {
            "download": "call telegram_music download --param q=... --param button_index=N",
            "or": "run listen --param q=... --param button_index=N",
            "force_top": "run listen --param q=... --param force=true",
        },
    }


register_op("telegram_music", "search", op_search)
register_op("telegram_music", "download", op_download)
register_op("telegram_music", "search_download", op_search_download)
