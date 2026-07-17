"""Workflow: magnet/url → CloudDrive AddOfflineFiles."""
from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.config import load_json_config, section
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.providers.clouddrive.client import resolve_save_path
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    magnet = (
        params.get("magnet")
        or params.get("urls")
        or params.get("url")
        or params.get("link")
        or ""
    )
    magnet = str(magnet).strip()
    if not magnet:
        return fail("missing_param", need="magnet|urls|url")

    save_path_raw = (
        params.get("save_path")
        or params.get("to_folder")
        or params.get("path")
        or params.get("folder")
        or ""
    )
    conf = section(load_json_config(), "clouddrive")
    save_path = resolve_save_path(str(save_path_raw) if save_path_raw else None, conf)
    title = params.get("title") or params.get("name") or ""

    op_params: dict[str, Any] = {"magnet": magnet, "save_path": save_path}
    if params.get("check_folder_after_secs") not in (None, ""):
        op_params["check_folder_after_secs"] = params.get("check_folder_after_secs")

    result = call_op("clouddrive", "add_offline", op_params)
    success = bool(result.get("success"))
    err = result.get("error") or "failed"
    folder = result.get("to_folder") or save_path or "(default)"
    label = title or _short_magnet(magnet)
    return ok(
        {
            "workflow": "offline",
            "success": success,
            "title": title or None,
            "magnet": _short_magnet(magnet),
            "save_path": folder,
            "result": result,
            "error": None if success else result.get("error"),
            "summary": (
                f"offline '{label}' → {folder}: ok"
                if success
                else f"offline '{label}': {err}"
            ),
        }
    )


def _short_magnet(url: str) -> str:
    text = str(url or "")
    if text.startswith("magnet:?") and "btih:" in text.lower():
        try:
            h = text.split("btih:", 1)[1].split("&", 1)[0][:16]
            return f"magnet:…{h}"
        except Exception:  # noqa: BLE001
            return "magnet:…"
    return text[:48] + ("…" if len(text) > 48 else "")
