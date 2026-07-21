"""HTTP client for NextFind Agent OpenAPI.

Base: http://host:port/api/openapi
Auth: Header X-API-Key
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _norm_media_type(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in {"movie", "电影", "film", "films", "mov"}:
        return "movie"
    if s in {"tv", "电视剧", "剧集", "anime", "动漫", "series", "show"}:
        return "tv"
    return s or "movie"


class NextFindClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 45.0,
        prefix: str = "/api/openapi",
    ) -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key or "").strip()
        self.timeout = float(timeout or 45.0)
        pref = str(prefix or "/api/openapi").strip() or "/api/openapi"
        if not pref.startswith("/"):
            pref = "/" + pref
        self.prefix = pref.rstrip("/") or "/api/openapi"

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        p = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{self.prefix}{p}"
        if query:
            q = {k: v for k, v in query.items() if v not in (None, "")}
            if q:
                url += "?" + urllib.parse.urlencode(q)
        return url

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            return {"success": False, "error": "missing_base_url"}
        if not self.api_key:
            return {"success": False, "error": "missing_api_key"}
        url = self._url(path, query)
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "media-mgmt-nextfind/1.0",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        to = self.timeout if timeout is None else float(timeout)
        try:
            with urllib.request.urlopen(req, timeout=to) as resp:
                raw = resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            code = e.code
            text = raw.decode("utf-8", "replace") if raw else str(e)
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {"detail": text[:500]}
            return {
                "success": False,
                "error": "http_error",
                "http_status": code,
                "detail": parsed,
                "path": path,
            }
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": "request_failed", "detail": str(e), "path": path}

        text = raw.decode("utf-8", "replace") if raw else ""
        try:
            parsed: Any = json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "bad_json",
                "http_status": code,
                "raw": text[:500],
                "path": path,
            }

        if isinstance(parsed, dict):
            status = str(parsed.get("status") or "").lower()
            if status == "error":
                return {
                    "success": False,
                    "error": "api_error",
                    "http_status": code,
                    "message": parsed.get("message") or parsed.get("detail"),
                    "data": parsed.get("data"),
                    "path": path,
                }
            if status == "success" or "data" in parsed:
                return {
                    "success": True,
                    "http_status": code,
                    "data": parsed.get("data"),
                    "raw": parsed,
                    "path": path,
                }
            return {"success": True, "http_status": code, "data": parsed, "path": path}

        return {"success": True, "http_status": code, "data": parsed, "path": path}

    def search(self, query: str, media_type: str | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {"query": query}
        if media_type:
            t = _norm_media_type(media_type)
            q["type"] = "电影" if t == "movie" else ("剧集" if t == "tv" else media_type)
        return self.request("GET", "/search", query=q)

    def resources_search(
        self,
        tmdb_id: str | int,
        media_type: str,
        *,
        season: int | None = None,
        episode: int | None = None,
    ) -> dict[str, Any]:
        q: dict[str, Any] = {
            "tmdb_id": str(tmdb_id),
            "media_type": _norm_media_type(media_type),
        }
        if season not in (None, ""):
            q["season"] = season
        if episode not in (None, ""):
            q["episode"] = episode
        return self.request("GET", "/resources/search", query=q)

    def preview(self, slug: str) -> dict[str, Any]:
        return self.request("POST", "/preview", body={"slug": str(slug)})

    def hdhive_unlock(self, resource_id: str | int, resource_type: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/hdhive/unlock",
            body={"id": resource_id, "type": resource_type},
        )

    def quota(self) -> dict[str, Any]:
        return self.request("GET", "/quota")

    def transfer(self, slug: str, target_folder: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"slug": str(slug)}
        if target_folder:
            body["target_folder"] = target_folder
        return self.request("POST", "/transfer", body=body)

    def directories(self, cid: str | None = None) -> dict[str, Any]:
        q = {"cid": cid} if cid not in (None, "") else None
        return self.request("GET", "/directories", query=q)

    def create_directory(self, parent_cid: str, name: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/directories",
            body={"parent_cid": parent_cid, "name": name},
        )

    def local_library_filter(self, status_filter: str = "missing") -> dict[str, Any]:
        return self.request(
            "GET",
            "/local_library/filter",
            query={"status_filter": status_filter},
        )

    def logs(self) -> dict[str, Any]:
        return self.request("GET", "/logs")

    def history(self) -> dict[str, Any]:
        return self.request("GET", "/history")

    def subscriptions(self) -> dict[str, Any]:
        return self.request("GET", "/subscriptions")

    def subscriptions_add(self, tmdb_id: str | int, media_type: str, **extra: Any) -> dict[str, Any]:
        body = {
            "tmdb_id": str(tmdb_id),
            "media_type": _norm_media_type(media_type),
            **extra,
        }
        return self.request("POST", "/subscriptions/add", body=body)

    def subscriptions_remove(self, tmdb_id: str | int, media_type: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "/subscriptions/remove",
            body={"tmdb_id": str(tmdb_id), "media_type": _norm_media_type(media_type)},
        )

    def subscriptions_info(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", "/subscriptions/info", body={"items": items})

    def fill_missing(self, **body: Any) -> dict[str, Any]:
        return self.request("POST", "/media/fill_missing", body=body or {})

    def delete_media_episode(
        self,
        tmdb_id: str | int,
        season: int | str,
        episode: int | str,
    ) -> dict[str, Any]:
        return self.request(
            "DELETE",
            "/media/episode",
            query={
                "tmdb_id": str(tmdb_id),
                "season": season,
                "episode": episode,
            },
        )

    def delete_media_season(self, tmdb_id: str | int, season: int | str) -> dict[str, Any]:
        return self.request(
            "DELETE",
            "/media/season",
            query={"tmdb_id": str(tmdb_id), "season": season},
        )

    def delete_media_movie(self, tmdb_id: str | int) -> dict[str, Any]:
        return self.request(
            "DELETE",
            "/media/movie",
            query={"tmdb_id": str(tmdb_id)},
        )

    def history_delete_all(self) -> dict[str, Any]:
        return self.request("DELETE", "/history/all")

    def history_delete_item(
        self,
        *,
        tmdb_id: str | int | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        q: dict[str, Any] = {}
        if tmdb_id not in (None, ""):
            q["tmdb_id"] = str(tmdb_id)
        if title not in (None, ""):
            q["title"] = title
        return self.request("DELETE", "/history/item", query=q or None)

    def settings_tg_channels_get(self) -> dict[str, Any]:
        return self.request("GET", "/settings/tg_channels")

    def settings_tg_channels_set(self, body: dict[str, Any] | list[Any]) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {"channels": body}
        return self.request("POST", "/settings/tg_channels", body=payload)

    def settings_rss_get(self) -> dict[str, Any]:
        return self.request("GET", "/settings/rss")

    def settings_rss_set(self, body: dict[str, Any] | list[Any]) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {"items": body}
        return self.request("POST", "/settings/rss", body=payload)

    def settings_rules_set(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/settings/rules", body=body or {})

    def settings_transfer_folder_set(self, folder: str, **extra: Any) -> dict[str, Any]:
        body = {"folder": folder, **extra} if folder else dict(extra)
        # accept common aliases used by callers
        if "transfer_folder" not in body and "path" in body:
            body["transfer_folder"] = body.get("path")
        if "folder" in body and "transfer_folder" not in body:
            body["transfer_folder"] = body["folder"]
        return self.request("POST", "/settings/transfer_folder", body=body)

    def ignored_episodes_toggle(
        self,
        tmdb_id: str | int,
        media_type: str,
        season: int | str,
        **extra: Any,
    ) -> dict[str, Any]:
        body = {
            "tmdb_id": str(tmdb_id),
            "media_type": _norm_media_type(media_type),
            "season": season,
            **extra,
        }
        return self.request("POST", "/ignored_episodes/toggle", body=body)

    def health(self) -> dict[str, Any]:
        r = self.quota()
        if r.get("success"):
            return {
                "success": True,
                "status": "ok",
                "quota": r.get("data"),
                "base_url": self.base_url,
            }
        return {
            "success": False,
            "status": "down",
            "error": r.get("error"),
            "detail": r.get("detail") or r.get("message"),
            "http_status": r.get("http_status"),
            "base_url": self.base_url,
        }


def client_from_config(cfg: dict[str, Any] | None) -> NextFindClient | None:
    sec = (cfg or {}).get("nextfind") if isinstance(cfg, dict) else None
    if not isinstance(sec, dict):
        return None
    base = str(sec.get("base_url") or sec.get("url") or "").strip()
    key = str(sec.get("api_key") or sec.get("openapi_key") or "").strip()
    if not base or not key:
        return None
    timeout = float(sec.get("timeout") or 45)
    prefix = str(sec.get("prefix") or "/api/openapi")
    return NextFindClient(base, key, timeout=timeout, prefix=prefix)
