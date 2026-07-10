"""MoviePilot ops wrappers (delegate to scripts/mp_api request helpers when possible)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op

ROOT = Path(__file__).resolve().parents[2]


def _run_mp_api(args: list[str]) -> dict[str, Any]:
    py = ROOT / ".venv" / "bin" / "python"
    exe = str(py) if py.exists() else sys.executable
    cmd = [exe, str(ROOT / "scripts" / "mp_api.py"), *args]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if not out and err:
        return {"success": False, "error": "mp_api_failed", "detail": err[:500], "returncode": proc.returncode}
    try:
        data = json.loads(out) if out else None
    except json.JSONDecodeError:
        return {"success": proc.returncode == 0, "raw": out[:1000], "returncode": proc.returncode}
    if isinstance(data, dict):
        data.setdefault("success", proc.returncode == 0)
        return data
    return {"success": proc.returncode == 0, "data": data, "returncode": proc.returncode}


def op_clients(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run_mp_api(["clients"])


def op_active(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _run_mp_api(["active"])


def op_identify(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    if not title:
        return {"success": False, "error": "missing_param", "need": "title"}
    args = ["identify", str(title)]
    if params.get("media_type"):
        args += ["--media-type", str(params["media_type"])]
    if params.get("year"):
        args += ["--year", str(params["year"])]
    return _run_mp_api(args)


def op_status(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    args = ["status"]
    if params.get("tmdbid"):
        args += ["--tmdbid", str(params["tmdbid"])]
    if params.get("title"):
        args += ["--title", str(params["title"])]
    if params.get("episode") is not None:
        args += ["--episode", str(params["episode"])]
    return _run_mp_api(args)


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    # prefer title search for flexibility
    title = params.get("title") or params.get("q")
    if not title:
        return {"success": False, "error": "missing_param", "need": "title"}
    return _run_mp_api(["title", str(title)])


register_op("moviepilot", "clients", op_clients)
register_op("moviepilot", "active", op_active)
register_op("moviepilot", "identify", op_identify)
register_op("moviepilot", "status", op_status)
register_op("moviepilot", "search", op_search)
register_op("qbittorrent", "clients", op_clients)
register_op("transmission", "clients", op_clients)
