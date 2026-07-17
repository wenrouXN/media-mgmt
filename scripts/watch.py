#!/usr/bin/env python3
"""One-shot watch pipeline for media-mgmt.

Flow: identify → (optional HDHive) → PT search fallback matrix → pick → download → status.

Agent should prefer this over hand-assembled MoviePilot JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from media_mgmt_lib.config import load_json_config, moviepilot_credentials  # noqa: E402
from media_mgmt_lib.torrent_pick import pick_torrent, summarize_candidate  # noqa: E402

import scripts.mp_api as mp_api  # noqa: E402

# Stage progress goes to stderr so stdout stays pure JSON for agents.
_STAGES: list[dict[str, Any]] = []


def _stage(name: str, **extra: Any) -> None:
    entry = {"stage": name, "t": round(time.time(), 3), **extra}
    _STAGES.append(entry)
    bits = [f"[watch] {name}"]
    for k, v in extra.items():
        if v is None or v == "":
            continue
        bits.append(f"{k}={v}")
    print(" ".join(bits), file=sys.stderr, flush=True)


def print_json(value: Any) -> None:
    if isinstance(value, dict) and _STAGES and "stages" not in value:
        value = {**value, "stages": list(_STAGES)}
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _title_variants(title: str, media: dict[str, Any] | None = None, *, limit: int = 6) -> list[str]:
    """Return a small high-signal title set. Avoid exploding on media.names (can be 20+ locales)."""
    variants: list[str] = []

    def add(val: Any) -> None:
        if not val:
            return
        text = str(val).strip()
        if not text or text in variants:
            return
        if len(text) > 80:
            return
        variants.append(text)

    add(title)
    if media:
        for key in ("title", "en_title", "original_title", "original_name", "name"):
            add(media.get(key))
        for name in media.get("names") or []:
            text = str(name).strip()
            if not text or len(text) > 40:
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in text) or any("\uac00" <= ch <= "\ud7a3" for ch in text) or text.isascii():
                add(text)
            if len(variants) >= limit:
                break
    return variants[:limit]


def _episode_keywords(season: int | None, episode: int | None) -> list[str]:
    if episode is None:
        return []
    keys = [f"E{episode:02d}", f"E{episode}", f"EP{episode:02d}", f"第{episode}集", f"第{episode:02d}集"]
    if season is not None:
        keys.extend(
            [
                f"S{season:02d}E{episode:02d}",
                f"S{season}E{episode:02d}",
                f"S{season:02d}E{episode}",
            ]
        )
    return keys


def _media_shell_usable(media: Any) -> bool:
    """MoviePilot may return a non-empty JSON shell with all-null fields when type_name is wrong."""
    if not isinstance(media, dict) or not media:
        return False
    if media.get("tmdb_id") or media.get("tmdbid"):
        return True
    if media.get("title") or media.get("name") or media.get("en_title") or media.get("original_title"):
        return True
    return False


def _title_match_score(query: str | None, detail: dict[str, Any]) -> int:
    """Score how well a media detail matches the user title. TMDB movie/tv share numeric ids."""
    if not query:
        return 0
    q = str(query).strip().lower()
    if not q:
        return 0
    fields = [
        detail.get("title"),
        detail.get("name"),
        detail.get("original_title"),
        detail.get("original_name"),
        detail.get("en_title"),
        detail.get("title_year"),
    ]
    best = 0
    for raw in fields:
        if not raw:
            continue
        c = str(raw).strip().lower()
        if not c:
            continue
        # strip trailing year in "Title (2026)"
        if c.endswith(")") and " (" in c:
            c = c[: c.rfind(" (")].strip()
        if c == q:
            best = max(best, 100)
        elif q in c or c in q:
            best = max(best, 80)
        else:
            # light token overlap for multi-word titles
            qt = {t for t in q.replace("：", " ").replace(":", " ").split() if len(t) > 1}
            ct = {t for t in c.replace("：", " ").replace(":", " ").split() if len(t) > 1}
            if qt and ct:
                overlap = len(qt & ct) / max(len(qt), 1)
                if overlap >= 0.5:
                    best = max(best, int(50 + 40 * overlap))
    return best


def _score_tmdb_detail(
    detail: dict[str, Any],
    *,
    title: str | None,
    year: str | None,
    media_type: str | None,
    prefer_tv: bool,
) -> int:
    if not _media_shell_usable(detail):
        return -1
    score = 1
    dtype = mp_api.normalize_mtype(detail.get("type") or "") or ""
    preferred = mp_api.normalize_mtype(media_type) if media_type else None
    if preferred in {"电影", "电视剧"} and dtype == preferred:
        score += 40
    if prefer_tv and dtype == "电视剧":
        score += 25
    elif not prefer_tv and preferred is None and dtype == "电影":
        # mild movie bias only when no episode/type hint (legacy default)
        score += 5
    score += _title_match_score(title, detail)
    if year:
        dy = str(detail.get("year") or "").strip()
        if dy and dy == str(year).strip():
            score += 15
        elif dy and dy != str(year).strip():
            score -= 10
    return score


def _fetch_tmdb_detail(
    tmdbid: int,
    *,
    title: str | None,
    year: str | None,
    media_type: str | None,
    prefer_tv: bool = False,
) -> dict[str, Any] | None:
    """Fetch media detail by tmdb id, trying movie/tv when type is unknown or wrong.

    TMDB movie and TV namespaces share numeric ids but are different works. Always try
    both when type is ambiguous, then pick the best title/type/year match — never return
    the first non-empty shell blindly.
    """
    preferred = mp_api.normalize_mtype(media_type) if media_type else None
    if preferred in {"电影", "电视剧"}:
        order = [preferred, "电视剧" if preferred == "电影" else "电影"]
    elif prefer_tv:
        order = ["电视剧", "电影"]
    else:
        # Heuristic default: movie first, but scoring may still prefer TV if title matches.
        order = ["电影", "电视剧"]

    candidates: list[dict[str, Any]] = []
    for mtype in order:
        try:
            detail = mp_api.request(
                "GET",
                f"/api/v1/media/tmdb:{tmdbid}",
                params={"type_name": mtype, "title": title, "year": year},
            )
        except SystemExit:
            continue
        if not isinstance(detail, dict):
            continue
        if not detail.get("tmdb_id") and not detail.get("tmdbid"):
            detail = {**detail, "tmdb_id": int(tmdbid)}
        if not detail.get("type"):
            detail = {**detail, "type": mtype}
        if _media_shell_usable(detail):
            candidates.append(detail)

    if not candidates:
        return None

    best = max(
        candidates,
        key=lambda d: _score_tmdb_detail(
            d, title=title, year=year, media_type=media_type, prefer_tv=prefer_tv
        ),
    )
    # If user gave a title and best score is still weak, still return best usable shell
    # (explicit tmdbid path); callers may refine via recognize fallback.
    return best

def identify_media(
    title: str,
    media_type: str | None,
    year: str | None,
    tmdbid: int | None,
    *,
    episode: int | None = None,
) -> dict[str, Any]:
    _stage("identify_start", title=title, tmdbid=tmdbid)
    prefer_tv = episode is not None or bool(media_type and mp_api.normalize_mtype(media_type) == "电视剧")
    if tmdbid:
        detail = _fetch_tmdb_detail(
            int(tmdbid),
            title=title,
            year=year,
            media_type=media_type,
            prefer_tv=prefer_tv,
        )
        if _media_shell_usable(detail):
            # Title strongly disagrees with tmdb shell → try recognize as safety net
            if title and _title_match_score(title, detail or {}) < 40:
                try:
                    rec = mp_api.request("GET", "/api/v1/media/recognize", params={"title": title})
                except SystemExit:
                    rec = None
                if (
                    isinstance(rec, dict)
                    and isinstance(rec.get("media_info"), dict)
                    and _media_shell_usable(rec.get("media_info"))
                    and _title_match_score(title, rec["media_info"]) > _title_match_score(title, detail or {})
                ):
                    _stage(
                        "identify_done",
                        via="recognize_title_override",
                        tmdb_id=rec["media_info"].get("tmdb_id"),
                        media_type=rec["media_info"].get("type"),
                    )
                    return rec["media_info"]
            _stage(
                "identify_done",
                via="tmdb_detail",
                tmdb_id=(detail or {}).get("tmdb_id") or (detail or {}).get("tmdbid") or tmdbid,
                media_type=(detail or {}).get("type"),
            )
            return detail  # type: ignore[return-value]
        # fallback recognize
        try:
            rec = mp_api.request("GET", "/api/v1/media/recognize", params={"title": title})
        except SystemExit:
            rec = None
        if isinstance(rec, dict) and isinstance(rec.get("media_info"), dict) and _media_shell_usable(rec.get("media_info")):
            _stage("identify_done", via="recognize_fallback", tmdb_id=(rec["media_info"] or {}).get("tmdb_id"))
            return rec["media_info"]
        raise SystemExit(json.dumps({"success": False, "error": "identify_failed", "tmdbid": tmdbid, "stages": list(_STAGES)}, ensure_ascii=False))

    # Prefer recognize (returns full media_info incl. names/category)
    rec = mp_api.request("GET", "/api/v1/media/recognize", params={"title": title})
    if isinstance(rec, dict) and isinstance(rec.get("media_info"), dict) and rec["media_info"].get("tmdb_id"):
        media = rec["media_info"]
        if year and str(media.get("year") or "") not in {"", str(year)}:
            pass  # keep but continue with search refine
        else:
            _stage("identify_done", via="recognize", tmdb_id=media.get("tmdb_id"))
            return media

    results = mp_api.request("GET", "/api/v1/media/search", params={"title": title, "type": "media", "page": 1, "count": 10})
    selected = mp_api._pick_media_search_result(results, title=title, media_type=media_type, year=year)
    if not selected:
        raise SystemExit(json.dumps({"success": False, "error": "media_not_found", "title": title, "stages": list(_STAGES)}, ensure_ascii=False))
    tmdb_id = selected.get("tmdb_id") or selected.get("tmdbid")
    mtype = mp_api.normalize_mtype(media_type or selected.get("type") or "tv") or "电视剧"
    if tmdb_id:
        detail = mp_api.request(
            "GET",
            f"/api/v1/media/tmdb:{tmdb_id}",
            params={"type_name": mtype, "title": selected.get("title") or title, "year": selected.get("year") or year},
        )
        if isinstance(detail, dict) and detail.get("tmdb_id"):
            _stage("identify_done", via="media_search+detail", tmdb_id=detail.get("tmdb_id"))
            return detail
    # recognize with selected title
    rec2 = mp_api.request("GET", "/api/v1/media/recognize", params={"title": selected.get("title") or title})
    if isinstance(rec2, dict) and isinstance(rec2.get("media_info"), dict):
        _stage("identify_done", via="media_search+recognize", tmdb_id=(rec2["media_info"] or {}).get("tmdb_id"))
        return rec2["media_info"]
    _stage("identify_done", via="media_search_selected", tmdb_id=tmdb_id)
    return selected


def search_pt_resources(
    media: dict[str, Any],
    season: int | None,
    episode: int | None,
    sites: str | None,
    *,
    enough: int = 5,
) -> list[dict[str, Any]]:
    """Search PT with early-exit. Avoid N titles x M episode keywords explosion."""
    tmdb_id = media.get("tmdb_id") or media.get("tmdbid")
    mtype = mp_api.normalize_mtype(media.get("type") or "tv")
    title = media.get("title") or media.get("en_title") or media.get("original_title") or ""
    year = media.get("year")
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    _stage("pt_search_start", tmdb_id=tmdb_id, season=season, episode=episode, enough=enough)

    def add_items(items: Any, source: str) -> int:
        added = 0
        if not isinstance(items, list):
            if isinstance(items, dict):
                maybe = items.get("data")
                if isinstance(maybe, list):
                    items = maybe
                else:
                    return 0
            else:
                return 0
        for it in items:
            if not isinstance(it, dict):
                continue
            ti = it.get("torrent_info") if isinstance(it.get("torrent_info"), dict) else it
            key = str((ti or {}).get("enclosure") or (ti or {}).get("page_url") or (ti or {}).get("title") or id(it))
            if key in seen:
                continue
            seen.add(key)
            wrapped = it if "torrent_info" in it else {"torrent_info": it, "source_query": source}
            if "source_query" not in wrapped:
                wrapped = {**wrapped, "source_query": source}
            collected.append(wrapped)
            added += 1
        return added

    def episode_hits() -> int:
        if episode is None:
            return len(collected)
        from media_mgmt_lib.torrent_pick import matches_episode

        return sum(1 for it in collected if matches_episode(it, season=season, episode=episode))

    # 1) media id search
    if tmdb_id:
        try:
            _stage("pt_search_media_id", tmdb_id=tmdb_id)
            res = mp_api.request(
                "GET",
                f"/api/v1/search/media/{urllib.parse.quote(f'tmdb:{tmdb_id}', safe=':')}",
                params={"mtype": mtype, "title": title, "year": year, "season": season, "sites": sites},
            )
            added = add_items(res, f"media:tmdb:{tmdb_id}")
            _stage("pt_search_media_id_done", added=added, total=len(collected), ep_hits=episode_hits())
        except SystemExit:
            _stage("pt_search_media_id_failed")
        if episode_hits() >= enough:
            _stage("pt_search_early_exit", reason="media_id_enough", total=len(collected))
            return collected

    variants = _title_variants(title, media, limit=4)
    # 2) plain title variants first (broad net)
    for base in variants:
        try:
            _stage("pt_search_title", keyword=base)
            res = mp_api.request("GET", "/api/v1/search/title", params={"keyword": base, "page": 0, "sites": sites})
            added = add_items(res, f"title:{base}")
            _stage("pt_search_title_done", keyword=base, added=added, total=len(collected), ep_hits=episode_hits())
        except SystemExit:
            _stage("pt_search_title_failed", keyword=base)
            continue
        if episode_hits() >= enough:
            _stage("pt_search_early_exit", reason="title_enough", total=len(collected))
            return collected

    # 3) precise episode keywords only on top 2 titles, top 3 episode forms
    ep_keys = _episode_keywords(season, episode)[:3]
    for base in variants[:2]:
        for ek in ep_keys:
            kw = f"{base} {ek}"
            try:
                _stage("pt_search_ep_kw", keyword=kw)
                res = mp_api.request("GET", "/api/v1/search/title", params={"keyword": kw, "page": 0, "sites": sites})
                added = add_items(res, f"title:{kw}")
                _stage("pt_search_ep_kw_done", keyword=kw, added=added, total=len(collected), ep_hits=episode_hits())
            except SystemExit:
                _stage("pt_search_ep_kw_failed", keyword=kw)
                continue
            if episode_hits() >= enough:
                _stage("pt_search_early_exit", reason="ep_kw_enough", total=len(collected))
                return collected

    _stage("pt_search_done", total=len(collected), ep_hits=episode_hits())
    return collected


def try_hdhive(
    media: dict[str, Any],
    season: int | None,
    episode: int | None,
    *,
    timeout: float = 90,
    transfer: bool = True,
) -> dict[str, Any] | None:
    """Run HDHive grab (search → unlock → optional 115 transfer) for this media.

    Prefer the ops facade so unlock/transfer validation stays in one place.
    """
    tmdb_id = media.get("tmdb_id") or media.get("tmdbid")
    title = media.get("title") or media.get("en_title") or media.get("original_title") or ""
    if not tmdb_id and not title:
        return None
    mtype_raw = str(media.get("type") or "")
    kind = "movie" if mtype_raw in {"电影", "movie"} else "tv"
    _stage("hdhive_start", tmdb_id=tmdb_id, kind=kind, timeout=timeout, transfer=transfer)
    try:
        # Import inside function to keep watch.py usable even if hdhive deps missing.
        import media_mgmt_lib.ops.bootstrap  # noqa: F401
        from media_mgmt_lib.ops import call_op

        params: dict[str, Any] = {
            "tmdbid": tmdb_id,
            "title": title,
            "q": title,
            "media_type": kind,
            "transfer": transfer,
        }
        # Bound total wall time roughly via subprocess-less call; CDP unlock may still take long.
        result = call_op("hdhive", "grab", params)
    except Exception as e:  # noqa: BLE001
        _stage("hdhive_failed", detail=str(e))
        return {"success": False, "error": "hdhive_exec_failed", "detail": str(e), "season": season, "episode": episode}

    ok = bool(isinstance(result, dict) and result.get("success"))
    share_url = (result or {}).get("share_url") if isinstance(result, dict) else None
    transfer_info = (result or {}).get("transfer") if isinstance(result, dict) else None
    _stage(
        "hdhive_done",
        success=ok,
        has_share=bool(share_url),
        transfer_ok=bool(isinstance(transfer_info, dict) and (transfer_info.get("code") == 0 or transfer_info.get("success") is True)),
    )
    return {
        "success": ok,
        "result": result,
        "share_url": share_url,
        "transfer": transfer_info,
        "source": "hdhive_115",
        "season": season,
        "episode": episode,
        "note": "HDHive grab unlocks 115 share and transfers via P115StrmHelper when possible; on failure watch continues to PT." if not ok else "HDHive grab succeeded",
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


def cmd_watch(args: argparse.Namespace) -> int:
    _STAGES.clear()
    media = identify_media(
        args.title,
        args.media_type,
        args.year,
        args.tmdbid,
        episode=args.episode,
    )
    tmdbid = media.get("tmdb_id") or media.get("tmdbid")
    report: dict[str, Any] = {
        "media": {
            "title": media.get("title"),
            "year": media.get("year"),
            "type": media.get("type"),
            "tmdb_id": tmdbid,
            "original_title": media.get("original_title") or media.get("original_name"),
            "category": media.get("category"),
        },
        "request": {
            "title": args.title,
            "season": args.season,
            "episode": args.episode,
            "prefer": args.prefer,
            "dry_run": args.dry_run,
        },
    }

    hdhive_result = None
    hdhive_timeout = float(getattr(args, "hdhive_timeout", 90) or 90)
    if args.prefer in {"hdhive", "auto"} and not args.skip_hdhive:
        hdhive_result = try_hdhive(media, args.season, args.episode, timeout=hdhive_timeout)
        report["hdhive"] = hdhive_result
        if args.hdhive_only:
            print_json(report)
            return 0 if hdhive_result and hdhive_result.get("success") else 1

        # Full HDHive success (unlock + transfer) can short-circuit PT path.
        if (
            hdhive_result
            and hdhive_result.get("success")
            and not args.force_pt
            and not args.dry_run
        ):
            report["success"] = True
            report["source"] = "hdhive_115"
            report["note"] = "HDHive unlock+transfer succeeded; skipped PT."
            try:
                report["status"] = status_snapshot(media, args.episode)
            except Exception:  # noqa: BLE001
                report["status"] = None
            print_json(report)
            return 0

        if hdhive_result and not hdhive_result.get("success"):
            report["note"] = (
                "HDHive failed ("
                + str((hdhive_result.get("result") or {}).get("error") or hdhive_result.get("error") or "unknown")
                + "); continuing PT."
            )

    _stage("clients_check")
    clients = ensure_clients()
    report["clients"] = clients
    _stage("clients_ok", count=len(clients) if isinstance(clients, list) else 0)

    items = search_pt_resources(media, args.season, args.episode, args.sites)
    report["search_count"] = len(items)
    if not items:
        report["success"] = False
        report["error"] = "no_resources"
        report["hint"] = "Resource may be too new / not indexed. Prefer run updates/subscribe; do not invent mp_api flags."
        if args.subscribe:
            report["subscribe"] = maybe_subscribe(media, args.season, args.dry_run)
        print_json(report)
        return 4

    _stage("pick_start", search_count=len(items))
    site_priority = [s.strip() for s in (args.site_priority or "").split(",") if s.strip()] or None
    media_year = media.get("year") or args.year
    max_age_days = getattr(args, "max_age_days", None)
    mtype_raw = str(media.get("type") or args.media_type or "")
    is_tv = mtype_raw in {"电视剧", "tv", "TV", "show", "series"} or args.episode is not None
    # TV default: prefer 4K SDR; if missing, fallback ranks highest seeded quality.
    # Movie default stays 1080p / any HDR unless user overrides.
    prefer_resolution = args.resolution or ("2160p" if is_tv else "1080p")
    hdr_mode = getattr(args, "hdr_mode", None) or ("sdr" if is_tv else "any")
    picked = pick_torrent(
        items,
        season=args.season,
        episode=args.episode,
        media_year=media_year,
        prefer_fresh=not bool(getattr(args, "ignore_freshness", False)),
        max_age_days=max_age_days,
        prefer_resolution=prefer_resolution,
        site_priority=site_priority,
        require_chinese=bool(getattr(args, "require_chinese", False)),
        hdr_mode=str(hdr_mode or "any"),
        top_n=args.top,
    )
    report["quality_policy"] = {
        "is_tv": bool(is_tv),
        "prefer_resolution": prefer_resolution,
        "hdr_mode": str(hdr_mode or "any"),
        "fallback": "best_seeded_resolution" if is_tv else "soft_rank",
    }
    report["candidates"] = [summarize_candidate(x) for x in picked.get("candidates") or []]
    report["pick_meta"] = {
        "media_year": media_year,
        "needs_confirm": bool(picked.get("needs_confirm")),
        "confirm_reasons": picked.get("confirm_reasons") or [],
        "year_match": picked.get("year_match"),
        "pubdate_age_days": picked.get("pubdate_age_days"),
        "max_age_days": max_age_days,
    }
    selected = picked.get("selected")
    _stage("pick_done", selected=bool(selected), candidates=len(report["candidates"]))
    if not selected:
        report["success"] = False
        report["error"] = "pick_failed"
        report["hint"] = "Search returned items but none matched season/episode/year filter. Resource may not be out yet."
        print_json(report)
        return 5

    if args.pick_index is not None:
        cands = picked.get("candidates") or []
        idx = args.pick_index
        if idx < 0 or idx >= len(cands):
            report["success"] = False
            report["error"] = "pick_index_out_of_range"
            print_json(report)
            return 5
        selected = cands[idx]

    report["selected"] = summarize_candidate(selected)
    force_confirm_risk = bool(picked.get("needs_confirm")) and not bool(getattr(args, "force", False))
    # When agent passes --yes/--auto but pick is risky (year/pubdate/low seeders), block unless --force.
    if force_confirm_risk and (args.yes or args.auto) and not args.dry_run:
        report["success"] = False
        report["error"] = "safety_confirmation_required"
        report["hint"] = (
            "Selected torrent looks risky (year/pubdate/seeders). "
            "Show candidates to user, then re-run with --force --yes, or --pick-index N --force --yes. "
            "If already downloaded wrong one: media_ctl run cancel."
        )
        print_json(report)
        return 6
    if not args.yes and not args.dry_run and not args.auto:
        report["success"] = False
        report["error"] = "confirmation_required"
        report["hint"] = "Re-run with --yes to download selected candidate, or --pick-index N --yes."
        print_json(report)
        return 6

    downloader = args.downloader
    if not downloader and clients:
        # Prefer QB if present
        names = [c.get("name") for c in clients if isinstance(c, dict)]
        downloader = "QB" if "QB" in names else names[0]

    dl = download_selected(
        media,
        selected,
        downloader=downloader,
        save_path=args.save_path,
        dry_run=args.dry_run,
    )
    report["download"] = dl

    if args.dry_run:
        report["success"] = True
        print_json(report)
        return 0

    if not dl.get("success"):
        report["success"] = False
        print_json(report)
        return 7

    if args.wait > 0:
        deadline = time.time() + args.wait
        last = None
        while time.time() < deadline:
            last = status_snapshot(media, args.episode)
            if last.get("state") in {"transferred", "downloading"}:
                if last.get("state") == "transferred":
                    break
            time.sleep(min(5, max(1, args.wait // 6 or 1)))
        report["status"] = last or status_snapshot(media, args.episode)
    else:
        report["status"] = status_snapshot(media, args.episode)

    if args.subscribe:
        report["subscribe"] = maybe_subscribe(media, args.season, dry_run=False) if not args.dry_run else maybe_subscribe(media, args.season, True)

    report["success"] = True
    print_json(report)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    media: dict[str, Any]
    if args.tmdbid:
        media = {"tmdb_id": args.tmdbid, "title": args.title}
    elif args.title:
        media = identify_media(args.title, args.media_type, args.year, None)
    else:
        raise SystemExit("status requires --title or --tmdbid")
    snap = status_snapshot(media, args.episode)
    clients = mp_api.request("GET", "/api/v1/download/clients") or []
    print_json(
        {
            "media": {
                "title": media.get("title") or args.title,
                "tmdb_id": media.get("tmdb_id") or media.get("tmdbid") or args.tmdbid,
            },
            **snap,
            "clients": clients,
            "note": "Empty active list means no running tasks, not missing downloaders.",
        }
    )
    return 0


def build_watch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="One-shot watch pipeline for media-mgmt")
    parser.add_argument("title", nargs="?", help="Title to watch")
    parser.add_argument("--tmdbid", type=int)
    parser.add_argument("--media-type", dest="media_type", help="movie/tv")
    parser.add_argument("--year")
    parser.add_argument("--season", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--prefer", choices=["auto", "pt", "hdhive"], default="auto", help="Resource preference")
    parser.add_argument("--skip-hdhive", action="store_true")
    parser.add_argument("--hdhive-only", action="store_true")
    parser.add_argument("--force-pt", action="store_true")
    parser.add_argument("--sites", help="comma-separated site ids")
    parser.add_argument(
        "--resolution",
        default=None,
        help="Preferred resolution (e.g. 2160p/1080p). Default: 2160p for TV, 1080p for movie",
    )
    parser.add_argument("--require-chinese", action="store_true", help="Prefer/require Chinese audio/subs signals in title")
    parser.add_argument(
        "--hdr-mode",
        choices=["any", "sdr", "hdr"],
        default=None,
        help="HDR preference. Default: sdr for TV, any for movie",
    )
    parser.add_argument("--site-priority", help="comma-separated preferred site names")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--pick-index", type=int, help="Choose candidate index from ranked list")
    parser.add_argument(
        "--max-age-days",
        type=float,
        default=None,
        help="Prefer/require torrent pubdate within N days; older candidates score stale and need --force",
    )
    parser.add_argument(
        "--ignore-freshness",
        action="store_true",
        help="Do not rank by torrent pubdate freshness",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass safety gate for year/pubdate/low-seeders (still requires --yes)",
    )
    parser.add_argument("--downloader", help="QB/TR/...")
    parser.add_argument("--save-path")
    parser.add_argument("--yes", action="store_true", help="Download without interactive confirmation")
    parser.add_argument("--auto", action="store_true", help="Alias of --yes for agent automation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--wait", type=int, default=0, help="Seconds to poll status after download")
    parser.add_argument("--subscribe", action="store_true", help="Suggest/create subscription when unfinished")
    parser.add_argument(
        "--hdhive-timeout",
        type=float,
        default=90,
        help="Seconds before HDHive subprocess is aborted (default 90); watch continues to PT",
    )
    return parser


def build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check download/transfer status")
    parser.add_argument("--title")
    parser.add_argument("--tmdbid", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--media-type", dest="media_type")
    parser.add_argument("--year")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "status":
        args = build_status_parser().parse_args(argv[1:])
        return cmd_status(args)
    parser = build_watch_parser()
    args = parser.parse_args(argv)
    if not args.title and not args.tmdbid:
        parser.error("title or --tmdbid is required")
    if not args.title:
        args.title = f"tmdb:{args.tmdbid}"
    return cmd_watch(args)


if __name__ == "__main__":
    raise SystemExit(main())
