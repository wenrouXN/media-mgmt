"""Watch workflow: call pure pipeline (no subprocess)."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, need_any
from media_mgmt_lib.watch_run import params_to_args, run_watch_pipeline


def run(params: dict[str, Any]) -> dict[str, Any]:
    miss = need_any(params, ["title", "tmdbid"])
    title = params.get("title")
    if not title and not params.get("tmdbid"):
        return fail("missing_param", need="title")

    try:
        args = params_to_args(params)
    except ValueError as e:
        return fail("invalid_param", detail=str(e))

    if not args.title and not args.tmdbid:
        return fail("missing_param", need="title|tmdbid")

    try:
        code, report = run_watch_pipeline(args)
    except SystemExit as e:
        # identify_media may raise SystemExit with JSON
        msg = str(e)
        try:
            import json

            payload = json.loads(msg)
            if isinstance(payload, dict):
                return {
                    "success": False,
                    "workflow": "watch",
                    "returncode": 1,
                    "result": payload,
                    "error": payload.get("error") or "watch_failed",
                }
        except Exception:  # noqa: BLE001
            pass
        return fail("watch_aborted", detail=msg[:500])
    except Exception as e:  # noqa: BLE001
        return fail("watch_exception", detail=str(e)[:500])

    success = code == 0 and (not isinstance(report, dict) or report.get("success") is not False)
    out: dict[str, Any] = {
        "success": success,
        "workflow": "watch",
        "returncode": code,
        "result": report,
        "error": (report or {}).get("error") if isinstance(report, dict) else None,
        "stages": (report or {}).get("stages") if isinstance(report, dict) else None,
    }
    if isinstance(report, dict):
        for k in ("warnings", "lock", "selected", "source", "download", "hdhive", "note"):
            if k in report:
                out[k] = report[k]
    return out
