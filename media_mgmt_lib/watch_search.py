"""PT resource search with early-exit."""
from __future__ import annotations

import urllib.parse
from typing import Any

import scripts.mp_api as mp_api
from media_mgmt_lib.watch_identify import _title_variants, _episode_keywords
from media_mgmt_lib.watch_stages import stage as _stage

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


