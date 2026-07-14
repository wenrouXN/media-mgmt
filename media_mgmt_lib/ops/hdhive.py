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
    from media_mgmt_lib.quality_pref import parse_quality_params

    url = params.get("url") or params.get("page_url")
    if not url:
        return {"success": False, "error": "missing_param", "need": "url"}
    qpref = parse_quality_params(params)
    try:
        resources = asyncio.run(hdhive.list_resources(str(url)))
        best = (
            pick_best_resource(
                resources or [],
                resolution=qpref.get("resolution"),
                require_chinese=qpref.get("require_chinese", False),
                hdr_mode=qpref.get("hdr_mode") or "any",
            )
            if resources
            else None
        )
        return {"success": True, "resources": resources or [], "best": best, "quality": qpref}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_resources_failed", "detail": str(e)}


def _share_url_ok(share_url: Any) -> bool:
    text = str(share_url or "").strip()
    if not text or "unlock_failed" in text:
        return False
    if "/s/" not in text:
        return False
    # DOM-masked password is never usable for P115StrmHelper transfer.
    if "***" in text:
        return False
    # require password query with non-empty plaintext
    if "password=" not in text.lower():
        return False
    try:
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(text).query)
        pwd = (qs.get("password") or [""])[0]
        if not pwd or "*" in pwd:
            return False
    except Exception:  # noqa: BLE001
        return False
    return True


def _transfer_ok(transfer: Any) -> bool:
    if not isinstance(transfer, dict):
        return False
    if transfer.get("error"):
        return False
    # P115StrmHelper returns {code:0,msg:...} on success; code:-1 on failure.
    if "code" in transfer:
        if transfer.get("code") == 0:
            return True
        msg = str(transfer.get("msg") or "")
        return "已经转存" in msg or "已存在" in msg
    if transfer.get("success") is True:
        return True
    return False


def op_unlock(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    url = params.get("url") or params.get("resource_url")
    if not url:
        return {"success": False, "error": "missing_param", "need": "url"}
    try:
        share_url = asyncio.run(hdhive.unlock_share(str(url)))
        ok = _share_url_ok(share_url)
        return {
            "success": ok,
            "share_url": share_url if ok else None,
            "raw_share_url": share_url,
            "error": None if ok else "masked_or_invalid_share_password",
        }
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_unlock_failed", "detail": str(e)}


def op_grab(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """search → best resource (quality-aware) → unlock → optional 115 transfer."""
    from media_mgmt_lib.quality_pref import parse_quality_params

    q = params.get("q") or params.get("title") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    if not q and not tmdbid:
        return {"success": False, "error": "missing_param", "need": "q|tmdbid"}
    select = int(params.get("select") or 1)
    do_transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    qpref = parse_quality_params(params)

    try:
        if tmdbid:
            kind = "movie" if str(media_type).lower() in {"movie", "电影", "films"} else "tv"
            tmdb_hit = asyncio.run(hdhive.search_tmdb(kind, str(tmdbid)))
            # search_tmdb may return page dict or list depending on provider
            if isinstance(tmdb_hit, dict) and tmdb_hit.get("url"):
                results = [tmdb_hit]
            elif isinstance(tmdb_hit, list):
                results = tmdb_hit
            elif isinstance(tmdb_hit, dict) and tmdb_hit.get("results"):
                results = tmdb_hit["results"]
            else:
                results = asyncio.run(hdhive.search_titles(str(q or tmdbid))) if q or tmdbid else []
        else:
            results = asyncio.run(hdhive.search_titles(str(q)))
        if not results:
            return {"success": False, "error": "no_results", "quality": qpref}
        idx = max(0, select - 1)
        if idx >= len(results):
            idx = 0
        chosen = results[idx]
        page_url = chosen.get("url") if isinstance(chosen, dict) else None
        if not page_url:
            return {"success": False, "error": "no_page_url", "selected": chosen, "quality": qpref}
        resources = asyncio.run(hdhive.list_resources(page_url))
        if not resources:
            return {"success": False, "error": "no_resources", "selected": chosen, "quality": qpref}
        best = pick_best_resource(
            resources,
            resolution=qpref.get("resolution"),
            require_chinese=qpref.get("require_chinese", False),
            hdr_mode=qpref.get("hdr_mode") or "any",
        )
        share_url = asyncio.run(hdhive.unlock_share(best["url"]))
        ok_unlock = _share_url_ok(share_url)
        transfer = None
        if ok_unlock and do_transfer:
            try:
                transfer = transfer_share_to_moviepilot(str(share_url))
            except Exception as e:  # noqa: BLE001
                transfer = {"error": str(e)}
        elif do_transfer and not ok_unlock:
            transfer = {
                "error": "masked_or_invalid_share_password",
                "raw_share_url": share_url,
                "hint": "HDHive unlock returned masked password=***; refuse transfer and fall back to PT",
            }
        transfer_ok = _transfer_ok(transfer) if do_transfer else True
        success = ok_unlock and (transfer_ok if do_transfer else True)
        error = None
        if not ok_unlock:
            error = "masked_or_invalid_share_password"
        elif do_transfer and not transfer_ok:
            error = "transfer_failed"
        return {
            "success": success,
            "selected": chosen,
            "best_resource": best,
            "share_url": share_url if ok_unlock else None,
            "raw_share_url": share_url,
            "transfer": transfer,
            "quality": qpref,
            "source": "hdhive_115",
            "resources_count": len(resources),
            "error": error,
        }
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "hdhive_grab_failed", "detail": str(e), "quality": qpref}


register_op("hdhive", "search", op_search)
register_op("hdhive", "resources", op_resources)
register_op("hdhive", "unlock", op_unlock)
register_op("hdhive", "grab", op_grab)
