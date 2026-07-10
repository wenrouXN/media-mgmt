"""Bilibili ops."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.providers.bilibili.provider import BilibiliProvider, BilibiliRequest


def _run(svc: Service, cfg: dict[str, Any], params: dict[str, Any], action: str) -> dict[str, Any]:
    conf = section(cfg, "bilibili")
    url = params.get("url") or params.get("link")
    if not url:
        return {"success": False, "error": "missing_param", "need": "url"}
    download_dir = params.get("download_dir") or conf.get("download_dir")
    req = BilibiliRequest(
        url=str(url),
        action=action,
        download_dir=Path(str(download_dir)) if download_dir else None,
        api_base_url=str(params.get("api_base_url") or conf.get("api_base_url") or "http://localhost:7899"),
        quality=int(params.get("quality") or conf.get("quality") or 80),
        timeout=float(params.get("timeout") or conf.get("timeout") or 120),
    )
    try:
        result = asyncio.run(BilibiliProvider().run(req))
        from dataclasses import asdict

        out = asdict(result)
        if out.get("file_path"):
            out["file_path"] = str(out["file_path"])
        out["success"] = bool(result.success)
        return out
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": f"bilibili_{action}_failed", "detail": str(e)}


def op_parse(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(svc, cfg, params, "parse")


def op_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run(svc, cfg, params, "download")


register_op("bilibili", "parse", op_parse)
register_op("bilibili", "download", op_download)
