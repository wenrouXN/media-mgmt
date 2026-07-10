from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok
from media_mgmt_lib.ops import call_op
import media_mgmt_lib.ops.bootstrap  # noqa: F401

def run(params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("link")
    if not url:
        return fail("missing_param", need="url")
    intent = params.get("intent") or params.get("q") or params.get("want") or "解析"
    # reuse hybrid intent
    result = call_op("hybrid", "intent", {**params, "url": url, "intent": intent})
    return ok({
        "workflow": "link",
        "url": url,
        "intent": intent,
        "platform": result.get("platform") or result.get("service"),
        "result": result,
        "success": bool(result.get("success")),
        "summary": f"link/{intent} → {result.get('op') or result.get('service')}: {'ok' if result.get('success') else result.get('error')}",
    })
