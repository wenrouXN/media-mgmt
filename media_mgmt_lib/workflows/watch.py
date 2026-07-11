from __future__ import annotations
import subprocess
import sys
import json
from pathlib import Path
from typing import Any
from media_mgmt_lib.workflows._util import fail, need_any

ROOT = Path(__file__).resolve().parents[2]

def run(params: dict[str, Any]) -> dict[str, Any]:
    miss = need_any(params, ["title", "tmdbid"])
    # title preferred
    title = params.get("title")
    if not title and not params.get("tmdbid"):
        return fail("missing_param", need="title")
    py = ROOT / ".venv" / "bin" / "python"
    exe = str(py) if py.exists() else sys.executable
    cmd = [exe, str(ROOT / "scripts" / "watch.py")]
    if title:
        cmd.append(str(title))
    for key, flag in (
        ("tmdbid", "--tmdbid"),
        ("media_type", "--media-type"),
        ("year", "--year"),
        ("season", "--season"),
        ("episode", "--episode"),
        ("prefer", "--prefer"),
        ("downloader", "--downloader"),
        ("save_path", "--save-path"),
        ("resolution", "--resolution"),
        ("pick_index", "--pick-index"),
        ("wait", "--wait"),
        ("hdr_mode", "--hdr-mode"),
        ("site_priority", "--site-priority"),
    ):
        if params.get(key) not in (None, ""):
            cmd += [flag, str(params[key])]
    if str(params.get("require_chinese") or params.get("chinese") or "").lower() in {
        "1",
        "true",
        "yes",
        "中文",
    }:
        cmd.append("--require-chinese")
    if str(params.get("yes", "true")).lower() in {"1", "true", "yes"} and not params.get("dry_run"):
        cmd.append("--yes")
    if params.get("dry_run") in (True, "true", "1", "yes"):
        cmd.append("--dry-run")
    if params.get("skip_hdhive") in (True, "true", "1", "yes"):
        cmd.append("--skip-hdhive")
    if params.get("subscribe") in (True, "true", "1", "yes"):
        cmd.append("--subscribe")
    if params.get("hdhive_only") in (True, "true", "1", "yes"):
        cmd.append("--hdhive-only")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=float(params.get("timeout") or 900))
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            # last json object
            for i in range(len(out) - 1, -1, -1):
                if out[i] == "{":
                    try:
                        parsed = json.loads(out[i:])
                        break
                    except json.JSONDecodeError:
                        continue
    success = proc.returncode == 0 and (not isinstance(parsed, dict) or parsed.get("success") is not False)
    return {
        "success": success,
        "workflow": "watch",
        "returncode": proc.returncode,
        "result": parsed,
        "raw": None if parsed else out[:3000],
        "stderr": err[:800] if err else None,
        "cmd": cmd[2:],
    }
