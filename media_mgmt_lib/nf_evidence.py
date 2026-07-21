"""Unified NextFind evidence chain for library / search / fill.

CEO B (2026-07-20): one parse path for 有没有 + resources; surface search/resources mismatch.
"""
from __future__ import annotations

from typing import Any


def truthy_lib(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "有", "in_library"}:
        return True
    if s in {"0", "false", "no", "n", "无", "none", "missing"}:
        return False
    return None


def norm_media_type(v: Any, default: str = "movie") -> str:
    s = str(v or "").strip().lower()
    if s in {"movie", "电影", "film", "films", "mov"}:
        return "movie"
    if s in {"tv", "电视剧", "剧集", "anime", "动漫", "series", "show"}:
        return "tv"
    return s or default


def is_netdisk_item(it: dict[str, Any]) -> bool:
    if not isinstance(it, dict):
        return False
    if it.get("slug"):
        return True
    st = str(it.get("source_type") or it.get("pan_type") or "").lower()
    if st in {"hdhive", "radar", "115", "netdisk", "pan", "cloud"}:
        return True
    if "hdhive://" in str(it.get("slug") or it.get("media_url") or ""):
        return True
    # 115 share URLs without slug
    u = str(it.get("media_url") or it.get("url") or it.get("share_url") or "")
    if "115cdn.com" in u or "115.com" in u:
        return True
    return False


def is_pt_item(it: dict[str, Any]) -> bool:
    if not isinstance(it, dict) or is_netdisk_item(it):
        return False
    for k in ("torrent_info", "enclosure", "magnet", "download_url", "site", "seeders", "peers"):
        if it.get(k) not in (None, "", [], {}):
            return True
    st = str(it.get("source_type") or it.get("source") or it.get("channel_name") or "").lower()
    return any(x in st for x in ("pt", "torrent", "tracker", "moviepilot", "mp"))


def tag_path(it: dict[str, Any]) -> str:
    if is_netdisk_item(it):
        return "netdisk"
    if is_pt_item(it):
        return "pt"
    return "unknown"


def extract_list(payload: Any, keys: tuple[str, ...] = ("data", "results", "items", "resources", "candidates")) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            for nested in ("list", "data", "results", "items", "torrents", "resources"):
                maybe = val.get(nested)
                if isinstance(maybe, list):
                    return [x for x in maybe if isinstance(x, dict)]
    raw = payload.get("raw")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return extract_list(raw, keys)
    return []


def parse_in_library(
    library_info: dict[str, Any] | None = None,
    media: dict[str, Any] | None = None,
) -> bool | None:
    """Parse NF in-library from library_info op and/or identify selected."""
    if isinstance(library_info, dict):
        data = library_info.get("data") if isinstance(library_info.get("data"), (dict, list)) else library_info
        if isinstance(data, dict) and library_info.get("success") is not False:
            v = truthy_lib(
                data.get("is_in_library")
                if "is_in_library" in data
                else data.get("in_library") or data.get("exists")
            )
            if v is not None:
                return v
            try:
                if data.get("local_episodes") is not None and int(data.get("local_episodes")) > 0:
                    return True
            except (TypeError, ValueError):
                pass
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            row = data[0]
            v = truthy_lib(row.get("is_in_library") if "is_in_library" in row else row.get("in_library"))
            if v is not None:
                return v
            try:
                if row.get("local_episodes") is not None and int(row.get("local_episodes")) > 0:
                    return True
            except (TypeError, ValueError):
                pass

    if isinstance(media, dict):
        v = truthy_lib(media.get("is_in_library"))
        if v is not None:
            return v
        raw = media.get("raw") if isinstance(media.get("raw"), dict) else {}
        v2 = truthy_lib(raw.get("is_in_library"))
        if v2 is not None:
            return v2
        try:
            if media.get("local_episodes") is not None and int(media.get("local_episodes")) > 0:
                return True
            if raw.get("local_episodes") is not None and int(raw.get("local_episodes")) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return None


def classify_resources(items: list[dict[str, Any]]) -> dict[str, Any]:
    tagged = []
    for it in items:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        row["_path"] = tag_path(it)
        tagged.append(row)
    netdisk = [x for x in tagged if x.get("_path") == "netdisk"]
    pt = [x for x in tagged if x.get("_path") == "pt"]
    return {
        "items": tagged,
        "netdisk": netdisk,
        "pt": pt,
        "netdisk_count": len(netdisk),
        "pt_count": len(pt),
        "total": len(tagged),
    }


def consistency_report(
    *,
    search_hint_count: int | None = None,
    resources_count: int | None = None,
    identify_in_library: bool | None = None,
    library_info_in_library: bool | None = None,
) -> dict[str, Any]:
    """Surface silent mismatches for agents (named, not swallowed)."""
    warnings: list[str] = []
    if (
        search_hint_count is not None
        and resources_count is not None
        and search_hint_count > 0
        and resources_count == 0
    ):
        warnings.append("nf_search_hint_but_resources_empty")
    if (
        search_hint_count is not None
        and resources_count is not None
        and search_hint_count == 0
        and resources_count > 0
    ):
        warnings.append("nf_resources_present_but_search_empty")
    if (
        identify_in_library is not None
        and library_info_in_library is not None
        and bool(identify_in_library) != bool(library_info_in_library)
    ):
        warnings.append("nf_identify_vs_library_info_mismatch")
    return {
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "search_hint_count": search_hint_count,
        "resources_count": resources_count,
        "identify_in_library": identify_in_library,
        "library_info_in_library": library_info_in_library,
    }


def nf_subscribe_active(info: dict[str, Any] | None, tmdbid: Any = None) -> bool:
    """Normalize subscribe_info / identify flags into a single subscribed_nf bool."""
    if not isinstance(info, dict):
        return False
    if info.get("success") is False:
        return False
    data = info.get("data")
    if isinstance(data, list):
        if not data:
            return False
        if tmdbid is None:
            return True
        for row in data:
            if not isinstance(row, dict):
                continue
            tid = row.get("tmdb_id") or row.get("tmdbid")
            if tid is not None and str(tid) == str(tmdbid):
                return True
        # list non-empty but no tmdb match — still treat as signal if single row
        return len(data) == 1
    if isinstance(data, dict):
        if truthy_lib(data.get("is_subscribed")) is True:
            return True
        tid = data.get("tmdb_id") or data.get("tmdbid")
        if tmdbid is not None and tid is not None and str(tid) == str(tmdbid):
            return True
        if data.get("id") or data.get("title"):
            return True
    # raw nested
    raw = info.get("raw")
    if isinstance(raw, dict):
        return nf_subscribe_active({"success": True, "data": raw.get("data")}, tmdbid)
    return False


def subscribe_state(*, mp: bool, nf: bool, mp_err: bool = False, nf_err: bool = False) -> str:
    """State machine for dual subscribe.

    States: both | mp_only | nf_only | none | partial_error | nf_down | mp_down
    """
    if mp_err and nf_err:
        return "both_down"
    if nf_err and not mp_err:
        return "nf_down"
    if mp_err and not nf_err:
        return "mp_down"
    if mp and nf:
        return "both"
    if mp and not nf:
        return "mp_only"
    if nf and not mp:
        return "nf_only"
    return "none"
