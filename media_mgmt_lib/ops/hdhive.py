"""HDHive ops: search / resources / unlock / grab."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops._runner import run_json
from media_mgmt_lib.providers.hdhive import provider as hdhive
from media_mgmt_lib.providers.hdhive.grab import pick_best_resource, transfer_share_to_moviepilot


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    try:
        if tmdbid:
            kind = "movie" if str(media_type).lower() in {"movie", "电影", "films"} else "tv"
            result = asyncio.run(hdhive.search_tmdb(kind, str(tmdbid)))
            return {"success": True, "mode": "tmdb", "data": result}
        if not q:
            return {"success": False, "error": "missing_param", "need": "q|tmdbid"}
        results = asyncio.run(hdhive.search_titles(str(q)))
        return {"success": True, "mode": "keyword", "results": results, "count": len(results or [])}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_search_failed", "detail": str(e)}


def op_resources(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("page_url")
    if not url:
        return {"success": False, "error": "missing_param", "need": "url"}
    try:
        resources = asyncio.run(hdhive.list_resources(str(url)))
        best = pick_best_resource(resources or []) if resources else None
        return {"success": True, "resources": resources or [], "best": best}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_resources_failed", "detail": str(e)}


def op_unlock(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("resource_url")
    if not url:
        return {"success": False, "error": "missing_param", "need": "url"}
    try:
        share_url = asyncio.run(hdhive.unlock_share(str(url)))
        ok = bool(share_url) and "unlock_failed" not in str(share_url) and "***" not in str(share_url)
        return {"success": ok, "share_url": share_url}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_unlock_failed", "detail": str(e)}


def op_grab(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """search → best resource → unlock → optional transfer."""
    q = params.get("q") or params.get("title") or params.get("keyword")
    if not q:
        return {"success": False, "error": "missing_param", "need": "q"}
    select = int(params.get("select") or 1)
    do_transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    # reuse grab CLI for battle-tested flow when transfer requested
    if do_transfer:
        # grab.py prints human text; call programmatic path
        from media_mgmt_lib.providers.hdhive.grab import grab_and_transfer
        # grab_and_transfer prints; capture via redirect is hard — reimplement compact JSON path
        pass

    try:
        results = asyncio.run(hdhive.search_titles(str(q)))
        if not results:
            return {"success": False, "error": "no_results"}
        idx = max(0, select - 1)
        if idx >= len(results):
            idx = 0
        chosen = results[idx]
        resources = asyncio.run(hdhive.list_resources(chosen["url"]))
        if not resources:
            return {"success": False, "error": "no_resources", "selected": chosen}
        best = pick_best_resource(resources)
        share_url = asyncio.run(hdhive.unlock_share(best["url"]))
        ok_unlock = bool(share_url) and "unlock_failed" not in str(share_url) and "***" not in str(share_url)
        transfer = None
        if ok_unlock and do_transfer:
            try:
                transfer = transfer_share_to_moviepilot(str(share_url))
            except Exception as e:  # noqa: BLE001
                transfer = {"error": str(e)}
        return {
            "success": ok_unlock,
            "selected": chosen,
            "best_resource": best,
            "share_url": share_url,
            "transfer": transfer,
        }
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_grab_failed", "detail": str(e)}


register_op("hdhive", "search", op_search)
register_op("hdhive", "resources", op_resources)
register_op("hdhive", "unlock", op_unlock)
register_op("hdhive", "grab", op_grab)
