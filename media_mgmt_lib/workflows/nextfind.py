"""NextFind OpenAPI workflow: search → resources → grab/transfer/subscribe."""
from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword") or params.get("query")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    op = str(params.get("op") or params.get("action") or "grab").strip().lower()
    media_type = params.get("media_type") or params.get("kind") or params.get("type") or "movie"

    if op in {"health", "quota", "subscriptions", "directories"}:
        result = call_op("nextfind", op if op != "quota" else "quota", params)
        return ok(
            {
                "workflow": "nextfind",
                "mode": op,
                "result": result,
                "success": bool(result.get("success")),
            }
        )

    if op in {"search"}:
        if not q and not tmdbid:
            return fail("missing_param", need="q|title|tmdbid")
        result = call_op(
            "nextfind",
            "search",
            {
                "q": q or tmdbid,
                "media_type": media_type,
            },
        )
        return ok(
            {
                "workflow": "nextfind",
                "mode": "search",
                "result": result,
                "success": bool(result.get("success")),
                "summary": f"nextfind search '{q or tmdbid}': "
                f"{'ok' if result.get('success') else result.get('error') or 'failed'}",
            }
        )

    if op in {"identify"}:
        if not q and not tmdbid:
            return fail("missing_param", need="q|title|tmdbid")
        result = call_op(
            "nextfind",
            "identify",
            {
                "q": q,
                "title": params.get("title") or q,
                "tmdbid": tmdbid,
                "media_type": media_type,
                "year": params.get("year"),
                "select": params.get("select"),
            },
        )
        return ok(
            {
                "workflow": "nextfind",
                "mode": "identify",
                "path": "nextfind_openapi",
                "result": result,
                "selected": result.get("selected") if isinstance(result, dict) else None,
                "tmdb_id": result.get("tmdb_id") if isinstance(result, dict) else None,
                "success": bool(result.get("success")),
                "summary": f"nextfind identify '{q or tmdbid}': "
                f"{'ok' if result.get('success') else result.get('error') or 'failed'}",
            }
        )

    if op in {"resources"}:
        if not tmdbid:
            return fail("missing_param", need="tmdbid")
        result = call_op(
            "nextfind",
            "resources",
            {
                "tmdbid": tmdbid,
                "media_type": media_type,
                "season": params.get("season"),
                "episode": params.get("episode"),
                "resolution": params.get("resolution"),
                "require_chinese": params.get("require_chinese") or params.get("chinese"),
                "hdr_mode": params.get("hdr_mode"),
            },
        )
        return ok(
            {
                "workflow": "nextfind",
                "mode": "resources",
                "result": result,
                "success": bool(result.get("success")),
            }
        )

    if op in {"subscribe", "subscribe_add"}:
        if not tmdbid and not q:
            return fail("missing_param", need="tmdbid|q")
        if not tmdbid and q:
            sr = call_op("nextfind", "search", {"q": q, "media_type": media_type})
            if not sr.get("success"):
                return ok(
                    {
                        "workflow": "nextfind",
                        "mode": "subscribe",
                        "success": False,
                        "result": sr,
                        "error": sr.get("error"),
                    }
                )
            selected = sr.get("selected") or {}
            tmdbid = selected.get("tmdb_id") or selected.get("id")
            if selected.get("type") or selected.get("raw_type"):
                media_type = selected.get("raw_type") or selected.get("type") or media_type
        if not tmdbid:
            return fail("no_tmdb_id", need="tmdbid after search")
        result = call_op(
            "nextfind",
            "subscribe_add",
            {
                "tmdbid": tmdbid,
                "media_type": media_type,
                "title": params.get("title") or q,
                "target_resolution": params.get("resolution") or params.get("target_resolution"),
            },
        )
        return ok(
            {
                "workflow": "nextfind",
                "mode": "subscribe_add",
                "tmdbid": tmdbid,
                "media_type": media_type,
                "result": result,
                "success": bool(result.get("success")),
            }
        )

    # default: grab (search optional → resources → pick → transfer)
    if not q and not tmdbid:
        return fail("missing_param", need="q|title|tmdbid")
    transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
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
            "workflow": "nextfind",
            "mode": "grab",
            "query": q,
            "tmdbid": result.get("tmdb_id") or tmdbid,
            "media_type": result.get("media_type") or media_type,
            "transfer": transfer,
            "dry_run": dry_run,
            "success": success,
            "result": result,
            "slug": result.get("slug"),
            "error": result.get("error"),
            "summary": f"nextfind '{label}': {'ok' if success else err}",
        }
    )
