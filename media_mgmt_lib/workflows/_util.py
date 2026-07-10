from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op


def need_any(params: dict[str, Any], keys: list[str]) -> str | None:
    for k in keys:
        if params.get(k) not in (None, ""):
            return None
    return "|".join(keys)


def ok(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("success", True)
    return payload


def fail(error: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error": error, **extra}


def mp(op: str, **params: Any) -> dict[str, Any]:
    return call_op("moviepilot", op, params)
