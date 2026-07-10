"""MoviePilot ops wrappers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import register_op
from media_mgmt_lib.ops._runner import run_mp_api

ROOT = Path(__file__).resolve().parents[2]


def _write_tmp(name: str, payload: Any) -> str:
    path = Path("/tmp") / f"media-mgmt-{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


def op_clients(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return run_mp_api(["clients"])


def op_active(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return run_mp_api(["active"])


def op_identify(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    if not title and not params.get("tmdbid"):
        return {"success": False, "error": "missing_param", "need": "title|tmdbid"}
    args = ["identify"]
    if title:
        args.append(str(title))
    if params.get("media_type"):
        args += ["--media-type", str(params["media_type"])]
    if params.get("year"):
        args += ["--year", str(params["year"])]
    if params.get("tmdbid"):
        args += ["--tmdbid", str(params["tmdbid"])]
    return run_mp_api(args)


def op_status(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    args = ["status"]
    if params.get("tmdbid"):
        args += ["--tmdbid", str(params["tmdbid"])]
    if params.get("title"):
        args += ["--title", str(params["title"])]
    if params.get("episode") is not None:
        args += ["--episode", str(params["episode"])]
    if params.get("count"):
        args += ["--count", str(params["count"])]
    return run_mp_api(args)


def op_search(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid")
    if tmdbid:
        media_type = params.get("media_type") or "tv"
        # mp_api search uses mediaid path via search subcommand
        return run_mp_api(["search", f"tmdb:{tmdbid}"])
    if not title:
        return {"success": False, "error": "missing_param", "need": "title|tmdbid"}
    return run_mp_api(["title", str(title)])


def op_download(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Download via mp_api. Prefer paths to JSON files or inline JSON strings.

    params:
      torrent_json / from_search_result / media_json: path or JSON string
      save_path, downloader, dry_run
    """
    args = ["download"]
    for key, flag in (
        ("from_search_result", "--from-search-result"),
        ("torrent_json", "--torrent-json"),
        ("media_json", "--media-json"),
        ("save_path", "--save-path"),
        ("downloader", "--downloader"),
        ("tmdbid", "--tmdbid"),
        ("doubanid", "--doubanid"),
    ):
        if params.get(key) is not None and params.get(key) != "":
            val = params[key]
            if key in {"from_search_result", "torrent_json", "media_json"} and not isinstance(val, str):
                val = _write_tmp(key, val)
            elif key in {"from_search_result", "torrent_json", "media_json"} and isinstance(val, str):
                s = val.strip()
                if s.startswith("{") or s.startswith("["):
                    val = _write_tmp(key, json.loads(s))
            args += [flag, str(val)]
    if str(params.get("dry_run", "")).lower() in {"1", "true", "yes"} or params.get("dry_run") is True:
        args.append("--dry-run")
    if not any(x in args for x in ("--from-search-result", "--torrent-json")):
        return {
            "success": False,
            "error": "missing_param",
            "need": "from_search_result|torrent_json (+ media_json recommended)",
            "hint": "Prefer media_ctl watch workflow for full download path.",
        }
    return run_mp_api(args, timeout=180)


def op_subscribe(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    if str(params.get("action") or "create") == "get":
        args = ["subscribe-get"]
        if params.get("mediaid"):
            args += ["--mediaid", str(params["mediaid"])]
        if params.get("tmdbid"):
            args += ["--tmdbid", str(params["tmdbid"])]
        if params.get("season") is not None:
            args += ["--season", str(params["season"])]
        if params.get("title"):
            args += ["--title", str(params["title"])]
        return run_mp_api(args)

    args = ["subscribe"]
    if params.get("json"):
        val = params["json"]
        if not isinstance(val, str):
            val = _write_tmp("subscribe", val)
        elif val.strip().startswith("{"):
            val = _write_tmp("subscribe", json.loads(val))
        args += ["--json", str(val)]
    for key, flag in (
        ("name", "--name"),
        ("media_type", "--media-type"),
        ("year", "--year"),
        ("tmdbid", "--tmdbid"),
        ("season", "--season"),
        ("sites", "--sites"),
        ("resolution", "--resolution"),
        ("quality", "--quality"),
        ("save_path", "--save-path"),
        ("downloader", "--downloader"),
    ):
        if params.get(key) is not None and params.get(key) != "":
            args += [flag, str(params[key])]
    if str(params.get("dry_run", "")).lower() in {"1", "true", "yes"} or params.get("dry_run") is True:
        args.append("--dry-run")
    if len(args) == 1:
        return {"success": False, "error": "missing_param", "need": "name+tmdbid or json", "hint": "action=get for lookup"}
    return run_mp_api(args)


def op_paths(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return run_mp_api(["paths"])


def op_transfer_share(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """115 share transfer via P115StrmHelper plugin."""
    from media_mgmt_lib.providers.hdhive.grab import transfer_share_to_moviepilot

    share_url = params.get("share_url") or params.get("url")
    if not share_url:
        return {"success": False, "error": "missing_param", "need": "share_url"}
    try:
        result = transfer_share_to_moviepilot(str(share_url))
        ok = result.get("code") == 0 or "已经转存" in str(result.get("msg") or "")
        return {"success": ok, "result": result}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "transfer_failed", "detail": str(e)}


register_op("moviepilot", "clients", op_clients)
register_op("moviepilot", "active", op_active)
register_op("moviepilot", "identify", op_identify)
register_op("moviepilot", "status", op_status)
register_op("moviepilot", "search", op_search)
register_op("moviepilot", "download", op_download)
register_op("moviepilot", "subscribe", op_subscribe)
register_op("moviepilot", "paths", op_paths)
register_op("moviepilot", "transfer_share", op_transfer_share)
register_op("qbittorrent", "clients", op_clients)
register_op("transmission", "clients", op_clients)


def op_library_exists(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Check if media exists in mediaserver library."""
    import urllib.parse
    import urllib.request
    import json as _json
    from media_mgmt_lib.config import moviepilot_credentials, load_json_config

    creds = moviepilot_credentials(cfg if cfg else load_json_config())
    if not creds:
        return {"success": False, "error": "missing_moviepilot_config"}
    q = {"apikey": creds["API_KEY"]}
    for src, dst in (("title", "title"), ("year", "year"), ("mtype", "mtype"), ("media_type", "mtype"), ("tmdbid", "tmdbid"), ("season", "season")):
        if params.get(src) is not None and params.get(src) != "":
            q[dst] = params[src]
    if "title" not in q and "tmdbid" not in q:
        return {"success": False, "error": "missing_param", "need": "title|tmdbid"}
    # title-only often more reliable for Emby match
    url = f"{creds['BASE_URL'].rstrip('/')}/api/v1/mediaserver/exists?{urllib.parse.urlencode(q)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = _json.loads(resp.read().decode())
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "request_failed", "detail": str(e)}
    item = (body.get("data") or {}).get("item") if isinstance(body, dict) else None
    exists = isinstance(item, dict) and bool(item)
    return {"success": True, "exists": exists, "item": item if exists else None, "raw": body, "query": {k: q[k] for k in q if k != "apikey"}}


def op_missing_episodes(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Which episodes are missing in library (mediaserver/notexists)."""
    import json as _json
    import urllib.parse
    import urllib.request
    from media_mgmt_lib.config import moviepilot_credentials, load_json_config
    from media_mgmt_lib.ops._runner import run_mp_api

    creds = moviepilot_credentials(cfg if cfg else load_json_config())
    if not creds:
        return {"success": False, "error": "missing_moviepilot_config"}
    media = params.get("media") or params.get("media_json")
    if isinstance(media, str) and media.strip().startswith("{"):
        media = _json.loads(media)
    if not isinstance(media, dict):
        title = params.get("title")
        tmdbid = params.get("tmdbid")
        if not title and not tmdbid:
            return {"success": False, "error": "missing_param", "need": "title|tmdbid|media"}
        args = ["identify"]
        if title:
            args.append(str(title))
        if tmdbid:
            args += ["--tmdbid", str(tmdbid)]
        mt = params.get("media_type") or params.get("mtype")
        if mt:
            args += ["--media-type", str(mt)]
        identified = run_mp_api(args)
        media = identified.get("selected") if isinstance(identified, dict) else None
        if not isinstance(media, dict):
            return {"success": False, "error": "identify_failed", "detail": identified}
    url = f"{creds['BASE_URL'].rstrip('/')}/api/v1/mediaserver/notexists?{urllib.parse.urlencode({'apikey': creds['API_KEY']})}"
    data = _json.dumps(media, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            missing = _json.loads(raw) if raw else []
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "notexists_failed", "detail": str(e)}
    episodes = []
    if isinstance(missing, list):
        for block in missing:
            if isinstance(block, dict):
                for ep in block.get("episodes") or []:
                    episodes.append({"season": block.get("season"), "episode": ep, **{k: block.get(k) for k in ("total_episode", "start_episode") if k in block}})
    has_update = len(episodes) > 0
    return {
        "success": True,
        "has_update": has_update,
        "missing": missing,
        "missing_episodes": episodes,
        "media": {
            "title": media.get("title"),
            "tmdb_id": media.get("tmdb_id") or media.get("tmdbid"),
            "type": media.get("type") or media.get("media_type"),
            "year": media.get("year"),
        },
        "summary": f"缺 {len(episodes)} 集" if has_update else "媒体库已齐或无法比对缺集",
    }


def op_transfer_history(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    import urllib.parse
    import urllib.request
    import json as _json
    from media_mgmt_lib.config import moviepilot_credentials, load_json_config

    creds = moviepilot_credentials(cfg if cfg else load_json_config())
    q = {"apikey": creds["API_KEY"], "page": params.get("page") or 1, "count": params.get("count") or 50}
    if params.get("title"):
        q["title"] = params["title"]
    if params.get("status"):
        q["status"] = params["status"]
    url = f"{creds['BASE_URL'].rstrip('/')}/api/v1/history/transfer?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = _json.loads(resp.read().decode())
    return {"success": True, "data": body}


def op_download_history(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    import urllib.parse
    import urllib.request
    import json as _json
    from media_mgmt_lib.config import moviepilot_credentials, load_json_config

    creds = moviepilot_credentials(cfg if cfg else load_json_config())
    q = {"apikey": creds["API_KEY"], "page": params.get("page") or 1, "count": params.get("count") or 50}
    url = f"{creds['BASE_URL'].rstrip('/')}/api/v1/history/download?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = _json.loads(resp.read().decode())
    return {"success": True, "data": body}


def op_subscribe_list(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    from media_mgmt_lib.ops._runner import run_mp_api
    return run_mp_api(["get", "/api/v1/subscribe/"])


def op_mediaserver_clients(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    from media_mgmt_lib.ops._runner import run_mp_api
    return run_mp_api(["get", "/api/v1/mediaserver/clients"])


def op_library_latest(svc: Service, cfg: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    from media_mgmt_lib.ops._runner import run_mp_api
    server = params.get("server") or "EMBY"
    count = params.get("count") or 20
    return run_mp_api(["get", "/api/v1/mediaserver/latest", f"server={server}", f"count={count}"])


register_op("moviepilot", "library_exists", op_library_exists)
register_op("moviepilot", "missing_episodes", op_missing_episodes)
register_op("moviepilot", "transfer_history", op_transfer_history)
register_op("moviepilot", "download_history", op_download_history)
register_op("moviepilot", "subscribe_list", op_subscribe_list)
register_op("moviepilot", "mediaserver_clients", op_mediaserver_clients)
register_op("moviepilot", "library_latest", op_library_latest)
