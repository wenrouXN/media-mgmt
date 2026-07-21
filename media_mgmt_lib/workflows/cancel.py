"""Cancel / recall a wrong download from the active queue."""
from __future__ import annotations

import argparse
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
        return fail(
            "missing_param",
            need="hash|title|tmdbid",
            hint="先 run status / call moviepilot active 找到任务",
        )

    import scripts.mp_api as mp_api

    def b(key: str) -> bool:
        return str(params.get(key) or "").lower() in {"1", "true", "yes", "on"}

    args = argparse.Namespace(
        hash=params.get("hash"),
        title=params.get("title"),
        tmdbid=int(params["tmdbid"]) if params.get("tmdbid") not in (None, "") else None,
        episode=int(params["episode"]) if params.get("episode") not in (None, "") else None,
        downloader=params.get("downloader"),
        delete_files=b("delete_files"),
        dry_run=b("dry_run"),
    )

    captured: list[Any] = []

    def capture(data: Any) -> None:
        captured.append(data)

    # mp_api.cmd_cancel uses print_json — temporarily patch
    orig = mp_api.print_json
    mp_api.print_json = capture  # type: ignore[assignment]
    try:
        mp_api.cmd_cancel(args)
    finally:
        mp_api.print_json = orig

    parsed = captured[-1] if captured else None
    success = isinstance(parsed, dict) and parsed.get("success") is True
    payload = {
        "workflow": "cancel",
        "success": success,
        "result": parsed,
        "hint": (
            "已取消下载任务。若文件已开始落盘且需要删文件，加 delete_files=true。"
            if success
            else "未匹配到活动任务或取消失败：先 status/active 核对 hash/title。"
        ),
    }
    return ok(payload) if success else {**payload, "error": "cancel_failed"}
