"""Search workflow: default NextFind once (netdisk + any PT rows); MP only on empty/force."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from media_mgmt_lib.nf_evidence import classify_resources, consistency_report, extract_list, tag_path
from media_mgmt_lib.ops._runner import run_mp_api
from media_mgmt_lib.torrent_pick import matches_episode, summarize_candidate
from media_mgmt_lib.workflows._util import fail, mp, ok


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes"}


def _extract_items(search: Any) -> list[dict[str, Any]]:
    return extract_list(search)


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
    return dict(sorted(counts.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 9999))


def _tag_path(it: dict[str, Any]) -> str:
    return tag_path(it)


def _nf_search_bundle(
    *,
    title: Any,
    tmdbid: Any,
    media_type: Any,
    year: Any,
    season: Any,
    episode: Any,
    qpref: dict[str, Any],
) -> dict[str, Any]:
    import media_mgmt_lib.ops.nextfind  # noqa: F401
    from media_mgmt_lib.ops import call_op

    out: dict[str, Any] = {"path": "nextfind_openapi", "identify": None, "resources": None}
    if not call_op("nextfind", "health", {}).get("success"):
        return {"success": False, "error": "nextfind_not_configured", **out}

    tid = tmdbid
    media = None
    if not tid:
        idr = call_op(
            "nextfind",
            "identify",
            {
                "title": title,
                "q": title,
                "media_type": media_type,
                "year": year,
                "select": 1,
            },
        )
        out["identify"] = {
            "success": idr.get("success"),
            "selected": idr.get("selected"),
            "count": idr.get("count") or idr.get("candidate_count"),
        }
        if idr.get("success"):
            media = idr.get("selected")
            tid = (media or {}).get("tmdb_id")
            media_type = (media or {}).get("type") or (media or {}).get("media_type") or media_type
    else:
        # still run identify-like search for candidates display
        sr = call_op("nextfind", "search", {"q": title or tid, "media_type": media_type})
        out["search"] = {"success": sr.get("success"), "count": sr.get("count"), "selected": sr.get("selected")}
        media = sr.get("selected")

    resources = []
    if tid:
        rr = call_op(
            "nextfind",
            "resources",
            {
                "tmdbid": tid,
                "media_type": media_type or "movie",
                "season": season,
                "episode": episode,
                **{k: qpref.get(k) for k in ("resolution", "require_chinese", "hdr_mode") if qpref.get(k) is not None},
            },
        )
        resources = _extract_items(rr)
        out["resources"] = {
            "success": rr.get("success"),
            "count": len(resources),
            "error": rr.get("error"),
            "best": rr.get("best"),
        }

    # Also harvest any list embedded in identify/search payloads as "search hints"
    search_hint_items: list[dict[str, Any]] = []
    for blob in (out.get("identify"), out.get("search")):
        if isinstance(blob, dict):
            # selected only — hints come from raw candidates if present
            pass
    # classify resources (authoritative for grab)
    classified = classify_resources(resources)
    tagged = classified["items"]
    search_hint_count = out.get("search", {}).get("count") if isinstance(out.get("search"), dict) else None
    if search_hint_count is None and isinstance(out.get("identify"), dict):
        search_hint_count = out["identify"].get("count")
    try:
        search_hint_count = int(search_hint_count) if search_hint_count is not None else None
    except (TypeError, ValueError):
        search_hint_count = None

    media_in_lib = None
    if isinstance(media, dict):
        from media_mgmt_lib.nf_evidence import parse_in_library

        media_in_lib = parse_in_library(None, media)

    cons = consistency_report(
        search_hint_count=search_hint_count,
        resources_count=len(resources),
        identify_in_library=media_in_lib,
        library_info_in_library=None,
    )

    out.update(
        {
            "success": bool(tid) and (bool(resources) or bool(out.get("identify", {}).get("success")) or search_hint_count),
            "tmdb_id": tid,
            "media": media,
            "media_type": media_type,
            "items": tagged,
            "netdisk_count": classified["netdisk_count"],
            "pt_count": classified["pt_count"],
            "consistency": cons,
            "resource_authority": "resources_op",
        }
    )
    if tid and not resources:
        out["success"] = True  # identified but no resources still a valid NF answer
        out["error"] = "no_resources"
        if cons.get("warnings"):
            out["error"] = "no_resources"
            out["warnings"] = cons["warnings"]
    elif cons.get("warnings"):
        out["warnings"] = cons["warnings"]
    return out


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    season = params.get("season")
    episode = params.get("episode")
    force_mp = _truthy(params.get("force_mp_search") or params.get("force_mp") or params.get("prefer_mp"))
    prefer = str(params.get("prefer") or "auto").lower()

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

    qpref = {
        "resolution": params.get("resolution"),
        "require_chinese": params.get("require_chinese") or params.get("chinese"),
        "hdr_mode": params.get("hdr_mode"),
    }

    nf_bundle = None
    if not force_mp and prefer not in {"mp", "moviepilot", "pt_only_mp"}:
        try:
            nf_bundle = _nf_search_bundle(
                title=title,
                tmdbid=tmdbid,
                media_type=params.get("media_type"),
                year=params.get("year"),
                season=season,
                episode=episode,
                qpref=qpref,
            )
        except Exception as e:  # noqa: BLE001
            nf_bundle = {"success": False, "error": str(e), "path": "nextfind_openapi"}

    # Default: return NF results without MP re-search
    if nf_bundle and nf_bundle.get("success") and not force_mp:
        items = nf_bundle.get("items") or []
        sample = []
        for it in items[:8]:
            sample.append(
                {
                    "path": it.get("_path"),
                    "title": it.get("title") or it.get("name"),
                    "slug": it.get("slug"),
                    "source_type": it.get("source_type"),
                    "channel_name": it.get("channel_name"),
                    "share_size": it.get("share_size"),
                    "video_resolution": it.get("video_resolution"),
                    "subtitle_language": it.get("subtitle_language"),
                }
            )
        resolved_title = title or (nf_bundle.get("media") or {}).get("title")
        resolved_tmdb = nf_bundle.get("tmdb_id") or tmdbid
        summary = (
            f"search(NF) '{resolved_title or resolved_tmdb}': "
            f"{len(items)} resources (netdisk={nf_bundle.get('netdisk_count')} pt={nf_bundle.get('pt_count')})"
        )
        if nf_bundle.get("error") == "no_resources":
            summary += "；NF 无资源（未二搜 MP；要 MP 请 force_mp_search=true）"
        warns = nf_bundle.get("warnings") or (nf_bundle.get("consistency") or {}).get("warnings") or []
        if warns:
            summary += f"；warnings={warns}"
        return ok(
            {
                "workflow": "search",
                "source": "nextfind_openapi",
                "path": "nextfind_openapi",
                "media": nf_bundle.get("media"),
                "query": {
                    "title": resolved_title,
                    "tmdbid": resolved_tmdb,
                    "season": season,
                    "episode": episode,
                    "media_type": nf_bundle.get("media_type") or params.get("media_type"),
                },
                "result_count": len(items),
                "netdisk_count": nf_bundle.get("netdisk_count"),
                "pt_count": nf_bundle.get("pt_count"),
                "sample": sample,
                "consistency": nf_bundle.get("consistency"),
                "warnings": warns or None,
                "resource_authority": nf_bundle.get("resource_authority") or "resources_op",
                "nextfind": {
                    "identify": nf_bundle.get("identify"),
                    "resources": nf_bundle.get("resources"),
                    "search": nf_bundle.get("search"),
                },
                "summary": summary,
                "success": True,
                "hint": (
                    "NF 一次搜索完成。可转存资源以 resources 为准（resource_authority=resources_op）。"
                    "若 warnings 含 nf_search_hint_but_resources_empty：界面提示有货但 resources 空，勿盲 grab。"
                    "PT 若结果内无 pt 行需 force_mp_search=true 才 MP 搜站；禁止默认 MP 重搜。"
                ),
            }
        )

    # MP path: force, or NF failed/empty of everything including identify
    identified = mp(
        "identify",
        title=title,
        tmdbid=tmdbid or (nf_bundle or {}).get("tmdb_id"),
        media_type=params.get("media_type"),
        year=params.get("year"),
    )
    media = identified.get("selected") if isinstance(identified, dict) else None
    resolved_title = title or (media or {}).get("title")
    resolved_tmdb = tmdbid or (media or {}).get("tmdb_id") or (media or {}).get("tmdbid") or (nf_bundle or {}).get("tmdb_id")
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

    items = _extract_items(search)
    if not items and resolved_title:
        fallback = mp("search", title=resolved_title, sites=params.get("sites"), timeout=params.get("timeout") or 180)
        fb_items = _extract_items(fallback)
        if fb_items:
            search = fallback
            items = fb_items

    filtered = items
    if episode is not None or season is not None:
        filtered = [it for it in items if matches_episode(it, season=season, episode=episode)]

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
        picked = {
            "success": True,
            "selected": None,
            "candidates": [],
            "note": "no_episode_match",
            "episode_counts": _episode_counts(items, season=season),
        }

    sample = []
    for it in (filtered or items)[:5]:
        try:
            sample.append(summarize_candidate(it))
        except Exception:  # noqa: BLE001
            ti = it.get("torrent_info") if isinstance(it.get("torrent_info"), dict) else it
            sample.append(
                {
                    "path": "pt",
                    "title": (ti or {}).get("title") or it.get("title"),
                    "site": (ti or {}).get("site_name"),
                    "seeders": (ti or {}).get("seeders"),
                }
            )

    count_all = len(items)
    count_ep = len(filtered) if (episode is not None or season is not None) else count_all
    ep_counts = _episode_counts(items, season=season) if items else {}
    summary_bits = [f"search(MP) '{resolved_title or resolved_tmdb}': {count_all} candidates"]
    if episode is not None:
        summary_bits.append(f"E{int(episode):02d} hits={count_ep}")
    reason = "force_mp_search" if force_mp else "nf_unavailable_or_failed"
    summary_bits.append(f"reason={reason}")

    search_ok = not (isinstance(search, dict) and search.get("success") is False and not items)

    return ok(
        {
            "workflow": "search",
            "source": "moviepilot",
            "path": "pt",
            "media": media,
            "nextfind_prior": {
                "success": (nf_bundle or {}).get("success"),
                "error": (nf_bundle or {}).get("error"),
                "netdisk_count": (nf_bundle or {}).get("netdisk_count"),
                "pt_count": (nf_bundle or {}).get("pt_count"),
            }
            if nf_bundle
            else None,
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
            },
            "pick": picked,
            "summary": "; ".join(summary_bits),
            "success": search_ok,
            "hint": "MP search used as exception path (force or NF failed). Default is NF-only.",
        }
    )
