from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok
from media_mgmt_lib.ops import call_op
import media_mgmt_lib.ops.bootstrap  # noqa: F401

def run(params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    if not q and not params.get("tmdbid"):
        return fail("missing_param", need="q|title|tmdbid")
    transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    if params.get("tmdbid") and not q:
        result = call_op("hdhive", "search", {"tmdbid": params.get("tmdbid"), "media_type": params.get("media_type") or "tv"})
        return ok({"workflow": "hdhive", "mode": "tmdb_search", "result": result, "success": bool(result.get("success"))})
    result = call_op("hdhive", "grab", {"q": q, "select": params.get("select") or 1, "transfer": transfer})
    return ok({
        "workflow": "hdhive",
        "query": q,
        "transfer": transfer,
        "success": bool(result.get("success")),
        "result": result,
        "share_url": result.get("share_url"),
        "summary": f"hdhive '{q}': {'ok' if result.get('success') else result.get('error')}",
    })
