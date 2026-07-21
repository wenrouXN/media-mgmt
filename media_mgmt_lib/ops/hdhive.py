"""HDHive ops — thin aliases of NextFind OpenAPI (no Cloak).

Kept for backward CLI/workflow names: `call hdhive *` / `run hdhive`.
Primary implementation: media_mgmt_lib.ops.nextfind.
"""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op


def _call_nextfind(op: str, params: dict[str, Any]) -> dict[str, Any]:
    import media_mgmt_lib.ops.nextfind  # noqa: F401
    from media_mgmt_lib.ops import call_op

    result = call_op("nextfind", op, params)
    if not isinstance(result, dict):
        return {"success": False, "error": "nextfind_bad_response", "path": "nextfind_openapi"}
    out = dict(result)
    out.setdefault("path", "nextfind_openapi")
    out.setdefault("source", "nextfind_openapi")
    if out.get("error") == "nextfind_not_configured":
        out["hint"] = (
            "Configure workspace .credentials/nextfind.env "
            "(NEXTFIND_BASE_URL + NEXTFIND_API_KEY). Cloak HDHive path removed."
        )
    return out


def op_health(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return _call_nextfind("health", params or {})


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    if not q and tmdbid:
        q = str(tmdbid)
    if not q:
        return {"success": False, "error": "missing_param", "need": "q|tmdbid"}
    return _call_nextfind(
        "search",
        {"q": q, "media_type": media_type, "title": params.get("title")},
    )


def op_resources(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not tmdbid:
        return {
            "success": False,
            "error": "missing_param",
            "need": "tmdbid",
            "hint": "Cloak page-url resources removed; use NextFind tmdb_id",
        }
    return _call_nextfind(
        "resources",
        {
            "tmdbid": tmdbid,
            "media_type": params.get("media_type") or params.get("kind") or params.get("type") or "movie",
            "season": params.get("season"),
            "episode": params.get("episode"),
            "resolution": params.get("resolution"),
            "require_chinese": params.get("require_chinese") or params.get("chinese"),
            "hdr_mode": params.get("hdr_mode"),
        },
    )


def op_unlock(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    rid = params.get("id") or params.get("resource_id")
    rtype = params.get("type") or params.get("resource_type")
    if rid is None or rtype in (None, ""):
        return {
            "success": False,
            "error": "missing_param",
            "need": "id+type",
            "hint": "Use NextFind resource id+type; Cloak URL unlock removed",
        }
    return _call_nextfind("unlock", {"id": rid, "type": rtype})


def op_grab(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not q and not tmdbid:
        return {"success": False, "error": "missing_param", "need": "q|tmdbid"}
    return _call_nextfind(
        "grab",
        {
            "q": q,
            "tmdbid": tmdbid,
            "media_type": params.get("media_type") or params.get("kind") or "movie",
            "select": params.get("select") or 1,
            "transfer": params.get("transfer", "true"),
            "dry_run": params.get("dry_run"),
            "preview": params.get("preview"),
            "season": params.get("season"),
            "episode": params.get("episode"),
            "resolution": params.get("resolution"),
            "require_chinese": params.get("require_chinese") or params.get("chinese"),
            "hdr_mode": params.get("hdr_mode"),
            "target_folder": params.get("target_folder") or params.get("folder"),
        },
    )


register_op("hdhive", "health", op_health)
register_op("hdhive", "search", op_search)
register_op("hdhive", "resources", op_resources)
register_op("hdhive", "unlock", op_unlock)
register_op("hdhive", "grab", op_grab)
