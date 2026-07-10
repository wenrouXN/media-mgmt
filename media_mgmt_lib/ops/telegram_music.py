"""Telegram music ops."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.provider_base import ProviderRunRequest
from media_mgmt_lib.provider_registry import get_provider


def op_search_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "telegram_music")
    query = params.get("q") or params.get("query") or params.get("title")
    if not query:
        return {"success": False, "error": "missing_param", "need": "q"}
    download_dir = params.get("download_dir") or conf.get("download_dir")
    if not download_dir:
        return {"success": False, "error": "missing_config", "need": "telegram_music.download_dir"}
    req = ProviderRunRequest(
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
    try:
        provider = get_provider("telegram_music")
        path = asyncio.run(provider.run(req))
        return {"success": True, "path": str(path), "query": query}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "telegram_music_failed", "detail": str(e)}


register_op("telegram_music", "search_download", op_search_download)
