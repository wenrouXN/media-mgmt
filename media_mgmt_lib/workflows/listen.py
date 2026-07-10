from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok
from media_mgmt_lib.ops import call_op
import media_mgmt_lib.ops.bootstrap  # noqa: F401

def run(params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("query") or params.get("title")
    if not q:
        return fail("missing_param", need="q")
    result = call_op("telegram_music", "search_download", {**params, "q": q})
    return ok({
        "workflow": "listen",
        "query": q,
        "success": bool(result.get("success")),
        "path": result.get("path"),
        "result": result,
        "summary": f"music '{q}' → {result.get('path') or result.get('error') or result.get('detail')}",
    })
