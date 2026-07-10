from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    action = str(params.get("action") or "check")  # check|create|list
    if action == "list":
        return ok({"workflow": "subscribe", "action": "list", "result": mp("subscribe_list")})
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    identified = mp("identify", title=title, tmdbid=tmdbid, media_type=params.get("media_type"))
    media = identified.get("selected") if isinstance(identified, dict) else None
    if not isinstance(media, dict):
        return fail("identify_failed", detail=identified)
    tid = media.get("tmdb_id") or media.get("tmdbid") or tmdbid
    existing = mp("subscribe", action="get", tmdbid=tid, title=media.get("title"), season=params.get("season") or 1)
    if action == "check":
        return ok({
            "workflow": "subscribe",
            "action": "check",
            "media": {"title": media.get("title"), "tmdb_id": tid, "type": media.get("type"), "year": media.get("year")},
            "subscription": existing,
            "subscribed": bool(existing) and not existing.get("error") and (existing.get("id") or existing.get("name")),
            "summary": f"subscribe check {media.get('title')}: {'yes' if existing.get('id') else 'no/unknown'}",
        })
    # create
    dry = params.get("dry_run") in (True, "true", "1", "yes") or action != "create"
    body = {
        "name": media.get("title"),
        "tmdbid": tid,
        "type": media.get("type") or params.get("media_type") or "电视剧",
        "year": media.get("year"),
        "season": params.get("season") or 1,
    }
    if dry and action != "create":
        return ok({"workflow": "subscribe", "action": "suggest", "would_create": body, "existing": existing, "summary": "dry suggest only; pass action=create to submit"})
    created = mp("subscribe", name=body["name"], tmdbid=body["tmdbid"], media_type=body["type"], year=body.get("year"), season=body.get("season"), dry_run=dry)
    return ok({"workflow": "subscribe", "action": "create", "dry_run": dry, "result": created, "existing": existing})
