"""Watch identify: NextFind first, then MoviePilot tmdb/recognize."""
from __future__ import annotations

import json
from typing import Any

import scripts.mp_api as mp_api
from media_mgmt_lib.watch_stages import STAGES as _STAGES, stage as _stage

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
    # NextFind identify first (CEO 2026-07-20); fall back to MP below
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if call_op("nextfind", "health", {}).get("success"):
            nf = call_op(
                "nextfind",
                "identify",
                {
                    "title": title,
                    "q": title,
                    "tmdbid": tmdbid,
                    "media_type": media_type,
                    "year": year,
                    "select": 1,
                },
            )
            sel = nf.get("selected") if isinstance(nf, dict) else None
            if nf.get("success") and isinstance(sel, dict) and (sel.get("tmdb_id") or sel.get("tmdbid")):
                tid = sel.get("tmdb_id") or sel.get("tmdbid")
                detail = _fetch_tmdb_detail(
                    int(tid),
                    title=title or sel.get("title"),
                    media_type=media_type or sel.get("type") or sel.get("media_type"),
                    year=year or sel.get("year"),
                    prefer_tv=prefer_tv,
                )
                if isinstance(detail, dict) and _media_shell_usable(detail):
                    _stage("identify_done", via="nextfind+tmdb_detail", tmdb_id=detail.get("tmdb_id") or tid)
                    return detail
                shell = {
                    "title": sel.get("title") or title,
                    "tmdb_id": int(tid) if str(tid).isdigit() else tid,
                    "year": sel.get("year") or year,
                    "type": sel.get("type") or sel.get("media_type") or media_type,
                    "media_type": sel.get("media_type") or sel.get("type") or media_type,
                }
                _stage("identify_done", via="nextfind", tmdb_id=shell.get("tmdb_id"))
                return shell
    except Exception as e:  # noqa: BLE001
        _stage("identify_nf_skip", detail=str(e)[:160])
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


