"""Cancel / recall a wrong download from the active queue."""

from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Cancel active download task(s).

    Params:
      hash | title | tmdbid | episode
      delete_files: also remove files when supported
      dry_run: preview only
      downloader: optional fallback name
    """
    if not any(params.get(k) not in (None, "") for k in ("hash", "title", "tmdbid")):
        return fail("missing_param", need="hash|title|tmdbid", hint="先 run status / call moviepilot active 找到任务")

    # Prefer mp_api cancel path via direct script for full filter support.
    from pathlib import Path
    import json
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, str(root / "scripts" / "mp_api.py"), "cancel"]
    for key, flag in (
        ("hash", "--hash"),
        ("title", "--title"),
        ("tmdbid", "--tmdbid"),
        ("episode", "--episode"),
        ("downloader", "--downloader"),
    ):
        if params.get(key) not in (None, ""):
            cmd += [flag, str(params[key])]
    if str(params.get("delete_files") or "").lower() in {"1", "true", "yes"}:
        cmd.append("--delete-files")
    if str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=60)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    parsed: Any = None
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
    success = proc.returncode == 0 and isinstance(parsed, dict) and parsed.get("success") is True
    payload = {
        "workflow": "cancel",
        "success": success,
        "result": parsed,
        "raw": None if parsed else out[:2000],
        "stderr": err[:500] if err else None,
        "cmd": cmd[2:],
        "hint": (
            "已取消下载任务。若文件已开始落盘且需要删文件，加 delete_files=true。"
            if success
            else "未匹配到活动任务或取消失败：先 status/active 核对 hash/title。"
        ),
    }
    return ok(payload) if success else {**payload, "error": "cancel_failed"}
