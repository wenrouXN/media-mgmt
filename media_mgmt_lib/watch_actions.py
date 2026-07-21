"""Watch side actions: netdisk grab, clients, download, status, subscribe suggest."""
from __future__ import annotations

import argparse
import json
from typing import Any

import scripts.mp_api as mp_api
from media_mgmt_lib.torrent_pick import summarize_candidate
from media_mgmt_lib.watch_stages import stage as _stage

def try_nextfind(
    media: dict[str, Any],
    season: int | None,
    episode: int | None,
    *,
    timeout: float = 90,
    transfer: bool = True,
) -> dict[str, Any] | None:
    """Netdisk grab via NextFind OpenAPI (NextFind OpenAPI). On failure watch continues to PT."""
    tmdb_id = media.get("tmdb_id") or media.get("tmdbid")
    title = media.get("title") or media.get("en_title") or media.get("original_title") or ""
    if not tmdb_id and not title:
        return None
    mtype_raw = str(media.get("type") or "")
    kind = "movie" if mtype_raw in {"电影", "movie"} else "tv"
    _stage("nextfind_start", tmdb_id=tmdb_id, kind=kind, timeout=timeout, transfer=transfer)
    try:
        import media_mgmt_lib.ops.bootstrap  # noqa: F401
        from media_mgmt_lib.ops import call_op

        params: dict[str, Any] = {
            "tmdbid": tmdb_id,
            "title": title,
            "q": title,
            "media_type": kind,
            "transfer": transfer,
            "season": season,
            "episode": episode,
        }
        result = call_op("nextfind", "grab", params)
    except Exception as e:  # noqa: BLE001
        _stage("nextfind_failed", detail=str(e))
        return {"success": False, "error": "nextfind_exec_failed", "detail": str(e), "season": season, "episode": episode}

    ok = bool(isinstance(result, dict) and result.get("success"))
    share_url = (result or {}).get("share_url") if isinstance(result, dict) else None
    transfer_info = (result or {}).get("transfer") if isinstance(result, dict) else None
    path = (result or {}).get("path") if isinstance(result, dict) else None
    source = (result or {}).get("source") if isinstance(result, dict) else None
    if not source:
        source = "nextfind_openapi" if path == "nextfind_openapi" or (isinstance(result, dict) and result.get("slug")) else "nextfind_openapi"
    transfer_ok = bool(
        isinstance(transfer_info, dict)
        and (
            transfer_info.get("code") == 0
            or transfer_info.get("success") is True
            or transfer_info.get("dry_run") is True
        )
    )
    _stage(
        "nextfind_done",
        success=ok,
        path=path or source,
        has_share=bool(share_url),
        has_slug=bool(isinstance(result, dict) and result.get("slug")),
        transfer_ok=transfer_ok,
    )
    return {
        "success": ok,
        "result": result,
        "share_url": share_url,
        "slug": (result or {}).get("slug") if isinstance(result, dict) else None,
        "transfer": transfer_info,
        "source": source,
        "path": path or source,
        "season": season,
        "episode": episode,
        "note": (
            "Netdisk grab failed; watch continues to PT."
            if not ok
            else f"Netdisk grab succeeded via {path or source}"
        ),
    }


def ensure_clients() -> list[dict[str, Any]]:
    clients = mp_api.request("GET", "/api/v1/download/clients") or []
    if not isinstance(clients, list) or not clients:
        raise SystemExit(
            json.dumps(
                {
                    "success": False,
                    "error": "no_download_clients",
                    "hint": "Configure qBittorrent/Transmission in MoviePilot. Do not confuse with empty GET /download/ task list.",
                },
                ensure_ascii=False,
            )
        )
    return clients


def download_selected(
    media: dict[str, Any],
    selected: dict[str, Any],
    *,
    downloader: str | None,
    save_path: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    torrent_in = selected.get("torrent_info") if isinstance(selected.get("torrent_info"), dict) else selected
    missing = mp_api.validate_torrent_info(torrent_in)
    missing_media = mp_api.validate_media_info(media, require_full=True)
    if missing or missing_media:
        return {
            "success": False,
            "error": "validation_failed",
            "missing_torrent_fields": missing,
            "missing_media_fields": missing_media,
        }
    resolved = None
    if not save_path:
        paths = mp_api.request("GET", "/api/v1/download/paths") or []
        category_config = mp_api.request("GET", "/api/v1/media/category/config")
        resolved = mp_api.choose_download_path(media, paths, category_config)
        save_path = resolved.get("save_path")
    if not save_path:
        return {"success": False, "error": "save_path_missing"}
    body = {"media_in": media, "torrent_in": torrent_in, "downloader": downloader, "save_path": save_path}
    if dry_run:
        return {
            "dry_run": True,
            "endpoint": "/api/v1/download/",
            "save_path": save_path,
            "resolved_path": resolved,
            "selected_summary": summarize_candidate(selected),
            "downloader": downloader,
        }
    try:
        result = mp_api.request("POST", "/api/v1/download/", body=body)
    except SystemExit as e:
        # mp_api.request already JSON-encoded errors into SystemExit message
        msg = str(e)
        try:
            return json.loads(msg)
        except json.JSONDecodeError:
            return {"success": False, "error": "download_failed", "detail": msg}
    if isinstance(result, dict) and result.get("success") is False:
        return {
            **result,
            "hint": "Check clients, enclosure/cookie completeness, and retry with another candidate.",
            "selected_summary": summarize_candidate(selected),
        }
    return {"success": True, "result": result, "save_path": save_path, "selected_summary": summarize_candidate(selected)}


def status_snapshot(media: dict[str, Any], episode: int | None) -> dict[str, Any]:
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    args = argparse.Namespace(title=media.get("title"), tmdbid=int(tmdbid) if tmdbid else None, episode=episode, count=20)
    # reuse mp_api status logic without printing
    active = mp_api.request("GET", "/api/v1/download/") or []
    if not isinstance(active, list):
        active = []
    transfers = mp_api.request("GET", "/api/v1/history/transfer", params={"page": 1, "count": 20}) or {}
    transfer_list: list[Any] = []
    if isinstance(transfers, dict):
        data = transfers.get("data")
        if isinstance(data, dict):
            transfer_list = data.get("list") or []
        elif isinstance(data, list):
            transfer_list = data
    matched_active = []
    for item in active:
        if not isinstance(item, dict):
            continue
        m = item.get("media") or {}
        if tmdbid and int(m.get("tmdbid") or m.get("tmdb_id") or 0) == int(tmdbid):
            if episode is None or f"E{int(episode):02d}" in str(m.get("episode") or "").upper() or str(episode) in str(m.get("episode") or ""):
                matched_active.append(item)
    matched_transfers = []
    for item in transfer_list:
        if not isinstance(item, dict):
            continue
        if tmdbid and int(item.get("tmdbid") or 0) == int(tmdbid):
            if episode is None or f"E{int(episode):02d}" in str(item.get("episodes") or "").upper() or str(episode) in str(item.get("episodes") or ""):
                matched_transfers.append(item)
    state = "downloading" if matched_active else ("transferred" if matched_transfers else "unknown")
    return {"state": state, "active": matched_active, "transfers": matched_transfers[:5]}


def maybe_subscribe(media: dict[str, Any], season: int | None, dry_run: bool) -> dict[str, Any] | None:
    # Only suggest/create when clearly unfinished
    status = str(media.get("status") or "").lower()
    unfinished = status in {"returning series", "in production", "planned", "continuing"} or not media.get("number_of_episodes")
    if not unfinished:
        return None
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    body = {
        "name": media.get("title"),
        "type": mp_api.normalize_mtype(media.get("type") or "tv"),
        "year": media.get("year"),
        "tmdbid": int(tmdbid) if tmdbid else None,
        "season": season or 1,
    }
    if dry_run:
        return {"dry_run": True, "would_subscribe": body}
    # Default: do not auto-create unless --subscribe
    return {"suggested_subscribe": body}


