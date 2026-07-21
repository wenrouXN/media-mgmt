"""Watch pipeline pure helpers (pick/policy). CLI stays in scripts/watch.py."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.watch_pick import apply_lock_and_pick


def is_tv_media(
    media_type: Any = None,
    episode: Any = None,
    media: dict[str, Any] | None = None,
) -> bool:
    mtype = ""
    if isinstance(media, dict):
        mtype = str(media.get("type") or media.get("media_type") or "")
    if media_type not in (None, ""):
        mtype = str(media_type)
    if mtype in {"电视剧", "tv", "TV", "show", "series", "anime", "动漫"}:
        return True
    if episode is not None and str(episode).strip() != "":
        return True
    return False


def quality_policy(
    *,
    is_tv: bool,
    resolution: str | None = None,
    hdr_mode: str | None = None,
    require_chinese: bool = False,
    no_require_chinese: bool = False,
    allow_disc: bool = False,
    no_fx_sub: bool = False,
) -> dict[str, Any]:
    """Default PT quality: TV 4K SDR; movie no disc, fx sub, Chinese."""
    prefer_resolution = resolution or ("2160p" if is_tv else None)
    hdr = hdr_mode or ("sdr" if is_tv else "any")
    req_zh = bool(require_chinese)
    prefer_fx = False
    exclude_disc = False
    if not is_tv:
        req_zh = True
        prefer_fx = True
        exclude_disc = True
        if no_require_chinese:
            req_zh = False
        if require_chinese:
            req_zh = True
        if allow_disc:
            exclude_disc = False
        if no_fx_sub:
            prefer_fx = False
    return {
        "is_tv": bool(is_tv),
        "prefer_resolution": prefer_resolution or ("best" if not is_tv else "2160p"),
        "hdr_mode": str(hdr or "any"),
        "require_chinese": bool(req_zh),
        "prefer_fx_sub": bool(prefer_fx),
        "exclude_disc": bool(exclude_disc),
        "fallback": (
            "best_seeded_resolution" if is_tv else "fx_sub_then_best_chinese_quality"
        ),
    }


def pick_for_watch(
    items: list[dict[str, Any]],
    *,
    media: dict[str, Any] | None = None,
    media_type: Any = None,
    season: int | None = None,
    episode: int | None = None,
    media_year: Any = None,
    resolution: str | None = None,
    hdr_mode: str | None = None,
    require_chinese: bool = False,
    no_require_chinese: bool = False,
    allow_disc: bool = False,
    no_fx_sub: bool = False,
    site_name: str | None = None,
    title_contains: str | None = None,
    page_url: str | None = None,
    site_priority: list[str] | None = None,
    pick_index: int | None = None,
    prefer_fresh: bool = True,
    max_age_days: float | None = None,
    top_n: int = 3,
) -> dict[str, Any]:
    """Lock → quality policy → rank → optional pick_index. Pure for tests."""
    tv = is_tv_media(media_type, episode, media)
    policy = quality_policy(
        is_tv=tv,
        resolution=resolution,
        hdr_mode=hdr_mode,
        require_chinese=require_chinese,
        no_require_chinese=no_require_chinese,
        allow_disc=allow_disc,
        no_fx_sub=no_fx_sub,
    )
    year = media_year
    if year is None and isinstance(media, dict):
        year = media.get("year")
    picked = apply_lock_and_pick(
        items,
        site_name=site_name,
        title_contains=title_contains,
        page_url=page_url,
        pick_index=pick_index,
        season=season,
        episode=episode,
        media_year=year,
        prefer_resolution=policy["prefer_resolution"]
        if policy["prefer_resolution"] != "best"
        else (resolution or ""),
        site_priority=site_priority,
        require_chinese=policy["require_chinese"],
        hdr_mode=policy["hdr_mode"],
        prefer_fx_sub=policy["prefer_fx_sub"],
        exclude_disc=policy["exclude_disc"],
        top_n=top_n,
        prefer_fresh=prefer_fresh,
        max_age_days=max_age_days,
    )
    picked["quality_policy"] = policy
    return picked
