"""Parser for ``hongguoduanju.com`` (the public web frontend for Hongguo).

The downloader only uses public information: the SSR HTML embeds a
``window._ROUTER_DATA`` blob that contains the full series metadata and, on the
``/player/{series_id}/{vid}`` route, the actual media URL plus its duration.

This module re-implements the surface area that ``hongguo_downloader.py`` needs:

* :data:`MOBILE_UA`, :data:`WEB_UA`, :data:`DEFAULT_TIMEOUT`,
  :data:`LOCAL_PROXY_EXAMPLE`
* :class:`ParseError`
* :func:`make_session`, :func:`to_int`, :func:`iso_utc`
* :func:`media_url_expiry`, :func:`media_clip_seconds`
* :func:`load_series_seed`, :func:`request_player_for_vid`

Public episodes (the first ``accessible_episode_cnt`` ones) resolve to full
MP4 URLs.  Everything else returns ``None`` so the downloader can raise an
``EpisodeLockedError`` and stop or fall back to its authorised-API path.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
    "Mobile/15E148 Safari/604.1"
)
DEFAULT_TIMEOUT = 30
LOCAL_PROXY_EXAMPLE = "http://127.0.0.1:7890"

BASE_URL = "https://hongguoduanju.com"
# novelquickapp.com is the share-link domain for 红果短剧 (Hongguo).
# Its SSR uses `series_data` inside `pageData` instead of `seriesDetail`.
_SHARE_DOMAINS = {"novelquickapp.com", "hongguoduanju.com"}


class ParseError(RuntimeError):
    """Raised when a Hongguo page cannot be parsed."""


def to_int(value: Any) -> int | None:
    """Best-effort conversion of ``value`` to ``int``; returns ``None`` on failure."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 10)
        except ValueError:
            match = re.search(r"-?\d+", text)
            return int(match.group(0)) if match else None
    return None


def iso_utc() -> str:
    """Return the current UTC time in ISO-8601 with a trailing ``Z``."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def make_session(proxy: str | None = None) -> requests.Session:
    """Build a :class:`requests.Session` with the web UA and an optional proxy."""
    session = requests.Session()
    session.trust_env = False
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.headers.update(
        {
            "User-Agent": WEB_UA,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
    )
    return session


def media_url_expiry(url: str | None) -> int | None:
    """Estimate when ``url`` stops being valid (unix seconds).

    Byteview/Volcengine URLs include a ``dy_q`` query parameter that is the
    generation timestamp.  The CDN typically honours them for ~24 hours, so we
    return ``dy_q + 86400`` when available.
    """
    if not url:
        return None
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError:
        return None
    if "dy_q" in params:
        ts = to_int(params["dy_q"][0])
        if ts is None:
            return None
        if ts > 10**12:  # microseconds
            ts //= 1000
        return ts + 24 * 3600
    return None


def media_clip_seconds(url: str | None) -> int | None:
    """Return ``30`` for known preview URLs, otherwise ``None``."""
    if not url:
        return None
    lowered = url.lower()
    if any(token in lowered for token in ("preview", "trial", "sample")):
        return 30
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_router_data(html: str) -> dict[str, Any]:
    """Parse the ``window._ROUTER_DATA = {...};`` payload from an SSR page."""
    marker = "window._ROUTER_DATA"
    idx = html.find(marker)
    if idx < 0:
        raise ParseError("page did not embed window._ROUTER_DATA")
    start = html.find("{", idx)
    if start < 0:
        raise ParseError("could not locate JSON object start in _ROUTER_DATA")
    depth = 0
    in_string = False
    escape = False
    end = -1
    for j in range(start, len(html)):
        ch = html[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = j
                break
    if end < 0:
        raise ParseError("could not locate JSON object end in _ROUTER_DATA")
    try:
        return json.loads(html[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid _ROUTER_DATA JSON: {exc}") from exc


def _is_supported_host(netloc: str) -> bool:
    return any(d in netloc for d in _SHARE_DOMAINS)


def _series_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and not _is_supported_host(parsed.netloc):
        raise ParseError(f"unsupported host: {parsed.netloc!r}")
    query = parse_qs(parsed.query)
    if "series_id" in query and query["series_id"]:
        return str(query["series_id"][0])
    # novelquickapp share links carry video_series_id in schemeParams
    zlink = query.get("zlink", [""])[0]
    if zlink:
        inner = parse_qs(urlparse(zlink).query).get("schemeParams", [""])[0]
        if inner:
            try:
                sp = json.loads(inner)
                sid = sp.get("video_series_id")
                if sid:
                    return str(sid)
            except (json.JSONDecodeError, ValueError):
                pass
    # novelquickapp short links: extract series_id from redirect target
    if "novelquickapp.com" in parsed.netloc:
        match = re.search(r"video_series_id[^\d]*(\d{10,})", url)
        if match:
            return match.group(1)
    match = re.search(r"/player/(\d+)", parsed.path)
    if match:
        return match.group(1)
    match = re.search(r"/detail/(\d+)", parsed.path)
    if match:
        return match.group(1)
    raise ParseError(f"could not extract series_id from {url!r}")


def _extract_series_id_from_html(html: str, url: str) -> str:
    """Extract series_id from the SSR HTML when URL parsing fails."""
    # Try from zlink in the redirect URL
    match = re.search(r"video_series_id[^\d]*(\d{10,})", html)
    if match:
        return match.group(1)
    # Try from schemeParams in JSON
    match = re.search(r'"video_series_id":\s*"(\d+)"', html)
    if match:
        return match.group(1)
    return _series_id_from_url(url)


def _vid_from_url(url: str) -> str | None:
    match = re.search(r"/player/\d+/(\d+)", urlparse(url).path)
    return match.group(1) if match else None


def _normalise_series_from_detail(sd: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    """Normalise hongguoduanju.com `seriesDetail` format."""
    vid_list = [str(value) for value in (sd.get("vid_list") or []) if value]
    if not vid_list:
        raise ParseError("seriesDetail.vid_list missing")
    series_id = str(sd.get("series_id") or "")
    if not series_id:
        raise ParseError("seriesDetail.series_id missing")
    return {
        "series_id": series_id,
        "title": sd.get("series_name"),
        "intro": sd.get("series_intro"),
        "cover": sd.get("series_cover"),
        "tags": list(sd.get("tags") or []),
        "chapter_ids": vid_list,
        "episode_count": to_int(sd.get("episode_cnt")) or len(vid_list),
        "accessible_episode_count": to_int(sd.get("accessible_episode_cnt")) or 0,
        "content_type": "standard",
        "web_id": req.get("webID"),
        "uuid": req.get("uuid"),
        "celebrities": list(sd.get("celebrities") or []),
    }


def _normalise_series_from_share(
    page_data: dict[str, Any],
    series_id: str,
) -> dict[str, Any]:
    """Normalise novelquickapp.com share-page format.

    ``page_data`` is the full ``pageData`` dict from loaderData, which contains
    both ``series_data`` (metadata) and ``chapter_ids`` (episode list).
    ``series_id`` is pre-extracted from the URL's ``zlink`` query parameter.
    """
    sd = page_data.get("series_data") or {}
    vid_list = [str(v) for v in (page_data.get("chapter_ids") or sd.get("chapter_ids") or []) if v]
    if not vid_list:
        raise ParseError("pageData.chapter_ids missing")
    serial_count = to_int(sd.get("serial_count"))
    return {
        "series_id": series_id,
        "title": sd.get("title"),
        "intro": sd.get("series_intro"),
        "cover": sd.get("series_cover"),
        "tags": list(sd.get("category_list") or sd.get("tags") or []),
        "chapter_ids": vid_list,
        "episode_count": serial_count or len(vid_list),
        "accessible_episode_count": serial_count or len(vid_list),  # share page lists all
        "content_type": "standard",
        "web_id": None,
        "uuid": None,
        "celebrities": list(sd.get("actor_list") or []),
        "play_url": sd.get("play_url"),  # first-episode play URL from share page
        "source": "novelquickapp_share",
    }


def _normalise_series(sd: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    """Try share-page format first, then detail-page format."""
    # share-page indicator: has chapter_ids + title but no vid_list
    if "chapter_ids" in sd and "vid_list" not in sd:
        return _normalise_series_from_share(sd, req)
    return _normalise_series_from_detail(sd, req)


# ---------------------------------------------------------------------------
# Public API used by hongguo_downloader.py
# ---------------------------------------------------------------------------


def load_series_seed(
    session: requests.Session,
    input_url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[dict[str, Any], str, None]:
    """Resolve a detail, player, or share URL into the downloader's seed structure.

    Returns a ``(series, referer, None)`` tuple.  ``series`` matches the keys
    ``run_download`` expects: ``series_id``, ``title``, ``chapter_ids``,
    ``episode_count``, ``accessible_episode_count``, ``content_type``,
    ``web_id``.
    """
    parsed = urlparse(input_url)
    is_share_domain = any(d in parsed.netloc for d in _SHARE_DOMAINS)

    # For novelquickapp.com share links, just follow redirects to the SSR page
    response = session.get(input_url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    referer = response.url
    html = response.text
    data = _extract_router_data(html)
    loader = data.get("loaderData") or {}

    # Try hongguoduanju.com format first: seriesDetail in loaderData
    page: dict[str, Any] | None = None
    for key, value in loader.items():
        if isinstance(value, dict) and "seriesDetail" in value:
            page = value
            break

    if page is not None:
        series = _normalise_series_from_detail(page.get("seriesDetail") or {}, page.get("req") or {})
    else:
        # Try novelquickapp.com share format: series_data + chapter_ids inside pageData
        page_data: dict[str, Any] | None = None
        for key, value in loader.items():
            if isinstance(value, dict):
                pd = value.get("pageData")
                if isinstance(pd, dict) and ("series_data" in pd or "chapter_ids" in pd):
                    page_data = pd
                    break
        if page_data is None:
            raise ParseError(
                f"no seriesDetail or pageData.series_data in loaderData keys={list(loader)}"
            )
        # Extract series_id from the redirect URL's zlink parameter
        series_id = ""
        redirect_url = response.url
        redirect_query = parse_qs(urlparse(redirect_url).query)
        zlink = redirect_query.get("zlink", [""])[0]
        if zlink:
            scheme_params = parse_qs(urlparse(zlink).query).get("schemeParams", [""])[0]
            if scheme_params:
                try:
                    sp = json.loads(scheme_params)
                    series_id = str(sp.get("video_series_id", ""))
                except (json.JSONDecodeError, ValueError):
                    pass
        if not series_id:
            series_id = _extract_series_id_from_html(html, input_url)
        if not series_id:
            raise ParseError("could not determine series_id from share page")
        series = _normalise_series_from_share(page_data, series_id)

    return series, referer, None


def request_player_for_vid(
    proxy: str | None,
    series_id: str,
    vid: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    referer: str | None = None,
    sleep: float = 0,
    validate_media: bool = True,
    min_url_ttl: int = 120,
    base_url: str | None = None,
) -> dict[str, Any] | None:
    """Resolve one episode's full media URL via the public web SSR payload.

    Returns a dict (``url``, ``url_type``, ``duration_seconds``, ...) or
    ``None`` when the episode is not publicly accessible.  Raises
    :class:`ParseError` when the page is malformed, the URL fails validation,
    or its TTL is shorter than ``min_url_ttl``.
    """
    base = (base_url or BASE_URL).rstrip("/")
    session = make_session(proxy)
    try:
        target = f"{base}/player/{series_id}/{vid}"
        headers: dict[str, str] = {}
        if referer:
            headers["Referer"] = referer
        response = session.get(
            target,
            timeout=timeout,
            allow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()
        html = response.text
        if sleep:
            time.sleep(sleep)
        data = _extract_router_data(html)
        loader = data.get("loaderData") or {}
        page = loader.get("player_(series_id)/(vid)/page")
        if not isinstance(page, dict) or not page.get("isSuccess"):
            return None

        vpi = page.get("video_player_info") or {}
        main_url = vpi.get("main_url")
        if not main_url:
            return None

        raw_duration = vpi.get("duration")
        try:
            duration = float(raw_duration) if raw_duration is not None else None
        except (TypeError, ValueError):
            duration = None

        width = to_int(vpi.get("width"))
        height = to_int(vpi.get("height"))
        expires_at = media_url_expiry(main_url)

        definition = None
        if width and height:
            long_side = max(width, height)
            short_side = min(width, height)
            if long_side >= 1080 or short_side >= 1080:
                definition = "1080p"
            elif long_side >= 720 or short_side >= 720:
                definition = "720p"
            else:
                definition = f"{short_side}p"

        result: dict[str, Any] = {
            "url": main_url,
            "url_type": "full",
            "duration_seconds": duration,
            "expires_at": expires_at,
            "source_url": response.url,
            "width": width,
            "height": height,
            "definition": definition,
            "bitrate": None,
            "size": None,
            "encrypted": False,
        }

        clip = media_clip_seconds(main_url)
        if clip is not None:
            result["url_type"] = "preview"
            result["clip_seconds"] = clip

        if validate_media:
            try:
                head = session.head(
                    main_url,
                    timeout=min(timeout, 15),
                    allow_redirects=True,
                    headers={"Referer": response.url},
                )
            except requests.RequestException as exc:
                raise ParseError(f"media HEAD failed: {exc}") from exc
            if head.status_code in (401, 403):
                raise ParseError(f"media URL rejected (HTTP {head.status_code})")
            head.raise_for_status()
            content_type = (head.headers.get("Content-Type") or "").lower()
            if content_type and not (
                content_type.startswith("video/")
                or "octet-stream" in content_type
                or content_type.startswith("application/")
            ):
                raise ParseError(f"unexpected media Content-Type: {content_type!r}")
            length = head.headers.get("Content-Length")
            if length and length.isdigit():
                result["size"] = int(length)

        if expires_at is not None and expires_at <= int(time.time()) + min_url_ttl:
            raise ParseError("media URL TTL shorter than requested minimum")

        return result
    finally:
        session.close()