"""Torrent selection helpers for media-mgmt watch/download pipelines."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from media_mgmt_lib.quality_pref import (
    quality_score,
    matches_quality,
    blob_of,
    has_chinese,
    has_fx_subtitle,
    is_original_disc,
)


_EP_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})"),
    re.compile(r"[Ee][Pp]?(\d{1,3})\b"),
    re.compile(r"第\s*0*(\d{1,3})\s*[集话話]"),
    re.compile(r"\b0*(\d{1,3})\s*集"),
]


def _as_torrent_info(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    ti = item.get("torrent_info")
    if isinstance(ti, dict) and ti:
        return ti
    # Already a TorrentInfo-like object
    if "enclosure" in item or "site_name" in item:
        return item
    return {}


def _text_blob(item: dict[str, Any], ti: dict[str, Any]) -> str:
    parts = [
        ti.get("title"),
        ti.get("description"),
        item.get("title"),
        (item.get("meta_info") or {}).get("title") if isinstance(item.get("meta_info"), dict) else None,
        (item.get("meta_info") or {}).get("subtitle") if isinstance(item.get("meta_info"), dict) else None,
        (item.get("meta_info") or {}).get("org_string") if isinstance(item.get("meta_info"), dict) else None,
    ]
    return " ".join(str(p) for p in parts if p)


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_title_year(text: str) -> int | None:
    """Extract production/release year from torrent title-ish text."""
    if not text:
        return None
    candidates: list[int] = []
    for m in re.finditer(r"(?<![A-Za-z0-9])((?:19|20)\d{2})(?![A-Za-z0-9])", text):
        candidates.append(int(m.group(1)))
    if not candidates:
        return None
    # Prefer the last year token (often "... S01E06 2025 1080p ...")
    return candidates[-1]


def extract_pubdate(item: dict[str, Any], ti: dict[str, Any] | None = None) -> datetime | None:
    ti = ti if ti is not None else _as_torrent_info(item)
    for key in (
        "pubdate",
        "pub_date",
        "publish_date",
        "published_at",
        "date",
        "release_date",
        "time",
    ):
        dt = _parse_dt(ti.get(key))
        if dt is not None:
            return dt
        if isinstance(item, dict):
            dt = _parse_dt(item.get(key))
            if dt is not None:
                return dt
    return None


def pubdate_age_days(item: dict[str, Any], *, now: datetime | None = None) -> float | None:
    dt = extract_pubdate(item)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def year_match_score(item: dict[str, Any], media_year: int | str | None) -> int:
    """2 exact match, 1 unknown year, 0 mismatch, -1 no media year constraint."""
    if media_year in (None, ""):
        return -1
    try:
        want = int(str(media_year)[:4])
    except (TypeError, ValueError):
        return -1
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
    got = extract_title_year(blob)
    if got is None:
        for key in ("year", "release_year"):
            raw = ti.get(key) or (item.get(key) if isinstance(item, dict) else None)
            if raw not in (None, ""):
                try:
                    got = int(str(raw)[:4])
                    break
                except (TypeError, ValueError):
                    continue
    if got is None:
        return 1
    return 2 if got == want else 0


def freshness_score(
    item: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: float | None = None,
) -> int:
    """Higher is fresher. Unknown pubdate scores 0 so known-fresh wins.

    If max_age_days is set and age exceeds it, score becomes -1 (stale hard signal).
    """
    age = pubdate_age_days(item, now=now)
    if age is None:
        return 0
    if max_age_days is not None and age > float(max_age_days):
        return -1
    if age <= 1:
        return 5
    if age <= 3:
        return 4
    if age <= 7:
        return 3
    if age <= 14:
        return 2
    if age <= 30:
        return 1
    return 0


def extract_episode(text: str) -> int | None:
    if not text:
        return None
    m = _EP_PATTERNS[0].search(text)
    if m:
        return int(m.group(2))
    for pat in _EP_PATTERNS[1:]:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def extract_season(text: str) -> int | None:
    if not text:
        return None
    m = _EP_PATTERNS[0].search(text)
    if m:
        return int(m.group(1))
    m = re.search(r"[Ss]eason\s*(\d{1,2})", text)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*0*(\d{1,2})\s*季", text)
    if m:
        return int(m.group(1))
    return None


def matches_episode(
    item: dict[str, Any],
    *,
    season: int | None = None,
    episode: int | None = None,
) -> bool:
    if episode is None and season is None:
        return True
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
    meta = item.get("meta_info") if isinstance(item.get("meta_info"), dict) else {}
    ep = extract_episode(blob)
    se = extract_season(blob)
    if ep is None and meta:
        ep = meta.get("begin_episode") or meta.get("end_episode")
        try:
            ep = int(ep) if ep is not None else None
        except (TypeError, ValueError):
            ep = None
    if se is None and meta:
        se = meta.get("begin_season") or meta.get("end_season")
        try:
            se = int(se) if se is not None else None
        except (TypeError, ValueError):
            se = None
    if episode is not None and ep != episode:
        # Allow multi-episode packs that cover the target episode when explicit range is present
        if not _covers_episode(blob, episode):
            return False
    if season is not None and se is not None and se != season:
        return False
    return True


def _covers_episode(text: str, episode: int) -> bool:
    # E01-E05 / EP01-EP05 / 第1-5集
    m = re.search(r"[Ee][Pp]?0*(\d{1,3})\s*[-~～到至]\s*[Ee]?[Pp]?0*(\d{1,3})", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = (a, b) if a <= b else (b, a)
        return lo <= episode <= hi
    m = re.search(r"第\s*0*(\d{1,3})\s*[-~～到至]\s*0*(\d{1,3})\s*[集话話]", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        lo, hi = (a, b) if a <= b else (b, a)
        return lo <= episode <= hi
    return False


def score_torrent(
    item: dict[str, Any],
    *,
    season: int | None = None,
    episode: int | None = None,
    media_year: int | str | None = None,
    prefer_fresh: bool = True,
    max_age_days: float | None = None,
    now: datetime | None = None,
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    prefer_fx_sub: bool = False,
    exclude_disc: bool = False,
) -> tuple[int, ...]:
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
    title = str(ti.get("title") or "")
    full = blob_of(title, blob)
    seeders = int(ti.get("seeders") or 0)
    seeder_alive = 1 if seeders > 0 else 0
    dvf = ti.get("downloadvolumefactor")
    try:
        dvf_f = float(dvf) if dvf is not None else 1.0
    except (TypeError, ValueError):
        dvf_f = 1.0
    free = 1 if dvf_f == 0 else 0
    half = 1 if abs(dvf_f - 0.5) < 1e-9 else 0
    q = quality_score(
        full,
        resolution=prefer_resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
        prefer_fx_sub=prefer_fx_sub,
        exclude_disc=exclude_disc,
    )
    exact_ep = 0
    if episode is not None:
        if re.search(rf"[Ss]\d{{1,2}}[Ee]0*{episode}\b", title) or re.search(rf"[Ee]0*{episode}\b", title):
            exact_ep = 2
        elif matches_episode(item, season=season, episode=episode):
            exact_ep = 1
    site = str(ti.get("site_name") or "")
    site_score = 0
    if site_priority:
        for i, name in enumerate(site_priority):
            if name and name in site:
                site_score = max(site_score, len(site_priority) - i)
    has_enclosure = 1 if ti.get("enclosure") else 0
    hard = 1 if q.get("matches_hard") else 0
    res_rank = int(q.get("resolution_rank") or 0)
    fx_hit = 1 if q.get("fx_sub") else 0
    cn_hit = 1 if q.get("chinese") else 0
    non_disc = 0 if (exclude_disc and q.get("is_disc")) else 1
    ymatch = year_match_score(item, media_year)
    # normalize: -1 (no constraint) behaves as neutral 1 for ranking base
    y_rank = 1 if ymatch < 0 else ymatch
    fresh = freshness_score(item, now=now, max_age_days=max_age_days) if prefer_fresh else 0
    # higher tuple wins
    # TV: preferred quality (4K SDR) > seeded > res ladder
    # Movie: non-disc > fx-sub > chinese > res ladder among seeded
    return (
        y_rank,  # wrong year must lose hard
        non_disc,  # exclude 原盘/REMUX when requested
        hard,  # preferred quality hit (e.g. 4K SDR / fx-sub hard match)
        fx_hit if prefer_fx_sub else 0,
        cn_hit if require_chinese else 0,
        seeder_alive,  # must prefer seeded over zero-seed
        res_rank,  # absolute quality ladder when preferred missing
        exact_ep,
        has_enclosure,
        fresh,
        int(q.get("score") or 0),
        seeders,
        free,
        half,
        site_score,
    )


def _seeders_of(item: dict[str, Any]) -> int:
    ti = _as_torrent_info(item)
    try:
        return int(ti.get("seeders") or 0)
    except (TypeError, ValueError):
        return 0


def _blob_for(item: dict[str, Any]) -> str:
    ti = _as_torrent_info(item)
    return blob_of(ti.get("title"), _text_blob(item, ti))


def filter_and_rank(
    items: list[dict[str, Any]],
    *,
    season: int | None = None,
    episode: int | None = None,
    media_year: int | str | None = None,
    prefer_fresh: bool = True,
    max_age_days: float | None = None,
    now: datetime | None = None,
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    prefer_fx_sub: bool = False,
    exclude_disc: bool = False,
    hard_filter: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    filtered = [it for it in items if matches_episode(it, season=season, episode=episode)]
    pool = filtered if filtered else list(items)
    # Drop hard year mismatches when media_year known and any year-matching candidate exists.
    if media_year not in (None, ""):
        year_ok = [it for it in pool if year_match_score(it, media_year) != 0]
        year_exact = [it for it in year_ok if year_match_score(it, media_year) == 2]
        if year_exact:
            pool = year_exact
        elif year_ok:
            pool = year_ok

    # Movie default: drop 原盘/REMUX when any non-disc alternative exists.
    if exclude_disc:
        non_disc = [it for it in pool if not is_original_disc(_blob_for(it))]
        if non_disc:
            pool = non_disc

    # Prefer preferred quality when available; otherwise keep full pool and rank by
    # absolute resolution + seeders (see score_torrent). Never hard-fail to empty.
    want_quality = hard_filter and (
        prefer_resolution
        or require_chinese
        or prefer_fx_sub
        or (hdr_mode or "any") != "any"
    )
    if want_quality:
        quality_pool = []
        for it in pool:
            blob = _blob_for(it)
            ok = matches_quality(
                blob,
                resolution=prefer_resolution,
                require_chinese=require_chinese,
                hdr_mode=hdr_mode,
            )
            if prefer_fx_sub and not has_fx_subtitle(blob):
                ok = False
            if exclude_disc and is_original_disc(blob):
                ok = False
            if ok:
                quality_pool.append(it)

        # Movie tiered prefer: fx-sub+chinese → chinese → any non-disc seeded
        if prefer_fx_sub or require_chinese:
            fx_cn = [
                it
                for it in pool
                if _seeders_of(it) > 0
                and has_fx_subtitle(_blob_for(it))
                and has_chinese(_blob_for(it))
                and not (exclude_disc and is_original_disc(_blob_for(it)))
            ]
            cn_only = [
                it
                for it in pool
                if _seeders_of(it) > 0
                and has_chinese(_blob_for(it))
                and not (exclude_disc and is_original_disc(_blob_for(it)))
            ]
            if prefer_fx_sub and fx_cn:
                pool = fx_cn
            elif require_chinese and cn_only:
                pool = cn_only
            elif quality_pool:
                seeded_quality = [it for it in quality_pool if _seeders_of(it) > 0]
                pool = seeded_quality or quality_pool
            else:
                seeded = [it for it in pool if _seeders_of(it) > 0]
                if seeded:
                    pool = seeded
        else:
            seeded_quality = [it for it in quality_pool if _seeders_of(it) > 0]
            if seeded_quality:
                pool = seeded_quality
            elif quality_pool:
                pool = quality_pool
            else:
                seeded = [it for it in pool if _seeders_of(it) > 0]
                if seeded:
                    pool = seeded

    ranked = sorted(
        pool,
        key=lambda it: score_torrent(
            it,
            season=season,
            episode=episode,
            media_year=media_year,
            prefer_fresh=prefer_fresh,
            max_age_days=max_age_days,
            now=now,
            prefer_resolution=prefer_resolution,
            site_priority=site_priority,
            require_chinese=require_chinese,
            hdr_mode=hdr_mode,
            prefer_fx_sub=prefer_fx_sub,
            exclude_disc=exclude_disc,
        ),
        reverse=True,
    )
    return ranked[: max(1, limit)] if ranked else []


def pick_torrent(
    items: list[dict[str, Any]],
    *,
    season: int | None = None,
    episode: int | None = None,
    media_year: int | str | None = None,
    prefer_fresh: bool = True,
    max_age_days: float | None = None,
    now: datetime | None = None,
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    prefer_fx_sub: bool = False,
    exclude_disc: bool = False,
    hard_filter: bool = True,
    top_n: int = 3,
) -> dict[str, Any]:
    ranked = filter_and_rank(
        items,
        season=season,
        episode=episode,
        media_year=media_year,
        prefer_fresh=prefer_fresh,
        max_age_days=max_age_days,
        now=now,
        prefer_resolution=prefer_resolution,
        site_priority=site_priority,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
        prefer_fx_sub=prefer_fx_sub,
        exclude_disc=exclude_disc,
        hard_filter=hard_filter,
        limit=max(top_n, 1),
    )
    if not ranked:
        return {
            "selected": None,
            "candidates": [],
            "reason": "no_candidates",
            "needs_confirm": False,
            "confirm_reasons": [],
        }
    selected = ranked[0]
    # confidence: gap between top and second hard scores
    scores = [
        score_torrent(
            it,
            season=season,
            episode=episode,
            media_year=media_year,
            prefer_fresh=prefer_fresh,
            max_age_days=max_age_days,
            now=now,
            prefer_resolution=prefer_resolution,
            site_priority=site_priority,
            require_chinese=require_chinese,
            hdr_mode=hdr_mode,
            prefer_fx_sub=prefer_fx_sub,
            exclude_disc=exclude_disc,
        )
        for it in ranked[:2]
    ]
    needs_confirm = False
    confirm_reasons: list[str] = []
    # compare first ranking dimensions for close race
    if len(scores) >= 2 and scores[0][:7] == scores[1][:7]:
        needs_confirm = True
        confirm_reasons.append("close_top_scores")
    ti = _as_torrent_info(selected)
    q = quality_score(
        blob_of(ti.get("title"), _text_blob(selected, ti)),
        resolution=prefer_resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
        prefer_fx_sub=prefer_fx_sub,
        exclude_disc=exclude_disc,
    )
    if not q.get("matches_hard"):
        needs_confirm = True
        confirm_reasons.append("quality_soft_match")
    ymatch = year_match_score(selected, media_year)
    if ymatch == 0:
        needs_confirm = True
        confirm_reasons.append("year_mismatch")
    elif ymatch == 1 and media_year not in (None, ""):
        needs_confirm = True
        confirm_reasons.append("year_unknown")
    age = pubdate_age_days(selected, now=now)
    if age is None and media_year not in (None, ""):
        needs_confirm = True
        confirm_reasons.append("pubdate_unknown")
    elif age is not None and max_age_days is not None and age > float(max_age_days):
        needs_confirm = True
        confirm_reasons.append("pubdate_stale")
    elif age is not None and age > 30:
        # old seed even without hard max_age: confirm before auto download
        needs_confirm = True
        confirm_reasons.append("pubdate_old")
    seeders = int(ti.get("seeders") or 0)
    if seeders <= 1:
        needs_confirm = True
        confirm_reasons.append("low_seeders")
    return {
        "selected": selected,
        "candidates": ranked[:top_n],
        "reason": "ranked",
        "score": scores[0] if scores else None,
        "quality": q,
        "needs_confirm": needs_confirm,
        "confirm_reasons": confirm_reasons,
        "year_match": ymatch,
        "pubdate_age_days": age,
    }


def summarize_candidate(item: dict[str, Any]) -> dict[str, Any]:
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
    pub = extract_pubdate(item, ti)
    age = pubdate_age_days(item)
    return {
        "site_name": ti.get("site_name"),
        "title": ti.get("title"),
        "seeders": ti.get("seeders"),
        "size": ti.get("size"),
        "downloadvolumefactor": ti.get("downloadvolumefactor"),
        "enclosure": bool(ti.get("enclosure")),
        "episode": extract_episode(blob),
        "season": extract_season(blob),
        "page_url": ti.get("page_url"),
        "title_year": extract_title_year(blob),
        "pubdate": pub.strftime("%Y-%m-%d %H:%M:%S") if pub else (ti.get("pubdate") or None),
        "date_elapsed": ti.get("date_elapsed"),
        "pubdate_age_days": round(age, 2) if age is not None else None,
    }
