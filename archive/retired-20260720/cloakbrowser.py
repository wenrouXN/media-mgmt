"""CloakBrowser manager ops."""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op


def _cloak_url(cfg: dict[str, Any]) -> str:
    conf = section(cfg, "hdhive")
    return str(conf.get("cloak_url") or "").rstrip("/")


def op_list_profiles(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    base = _cloak_url(cfg)
    if not base:
        return {"success": False, "error": "missing_config", "need": "hdhive.cloak_url"}
    try:
        with urllib.request.urlopen(base + "/api/profiles", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"success": True, "profiles": data}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "cloak_list_failed", "detail": str(e)}


def op_profile_status(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = section(cfg, "hdhive")
    base = _cloak_url(cfg)
    pid = params.get("profile_id") or conf.get("profile_id")
    if not base or not pid:
        return {"success": False, "error": "missing_param", "need": "profile_id"}
    try:
        with urllib.request.urlopen(f"{base}/api/profiles/{pid}/status", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"success": True, "profile_id": pid, "status": data}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "cloak_status_failed", "detail": str(e)}


register_op("cloakbrowser", "list_profiles", op_list_profiles)
register_op("cloakbrowser", "profile_status", op_profile_status)
