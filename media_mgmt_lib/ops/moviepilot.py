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
