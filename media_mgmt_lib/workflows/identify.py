"""Fixed workflow: resolve title → TMDB media before any resource search.

Primary: NextFind OpenAPI identify (search). Fallback: MoviePilot identify.
"""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, mp, ok


def _compact(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    tmdb_id = item.get("tmdb_id") or item.get("tmdbid") or item.get("id")
    mtype = item.get("type") or item.get("media_type") or item.get("raw_type")
    year = item.get("year") or (
        str(item.get("release_date") or item.get("first_air_date") or "")[:4] or None
    )
    poster = item.get("poster_path") or item.get("poster")
    return {
        "title": item.get("title") or item.get("name"),
        "original_title": item.get("original_title") or item.get("original_name"),
        "year": year,
        "type": mtype,
        "tmdb_id": int(tmdb_id) if tmdb_id not in (None, "") and str(tmdb_id).isdigit() else tmdb_id,
        "title_year": item.get("title_year"),
        "overview": (item.get("overview") or "")[:160] or None,
        "poster_path": poster,
        "detail_link": item.get("detail_link")
        or (
            f"https://www.themoviedb.org/tv/{tmdb_id}"
            if tmdb_id and any(x in str(mtype or "").lower() for x in ("tv", "剧", "series", "anime"))
            else None
        )
        or (f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else None),
        "origin_country": item.get("origin_country"),
        "vote_average": item.get("vote_average") or item.get("rating"),
        "is_in_library": item.get("is_in_library"),
        "local_episodes": item.get("local_episodes"),
    }


def _force_mp(params: dict[str, Any]) -> bool:
    return str(params.get("force_mp") or params.get("prefer_mp") or params.get("legacy_mp") or "").lower() in {
        "1",
        "true",
        "yes",
    }


def _nextfind_identify(params: dict[str, Any]) -> dict[str, Any] | None:
    """Return NextFind identify result or None if unavailable / soft-fail to MP."""
    if _force_mp(params):
        return None
    try:
        import media_mgmt_lib.ops.bootstrap  # noqa: F401
        from media_mgmt_lib.ops import call_op

        health = call_op("nextfind", "health", {})
        if not health.get("success"):
            return None
        result = call_op(
            "nextfind",
            "identify",
            {
                "title": params.get("title") or params.get("q"),
                "q": params.get("q") or params.get("title"),
                "tmdbid": params.get("tmdbid") or params.get("tmdb_id"),
                "media_type": params.get("media_type") or params.get("mtype") or params.get("kind"),
                "year": params.get("year"),
                "select": params.get("select"),
            },
        )
        if not isinstance(result, dict):
            return None
        if result.get("error") == "nextfind_not_configured":
            return None
        return result
    except Exception:  # noqa: BLE001
        return None


def _mp_identify(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    identified = mp(
        "identify",
        title=title,
        tmdbid=tmdbid,
        media_type=params.get("media_type") or params.get("mtype"),
        year=params.get("year"),
    )
    if not isinstance(identified, dict):
        return {"success": False, "error": "identify_failed", "detail": identified, "path": "moviepilot"}

    results_raw = identified.get("results") or []
    if not isinstance(results_raw, list):
        results_raw = []
    selected_raw = identified.get("selected") if isinstance(identified.get("selected"), dict) else None

    select = params.get("select")
    if select not in (None, ""):
        try:
            idx = int(select) - 1
        except (TypeError, ValueError):
            return {"success": False, "error": "bad_param", "need": "select=1-based integer", "path": "moviepilot"}
        if idx < 0 or idx >= len(results_raw):
            return {
                "success": False,
                "error": "select_out_of_range",
                "count": len(results_raw),
                "select": select,
                "path": "moviepilot",
            }
        selected_raw = results_raw[idx]

    candidates = [_compact(x) for x in results_raw if isinstance(x, dict)]
    candidates = [c for c in candidates if c]
    selected = _compact(selected_raw)
    if (not selected or not selected.get("tmdb_id")) and candidates and candidates[0].get("tmdb_id"):
        selected = candidates[0]

    conf = "high"
    needs_confirm = False
    if len(candidates) > 1 and select in (None, "") and not tmdbid:
        conf = "medium"
        needs_confirm = True
    if tmdbid or select not in (None, ""):
        conf = "high"
        needs_confirm = False

    ok_flag = bool(selected and selected.get("tmdb_id"))
    return {
        "success": ok_flag,
        "path": "moviepilot",
        "source": identified.get("source") or "moviepilot",
        "selected": selected,
        "tmdb_id": (selected or {}).get("tmdb_id") if selected else None,
        "candidates": candidates,
        "candidate_count": len(candidates),
        "confidence": conf,
        "needs_confirm": needs_confirm,
        "error": None if ok_flag else "identify_no_tmdb",
        "raw_source": identified.get("source"),
    }


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Identify media and stop for confirmation unless continue_to is set.

    params:
      title / q: free text
      tmdbid: skip search, force detail
      media_type, year
      select: 1-based index into results (default 1 / selected)
      force_mp=true: skip NextFind, use MoviePilot only
      continue_to: optional "search" | "watch" | "library" | "updates" | "subscribe" | "nextfind"
      episode/season/...: forwarded when continue_to=watch
    """
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    path = "nextfind_openapi"
    identified = _nextfind_identify(params)
    if identified is None or (
        not identified.get("success")
        and identified.get("error") in {"nextfind_not_configured", "identify_no_tmdb", "no_search_results"}
        and not _force_mp(params)
    ):
        # NextFind miss / down → MoviePilot fallback (unless force_mp already used)
        if identified is not None and identified.get("success"):
            pass
        else:
            mp_result = _mp_identify(params)
            # Prefer NextFind success only; if NF returned hard failure with candidates empty, still try MP
            if identified is None or not identified.get("success"):
                identified = mp_result
                path = "moviepilot"
            elif not identified.get("success") and mp_result.get("success"):
                identified = mp_result
                path = "moviepilot"

    if not isinstance(identified, dict):
        return fail("identify_failed", detail=identified)

    if not identified.get("success") and identified.get("error") in {
        "identify_no_tmdb",
        "select_out_of_range",
        "bad_param",
        "missing_param",
    }:
        return fail(
            identified.get("error") or "identify_failed",
            query={"title": title, "tmdbid": tmdbid},
            candidates=identified.get("candidates") or [],
            path=identified.get("path") or path,
            summary=f"无法为「{title or tmdbid}」确定 tmdb_id",
        )

    # Normalize shapes from either path
    if identified.get("path") == "nextfind_openapi" or identified.get("source") == "nextfind_openapi":
        path = "nextfind_openapi"
        candidates_raw = identified.get("candidates") or []
        candidates = [_compact(x) for x in candidates_raw if isinstance(x, dict)]
        candidates = [c for c in candidates if c]
        selected = _compact(identified.get("selected")) if identified.get("selected") else None
        if (not selected or not selected.get("tmdb_id")) and candidates:
            selected = candidates[0]
        conf = identified.get("confidence") or "high"
        needs_confirm = bool(identified.get("needs_confirm"))
        source = "nextfind_openapi"
    else:
        path = identified.get("path") or "moviepilot"
        candidates = [c for c in (identified.get("candidates") or []) if isinstance(c, dict)]
        selected = identified.get("selected") if isinstance(identified.get("selected"), dict) else None
        conf = identified.get("confidence") or "high"
        needs_confirm = bool(identified.get("needs_confirm"))
        source = identified.get("source") or "moviepilot"

    if not selected or not selected.get("tmdb_id"):
        return fail(
            "identify_no_tmdb",
            query={"title": title, "tmdbid": tmdbid},
            candidates=candidates,
            path=path,
            summary=f"无法为「{title or tmdbid}」确定 tmdb_id",
        )

    # Re-apply select confidence rules for uniform output
    select = params.get("select")
    if tmdbid or select not in (None, ""):
        conf = "high"
        needs_confirm = False
    elif len(candidates) > 1:
        conf = "medium"
        needs_confirm = True

    next_steps = {
        "confirm": "若候选不对：run identify --param title=... --param select=N",
        "search": f"run search --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
        "watch": f"run watch --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')} --param episode=N",
        "library": f"run library --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
        "updates": f"run updates --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')}",
        "nextfind": f"run nextfind --param tmdbid={selected['tmdb_id']} --param title={selected.get('title')} --param dry_run=true",
    }

    out = ok(
        {
            "workflow": "identify",
            "path": path,
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
            "source": source,
            "next": next_steps,
            "summary": (
                f"识别为《{selected.get('title')}》({selected.get('year')}) "
                f"tmdb_id={selected.get('tmdb_id')} type={selected.get('type')} path={path}"
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

    from media_mgmt_lib.workflows import (
        library as w_library,
        nextfind as w_nextfind,
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
        "nextfind": w_nextfind.run,
        "hdhive": w_nextfind.run,
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
