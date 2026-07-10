"""Ops facade: health and service-specific operations."""
from __future__ import annotations

from typing import Any, Callable

from media_mgmt_lib.catalog import Service, load_catalog, load_service
from media_mgmt_lib.config import load_json_config
from media_mgmt_lib.ops import health as health_mod

OpFn = Callable[[Service, dict[str, Any], dict[str, Any]], dict[str, Any]]

_OPS: dict[str, dict[str, OpFn]] = {}


def register_op(service_id: str, op_name: str, fn: OpFn) -> None:
    _OPS.setdefault(service_id, {})[op_name] = fn


def get_op(service_id: str, op_name: str) -> OpFn | None:
    if service_id in _OPS and op_name in _OPS[service_id]:
        return _OPS[service_id][op_name]
    if op_name == "health":
        return lambda svc, cfg, params: health_mod.check_service(svc, cfg)
    return None


def call_op(service_id: str, op_name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    svc = load_service(service_id)
    cfg = load_json_config()
    params = params or {}
    declared = list(svc.ops or [])
    if op_name != "health" and op_name not in declared:
        return {
            "success": False,
            "service": service_id,
            "op": op_name,
            "error": "op_not_declared",
            "declared_ops": declared,
        }
    fn = get_op(service_id, op_name)
    if fn is None:
        return {
            "success": False,
            "service": service_id,
            "op": op_name,
            "error": "op_not_implemented",
            "hint": "Use scripts/mp_api.py, watch.py, or provider CLIs until this op is wired.",
        }
    try:
        result = fn(svc, cfg, params)
        if isinstance(result, dict):
            result.setdefault("service", service_id)
            result.setdefault("op", op_name)
            return result
        return {"success": True, "service": service_id, "op": op_name, "data": result}
    except Exception as e:  # noqa: BLE001
        return {
            "success": False,
            "service": service_id,
            "op": op_name,
            "error": "op_exception",
            "detail": str(e),
        }


def list_ops(service_id: str | None = None) -> dict[str, Any]:
    if service_id:
        svc = load_service(service_id)
        implemented = sorted(set(list((_OPS.get(service_id) or {}).keys()) + (["health"] if "health" in (svc.ops or []) or True else [])))
        return {
            "service": service_id,
            "ops": svc.ops,
            "implemented": implemented,
        }
    return {s.id: {"ops": s.ops, "implemented": sorted(set(list((_OPS.get(s.id) or {}).keys()) + ["health"]))} for s in load_catalog()}
