"""PanSou search ops."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "pansou")
    base = str(conf.get("url") or "").rstrip("/")
    kw = params.get("q") or params.get("kw") or params.get("keyword")
    if not base:
        return {"success": False, "error": "missing_config", "need": "pansou.url"}
    if not kw:
        return {"success": False, "error": "missing_param", "need": "q"}
    cloud_types = params.get("cloud_types") or ["115"]
    if isinstance(cloud_types, str):
        cloud_types = [x.strip() for x in cloud_types.split(",") if x.strip()]
    body = {"kw": str(kw), "cloud_types": cloud_types}
    req = urllib.request.Request(
        f"{base}/api/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(params.get("timeout") or 30)) as resp:
            raw = resp.read().decode("utf-8", "replace")
        data = json.loads(raw) if raw else {}
        return {"success": True, "query": kw, "data": data}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "pansou_search_failed", "detail": str(e)}


register_op("pansou", "search", op_search)
