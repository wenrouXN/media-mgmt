from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from media_mgmt_lib.ops._runner import run_mp_api
from media_mgmt_lib.torrent_pick import matches_episode, pick_torrent, summarize_candidate
from media_mgmt_lib.workflows._util import fail, mp, ok


def _extract_items(search: Any) -> list[dict[str, Any]]:
    """Normalize MoviePilot / mp_api search payloads into a list of result dicts."""
    if isinstance(search, list):
        return [x for x in search if isinstance(x, dict)]
    if not isinstance(search, dict):
        return []

    for key in ("data", "results", "items"):
        val = search.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            for nested in ("list", "data", "results", "items", "torrents"):
                maybe = val.get(nested)
                if isinstance(maybe, list):
                    return [x for x in maybe if isinstance(x, dict)]
    # Some wrappers put the raw list under raw/parsed already handled by runner
    raw = search.get("raw")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _episode_counts(items: list[dict[str, Any]], season: int | None = None) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for it in items:
        mi = it.get("meta_info") if isinstance(it.get("meta_info"), dict) else {}
        be = mi.get("begin_episode")
        el = mi.get("episode_list") if isinstance(mi.get("episode_list"), list) else []
        if be is not None:
            counts[str(be)] += 1
        elif el:
            for e in el:
                counts[str(e)] += 1
        else:
            # fall back to matches_episode probe for known small range is expensive;
            # leave as unknown bucket only when nothing parseable
            pass
    return dict(sorted(counts.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 9999))


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid")
    season = params.get("season")
    episode = params.get("episode")
    if season is not None:
        try:
            season = int(season)
        except (TypeError, ValueError):
            return fail("invalid_param", field="season", value=season)
    if episode is not None:
        try:
            episode = int(episode)
        except (TypeError, ValueError):
            return fail("invalid_param", field="episode", value=episode)

    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    identified = mp(
        "identify",
        title=title,
        tmdbid=tmdbid,
        media_type=params.get("media_type"),
        year=params.get("year"),
    )
    media = identified.get("selected") if isinstance(identified, dict) else None
    resolved_title = title or (media or {}).get("title")
    resolved_tmdb = tmdbid or (media or {}).get("tmdb_id") or (media or {}).get("tmdbid")
    media_type = params.get("media_type") or (media or {}).get("type")
    year = params.get("year") or (media or {}).get("year")

    search = mp(
        "search",
        title=resolved_title,
        tmdbid=resolved_tmdb,
        media_type=media_type,
        year=year,
        season=season,
        sites=params.get("sites"),
        timeout=params.get("timeout") or 180,
    )

    # If media-id search failed hard, fall back to title keyword search once
    items = _extract_items(search)
    if not items and resolved_title:
        fallback = mp("search", title=resolved_title, sites=params.get("sites"), timeout=params.get("timeout") or 180)
        fb_items = _extract_items(fallback)
        if fb_items:
            search = fallback
            items = fb_items

    filtered = items
    if episode is not None or season is not None:
        filtered = [
            it
            for it in items
            if matches_episode(it, season=season, episode=episode)
        ]

    picked = None
    if filtered:
        p = Path("/tmp/media-mgmt-search-results.json")
        p.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
        args = ["pick", "--results-json", str(p)]
        if episode is not None:
            args += ["--episode", str(episode)]
        if season is not None:
            args += ["--season", str(season)]
        if params.get("resolution"):
            args += ["--resolution", str(params["resolution"])]
        if params.get("site_priority"):
            args += ["--site-priority", str(params["site_priority"])]
        if params.get("top") is not None:
            args += ["--top", str(params["top"])]
        picked = run_mp_api(args, timeout=60)
    elif items:
        # still report pick over full set when no ep filter match
        try:
            picked = {
                "success": True,
                "selected": None,
                "candidates": [],
                "note": "no_episode_match",
                "episode_counts": _episode_counts(items, season=season),
            }
        except Exception:  # noqa: BLE001
            picked = {"success": True, "selected": None, "candidates": [], "note": "no_episode_match"}

    # Compact sample for agent readability
    sample = []
    for it in (filtered or items)[:5]:
        try:
            sample.append(summarize_candidate(it))
        except Exception:  # noqa: BLE001
            ti = it.get("torrent_info") if isinstance(it.get("torrent_info"), dict) else it
            sample.append(
                {
                    "title": (ti or {}).get("title") or it.get("title"),
                    "site": (ti or {}).get("site_name"),
                    "seeders": (ti or {}).get("seeders"),
                }
            )

    count_all = len(items)
    count_ep = len(filtered) if (episode is not None or season is not None) else count_all
    ep_counts = _episode_counts(items, season=season) if items else {}

    summary_bits = [f"search '{resolved_title or resolved_tmdb}': {count_all} candidates"]
    if episode is not None:
        summary_bits.append(f"E{int(episode):02d} hits={count_ep}")
    elif season is not None:
        summary_bits.append(f"S{int(season):02d} hits={count_ep}")
    if ep_counts:
        summary_bits.append(f"ep_dist={ep_counts}")

    search_ok = not (
        isinstance(search, dict)
        and search.get("success") is False
        and not items
    )

    return ok(
        {
            "workflow": "search",
            "media": media,
            "query": {
                "title": resolved_title,
                "tmdbid": resolved_tmdb,
                "season": season,
                "episode": episode,
                "media_type": media_type,
                "year": year,
            },
            "result_count": count_all,
            "episode_match_count": count_ep if (episode is not None or season is not None) else None,
            "episode_counts": ep_counts or None,
            "sample": sample,
            "search": search
            if count_all <= 3
            else {
                "success": search_ok,
                "result_count": count_all,
                "truncated": True,
                "error": search.get("error") if isinstance(search, dict) else None,
                "detail": (search.get("detail") if isinstance(search, dict) else None),
            },
            "pick": picked,
            "summary": "; ".join(summary_bits),
            "success": search_ok,
            "hint": None
            if count_ep
            else (
                "No matching episode resources yet — likely not released/indexed. Prefer updates/subscribe over hand-rolled mp_api."
                if episode is not None
                else "No torrent candidates. Check title/tmdbid or try later."
            ),
        }
    )
