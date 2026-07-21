"""NextFind OpenAPI ops — primary path for 网盘源 / 认片 / 转存 / 订阅."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.providers.nextfind.client import (
    NextFindClient,
    _norm_media_type,
    client_from_config,
)
from media_mgmt_lib.quality_pref import parse_quality_params, pick_best_resource, resource_blob


def _client(cfg: dict[str, Any]) -> NextFindClient | None:
    return client_from_config(cfg)


def _need_client(cfg: dict[str, Any]) -> tuple[NextFindClient | None, dict[str, Any] | None]:
    c = _client(cfg)
    if c is None:
        return None, {
            "success": False,
            "error": "nextfind_not_configured",
            "need": "nextfind.base_url + api_key (workspace .credentials/nextfind.env)",
        }
    return c, None


def pick_best_nextfind_resource(
    resources: list[dict[str, Any]],
    *,
    resolution: str | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
) -> dict[str, Any] | None:
    """Alias of shared quality_pref.pick_best_resource (NextFind rows)."""
    return pick_best_resource(
        resources,
        resolution=resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode or "any",
        prefer_fx_sub=True,
        exclude_disc=False,
    )


# back-compat for any private helper imports
_resource_blob = resource_blob


def op_health(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.health()


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    q = params.get("query") or params.get("q") or params.get("title") or params.get("keyword")
    if not q:
        return {"success": False, "error": "missing_param", "need": "query|q|title"}
    media_type = params.get("media_type") or params.get("type") or params.get("kind")
    r = c.search(str(q), media_type=str(media_type) if media_type else None)
    if not r.get("success"):
        return r
    data = r.get("data")
    items = data if isinstance(data, list) else []
    # normalize candidates for identify-like use
    candidates = []
    for it in items:
        if not isinstance(it, dict):
            continue
        tid = it.get("id") or it.get("tmdb_id")
        candidates.append(
            {
                "tmdb_id": int(tid) if str(tid).isdigit() else tid,
                "title": it.get("title"),
                "year": it.get("year"),
                "type": it.get("raw_type") or it.get("type") or it.get("media_type"),
                "raw_type": it.get("raw_type"),
                "rating": it.get("rating") or it.get("vote_average") or it.get("_vote_average"),
                "poster": it.get("poster") or it.get("poster_path"),
                "is_in_library": it.get("is_in_library"),
                "fillable_movie_tag": it.get("fillable_movie_tag"),
                "local_episodes": it.get("local_episodes"),
                "raw": it,
            }
        )
    selected = candidates[0] if candidates else None
    return {
        "success": True,
        "count": len(candidates),
        "candidates": candidates,
        "selected": selected,
        "data": data,
    }


def op_resources(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or params.get("type") or "movie"
    if not tmdbid:
        return {"success": False, "error": "missing_param", "need": "tmdbid|tmdb_id"}
    r = c.resources_search(
        tmdbid,
        str(media_type),
        season=params.get("season"),
        episode=params.get("episode"),
    )
    if not r.get("success"):
        return r
    data = r.get("data")
    items = [x for x in (data if isinstance(data, list) else []) if isinstance(x, dict)]
    qpref = parse_quality_params(params)
    best = pick_best_nextfind_resource(
        items,
        resolution=qpref.get("resolution"),
        require_chinese=bool(qpref.get("require_chinese")),
        hdr_mode=str(qpref.get("hdr_mode") or "any"),
    )
    return {
        "success": True,
        "tmdb_id": str(tmdbid),
        "media_type": _norm_media_type(media_type),
        "count": len(items),
        "resources": items,
        "best": best,
        "quality": qpref,
    }


def op_preview(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    slug = params.get("slug") or params.get("url") or params.get("resource")
    if not slug:
        return {"success": False, "error": "missing_param", "need": "slug"}
    return c.preview(str(slug))


def op_unlock(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    rid = params.get("id") or params.get("resource_id")
    rtype = params.get("type") or params.get("resource_type") or params.get("media_type")
    if rid is None or rtype in (None, ""):
        return {"success": False, "error": "missing_param", "need": "id+type"}
    return c.hdhive_unlock(rid, str(rtype))


def op_quota(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.quota()


def op_transfer(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    slug = params.get("slug") or params.get("url") or params.get("resource")
    if not slug:
        return {"success": False, "error": "missing_param", "need": "slug"}
    folder = params.get("target_folder") or params.get("folder") or params.get("save_path")
    dry = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    if dry:
        return {
            "success": True,
            "dry_run": True,
            "would_transfer": {"slug": slug, "target_folder": folder},
            "hint": "remove dry_run to execute POST /transfer",
        }
    return c.transfer(str(slug), target_folder=str(folder) if folder else None)


def op_directories(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.directories(params.get("cid"))


def op_create_directory(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    parent = params.get("parent_cid") or params.get("cid") or params.get("parent")
    name = params.get("name") or params.get("folder") or params.get("dirname")
    if parent in (None, "") or not name:
        return {"success": False, "error": "missing_param", "need": "parent_cid+name"}
    return c.create_directory(str(parent), str(name))


def op_local_library_filter(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    status = params.get("status_filter") or params.get("status") or params.get("filter") or "missing"
    return c.local_library_filter(str(status))


def op_logs(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.logs()


def op_history(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.history()


def op_history_delete_all(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    confirm = str(params.get("confirm") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    if not confirm:
        return {
            "success": False,
            "error": "confirm_required",
            "need": "confirm=true",
            "hint": "DELETE /history/all is destructive",
        }
    return c.history_delete_all()


def op_history_delete_item(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    title = params.get("title") or params.get("q")
    if tmdbid in (None, "") and not title:
        return {"success": False, "error": "missing_param", "need": "tmdbid|title"}
    return c.history_delete_item(tmdb_id=tmdbid, title=str(title) if title else None)


def op_fill_missing(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    body = dict(params)
    # normalize common aliases
    if "tmdb_id" not in body and body.get("tmdbid") not in (None, ""):
        body["tmdb_id"] = body.get("tmdbid")
    if "media_type" in body:
        body["media_type"] = _norm_media_type(body.get("media_type"))
    for drop in ("service", "op"):
        body.pop(drop, None)
    return c.fill_missing(**body)


def op_delete_episode(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    season = params.get("season")
    episode = params.get("episode")
    if tmdbid in (None, "") or season in (None, "") or episode in (None, ""):
        return {"success": False, "error": "missing_param", "need": "tmdbid+season+episode"}
    confirm = str(params.get("confirm") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    if not confirm:
        return {
            "success": False,
            "error": "confirm_required",
            "need": "confirm=true",
            "hint": "DELETE /media/episode is destructive",
        }
    return c.delete_media_episode(tmdbid, season, episode)


def op_delete_season(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    season = params.get("season")
    if tmdbid in (None, "") or season in (None, ""):
        return {"success": False, "error": "missing_param", "need": "tmdbid+season"}
    confirm = str(params.get("confirm") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    if not confirm:
        return {
            "success": False,
            "error": "confirm_required",
            "need": "confirm=true",
            "hint": "DELETE /media/season is destructive",
        }
    return c.delete_media_season(tmdbid, season)


def op_delete_movie(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if tmdbid in (None, ""):
        return {"success": False, "error": "missing_param", "need": "tmdbid"}
    confirm = str(params.get("confirm") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    if not confirm:
        return {
            "success": False,
            "error": "confirm_required",
            "need": "confirm=true",
            "hint": "DELETE /media/movie is destructive",
        }
    return c.delete_media_movie(tmdbid)


def op_settings_tg_channels(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    if str(params.get("set") or params.get("write") or "").lower() in {"1", "true", "yes"} or params.get("channels") is not None:
        body = params.get("channels") if params.get("channels") is not None else params.get("body") or params
        if not isinstance(body, (dict, list)):
            return {"success": False, "error": "missing_param", "need": "channels|body"}
        return c.settings_tg_channels_set(body)
    return c.settings_tg_channels_get()


def op_settings_rss(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    if str(params.get("set") or params.get("write") or "").lower() in {"1", "true", "yes"} or params.get("items") is not None or params.get("rss") is not None:
        body = params.get("rss") if params.get("rss") is not None else params.get("items") if params.get("items") is not None else params.get("body") or params
        if not isinstance(body, (dict, list)):
            return {"success": False, "error": "missing_param", "need": "rss|items|body"}
        return c.settings_rss_set(body)
    return c.settings_rss_get()


def op_settings_rules(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    body = params.get("rules") if isinstance(params.get("rules"), dict) else params.get("body") if isinstance(params.get("body"), dict) else None
    if body is None:
        # pass through remaining params as body
        body = {k: v for k, v in params.items() if k not in {"service", "op"}}
    if not body:
        return {"success": False, "error": "missing_param", "need": "rules body"}
    return c.settings_rules_set(body)


def op_settings_transfer_folder(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    folder = params.get("folder") or params.get("transfer_folder") or params.get("path") or params.get("target_folder")
    if not folder:
        return {"success": False, "error": "missing_param", "need": "folder|transfer_folder|path"}
    extra = {k: v for k, v in params.items() if k not in {"folder", "transfer_folder", "path", "target_folder", "service", "op"}}
    return c.settings_transfer_folder_set(str(folder), **extra)


def op_ignore_season(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    season = params.get("season")
    if tmdbid in (None, "") or season in (None, ""):
        return {"success": False, "error": "missing_param", "need": "tmdbid+season"}
    extra = {k: v for k, v in params.items() if k not in {"tmdbid", "tmdb_id", "media_type", "kind", "season", "service", "op"}}
    return c.ignored_episodes_toggle(tmdbid, str(media_type), season, **extra)


def op_subscriptions(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    return c.subscriptions()


def op_subscribe_add(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    if not tmdbid:
        return {"success": False, "error": "missing_param", "need": "tmdbid"}
    extra = {}
    for k in ("title", "target_resolution", "year"):
        if params.get(k) not in (None, ""):
            extra[k] = params[k]
    return c.subscriptions_add(tmdbid, str(media_type), **extra)


def op_subscribe_remove(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or "tv"
    if not tmdbid:
        return {"success": False, "error": "missing_param", "need": "tmdbid"}
    return c.subscriptions_remove(tmdbid, str(media_type))


def op_subscribe_info(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None
    items = params.get("items")
    if not items:
        tmdbid = params.get("tmdbid") or params.get("tmdb_id")
        media_type = params.get("media_type") or params.get("kind") or "movie"
        if not tmdbid:
            return {"success": False, "error": "missing_param", "need": "items|tmdbid"}
        items = [{"tmdb_id": str(tmdbid), "media_type": _norm_media_type(media_type)}]
    return c.subscriptions_info(list(items))


def op_library_info(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Library presence via subscriptions/info (in_library + local_episodes)."""
    return op_subscribe_info(svc, cfg, params)


def op_identify(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Title/tmdb → TMDB candidates via NextFind OpenAPI search (identify surface).

    Params: q|title|keyword, tmdbid (optional seed), media_type, year, select (1-based).
    Returns candidates/selected shaped like media-mgmt identify workflow.
    """
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None

    title = params.get("title") or params.get("q") or params.get("keyword") or params.get("query")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("type") or params.get("kind")
    year = params.get("year")
    if not title and not tmdbid:
        return {"success": False, "error": "missing_param", "need": "title|q|tmdbid"}

    # Force-id path: still search by id/title seed to get NextFind metadata + library flags
    q = str(title or tmdbid)
    r = c.search(q, media_type=str(media_type) if media_type else None)
    if not r.get("success"):
        return {**r, "stage": "search", "path": "nextfind_openapi"}

    data = r.get("data") if isinstance(r.get("data"), list) else []
    candidates: list[dict[str, Any]] = []
    for it in data:
        if not isinstance(it, dict):
            continue
        tid = it.get("id") or it.get("tmdb_id")
        if tid in (None, ""):
            continue
        # optional year filter (soft)
        it_year = it.get("year") or (str(it.get("release_date") or it.get("first_air_date") or "")[:4] or None)
        if year not in (None, "") and it_year and str(it_year) != str(year):
            # keep but deprioritize later via order only if exact matches exist
            pass
        raw_type = it.get("raw_type") or it.get("type") or it.get("media_type")
        candidates.append(
            {
                "tmdb_id": int(tid) if str(tid).isdigit() else tid,
                "title": it.get("title") or it.get("name"),
                "original_title": it.get("original_title") or it.get("original_name"),
                "year": it_year,
                "type": raw_type,
                "media_type": _norm_media_type(raw_type) if raw_type else None,
                "rating": it.get("rating") or it.get("vote_average") or it.get("_vote_average"),
                "vote_average": it.get("vote_average") or it.get("rating") or it.get("_vote_average"),
                "poster": it.get("poster") or it.get("poster_path"),
                "poster_path": it.get("poster_path") or it.get("poster"),
                "is_in_library": it.get("is_in_library"),
                "fillable_movie_tag": it.get("fillable_movie_tag"),
                "local_episodes": it.get("local_episodes"),
                "overview": (it.get("overview") or "")[:160] or None,
                "raw": it,
            }
        )

    # If tmdbid forced, prefer exact match first
    if tmdbid not in (None, ""):
        want = str(tmdbid)
        exact = [x for x in candidates if str(x.get("tmdb_id")) == want]
        rest = [x for x in candidates if str(x.get("tmdb_id")) != want]
        candidates = exact + rest
        if not exact:
            # inject minimal forced selection so downstream can still use id
            candidates.insert(
                0,
                {
                    "tmdb_id": int(want) if want.isdigit() else want,
                    "title": title or want,
                    "year": year,
                    "type": media_type,
                    "media_type": _norm_media_type(media_type) if media_type else None,
                    "forced_tmdb": True,
                },
            )

    # soft year prefer: exact year first
    if year not in (None, "") and candidates:
        y = str(year)
        exact_y = [x for x in candidates if str(x.get("year") or "") == y]
        rest_y = [x for x in candidates if str(x.get("year") or "") != y]
        if exact_y:
            candidates = exact_y + rest_y

    select = params.get("select")
    idx = 0
    if select not in (None, ""):
        try:
            idx = max(0, int(select) - 1)
        except (TypeError, ValueError):
            return {"success": False, "error": "bad_param", "need": "select=1-based integer"}
        if candidates and idx >= len(candidates):
            return {
                "success": False,
                "error": "select_out_of_range",
                "count": len(candidates),
                "select": select,
            }

    selected = candidates[idx] if candidates else None
    if not selected or selected.get("tmdb_id") in (None, ""):
        return {
            "success": False,
            "error": "identify_no_tmdb",
            "path": "nextfind_openapi",
            "query": {"title": title, "tmdbid": tmdbid, "media_type": media_type, "year": year},
            "candidates": candidates,
            "count": len(candidates),
        }

    conf = "high"
    needs_confirm = False
    if len(candidates) > 1 and select in (None, "") and tmdbid in (None, ""):
        conf = "medium"
        needs_confirm = True
    if tmdbid not in (None, "") or select not in (None, ""):
        conf = "high"
        needs_confirm = False

    return {
        "success": True,
        "path": "nextfind_openapi",
        "source": "nextfind_openapi",
        "stage": "identify",
        "query": {"title": title, "tmdbid": tmdbid, "media_type": media_type, "year": year, "select": select},
        "selected": selected,
        "tmdb_id": selected.get("tmdb_id"),
        "candidates": candidates,
        "candidate_count": len(candidates),
        "count": len(candidates),
        "confidence": conf,
        "needs_confirm": needs_confirm,
        "data": data,
    }


def op_grab(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """search(optional) → resources → pick best → optional preview → transfer.

    Default dry_run=false when transfer=true (caller/workflow should pass dry_run for safety).
    """
    c, err = _need_client(cfg)
    if err:
        return err
    assert c is not None

    q = params.get("q") or params.get("title") or params.get("keyword") or params.get("query")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    media_type = params.get("media_type") or params.get("kind") or params.get("type") or "movie"
    do_transfer = str(params.get("transfer", "true")).lower() in {"1", "true", "yes"}
    dry_run = str(params.get("dry_run") or "").lower() in {"1", "true", "yes"}
    do_preview = str(params.get("preview", "false")).lower() in {"1", "true", "yes"}
    select = int(params.get("select") or 1)
    qpref = parse_quality_params(params)

    identified = None
    if not tmdbid:
        if not q:
            return {"success": False, "error": "missing_param", "need": "q|title|tmdbid"}
        sr = c.search(str(q), media_type=str(media_type) if media_type else None)
        if not sr.get("success"):
            return {**sr, "stage": "search"}
        items = sr.get("data") if isinstance(sr.get("data"), list) else []
        if not items:
            return {"success": False, "error": "no_search_results", "stage": "search"}
        idx = max(0, select - 1)
        if idx >= len(items):
            idx = 0
        chosen = items[idx] if isinstance(items[idx], dict) else {}
        tmdbid = chosen.get("id") or chosen.get("tmdb_id")
        raw_type = chosen.get("raw_type") or chosen.get("media_type") or chosen.get("type")
        if raw_type:
            media_type = raw_type
        identified = chosen
        if not tmdbid:
            return {"success": False, "error": "no_tmdb_id", "selected": chosen, "stage": "search"}

    rr = c.resources_search(
        tmdbid,
        str(media_type),
        season=params.get("season"),
        episode=params.get("episode"),
    )
    if not rr.get("success"):
        return {**rr, "stage": "resources", "tmdb_id": str(tmdbid), "identified": identified}
    resources = [x for x in (rr.get("data") or []) if isinstance(x, dict)]
    if not resources:
        from media_mgmt_lib.result_gate import grab_resources_gate

        hint_count = None
        if identified is not None:
            hint_count = 1
        gated = grab_resources_gate(
            resources=resources,
            search_hint_count=hint_count,
            force_grab=params.get("force_grab"),
            identified=identified,
        )
        base = {
            "tmdb_id": str(tmdbid),
            "media_type": _norm_media_type(media_type),
            "identified": identified,
            "quality": qpref,
            "resource_authority": "resources_op",
        }
        if gated:
            return {**base, **gated}
        return {
            "success": False,
            "error": "no_resources",
            "stage": "resources",
            **base,
        }

    best = pick_best_nextfind_resource(
        resources,
        resolution=qpref.get("resolution"),
        require_chinese=bool(qpref.get("require_chinese")),
        hdr_mode=str(qpref.get("hdr_mode") or "any"),
    )
    if not best:
        best = resources[0]
    slug = best.get("slug")
    if not slug:
        return {
            "success": False,
            "error": "no_slug",
            "best": best,
            "stage": "pick",
            "resources_count": len(resources),
        }

    preview = None
    if do_preview:
        preview = c.preview(str(slug))

    transfer = None
    transfer_ok = True
    if do_transfer:
        if dry_run:
            transfer = {
                "dry_run": True,
                "would_transfer": {
                    "slug": slug,
                    "target_folder": params.get("target_folder") or params.get("folder"),
                },
            }
            transfer_ok = True
        else:
            folder = params.get("target_folder") or params.get("folder") or params.get("save_path")
            transfer = c.transfer(str(slug), target_folder=str(folder) if folder else None)
            transfer_ok = bool(transfer.get("success"))

    success = bool(slug) and (transfer_ok if do_transfer else True)
    error = None
    if do_transfer and not transfer_ok:
        error = "transfer_failed"

    return {
        "success": success,
        "source": "nextfind_openapi",
        "tmdb_id": str(tmdbid),
        "media_type": _norm_media_type(media_type),
        "identified": identified,
        "best_resource": best,
        "slug": slug,
        "resources_count": len(resources),
        "preview": preview,
        "transfer": transfer,
        "dry_run": dry_run,
        "quality": qpref,
        "error": error,
    }


# register — full official Agent OpenAPI surface + grab composite
register_op("nextfind", "health", op_health)
register_op("nextfind", "search", op_search)
register_op("nextfind", "resources", op_resources)
register_op("nextfind", "preview", op_preview)
register_op("nextfind", "unlock", op_unlock)
register_op("nextfind", "quota", op_quota)
register_op("nextfind", "transfer", op_transfer)
register_op("nextfind", "directories", op_directories)
register_op("nextfind", "create_directory", op_create_directory)
register_op("nextfind", "local_library_filter", op_local_library_filter)
register_op("nextfind", "logs", op_logs)
register_op("nextfind", "history", op_history)
register_op("nextfind", "history_delete_all", op_history_delete_all)
register_op("nextfind", "history_delete_item", op_history_delete_item)
register_op("nextfind", "fill_missing", op_fill_missing)
register_op("nextfind", "delete_episode", op_delete_episode)
register_op("nextfind", "delete_season", op_delete_season)
register_op("nextfind", "delete_movie", op_delete_movie)
register_op("nextfind", "settings_tg_channels", op_settings_tg_channels)
register_op("nextfind", "settings_rss", op_settings_rss)
register_op("nextfind", "settings_rules", op_settings_rules)
register_op("nextfind", "settings_transfer_folder", op_settings_transfer_folder)
register_op("nextfind", "ignore_season", op_ignore_season)
register_op("nextfind", "subscriptions", op_subscriptions)
register_op("nextfind", "subscribe_add", op_subscribe_add)
register_op("nextfind", "subscribe_remove", op_subscribe_remove)
register_op("nextfind", "subscribe_info", op_subscribe_info)
register_op("nextfind", "library_info", op_library_info)
register_op("nextfind", "identify", op_identify)
register_op("nextfind", "grab", op_grab)
