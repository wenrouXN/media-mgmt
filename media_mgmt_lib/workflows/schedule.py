"""TMDB air schedule workflow (aired vs upcoming)."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows._util import fail, mp, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    if not params.get("title") and not params.get("tmdbid"):
        return fail("missing_param", need="title|tmdbid")
    result = mp(
        "schedule",
        title=params.get("title"),
        tmdbid=params.get("tmdbid"),
        media_type=params.get("media_type") or params.get("mtype"),
        season=params.get("season") or 1,
        as_of=params.get("as_of"),
    )
    if not result.get("success"):
        return result
    result["workflow"] = "schedule"
    return ok(result)
