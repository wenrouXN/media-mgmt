"""Fixed workflow: resolve title → TMDB media before any resource search."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, mp, ok


def _compact(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    tmdb_id = item.get("tmdb_id") or item.get("tmdbid")
    return {
        "title": item.get("title") or item.get("name"),
        "original_title": item.get("original_title") or item.get("original_name"),
        "year": item.get("year") or (str(item.get("release_date") or item.get("first_air_date") or "")[:4] or None),
        "type": item.get("type") or item.get("media_type"),
        "tmdb_id": int(tmdb_id) if tmdb_id not in (None, "") else None,
        "title_year": item.get("title_year"),
        "overview": (item.get("overview") or "")[:160] or None,
        "poster_path": item.get("poster_path"),
        "detail_link": item.get("detail_link")
        or (f"https://www.themoviedb.org/tv/{tmdb_id}" if tmdb_id and "剧" in str(item.get("type") or "") else None)
        or (f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else None),
        "origin_country": item.get("origin_country"),
        "vote_average": item.get("vote_average"),
    }


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Identify media and stop for confirmation unless continue_to is set.

    params:
      title / q: free text
      tmdbid: skip search, force detail
      media_type, year
      select: 1-based index into results (default 1 / selected)
      continue_to: optional "search" | "watch" | "library" | "updates" | "subscribe"
      episode/season/...: forwarded when continue_to=watch
    """
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    identified = mp(
        "identify",
        title=title,
        tmdbid=tmdbid,
        media_type=params.get("media_type") or params.get("mtype"),
        year=params.get("year"),
    )
    if not isinstance(identified, dict):
        return fail("identify_failed", detail=identified)

    results_raw = identified.get("results") or []
    if not isinstance(results_raw, list):
        results_raw = []
    selected_raw = identified.get("selected") if isinstance(identified.get("selected"), dict) else None

    # optional override selection by index
    select = params.get("select")
    if select not in (None, ""):
        try:
            idx = int(select) - 1
        except (TypeError, ValueError):
            return fail("bad_param", need="select=1-based integer")
        if idx < 0 or idx >= len(results_raw):
            return fail("select_out_of_range", count=len(results_raw), select=select)
        selected_raw = results_raw[idx]

    candidates = [_compact(x) for x in results_raw if isinstance(x, dict)]
    candidates = [c for c in candidates if c]
    selected = _compact(selected_raw)

    if not selected or not selected.get("tmdb_id"):
        # try first candidate
        if candidates and candidates[0].get("tmdb_id"):
            selected = candidates[0]
        else:
            return fail(
                "identify_no_tmdb",
                query={"title": title, "tmdbid": tmdbid},
                candidates=candidates,
                raw_source=identified.get("source"),
                summary=f"无法为「{title or tmdbid}」确定 tmdb_id",
            )

    # confidence heuristic
    conf = "high"
    needs_confirm = False
    if len(candidates) > 1:
        conf = "medium"
        needs_confirm = True
        # if top two titles differ a lot from query, still medium
    if tmdbid:
        conf = "high"
        needs_confirm = False
    if select not in (None, ""):
        needs_confirm = False
        conf = "high"

    next_steps = {
        "confirm": "若候选不对：run identify --param title=... --param select=N",
        "search": f"run search --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
        "watch": f"run watch --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')} --param episode=N",
        "library": f"run library --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
        "updates": f"run updates --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
    }

    out = ok(
        {
            "workflow": "identify",
            "query": {
                "title": title,
                "tmdbid": tmdbid,
                "media_type": params.get("media_type") or params.get("mtype"),
                "year": params.get("year"),
                "select": select,
            },
            "selected": selected,
            "tmdb_id": selected.get("tmdb_id"),
            "candidates": candidates,
            "candidate_count": len(candidates),
            "confidence": conf,
            "needs_confirm": needs_confirm,
            "source": identified.get("source"),
            "next": next_steps,
            "summary": (
                f"识别为《{selected.get('title')}》({selected.get('year')}) "
                f"tmdb_id={selected.get('tmdb_id')} type={selected.get('type')}"
                + (f"；另有 {len(candidates)-1} 个候选待确认" if needs_confirm else "")
            ),
        }
    )

    continue_to = str(params.get("continue_to") or params.get("then") or "").strip().lower()
    if not continue_to:
        return out
    if needs_confirm and str(params.get("force") or "").lower() not in {"1", "true", "yes"}:
        out["continued"] = None
        out["continue_blocked"] = True
        out["summary"] += "；多候选未确认，未继续（force=true 可强制）"
        return out

    # chain
    from media_mgmt_lib.workflows import (
        library as w_library,
        search as w_search,
        subscribe as w_subscribe,
        updates as w_updates,
        watch as w_watch,
    )

    chain_params = {
        **params,
        "title": selected.get("title") or title,
        "tmdbid": selected.get("tmdb_id"),
        "media_type": selected.get("type") or params.get("media_type"),
    }
    runners = {
        "search": w_search.run,
        "watch": w_watch.run,
        "library": w_library.run,
        "updates": w_updates.run,
        "subscribe": w_subscribe.run,
    }
    fn = runners.get(continue_to)
    if not fn:
        out["continue_error"] = f"unknown continue_to={continue_to}"
        return out
    chained = fn(chain_params)
    out["continued"] = continue_to
    out["continue_result"] = chained
    out["success"] = bool(chained.get("success")) if isinstance(chained, dict) else out["success"]
    if isinstance(chained, dict) and chained.get("summary"):
        out["summary"] += f" → {continue_to}: {chained.get('summary')}"
    return out
