#!/usr/bin/env python3
"""MoviePilot REST helper for media-mgmt.

Primary API path for media identify/search/download/subscription workflows.
Do not use MCP/mcporter as fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
repo_root_str = str(repo_root)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from media_mgmt_lib.config import load_json_config, moviepilot_credentials
from media_mgmt_lib.torrent_pick import pick_torrent, summarize_candidate


def creds() -> dict[str, str]:
    value = moviepilot_credentials(load_json_config())
    if not value:
        raise SystemExit("MoviePilot credentials missing: set moviepilot.base_url and moviepilot.api_key in config.json")
    return value


def api_url(path: str, params: dict[str, Any] | None = None) -> str:
    c = creds()
    base = c["BASE_URL"].rstrip()
    query = {"apikey": c["API_KEY"]}
    if params:
        for k, v in params.items():
            if v is not None and v != "":
                query[k] = v
    return f"{base}{path}?{urllib.parse.urlencode(query, doseq=True)}"


def request(method: str, path: str, params: dict[str, Any] | None = None, body: Any | None = None) -> Any:
    url = api_url(path, params)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        parsed: Any
        try:
            parsed = json.loads(err_body) if err_body else err_body
        except json.JSONDecodeError:
            parsed = err_body
        raise SystemExit(
            json.dumps(
                {
                    "success": False,
                    "error": "http_error",
                    "status": e.code,
                    "path": path,
                    "method": method.upper(),
                    "detail": parsed,
                    "hint": _download_error_hint(path, e.code, parsed),
                },
                ensure_ascii=False,
            )
        ) from e
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _download_error_hint(path: str, status: int, detail: Any) -> str:
    text = json.dumps(detail, ensure_ascii=False) if not isinstance(detail, str) else detail
    if path.startswith("/api/v1/download"):
        if status == 500:
            return (
                "Download API 500 usually means incomplete media_in/torrent_in. "
                "Pass full recognize media_info + full search torrent_info (with enclosure/site_cookie). "
                "Prefer: scripts/watch.py or --from-search-result."
            )
        if "任务添加失败" in text:
            return (
                "任务添加失败: check clients via /api/v1/download/clients, "
                "ensure torrent enclosure is reachable, and pass complete torrent_info."
            )
        if status == 422:
            return "Validation error: required fields missing (media_in/torrent_in)."
    return "See detail for API error."


def extract_torrent_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit("torrent payload must be a JSON object")
    if isinstance(value.get("torrent_info"), dict) and value["torrent_info"]:
        return value["torrent_info"]
    if isinstance(value.get("selected"), dict):
        selected = value["selected"]
        if isinstance(selected.get("torrent_info"), dict):
            return selected["torrent_info"]
        return selected
    return value


def extract_media_info(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SystemExit("media payload must be a JSON object")
    if isinstance(value.get("media_info"), dict) and value["media_info"]:
        return value["media_info"]
    if isinstance(value.get("selected"), dict) and value.get("source") in {"detail", "media-search", None}:
        # identify output
        selected = value["selected"]
        if isinstance(selected, dict):
            return selected
    return value


def validate_torrent_info(torrent_in: dict[str, Any], *, strict_site: bool = False) -> list[str]:
    missing: list[str] = []
    if not torrent_in.get("title"):
        missing.append("title")
    if not torrent_in.get("enclosure"):
        missing.append("enclosure")
    if strict_site and not torrent_in.get("site_name") and torrent_in.get("site") is None:
        missing.append("site_name|site")
    return missing


def validate_media_info(media_in: dict[str, Any] | None, *, require_full: bool = False) -> list[str]:
    if media_in is None:
        return ["media_in"] if require_full else []
    missing: list[str] = []
    if not media_in.get("type") and not media_in.get("media_type"):
        missing.append("type")
    if require_full:
        if not (media_in.get("tmdb_id") or media_in.get("tmdbid") or media_in.get("douban_id")):
            missing.append("tmdb_id|douban_id")
        if not (media_in.get("title") or media_in.get("name")):
            missing.append("title")
    return missing


def media_type_api_to_cn(media_type: str) -> str:
    value = (media_type or "").lower()
    if value in {"movie", "电影"}:
        return "电影"
    if value in {"tv", "series", "电视剧", "剧集"}:
        return "电视剧"
    if value in {"anime", "动漫"}:
        # MoviePilot download directories model anime as TV categories.
        return "电视剧"
    return media_type


def _split_rule_values(value: Any) -> set[str]:
    if value in (None, ""):
        return set()
    if isinstance(value, str):
        return {item.strip().lower() for item in value.replace(",", " ").split() if item.strip()}
    if isinstance(value, list | tuple | set):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    return {str(value).strip().lower()}


def _category_config_data(category_config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(category_config, dict):
        return {}
    data = category_config.get("data")
    if isinstance(data, dict):
        return data
    return category_config


def _configured_category_key(media_type: str) -> str:
    if media_type == "电影":
        return "movie"
    if media_type == "电视剧":
        return "tv"
    return ""


def _media_year(media: dict[str, Any]) -> str:
    for key in ("year", "release_year", "first_air_date", "release_date"):
        value = media.get(key)
        if value:
            return str(value)[:4]
    return ""


def _matches_category_rule(media: dict[str, Any], rule: dict[str, Any]) -> bool:
    original_language = str(media.get("original_language") or "").lower()
    origin_country = media.get("origin_country") or media.get("origin_countries") or []
    production_countries = media.get("production_countries") or []
    if isinstance(origin_country, str):
        origin_values = _split_rule_values(origin_country)
    else:
        origin_values = {str(x).lower() for x in origin_country if x}
    if isinstance(production_countries, str):
        production_values = _split_rule_values(production_countries)
    else:
        production_values = {
            str(x.get("iso_3166_1") or x.get("name") or x).lower() if isinstance(x, dict) else str(x).lower()
            for x in production_countries
            if x
        }
    genres = media.get("genres") or media.get("genre_ids") or []
    genre_values: set[str] = set()
    for genre in genres:
        if isinstance(genre, dict):
            if genre.get("id") is not None:
                genre_values.add(str(genre["id"]).lower())
        elif genre is not None:
            genre_values.add(str(genre).lower())

    checks = [
        ("original_language", {original_language} if original_language else set()),
        ("origin_country", origin_values),
        ("production_countries", production_values),
        ("genre_ids", genre_values),
        ("release_year", {_media_year(media)} if _media_year(media) else set()),
    ]
    for key, media_values in checks:
        rule_values = _split_rule_values(rule.get(key))
        if rule_values and not (media_values & rule_values):
            return False
    return True


def _infer_category_from_config(media: dict[str, Any], media_type: str, category_config: dict[str, Any] | None) -> str:
    typed_config = _category_config_data(category_config).get(_configured_category_key(media_type))
    if not isinstance(typed_config, dict):
        return ""

    fallback = ""
    for category, rule in typed_config.items():
        if rule is None:
            fallback = str(category)
            continue
        if isinstance(rule, dict) and _matches_category_rule(media, rule):
            return str(category)
    return fallback


def infer_category(media: dict[str, Any], category_config: dict[str, Any] | None = None) -> str:
    """Infer MoviePilot media category from media metadata and category config.

    This intentionally favors explicit media.category if present, then reproduces
    the common MP category rules used by this environment.
    """
    explicit = media.get("category") or media.get("media_category")
    if explicit:
        return str(explicit)

    media_type = media_type_api_to_cn(str(media.get("type") or media.get("media_type") or ""))
    configured_category = _infer_category_from_config(media, media_type, category_config)
    if configured_category:
        return configured_category

    original_language = str(media.get("original_language") or "").lower()
    origin_country = media.get("origin_country") or media.get("origin_countries") or []
    if isinstance(origin_country, str):
        countries = {x.strip().upper() for x in origin_country.replace(",", " ").split() if x.strip()}
    else:
        countries = {str(x).upper() for x in origin_country if x}
    genres = media.get("genres") or media.get("genre_ids") or []
    genre_ids: set[str] = set()
    for g in genres:
        if isinstance(g, dict):
            if g.get("id") is not None:
                genre_ids.add(str(g.get("id")))
        elif g is not None:
            genre_ids.add(str(g))

    if media_type == "电影":
        if original_language in {"zh", "cn", "bo", "za"} or countries & {"CN", "TW", "HK"}:
            return "国产电影"
        if original_language in {"ko", "ja"} or countries & {"KR", "KP", "JP"}:
            return "日韩电影"
        if original_language == "en" or countries & {"US", "GB", "UK", "FR", "DE", "ES", "IT", "NL", "PT", "RU"}:
            return "欧美电影"
        return "其他电影"

    if media_type == "电视剧":
        if "16" in genre_ids:
            if countries & {"CN"}:
                return "国语动漫"
            return "其他动漫"
        if "99" in genre_ids:
            return "纪录片"
        if "10762" in genre_ids:
            return "儿童"
        if genre_ids & {"10764", "10767"}:
            return "综艺"
        if countries & {"CN", "TW", "HK"}:
            return "国产剧"
        if countries & {"US", "FR", "GB", "DE", "ES", "IT", "NL", "PT", "RU", "UK"}:
            return "欧美剧"
        if countries & {"JP", "KP", "KR", "TH", "IN", "SG"} or original_language in {"ja", "ko", "th", "hi"}:
            return "日韩剧"
        return "其他剧集"

    return ""


def choose_download_path(media: dict[str, Any], paths: list[dict[str, Any]], category_config: dict[str, Any] | None = None) -> dict[str, Any]:
    media_type = media_type_api_to_cn(str(media.get("type") or media.get("media_type") or ""))
    category = infer_category(media, category_config)

    def norm(v: Any) -> str:
        return str(v or "").strip()

    # 1. exact media_type + category match from MP paths
    for item in sorted(paths, key=lambda x: x.get("priority") if x.get("priority") is not None else 999):
        if norm(item.get("media_type")) == media_type and norm(item.get("media_category")) == category:
            return {"save_path": item.get("save_path"), "media_type": media_type, "media_category": category, "source": "exact", "path_entry": item}

    # 2. generic media_type path + inferred category as second-level dir.
    # When MP only configures base paths (e.g. 电影 → /qbs/torrents/movies/), append
    # infer_category result (日韩电影/欧美电影/…) so layout matches library classification.
    # Exact path entries (media_type + media_category) still win in step 1.
    for item in sorted(paths, key=lambda x: x.get("priority") if x.get("priority") is not None else 999):
        if norm(item.get("media_type")) == media_type and not norm(item.get("media_category")):
            base = str(item.get("save_path") or item.get("download_path") or "")
            if category and base and not base.rstrip("/").endswith(category):
                base = base.rstrip("/") + "/" + category + "/"
            return {
                "save_path": base,
                "media_type": media_type,
                "media_category": category,
                "source": "generic_plus_category",
                "path_entry": item,
            }

    # 3. no safe path
    return {"save_path": None, "media_type": media_type, "media_category": category, "source": "unresolved", "path_entry": None}


def cmd_get(args: argparse.Namespace) -> None:
    params = dict(p.split("=", 1) for p in args.param or [])
    print_json(request("GET", args.path, params=params))


def cmd_post(args: argparse.Namespace) -> None:
    body = json.loads(args.json or "{}")
    params = dict(p.split("=", 1) for p in args.param or [])
    print_json(request("POST", args.path, params=params, body=body))


def cmd_paths(_: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/download/paths"))


def cmd_category(_: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/media/category/config"))


def cmd_resolve_path(args: argparse.Namespace) -> None:
    media = json.loads(args.media_json)
    paths = request("GET", "/api/v1/download/paths")
    category_config = request("GET", "/api/v1/media/category/config")
    print_json(choose_download_path(media, paths or [], category_config))


def normalize_mtype(value: str | None) -> str | None:
    if not value:
        return value
    lower = value.lower()
    if lower in {"tv", "series"}:
        return "电视剧"
    if lower == "movie":
        return "电影"
    if lower == "anime":
        return "动漫"
    return value


def cmd_search(args: argparse.Namespace) -> None:
    mediaid = args.mediaid or f"tmdb:{args.tmdbid}"
    params = {"mtype": normalize_mtype(args.media_type), "title": args.title, "year": args.year, "season": args.season, "sites": args.sites}
    print_json(request("GET", f"/api/v1/search/media/{urllib.parse.quote(mediaid, safe=':')}", params=params))


def cmd_title(args: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/search/title", params={"keyword": args.keyword, "page": args.page, "sites": args.sites}))


def cmd_media_search(args: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/media/search", params={"title": args.title, "type": args.kind, "page": args.page, "count": args.count}))


def cmd_recognize(args: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/media/recognize", params={"title": args.title, "subtitle": args.subtitle}))


def cmd_media_detail(args: argparse.Namespace) -> None:
    mediaid = args.mediaid or f"tmdb:{args.tmdbid}"
    print_json(request("GET", f"/api/v1/media/{urllib.parse.quote(mediaid, safe=':')}", params={"type_name": normalize_mtype(args.media_type), "title": args.title, "year": args.year}))


def _pick_media_search_result(results: Any, title: str | None = None, media_type: str | None = None, year: str | None = None) -> Any:
    if not isinstance(results, list) or not results:
        return None
    wanted_type = normalize_mtype(media_type)
    def score(item: dict[str, Any]) -> tuple[int, float]:
        s = 0
        if wanted_type and str(item.get("type") or item.get("media_type") or "") == wanted_type:
            s += 20
        if year and str(item.get("year") or "") == str(year):
            s += 10
        names = [str(item.get(k) or "") for k in ["title", "name", "en_title", "original_title", "original_name"]]
        names.extend(str(x) for x in item.get("names") or [])
        if title and any(title in n or n in title for n in names if n):
            s += 30
        return (s, float(item.get("vote_average") or item.get("vote") or 0))
    return max(results, key=score)


def _title_variants(title: str | None) -> list[str]:
    if not title:
        return []
    variants = [title]
    swaps = [("职员", "社员"), ("社员", "职员"), ("職員", "社員"), ("社員", "職員")]
    for old, new in swaps:
        if old in title:
            variants.append(title.replace(old, new))
    # de-duplicate preserving order
    out = []
    for v in variants:
        if v and v not in out:
            out.append(v)
    return out


def _media_shell_usable(media: Any) -> bool:
    if not isinstance(media, dict) or not media:
        return False
    if media.get("tmdb_id") or media.get("tmdbid"):
        return True
    if media.get("title") or media.get("name") or media.get("en_title") or media.get("original_title"):
        return True
    return False


def _fetch_tmdb_detail_for_identify(
    tmdbid: int,
    *,
    title: str | None,
    year: str | None,
    media_type: str | None,
) -> dict[str, Any] | None:
    preferred = normalize_mtype(media_type) if media_type else None
    if preferred in {"电影", "电视剧"}:
        order = [preferred, "电视剧" if preferred == "电影" else "电影"]
    else:
        order = ["电影", "电视剧"]
    for mtype in order:
        try:
            detail = request(
                "GET",
                f"/api/v1/media/tmdb:{tmdbid}",
                params={"type_name": mtype, "title": title, "year": year},
            )
        except SystemExit:
            continue
        if _media_shell_usable(detail):
            if isinstance(detail, dict) and not (detail.get("tmdb_id") or detail.get("tmdbid")):
                detail = {**detail, "tmdb_id": int(tmdbid)}
            return detail  # type: ignore[return-value]
    return None


def cmd_identify(args: argparse.Namespace) -> None:
    if args.tmdbid:
        detail = _fetch_tmdb_detail_for_identify(
            int(args.tmdbid),
            title=args.title,
            year=args.year,
            media_type=args.media_type,
        )
        if not detail:
            raise SystemExit(
                json.dumps(
                    {
                        "success": False,
                        "error": "identify_failed",
                        "tmdbid": args.tmdbid,
                        "hint": "tmdb detail empty for both movie/tv type_name",
                    },
                    ensure_ascii=False,
                )
            )
        print_json({"selected": detail, "source": "detail"})
        return
    all_results: list[Any] = []
    used_query = None
    for query in _title_variants(args.title):
        results = request("GET", "/api/v1/media/search", params={"title": query, "type": "media", "page": 1, "count": args.count})
        if isinstance(results, list):
            all_results.extend(results)
        if results:
            used_query = query
            break
    selected = _pick_media_search_result(all_results, title=args.title, media_type=args.media_type, year=args.year)
    print_json({"selected": selected, "results": all_results, "source": "media-search", "query": used_query})


def _load_json_arg(value: str) -> Any:
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def cmd_download(args: argparse.Namespace) -> None:
    media_in = extract_media_info(_load_json_arg(args.media_json)) if args.media_json else None
    if getattr(args, "from_search_result", None):
        search_item = _load_json_arg(args.from_search_result)
        torrent_in = extract_torrent_info(search_item)
        if media_in is None and isinstance(search_item, dict):
            maybe_media = search_item.get("media_info")
            if isinstance(maybe_media, dict) and maybe_media:
                media_in = maybe_media
    else:
        if not args.torrent_json:
            raise SystemExit("download requires --torrent-json or --from-search-result")
        torrent_in = extract_torrent_info(_load_json_arg(args.torrent_json))

    missing_torrent = validate_torrent_info(torrent_in)
    # Path-resolution dry-runs may only have type/language/country; require full media only for real downloads.
    missing_media = validate_media_info(media_in, require_full=bool(media_in) and not args.dry_run)
    if missing_torrent or missing_media:
        print_json(
            {
                "success": False,
                "error": "validation_failed",
                "missing_torrent_fields": missing_torrent,
                "missing_media_fields": missing_media,
                "hint": (
                    "Pass full search-result torrent_info (title/enclosure/site_name) "
                    "and full recognize media_info (type/title/tmdb_id). Prefer scripts/watch.py."
                ),
            }
        )
        raise SystemExit(2)

    save_path = args.save_path
    resolved = None
    if not save_path and media_in:
        paths = request("GET", "/api/v1/download/paths") or []
        category_config = request("GET", "/api/v1/media/category/config")
        resolved = choose_download_path(media_in, paths, category_config)
        save_path = resolved.get("save_path")
    if not save_path:
        raise SystemExit("Refusing to download without save_path. Pass --save-path or --media-json so it can be resolved.")
    if args.dry_run:
        print_json(
            {
                "dry_run": True,
                "endpoint": "/api/v1/download/" if media_in else "/api/v1/download/add",
                "save_path": save_path,
                "resolved_path": resolved,
                "media_in": media_in,
                "torrent_in": {k: torrent_in.get(k) for k in ["title", "site_name", "enclosure", "size", "seeders", "page_url"]},
                "downloader": args.downloader,
            }
        )
        return
    if media_in:
        body = {"media_in": media_in, "torrent_in": torrent_in, "downloader": args.downloader, "save_path": save_path}
        result = request("POST", "/api/v1/download/", body=body)
    else:
        body = {"torrent_in": torrent_in, "tmdbid": args.tmdbid, "doubanid": args.doubanid, "downloader": args.downloader, "save_path": save_path}
        result = request("POST", "/api/v1/download/add", body=body)
    if isinstance(result, dict) and result.get("success") is False:
        print_json(
            {
                **result,
                "hint": _download_error_hint("/api/v1/download/", 200, result),
                "next": "scripts/watch.py \"<title>\" --episode N  or re-run with --from-search-result full JSON",
            }
        )
        raise SystemExit(3)
    print_json(result)


def cmd_clients(_: argparse.Namespace) -> None:
    print_json(
        {
            "clients": request("GET", "/api/v1/download/clients"),
            "dashboard": request("GET", "/api/v1/dashboard/downloader"),
            "note": "GET /api/v1/download/ lists active tasks only; empty list does NOT mean downloaders are missing.",
        }
    )


def cmd_active(_: argparse.Namespace) -> None:
    print_json(request("GET", "/api/v1/download/") or [])


def cmd_cancel(args: argparse.Namespace) -> None:
    """Cancel/delete active download task(s) via DELETE /api/v1/download/{hash}."""
    active = request("GET", "/api/v1/download/") or []
    if not isinstance(active, list):
        active = []

    def match(item: dict[str, Any]) -> bool:
        if args.hash:
            h = str(item.get("hash") or "").lower()
            return h == str(args.hash).lower() or h.startswith(str(args.hash).lower())
        title = str(args.title or "").lower()
        tmdbid = args.tmdbid
        ep = args.episode
        blob = " ".join(
            str(x)
            for x in (
                item.get("title"),
                item.get("name"),
                item.get("season_episode"),
                item.get("path"),
                item.get("tags"),
            )
            if x
        ).lower()
        media = item.get("media") if isinstance(item.get("media"), dict) else {}
        ok = True
        if title:
            ok = ok and (title in blob or title in str(media.get("title") or "").lower())
        if tmdbid is not None:
            mid = media.get("tmdbid") or media.get("tmdb_id") or item.get("tmdbid")
            try:
                ok = ok and int(mid) == int(tmdbid)
            except (TypeError, ValueError):
                ok = False
        if ep is not None:
            se = str(item.get("season_episode") or "") + " " + str(media.get("episode") or "")
            ok = ok and (f"E{int(ep):02d}" in se.upper() or f"E{int(ep)}" in se.upper() or str(ep) in se)
        return ok

    matched = [it for it in active if isinstance(it, dict) and match(it)]
    if not matched:
        print_json(
            {
                "success": False,
                "error": "no_matching_active_download",
                "active_count": len(active),
                "filter": {"hash": args.hash, "title": args.title, "tmdbid": args.tmdbid, "episode": args.episode},
                "hint": "List first: mp_api.py active / media_ctl run status",
            }
        )
        return

    delete_files = bool(args.delete_files)
    results = []
    for it in matched:
        h = it.get("hash")
        name = it.get("downloader") or args.downloader or "QB"
        if not h:
            results.append({"success": False, "error": "missing_hash", "item": {"title": it.get("title")}})
            continue
        if args.dry_run:
            results.append(
                {
                    "success": True,
                    "dry_run": True,
                    "would_delete": {"hash": h, "downloader": name, "title": it.get("title"), "delete_files": delete_files},
                }
            )
            continue
        params: dict[str, Any] = {"name": name}
        # MoviePilot: DELETE /api/v1/download/{hashString}?name=QB
        # Some builds accept delete=true for removing files; pass when requested.
        if delete_files:
            params["delete"] = "true"
        try:
            resp = request("DELETE", f"/api/v1/download/{h}", params=params)
            results.append(
                {
                    "success": True,
                    "hash": h,
                    "downloader": name,
                    "title": it.get("title"),
                    "progress": it.get("progress"),
                    "response": resp,
                }
            )
        except SystemExit as e:
            # request() raises SystemExit with JSON on HTTP errors
            detail = str(e)
            try:
                detail = json.loads(detail)
            except json.JSONDecodeError:
                pass
            results.append({"success": False, "hash": h, "title": it.get("title"), "detail": detail})

    ok_n = sum(1 for r in results if r.get("success"))
    print_json(
        {
            "success": ok_n == len(results) and ok_n > 0,
            "cancelled": ok_n,
            "total_matched": len(matched),
            "delete_files": delete_files,
            "results": results,
        }
    )


def cmd_status(args: argparse.Namespace) -> None:
    active = request("GET", "/api/v1/download/") or []
    if not isinstance(active, list):
        active = []
    transfers = request("GET", "/api/v1/history/transfer", params={"page": 1, "count": args.count}) or {}
    transfer_list = []
    if isinstance(transfers, dict):
        data = transfers.get("data")
        if isinstance(data, dict):
            transfer_list = data.get("list") or []
        elif isinstance(data, list):
            transfer_list = data
    elif isinstance(transfers, list):
        transfer_list = transfers

    def match_active(item: dict[str, Any]) -> bool:
        media = item.get("media") or {}
        if args.tmdbid and int(media.get("tmdbid") or media.get("tmdb_id") or 0) == int(args.tmdbid):
            if args.episode is None:
                return True
            ep = str(media.get("episode") or "")
            return f"E{int(args.episode):02d}" in ep.upper() or str(args.episode) in ep
        blob = json.dumps(item, ensure_ascii=False)
        if args.title and args.title.lower() in blob.lower():
            return True
        return not args.tmdbid and not args.title

    def match_transfer(item: dict[str, Any]) -> bool:
        if args.tmdbid and int(item.get("tmdbid") or 0) == int(args.tmdbid):
            if args.episode is None:
                return True
            eps = str(item.get("episodes") or "")
            return f"E{int(args.episode):02d}" in eps.upper() or str(args.episode) in eps
        if args.title:
            return args.title.lower() in json.dumps(item, ensure_ascii=False).lower()
        return False

    matched_active = [x for x in active if isinstance(x, dict) and match_active(x)]
    matched_transfers = [x for x in transfer_list if isinstance(x, dict) and match_transfer(x)]
    state = "idle"
    if matched_active:
        state = "downloading"
    elif matched_transfers:
        state = "transferred"
    print_json(
        {
            "state": state,
            "active": matched_active,
            "transfers": matched_transfers[: max(1, args.count)],
            "clients": request("GET", "/api/v1/download/clients"),
            "note": "Empty active list means no running tasks, not missing downloaders.",
        }
    )


def cmd_pick(args: argparse.Namespace) -> None:
    payload = _load_json_arg(args.results_json)
    if isinstance(payload, dict):
        items = payload.get("data") if isinstance(payload.get("data"), list) else payload.get("results") or payload.get("items") or []
        if not items and isinstance(payload.get("selected"), dict):
            items = [payload["selected"]]
    elif isinstance(payload, list):
        items = payload
    else:
        raise SystemExit("results-json must be list or object containing data/results")
    site_priority = [s.strip() for s in (args.site_priority or "").split(",") if s.strip()] or None
    picked = pick_torrent(
        items,
        season=args.season,
        episode=args.episode,
        media_year=getattr(args, "media_year", None),
        max_age_days=getattr(args, "max_age_days", None),
        prefer_resolution=args.resolution or "1080p",
        site_priority=site_priority,
        top_n=args.top,
    )
    print_json(
        {
            "selected_summary": summarize_candidate(picked["selected"]) if picked.get("selected") else None,
            "candidates": [summarize_candidate(x) for x in picked.get("candidates") or []],
            "selected": picked.get("selected"),
            "reason": picked.get("reason"),
            "score": picked.get("score"),
            "needs_confirm": picked.get("needs_confirm"),
            "confirm_reasons": picked.get("confirm_reasons") or [],
            "year_match": picked.get("year_match"),
            "pubdate_age_days": picked.get("pubdate_age_days"),
        }
    )


def cmd_subscribe_get(args: argparse.Namespace) -> None:
    mediaid = args.mediaid or f"tmdb:{args.tmdbid}"
    print_json(request("GET", f"/api/v1/subscribe/media/{urllib.parse.quote(mediaid, safe=':')}", params={"season": args.season, "title": args.title}))


def cmd_subscribe(args: argparse.Namespace) -> None:
    body: dict[str, Any] = _load_json_arg(args.json) if args.json else {}
    if args.name:
        body["name"] = args.name
    if args.media_type:
        body["type"] = normalize_mtype(args.media_type)
    if args.year:
        body["year"] = args.year
    if args.tmdbid:
        body["tmdbid"] = int(args.tmdbid)
        body.setdefault("mediaid", f"tmdb:{args.tmdbid}")
    if args.season is not None:
        body["season"] = args.season
    if args.sites:
        body["sites"] = [int(x) for x in args.sites.split(",") if x.strip()]
    if args.resolution:
        body["resolution"] = args.resolution
    if args.quality:
        body["quality"] = args.quality
    if args.save_path:
        body["save_path"] = args.save_path
    if args.downloader:
        body["downloader"] = args.downloader
    if args.dry_run:
        print_json({"dry_run": True, "endpoint": "/api/v1/subscribe/", "body": body})
        return
    print_json(request("POST", "/api/v1/subscribe/", body=body))


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MoviePilot REST helper for media-mgmt")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("get", help="GET arbitrary MoviePilot API path")
    p.add_argument("path")
    p.add_argument("param", nargs="*", help="query params as key=value")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("post", help="POST arbitrary MoviePilot API path")
    p.add_argument("path")
    p.add_argument("param", nargs="*", help="query params as key=value")
    p.add_argument("--json", default="{}", help="JSON request body")
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("paths", help="List configured download paths")
    p.set_defaults(func=cmd_paths)

    p = sub.add_parser("category", help="Show media category config")
    p.set_defaults(func=cmd_category)

    p = sub.add_parser("resolve-path", help="Resolve save_path from media JSON")
    p.add_argument("media_json", help='e.g. {"type":"tv","origin_country":["KR"],"original_language":"ko"}')
    p.set_defaults(func=cmd_resolve_path)

    p = sub.add_parser("search", help="Search resources by media id")
    p.add_argument("--mediaid", help="tmdb:123 / douban:123 / bangumi:123")
    p.add_argument("--tmdbid", help="TMDB id; becomes tmdb:<id>")
    p.add_argument("--media-type", dest="media_type", help="movie/tv or MoviePilot mtype")
    p.add_argument("--title")
    p.add_argument("--year")
    p.add_argument("--season")
    p.add_argument("--sites")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("title", help="Fuzzy search resources by title")
    p.add_argument("keyword")
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--sites")
    p.set_defaults(func=cmd_title)

    p = sub.add_parser("media-search", help="Search MoviePilot/TMDB media metadata by title")
    p.add_argument("title")
    p.add_argument("--kind", default="media", help="media or person")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--count", type=int, default=8)
    p.set_defaults(func=cmd_media_search)

    p = sub.add_parser("recognize", help="Recognize media from torrent/title text")
    p.add_argument("title")
    p.add_argument("--subtitle")
    p.set_defaults(func=cmd_recognize)

    p = sub.add_parser("media-detail", help="Get media detail by tmdb/media id")
    p.add_argument("--mediaid")
    p.add_argument("--tmdbid")
    p.add_argument("--media-type", dest="media_type", required=True, help="movie/tv or Chinese type")
    p.add_argument("--title")
    p.add_argument("--year")
    p.set_defaults(func=cmd_media_detail)

    p = sub.add_parser("identify", help="Identify what the user wants to watch")
    p.add_argument("title", nargs="?")
    p.add_argument("--tmdbid")
    p.add_argument("--media-type", dest="media_type", help="movie/tv or Chinese type")
    p.add_argument("--year")
    p.add_argument("--count", type=int, default=8)
    p.set_defaults(func=cmd_identify)

    p = sub.add_parser("download", help="Add download with explicit or resolved save_path")
    p.add_argument("--torrent-json", help="TorrentInfo JSON or path")
    p.add_argument("--from-search-result", help="Full search result JSON/path; extracts torrent_info (+ media_info if present)")
    p.add_argument("--media-json", help="MediaInfo JSON or path; enables /api/v1/download/ and path resolution")
    p.add_argument("--save-path")
    p.add_argument("--downloader")
    p.add_argument("--tmdbid", type=int)
    p.add_argument("--doubanid")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("clients", help="List configured download clients (NOT active tasks)")
    p.set_defaults(func=cmd_clients)

    p = sub.add_parser("active", help="List active download tasks (GET /api/v1/download/)")
    p.set_defaults(func=cmd_active)

    p = sub.add_parser("cancel", help="Cancel/delete active download(s) by hash/title/tmdb/episode")
    p.add_argument("--hash", help="Torrent hash (prefix ok)")
    p.add_argument("--title")
    p.add_argument("--tmdbid", type=int)
    p.add_argument("--episode", type=int)
    p.add_argument("--downloader", help="Downloader name fallback (default QB / task value)")
    p.add_argument("--delete-files", action="store_true", help="Also delete downloaded files when supported")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("status", help="Status for a title/tmdb/episode across active downloads + transfer history")
    p.add_argument("--title")
    p.add_argument("--tmdbid", type=int)
    p.add_argument("--episode", type=int)
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("pick", help="Rank/filter torrent search results")
    p.add_argument("--results-json", required=True, help="Search result list/object JSON or path")
    p.add_argument("--season", type=int)
    p.add_argument("--episode", type=int)
    p.add_argument("--media-year", dest="media_year", help="Media production year for year-gate")
    p.add_argument("--max-age-days", type=float, help="Stale pubdate threshold in days")
    p.add_argument("--resolution", default="1080p")
    p.add_argument("--site-priority", help="comma-separated preferred site names")
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(func=cmd_pick)

    p = sub.add_parser("subscribe-get", help="Get subscription by media id")
    p.add_argument("--mediaid")
    p.add_argument("--tmdbid")
    p.add_argument("--season", type=int)
    p.add_argument("--title")
    p.set_defaults(func=cmd_subscribe_get)

    p = sub.add_parser("subscribe", help="Create MoviePilot subscription")
    p.add_argument("--json", help="Full Subscribe JSON or path")
    p.add_argument("--name")
    p.add_argument("--media-type", dest="media_type")
    p.add_argument("--year")
    p.add_argument("--tmdbid")
    p.add_argument("--season", type=int)
    p.add_argument("--sites", help="comma-separated site ids")
    p.add_argument("--resolution")
    p.add_argument("--quality")
    p.add_argument("--save-path")
    p.add_argument("--downloader")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_subscribe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
