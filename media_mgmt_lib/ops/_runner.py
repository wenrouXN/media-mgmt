"""Shared helpers for ops implementations."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def python_exe() -> str:
    """Always use host Python (no per-skill venv)."""
    return sys.executable


def run_json(args: list[str], *, timeout: float = 300, cwd: Path | None = None) -> dict[str, Any]:
    cmd = [python_exe(), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if not out:
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "error": "empty_stdout" if proc.returncode != 0 else None,
            "detail": err[:800] if err else None,
            "raw": "",
        }
    # try last JSON object/array in stdout (some scripts print progress)
    parsed: Any = None
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        # find last {...} or [...]
        for i in range(len(out) - 1, -1, -1):
            if out[i] in "{[":
                try:
                    parsed = json.loads(out[i:])
                    break
                except json.JSONDecodeError:
                    continue
    if isinstance(parsed, dict):
        parsed.setdefault("success", proc.returncode == 0)
        parsed.setdefault("returncode", proc.returncode)
        if err and "detail" not in parsed:
            parsed["stderr"] = err[:400]
        return parsed
    if parsed is not None:
        return {"success": proc.returncode == 0, "data": parsed, "returncode": proc.returncode}
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "raw": out[:2000],
        "detail": err[:500] if err else None,
    }


def run_mp_api(args: list[str], timeout: float = 180) -> dict[str, Any]:
    return run_json([str(ROOT / "scripts" / "mp_api.py"), *args], timeout=timeout)
