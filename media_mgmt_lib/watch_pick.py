"""Pure helpers for watch PT pick / locks (testable without full watch CLI)."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.torrent_pick import (
    filter_items_by_lock,
    lock_active,
    pick_torrent,
    summarize_candidate,
)


def map_pick_n_to_index(pick_n: Any) -> int | None:
    """User 第N个 (1-based) → 0-based index. None if unset."""
    if pick_n is None or str(pick_n).strip() == "":
        return None
    n = int(pick_n)
    if n < 1:
        raise ValueError("pick_n is 1-based (第一个=1)")
    return n - 1


def apply_lock_and_pick(
    items: list[dict[str, Any]],
    *,
    site_name: str | None = None,
    title_contains: str | None = None,
    page_url: str | None = None,
    pick_index: int | None = None,
    season: int | None = None,
    episode: int | None = None,
    media_year: Any = None,
    prefer_resolution: str | None = None,
    site_priority: list[str] | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
    prefer_fx_sub: bool = False,
    exclude_disc: bool = False,
    top_n: int = 3,
    prefer_fresh: bool = True,
    max_age_days: float | None = None,
) -> dict[str, Any]:
    """Lock filter → rank → optional pick_index. Pure function for unit tests."""
    before = len(items)
    locked = False
    if lock_active(site_name=site_name, title_contains=title_contains, page_url=page_url):
        locked = True
        items = filter_items_by_lock(
            items,
            site_name=site_name,
            title_contains=title_contains,
            page_url=page_url,
        )
        if site_name:
            site_priority = [site_name] + [s for s in (site_priority or []) if s != site_name]
    if locked and not items:
        return {
            "success": False,
            "error": "lock_no_match",
            "lock": {
                "site_name": site_name,
                "title_contains": title_contains,
                "page_url": page_url,
                "matched": 0,
                "before": before,
            },
            "candidates": [],
            "selected": None,
        }

    picked = pick_torrent(
        items,
        season=season,
        episode=episode,
        media_year=media_year,
        prefer_fresh=prefer_fresh,
        max_age_days=max_age_days,
        prefer_resolution=prefer_resolution or "",
        site_priority=site_priority,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode,
        prefer_fx_sub=prefer_fx_sub,
        exclude_disc=exclude_disc,
        top_n=top_n,
    )
    cands = picked.get("candidates") or []
    selected = picked.get("selected")
    if pick_index is not None:
        if pick_index < 0 or pick_index >= len(cands):
            return {
                "success": False,
                "error": "pick_index_out_of_range",
                "lock": {
                    "site_name": site_name,
                    "matched": len(items),
                    "before": before,
                }
                if locked
                else None,
                "candidates": [summarize_candidate(x) for x in cands],
                "selected": None,
                "pick_meta": {
                    "needs_confirm": picked.get("needs_confirm"),
                    "confirm_reasons": picked.get("confirm_reasons"),
                },
            }
        selected = cands[pick_index]

    return {
        "success": bool(selected),
        "error": None if selected else "pick_failed",
        "lock": {
            "site_name": site_name,
            "title_contains": title_contains,
            "page_url": page_url,
            "matched": len(items),
            "before": before,
        }
        if locked
        else None,
        "candidates": [summarize_candidate(x) for x in cands],
        "selected": summarize_candidate(selected) if selected else None,
        "selected_raw": selected,
        "needs_confirm": bool(picked.get("needs_confirm")),
        "confirm_reasons": picked.get("confirm_reasons") or [],
        "pick_meta": {
            "media_year": media_year,
            "year_match": picked.get("year_match"),
            "pubdate_age_days": picked.get("pubdate_age_days"),
            "quality": picked.get("quality"),
        },
    }
