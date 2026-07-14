from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok
from media_mgmt_lib.ops import call_op
import media_mgmt_lib.ops.bootstrap  # noqa: F401


def run(params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not q and not tmdbid:
        return fail("missing_param", need="q|title|tmdbid")
    transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    media_type = params.get("media_type") or params.get("kind") or "movie"
    search_only = str(params.get("search_only") or "").lower() in {"1", "true", "yes"}

    # Default path is grab (unlock + optional transfer). search_only keeps legacy tmdb probe.
    if search_only and tmdbid and not q:
        result = call_op("hdhive", "search", {"tmdbid": tmdbid, "media_type": media_type})
        return ok(
            {
                "workflow": "hdhive",
                "mode": "tmdb_search",
                "result": result,
                "success": bool(result.get("success")),
            }
        )

    result = call_op(
        "hdhive",
        "grab",
        {
            "q": q,
            "tmdbid": tmdbid,
            "media_type": media_type,
            "select": params.get("select") or 1,
            "transfer": transfer,
            "resolution": params.get("resolution"),
            "require_chinese": params.get("require_chinese") or params.get("chinese"),
            "hdr_mode": params.get("hdr_mode"),
        },
    )
    success = bool(result.get("success"))
    label = q or tmdbid
    err = result.get("error") or "failed"
    return ok(
        {
            "workflow": "hdhive",
            "query": q,
            "tmdbid": tmdbid,
            "media_type": media_type,
            "transfer": transfer,
            "success": success,
            "result": result,
            "share_url": result.get("share_url"),
            "error": result.get("error"),
            "summary": f"hdhive '{label}': {'ok' if success else err}",
        }
    )
