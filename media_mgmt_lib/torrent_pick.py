"""Torrent selection helpers for media-mgmt watch/download pipelines."""

from __future__ import annotations

import re
from typing import Any

from media_mgmt_lib.quality_pref import quality_score, matches_quality, blob_of


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
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
) -> tuple[int, ...]:
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
    blob_l = blob.lower()
    title = str(ti.get("title") or "")
    seeders = int(ti.get("seeders") or 0)
    dvf = ti.get("downloadvolumefactor")
    try:
        dvf_f = float(dvf) if dvf is not None else 1.0
    except (TypeError, ValueError):
        dvf_f = 1.0
    free = 1 if dvf_f == 0 else 0
    half = 1 if abs(dvf_f - 0.5) < 1e-9 else 0
    q = quality_score(
        blob_of(title, blob),
        resolution=prefer_resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
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
    # higher tuple wins
    return (
        hard,
        exact_ep,
        has_enclosure,
        int(q.get("score") or 0),
        seeders,
        free,
        half,
        site_score,
    )


def filter_and_rank(
    items: list[dict[str, Any]],
    *,
    season: int | None = None,
    episode: int | None = None,
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    hard_filter: bool = True,
    limit: int = 10,
) -> list[dict[str, Any]]:
    filtered = [it for it in items if matches_episode(it, season=season, episode=episode)]
    pool = filtered if filtered else list(items)
    if hard_filter and (prefer_resolution or require_chinese or (hdr_mode or "any") != "any"):
        quality_pool = []
        for it in pool:
            ti = _as_torrent_info(it)
            blob = _text_blob(it, ti)
            if matches_quality(
                blob_of(ti.get("title"), blob),
                resolution=prefer_resolution,
                require_chinese=require_chinese,
                hdr_mode=hdr_mode,
            ):
                quality_pool.append(it)
        if quality_pool:
            pool = quality_pool
    ranked = sorted(
        pool,
        key=lambda it: score_torrent(
            it,
            season=season,
            episode=episode,
            prefer_resolution=prefer_resolution,
            site_priority=site_priority,
            require_chinese=require_chinese,
            hdr_mode=hdr_mode,
        ),
        reverse=True,
    )
    return ranked[: max(1, limit)] if ranked else []


def pick_torrent(
    items: list[dict[str, Any]],
    *,
    season: int | None = None,
    episode: int | None = None,
    prefer_resolution: str = "1080p",
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    hard_filter: bool = True,
    top_n: int = 3,
) -> dict[str, Any]:
    ranked = filter_and_rank(
        items,
        season=season,
        episode=episode,
        prefer_resolution=prefer_resolution,
        site_priority=site_priority,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
        hard_filter=hard_filter,
        limit=max(top_n, 1),
    )
    if not ranked:
        return {"selected": None, "candidates": [], "reason": "no_candidates"}
    selected = ranked[0]
    # confidence: gap between top and second hard scores
    scores = [
        score_torrent(
            it,
            season=season,
            episode=episode,
            prefer_resolution=prefer_resolution,
            site_priority=site_priority,
            require_chinese=require_chinese,
            hdr_mode=hdr_mode,
        )
        for it in ranked[:2]
    ]
    needs_confirm = False
    if len(scores) >= 2 and scores[0][:4] == scores[1][:4]:
        needs_confirm = True
    ti = _as_torrent_info(selected)
    q = quality_score(
        blob_of(ti.get("title"), _text_blob(selected, ti)),
        resolution=prefer_resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
    )
    if not q.get("matches_hard"):
        needs_confirm = True
    return {
        "selected": selected,
        "candidates": ranked[:top_n],
        "reason": "ranked",
        "score": scores[0] if scores else None,
        "quality": q,
        "needs_confirm": needs_confirm,
    }


def summarize_candidate(item: dict[str, Any]) -> dict[str, Any]:
    ti = _as_torrent_info(item)
    blob = _text_blob(item, ti)
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
    }
