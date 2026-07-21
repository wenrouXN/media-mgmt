"""Subscribe workflow: dual-write NextFind + MoviePilot; optional NF fill on create."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.nf_evidence import nf_subscribe_active, subscribe_state
from media_mgmt_lib.workflows._util import fail, mp, ok


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes"}


def _norm_type(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in {"movie", "电影", "film", "films", "mov"}:
        return "movie"
    if s in {"tv", "电视剧", "剧集", "anime", "动漫", "series", "show"}:
        return "tv"
    return s or "tv"


def _identify(params: dict[str, Any]) -> dict[str, Any]:
    """Prefer NextFind identify; fall back to MP."""
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("mtype")
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        h = call_op("nextfind", "health", {})
        if h.get("success"):
            r = call_op(
                "nextfind",
                "identify",
                {
                    "title": title,
                    "q": title,
                    "tmdbid": tmdbid,
                    "media_type": media_type,
                    "year": params.get("year"),
                    "select": params.get("select") or 1,
                },
            )
            if r.get("success") and (r.get("selected") or {}).get("tmdb_id"):
                return {
                    "success": True,
                    "path": "nextfind_openapi",
                    "selected": r.get("selected"),
                    "candidates": r.get("candidates") or [],
                }
    except Exception:  # noqa: BLE001
        pass
    identified = mp("identify", title=title, tmdbid=tmdbid, media_type=media_type, year=params.get("year"))
    if not isinstance(identified, dict):
        return {"success": False, "path": "moviepilot", "error": "identify_failed", "detail": identified}
    selected = identified.get("selected") if isinstance(identified.get("selected"), dict) else None
    return {
        "success": bool(selected and (selected.get("tmdb_id") or selected.get("tmdbid"))),
        "path": "moviepilot",
        "selected": selected,
        "raw": identified,
    }


def _nf_subscribe_info(tmdbid: Any, media_type: str) -> dict[str, Any] | None:
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if not call_op("nextfind", "health", {}).get("success"):
            return None
        return call_op(
            "nextfind",
            "subscribe_info",
            {"tmdbid": tmdbid, "media_type": media_type},
        )
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "subscribe_nf_failed", "detail": str(e)}


def _nf_subscribe_add(tmdbid: Any, media_type: str, *, title: Any = None, year: Any = None, dry: bool = False) -> dict[str, Any]:
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if not call_op("nextfind", "health", {}).get("success"):
            return {"success": False, "error": "nextfind_not_configured"}
        if dry:
            return {
                "success": True,
                "dry_run": True,
                "would_subscribe_add": {
                    "tmdbid": tmdbid,
                    "media_type": media_type,
                    "title": title,
                    "year": year,
                },
            }
        body: dict[str, Any] = {"tmdbid": tmdbid, "media_type": media_type}
        if title not in (None, ""):
            body["title"] = title
        if year not in (None, ""):
            body["year"] = year
        return call_op("nextfind", "subscribe_add", body)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "subscribe_nf_failed", "detail": str(e)}


def _mp_subscribed(existing: Any) -> bool:
    if not isinstance(existing, dict):
        return False
    if existing.get("error"):
        return False
    return bool(existing.get("id") or existing.get("name") or existing.get("success"))


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    action = str(params.get("action") or "check").lower()  # check|create|list
    season = params.get("season") or 1
    dry = _truthy(params.get("dry_run")) or action not in {"create", "list"}
    # create + dry_run=true stays dry; create without dry is live
    if action == "create" and not _truthy(params.get("dry_run")):
        dry = False
    if action != "create" and action != "list":
        dry = True  # check/suggest never write

    if action == "list":
        mp_list = mp("subscribe_list")
        nf_list = None
        try:
            import media_mgmt_lib.ops.nextfind  # noqa: F401
            from media_mgmt_lib.ops import call_op

            if call_op("nextfind", "health", {}).get("success"):
                nf_list = call_op("nextfind", "subscriptions", {})
        except Exception as e:  # noqa: BLE001
            nf_list = {"success": False, "error": str(e)}
        return ok(
            {
                "workflow": "subscribe",
                "action": "list",
                "moviepilot": mp_list,
                "nextfind": nf_list,
                "summary": "subscribe list (MP + NF)",
            }
        )

    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")

    idr = _identify(params)
    selected = idr.get("selected") if isinstance(idr.get("selected"), dict) else None
    if not selected:
        return fail("identify_failed", detail=idr)
    tid = selected.get("tmdb_id") or selected.get("tmdbid") or tmdbid
    mtype_raw = selected.get("type") or selected.get("media_type") or params.get("media_type") or "电视剧"
    mtype_nf = _norm_type(mtype_raw)
    media = {
        "title": selected.get("title") or title,
        "tmdb_id": tid,
        "type": mtype_raw,
        "year": selected.get("year"),
        "identify_path": idr.get("path"),
    }

    # dual-read check
    existing_mp = mp(
        "subscribe",
        action="get",
        tmdbid=tid,
        title=media.get("title"),
        season=season,
    )
    existing_nf = _nf_subscribe_info(tid, mtype_nf)
    mp_err = isinstance(existing_mp, dict) and bool(existing_mp.get("error"))
    nf_err = isinstance(existing_nf, dict) and (
        existing_nf.get("success") is False or bool(existing_nf.get("error"))
    )
    mp_yes = _mp_subscribed(existing_mp) and not mp_err
    # NF: use evidence helper (list/is_subscribed), not bare HTTP success
    nf_yes = nf_subscribe_active(existing_nf if isinstance(existing_nf, dict) else None, tid)
    state = subscribe_state(mp=mp_yes, nf=nf_yes, mp_err=mp_err, nf_err=nf_err)

    if action == "check":
        return ok(
            {
                "workflow": "subscribe",
                "action": "check",
                "media": media,
                "moviepilot": existing_mp,
                "nextfind": existing_nf,
                "subscribed_mp": mp_yes,
                "subscribed_nf": nf_yes,
                "subscribed": mp_yes or nf_yes,
                "partial": state in {"mp_only", "nf_only"},
                "state": state,
                "summary": (
                    f"subscribe check {media.get('title')}: state={state} "
                    f"MP={'yes' if mp_yes else 'no'} NF={'yes' if nf_yes else 'no'}"
                    + (" (partial)" if state in {"mp_only", "nf_only"} else "")
                ),
            }
        )

    # create / suggest
    body = {
        "name": media.get("title"),
        "tmdbid": tid,
        "type": mtype_raw,
        "year": media.get("year"),
        "season": season,
    }

    if action != "create":
        return ok(
            {
                "workflow": "subscribe",
                "action": "suggest",
                "would_create": body,
                "would_dual_write": True,
                "existing_mp": existing_mp,
                "existing_nf": existing_nf,
                "summary": "dry suggest only; pass action=create to dual-write NF+MP",
            }
        )

    # live or dry create
    if dry:
        return ok(
            {
                "workflow": "subscribe",
                "action": "create",
                "dry_run": True,
                "would_create": body,
                "would_dual_write": {"moviepilot": True, "nextfind": True},
                "existing_mp": existing_mp,
                "existing_nf": existing_nf,
                "summary": f"dry dual-write subscribe {media.get('title')} tmdb={tid}",
            }
        )

    mp_created = mp(
        "subscribe",
        name=body["name"],
        tmdbid=body["tmdbid"],
        media_type=body["type"],
        year=body.get("year"),
        season=body.get("season"),
        dry_run=False,
    )
    nf_created = _nf_subscribe_add(
        tid,
        mtype_nf,
        title=media.get("title"),
        year=media.get("year"),
        dry=False,
    )

    mp_ok = bool(isinstance(mp_created, dict) and (mp_created.get("success") is not False) and not mp_created.get("error"))
    # some mp wrappers return data without success flag
    if isinstance(mp_created, dict) and mp_created.get("id"):
        mp_ok = True
    nf_ok = bool(isinstance(nf_created, dict) and nf_created.get("success") and not nf_created.get("error"))
    # nextfind may return success in nested forms
    if isinstance(nf_created, dict) and nf_created.get("error") == "nextfind_not_configured":
        nf_ok = False

    both = mp_ok and nf_ok
    partial = mp_ok ^ nf_ok
    state = subscribe_state(mp=mp_ok, nf=nf_ok)
    success = both or partial  # partial still "did something" but flagged

    out: dict[str, Any] = {
        "workflow": "subscribe",
        "action": "create",
        "dry_run": False,
        "media": media,
        "moviepilot": mp_created,
        "nextfind": nf_created,
        "subscribed_mp": mp_ok,
        "subscribed_nf": nf_ok,
        "partial": partial,
        "state": state,
        "error": None if both else ("subscribe_partial" if partial else "subscribe_failed"),
        "summary": (
            f"subscribe create {media.get('title')}: state={state} "
            f"MP={'ok' if mp_ok else 'fail'} NF={'ok' if nf_ok else 'fail'}"
            + (" PARTIAL" if partial else "")
        ),
    }

    # optional fill after create (CEO: 订阅时先 NF 补缺失)
    do_fill = _truthy(params.get("fill") if params.get("fill") is not None else True)
    if do_fill and (mp_ok or nf_ok):
        try:
            from media_mgmt_lib.workflows.nf_fill import fill_missing

            fill_params = {
                "title": media.get("title"),
                "tmdbid": tid,
                "media_type": mtype_nf,
                "season": season,
                "dry_run": _truthy(params.get("fill_dry_run") if params.get("fill_dry_run") is not None else True),
                "prefer": params.get("prefer") or "auto",
                "resolution": params.get("resolution"),
                "require_chinese": params.get("require_chinese"),
                "hdr_mode": params.get("hdr_mode"),
                "force_mp_search": params.get("force_mp_search"),
            }
            # allow user to execute fill: fill_dry_run=false or fill_execute=true
            if _truthy(params.get("fill_execute")) or params.get("fill_dry_run") in (False, "false", "0", "no"):
                fill_params["dry_run"] = False
            fill_result = fill_missing(fill_params)
            out["fill"] = fill_result
            out["summary"] += f"；fill path={fill_result.get('path')} ok={fill_result.get('success')}"
        except Exception as e:  # noqa: BLE001
            out["fill"] = {"success": False, "error": str(e)}
            out["summary"] += f"；fill error={e}"

    out["success"] = success if not partial else True
    if partial:
        out["success"] = True  # partial is success with warning
        out["error"] = "subscribe_partial"
    elif not both:
        out["success"] = False
        if not mp_ok:
            out["error"] = "subscribe_mp_failed"
        if not nf_ok:
            out["error"] = "subscribe_nf_failed" if mp_ok else out.get("error") or "subscribe_failed"

    return out if out.get("success") else fail(out.get("error") or "subscribe_failed", **{k: v for k, v in out.items() if k != "success"})
