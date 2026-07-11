"""Playlist workflow: public playlist URL → track list + listen queries."""
from __future__ import annotations

from typing import Any

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Parse public playlist metadata.

    params:
      url / link / playlist_url
      limit — optional max tracks
      proxy / timeout — optional
    """
    url = params.get("url") or params.get("link") or params.get("playlist_url")
    if not url:
        return fail("missing_param", need="url")

    result = call_op("playlist", "parse", {**params, "url": url})
    if not result.get("success"):
        return fail(
            str(result.get("error") or "parse_failed"),
            detail=result.get("detail"),
            supported_platforms=result.get("supported_platforms"),
            result=result,
            workflow="playlist",
            url=url,
            summary=f"playlist parse failed: {result.get('error') or result.get('detail')}",
        )

    pl = result.get("playlist") or {}
    tracks = result.get("tracks") or []
    summary = result.get("summary") or (
        f"{result.get('platform')} 歌单《{pl.get('name')}》{pl.get('track_count')} 首"
    )
    return ok(
        {
            "workflow": "playlist",
            "url": url,
            "platform": result.get("platform"),
            "playlist": pl,
            "tracks": tracks,
            "queries": result.get("queries") or [],
            "truncated": bool(result.get("truncated")),
            "track_count": pl.get("track_count"),
            "returned": len(tracks),
            "summary": summary,
            "next": {
                "listen_one": "run listen --param q='<queries[i]>'",
                "note": "批量下载由 agent 按 queries 循环 listen，本 workflow 不下歌",
            },
            "result": result,
        }
    )
