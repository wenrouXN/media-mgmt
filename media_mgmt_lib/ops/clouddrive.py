"""CloudDrive ops: health / add_offline / list_offline."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.config import section
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.providers.clouddrive.client import client_from_config


def _conf(cfg: dict[str, Any]) -> dict[str, Any]:
    return section(cfg, "clouddrive")


def op_health(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = _conf(cfg)
    if not conf:
        return {
            "success": False,
            "error": "missing_config",
            "need": "clouddrive section in config.json",
        }
    if not (conf.get("token") or (conf.get("username") and conf.get("password"))):
        return {
            "success": False,
            "error": "missing_config",
            "need": "clouddrive.token or username+password",
        }
    try:
        with client_from_config(conf) as client:
            result = client.health()
            result.setdefault("service", "clouddrive")
            result.setdefault("op", "health")
            return result
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error": "clouddrive_health_failed",
            "detail": str(e),
        }


def op_add_offline(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = _conf(cfg)
    if not conf:
        return {"success": False, "error": "missing_config", "need": "clouddrive"}
    urls = (
        params.get("urls")
        or params.get("magnet")
        or params.get("url")
        or params.get("link")
        or ""
    )
    to_folder = (
        params.get("to_folder")
        or params.get("save_path")
        or params.get("path")
        or params.get("folder")
        or ""
    )
    check = params.get("check_folder_after_secs")
    try:
        with client_from_config(conf) as client:
            result = client.add_offline(
                str(urls),
                str(to_folder) if to_folder else None,
                check_folder_after_secs=int(check) if check not in (None, "") else None,
            )
            result.setdefault("service", "clouddrive")
            result.setdefault("op", "add_offline")
            return result
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error": "clouddrive_add_offline_failed",
            "detail": str(e),
        }


def op_list_offline(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    conf = _conf(cfg)
    if not conf:
        return {"success": False, "error": "missing_config", "need": "clouddrive"}
    path = params.get("path") or params.get("to_folder") or params.get("save_path") or ""
    try:
        with client_from_config(conf) as client:
            result = client.list_offline(str(path) if path else None)
            result.setdefault("service", "clouddrive")
            result.setdefault("op", "list_offline")
            return result
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "error": "clouddrive_list_offline_failed",
            "detail": str(e),
        }


# register
register_op("clouddrive", "health", op_health)
register_op("clouddrive", "add_offline", op_add_offline)
register_op("clouddrive", "list_offline", op_list_offline)
