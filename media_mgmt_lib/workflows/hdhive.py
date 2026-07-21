"""Netdisk grab workflow — NextFind OpenAPI only (hdhive name kept as alias)."""
from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not q and not tmdbid:
        return fail("missing_param", need="q|title|tmdbid")
    transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    media_type = params.get("media_type") or params.get("kind") or "movie"
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    search_only = str(params.get("search_only") or "").lower() in {"1", "true", "yes"}

    if search_only:
        result = call_op(
            "nextfind",
            "search",
            {
                "q": q or tmdbid,
                "media_type": media_type,
                "title": params.get("title"),
            },
        )
        success = bool(result.get("success"))
        return ok(
            {
                "workflow": "hdhive",
                "path": "nextfind_openapi",
                "mode": "search_only",
                "result": result,
                "success": success,
                "summary": f"hdhive/nextfind search: {'ok' if success else result.get('error')}",
            }
        )

    result = call_op(
        "nextfind",
        "grab",
        {
            "q": q,
            "tmdbid": tmdbid,
            "media_type": media_type,
            "select": params.get("select") or 1,
            "transfer": transfer,
            "dry_run": dry_run or params.get("dry_run"),
            "preview": params.get("preview"),
            "season": params.get("season"),
            "episode": params.get("episode"),
            "resolution": params.get("resolution"),
            "require_chinese": params.get("require_chinese") or params.get("chinese"),
            "hdr_mode": params.get("hdr_mode"),
            "target_folder": params.get("target_folder") or params.get("folder"),
        },
    )
    success = bool(result.get("success"))
    label = q or tmdbid
    err = result.get("error") or "failed"
    return ok(
        {
            "workflow": "hdhive",
            "path": "nextfind_openapi",
            "query": q,
            "tmdbid": result.get("tmdb_id") or tmdbid,
            "media_type": result.get("media_type") or media_type,
            "transfer": transfer,
            "dry_run": dry_run,
            "success": success,
            "result": result,
            "slug": result.get("slug"),
            "error": result.get("error"),
            "summary": f"hdhive/nextfind '{label}': {'ok' if success else err}",
        }
    )
