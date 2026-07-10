from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Listen workflow: high-confidence auto download; ambiguous → must confirm.

    params:
      q / query / title
      button_index / button_text  — explicit choice (always download)
      force / yes — download top suggestion even if ambiguous
      search_only — only list candidates
    """
    q = params.get("q") or params.get("query") or params.get("title")
    if not q:
        return fail("missing_param", need="q")

    if str(params.get("search_only") or "").lower() in {"1", "true", "yes"}:
        result = call_op("telegram_music", "search", {**params, "q": q})
        return ok(
            {
                "workflow": "listen",
                "mode": "search_only",
                "query": q,
                "success": bool(result.get("success")),
                "candidates": result.get("candidates"),
                "decision": result.get("decision"),
                "result": result,
                "summary": (
                    f"music search '{q}': {result.get('candidate_count')} candidates; "
                    f"auto={((result.get('decision') or {}).get('auto'))}"
                ),
            }
        )

    # policy search_download
    result = call_op("telegram_music", "search_download", {**params, "q": q})
    needs = bool(result.get("needs_confirm"))
    downloaded = bool(result.get("path") or result.get("downloaded") is True or result.get("auto_downloaded"))
    summary = result.get("summary")
    if not summary:
        if downloaded:
            summary = f"music '{q}' → {result.get('path')} (auto={result.get('auto_downloaded')})"
        elif needs:
            sug = result.get("suggested") or (result.get("decision") or {}).get("suggested") or {}
            summary = (
                f"music '{q}' 需确认：建议 #{sug.get('index')} {sug.get('text')} "
                f"(confidence={(result.get('decision') or {}).get('confidence')})"
            )
        else:
            summary = f"music '{q}' → {result.get('error') or result.get('detail') or 'done'}"

    return ok(
        {
            "workflow": "listen",
            "query": q,
            "success": bool(result.get("success")),
            "downloaded": downloaded,
            "needs_confirm": needs,
            "path": result.get("path"),
            "candidates": result.get("candidates"),
            "decision": result.get("decision"),
            "suggested": result.get("suggested") or (result.get("decision") or {}).get("suggested"),
            "policy": result.get("policy"),
            "result": result,
            "summary": summary,
            "next": result.get("next"),
        }
    )
