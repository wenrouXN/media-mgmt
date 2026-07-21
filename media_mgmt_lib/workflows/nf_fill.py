"""NextFind fill helper: one NF resource pass — netdisk first, then PT via MP.

CEO rule (2026-07-20):
  - NF search/resources once = may include netdisk (+ PT when present)
  - Prefer netdisk grab/transfer
  - Netdisk quality gate fail → use PT from same NF results if any, else MP search
  - Never default MP re-search after NF already returned usable PT
"""
from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.quality_pref import parse_quality_params, pick_best_resource, resource_blob, matches_quality


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes"}


def _norm_type(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in {"movie", "电影", "film", "films", "mov"}:
        return "movie"
    if s in {"tv", "电视剧", "剧集", "anime", "动漫", "series", "show"}:
        return "tv"
    return s or "movie"


def _is_netdisk_item(it: dict[str, Any]) -> bool:
    if not isinstance(it, dict):
        return False
    if it.get("slug"):
        return True
    st = str(it.get("source_type") or it.get("pan_type") or "").lower()
    if st in {"hdhive", "radar", "115", "netdisk", "pan", "cloud"}:
        return True
    if "hdhive://" in str(it.get("slug") or it.get("media_url") or ""):
        return True
    return False


def _is_pt_item(it: dict[str, Any]) -> bool:
    """Heuristic: PT/torrent-like rows from NF (when present)."""
    if not isinstance(it, dict):
        return False
    if _is_netdisk_item(it):
        return False
    # common PT markers
    for k in ("torrent_info", "enclosure", "magnet", "download_url", "site", "seeders", "peers"):
        if it.get(k) not in (None, "", [], {}):
            return True
    st = str(it.get("source_type") or it.get("source") or it.get("channel_name") or "").lower()
    if any(x in st for x in ("pt", "torrent", "tracker", "moviepilot", "mp")):
        return True
    return False


def _netdisk_ok(best: dict[str, Any] | None, qpref: dict[str, Any]) -> tuple[bool, str | None]:
    if not best or not isinstance(best, dict):
        return False, "netdisk_no_resources"
    if not best.get("slug"):
        return False, "no_slug"
    text = resource_blob(best)
    hard = matches_quality(
        text,
        resolution=qpref.get("resolution"),
        require_chinese=bool(qpref.get("require_chinese")),
        hdr_mode=str(qpref.get("hdr_mode") or "any"),
    )
    if not hard and (qpref.get("resolution") or qpref.get("require_chinese")):
        return False, "netdisk_quality_gate"
    return True, None


def _nf_ready() -> bool:
    try:
        return bool(call_op("nextfind", "health", {}).get("success"))
    except Exception:  # noqa: BLE001
        return False


def fill_missing(params: dict[str, Any]) -> dict[str, Any]:
    """Fill one title/tmdb (optional season/episode) via NF-first path.

    params:
      title|q, tmdbid, media_type, season, episode
      dry_run, transfer (default true for netdisk)
      prefer=pt|netdisk|auto (default auto)
      force_mp_search: allow MP re-search when NF empty
      resolution / require_chinese / hdr_mode
    """
    title = params.get("title") or params.get("q") or params.get("keyword")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = _norm_type(params.get("media_type") or params.get("kind") or params.get("type") or "movie")
    season = params.get("season")
    episode = params.get("episode")
    dry_run = _truthy(params.get("dry_run"))
    prefer = str(params.get("prefer") or "auto").lower()
    force_mp_search = _truthy(params.get("force_mp_search") or params.get("force_mp"))
    qpref = parse_quality_params(params)
    do_transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}

    if not title and not tmdbid:
        return {"success": False, "error": "missing_param", "need": "title|tmdbid"}

    steps: list[dict[str, Any]] = []
    identified = None

    # 1) identify if no tmdb
    if not tmdbid:
        if not _nf_ready():
            return {"success": False, "error": "nextfind_not_configured", "stage": "identify"}
        idr = call_op(
            "nextfind",
            "identify",
            {
                "q": title,
                "title": title,
                "media_type": media_type,
                "year": params.get("year"),
                "select": params.get("select") or 1,
            },
        )
        steps.append({"stage": "identify", "result": {"success": idr.get("success"), "error": idr.get("error")}})
        if not idr.get("success"):
            return {
                "success": False,
                "error": idr.get("error") or "identify_failed",
                "stage": "identify",
                "steps": steps,
            }
        selected = idr.get("selected") or {}
        tmdbid = selected.get("tmdb_id") or selected.get("tmdbid")
        identified = selected
        if selected.get("type") or selected.get("media_type"):
            media_type = _norm_type(selected.get("media_type") or selected.get("type"))
        if not tmdbid:
            return {"success": False, "error": "identify_no_tmdb", "stage": "identify", "steps": steps}

    if not _nf_ready() and not force_mp_search:
        return {
            "success": False,
            "error": "nextfind_not_configured",
            "stage": "health",
            "hint": "set force_mp_search=true to use MP/PT only",
            "steps": steps,
        }

    resources: list[dict[str, Any]] = []
    nf_resources_ok = False
    if _nf_ready():
        rr = call_op(
            "nextfind",
            "resources",
            {
                "tmdbid": tmdbid,
                "media_type": media_type,
                "season": season,
                "episode": episode,
                "resolution": qpref.get("resolution"),
                "require_chinese": qpref.get("require_chinese"),
                "hdr_mode": qpref.get("hdr_mode"),
            },
        )
        steps.append(
            {
                "stage": "nf_resources",
                "success": rr.get("success"),
                "count": rr.get("count"),
                "error": rr.get("error"),
            }
        )
        if rr.get("success"):
            resources = [x for x in (rr.get("resources") or []) if isinstance(x, dict)]
            nf_resources_ok = True

    netdisk_items = [x for x in resources if _is_netdisk_item(x)]
    pt_items = [x for x in resources if _is_pt_item(x)]

    # prefer=pt → skip netdisk attempt
    try_netdisk = prefer not in {"pt", "torrent", "moviepilot", "mp"}
    try_pt_from_nf = prefer not in {"netdisk", "hdhive", "115", "cloud"}

    # 2) netdisk first
    if try_netdisk and netdisk_items:
        best = pick_best_resource(
            netdisk_items,
            resolution=qpref.get("resolution"),
            require_chinese=bool(qpref.get("require_chinese")),
            hdr_mode=str(qpref.get("hdr_mode") or "any"),
        )
        ok_nd, gate_err = _netdisk_ok(best, qpref)
        if ok_nd and best:
            grab = call_op(
                "nextfind",
                "grab",
                {
                    "tmdbid": tmdbid,
                    "title": title,
                    "media_type": media_type,
                    "season": season,
                    "episode": episode,
                    "transfer": do_transfer,
                    "dry_run": dry_run,
                    "resolution": qpref.get("resolution"),
                    "require_chinese": qpref.get("require_chinese"),
                    "hdr_mode": qpref.get("hdr_mode"),
                    "target_folder": params.get("target_folder") or params.get("folder"),
                },
            )
            steps.append({"stage": "netdisk_grab", "success": grab.get("success"), "error": grab.get("error")})
            if grab.get("success"):
                return {
                    "success": True,
                    "path": "netdisk",
                    "source": "nextfind_openapi",
                    "tmdb_id": tmdbid,
                    "media_type": media_type,
                    "title": title,
                    "identified": identified,
                    "best_resource": grab.get("best_resource") or best,
                    "slug": grab.get("slug"),
                    "transfer": grab.get("transfer"),
                    "dry_run": dry_run,
                    "quality": qpref,
                    "steps": steps,
                    "summary": f"nf_fill netdisk ok tmdb={tmdbid}"
                    + (" (dry_run)" if dry_run else ""),
                }
            # transfer/grab soft fail → try PT from same results
            steps.append({"stage": "netdisk_fail_fallback", "error": grab.get("error") or "grab_failed"})
        else:
            steps.append({"stage": "netdisk_gate", "error": gate_err, "best": bool(best)})

    elif try_netdisk and nf_resources_ok and not netdisk_items:
        steps.append({"stage": "netdisk_gate", "error": "netdisk_no_resources"})

    # 3) PT from same NF results (no re-search)
    if try_pt_from_nf and pt_items:
        best_pt = pick_best_resource(
            pt_items,
            resolution=qpref.get("resolution"),
            require_chinese=bool(qpref.get("require_chinese")),
            hdr_mode=str(qpref.get("hdr_mode") or "any"),
        ) or pt_items[0]
        steps.append(
            {
                "stage": "pt_from_nf",
                "count": len(pt_items),
                "selected_title": best_pt.get("title") or best_pt.get("name"),
            }
        )
        if dry_run:
            return {
                "success": True,
                "path": "pt",
                "source": "nextfind_pt_in_results",
                "tmdb_id": tmdbid,
                "media_type": media_type,
                "title": title,
                "dry_run": True,
                "would_push_mp": True,
                "pt_candidate": best_pt,
                "quality": qpref,
                "steps": steps,
                "summary": f"nf_fill would push PT from NF results → MP tmdb={tmdbid} (dry_run)",
                "hint": "PT items found in NF resources; execute without dry_run to push via MP download when torrent_json available",
            }
        # Live: only if we have torrent-shaped payload MP can consume
        torrent_payload = (
            best_pt.get("torrent_info")
            or best_pt.get("torrent")
            or best_pt.get("enclosure")
            or best_pt
        )
        dl = call_op(
            "moviepilot",
            "download",
            {
                "from_search_result": torrent_payload if isinstance(torrent_payload, (dict, list, str)) else None,
                "torrent_json": torrent_payload if isinstance(torrent_payload, (dict, list, str)) else None,
                "tmdbid": tmdbid,
                "dry_run": dry_run,
            },
        )
        # moviepilot download may reject non-torrent shapes
        steps.append({"stage": "mp_download", "success": dl.get("success"), "error": dl.get("error")})
        if dl.get("success"):
            return {
                "success": True,
                "path": "pt",
                "source": "nextfind_pt_in_results",
                "tmdb_id": tmdbid,
                "download": dl,
                "steps": steps,
                "summary": f"nf_fill PT-from-NF pushed to MP tmdb={tmdbid}",
            }
        steps.append(
            {
                "stage": "pt_from_nf_not_executable",
                "error": dl.get("error") or "mp_download_rejected",
                "hint": "NF PT row present but not MP-download shaped; need MP search only if force_mp_search",
            }
        )

    # 4) only if NF empty / no usable path
    if force_mp_search or (not nf_resources_ok) or (not netdisk_items and not pt_items):
        if force_mp_search or not nf_resources_ok or (nf_resources_ok and not netdisk_items and not pt_items):
            # MP search (exception path)
            if not force_mp_search and nf_resources_ok and not netdisk_items and not pt_items:
                # NF returned only netdisk-empty shape — allow MP search as nf_no_pt_in_results
                err = "nf_no_pt_in_results"
            else:
                err = None
            if force_mp_search or err == "nf_no_pt_in_results" or not nf_resources_ok:
                sr = call_op(
                    "moviepilot",
                    "search",
                    {
                        "title": title,
                        "tmdbid": tmdbid,
                        "media_type": media_type,
                    },
                )
                steps.append(
                    {
                        "stage": "mp_search_fallback",
                        "success": sr.get("success"),
                        "error": sr.get("error"),
                        "reason": err or ("force_mp_search" if force_mp_search else "nf_down"),
                    }
                )
                if dry_run:
                    return {
                        "success": bool(sr.get("success")),
                        "path": "pt",
                        "source": "moviepilot_search",
                        "tmdb_id": tmdbid,
                        "dry_run": True,
                        "search": sr,
                        "steps": steps,
                        "summary": f"nf_fill fallback MP search tmdb={tmdbid} (dry_run)",
                        "error": None if sr.get("success") else (sr.get("error") or err),
                    }
                return {
                    "success": bool(sr.get("success")),
                    "path": "pt",
                    "source": "moviepilot_search",
                    "tmdb_id": tmdbid,
                    "search": sr,
                    "steps": steps,
                    "error": None if sr.get("success") else (sr.get("error") or err or "mp_search_failed"),
                    "summary": f"nf_fill fallback MP search tmdb={tmdbid}",
                    "hint": "Use run watch --param prefer=pt to download selected torrent",
                }

    return {
        "success": False,
        "error": "no_fill_path",
        "tmdb_id": tmdbid,
        "media_type": media_type,
        "netdisk_count": len(netdisk_items),
        "pt_in_nf_count": len(pt_items),
        "nf_resources_ok": nf_resources_ok,
        "steps": steps,
        "hint": "pass force_mp_search=true to allow MP re-search; or prefer=pt",
        "summary": f"nf_fill no path tmdb={tmdbid}",
    }
