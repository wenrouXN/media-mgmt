from __future__ import annotations
import re
from collections import defaultdict
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

_RES_RE = re.compile(r"(2160p|4k|1080p|720p|480p)", re.I)
_GROUP_RE = re.compile(r"([A-Za-z0-9]+)\.mkv$|([A-Za-z0-9\-]+)$")


def _score(item: dict[str, Any]) -> tuple:
    dest = str(item.get("dest") or "")
    src = str(item.get("src") or "")
    blob = dest + " " + src
    res = 0
    m = _RES_RE.search(blob)
    if m:
        r = m.group(1).lower()
        res = {"2160p": 4, "4k": 4, "1080p": 3, "720p": 2, "480p": 1}.get(r, 0)
    # prefer library dest under /links/
    in_links = 1 if "/links/" in dest else 0
    status = 1 if item.get("status") in (True, "true", 1, "success") else 0
    # newer id higher
    iid = int(item.get("id") or 0)
    return (status, in_links, res, iid)


def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    tmdbid = params.get("tmdbid")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    # pull more history
    hist = mp("transfer_history", title=title, count=params.get("count") or 100)
    body = hist.get("data") if isinstance(hist, dict) else hist
    items = []
    if isinstance(body, dict):
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        if isinstance(data, dict):
            items = data.get("list") or []
        elif isinstance(body.get("list"), list):
            items = body["list"]
    if tmdbid:
        items = [i for i in items if str(i.get("tmdbid") or "") == str(tmdbid) or not tmdbid]
    # group by season+episode
    groups: dict[str, list] = defaultdict(list)
    for it in items or []:
        if not isinstance(it, dict):
            continue
        key = f"{it.get('seasons') or ''}::{it.get('episodes') or ''}::{it.get('tmdbid') or ''}"
        if not it.get("episodes") and not it.get("seasons"):
            key = f"movie::{it.get('title')}::{it.get('tmdbid')}"
        groups[key].append(it)
    dup_groups = []
    for key, lst in groups.items():
        if len(lst) < 2:
            continue
        ranked = sorted(lst, key=_score, reverse=True)
        keep = ranked[0]
        drop = ranked[1:]
        dup_groups.append({
            "key": key,
            "title": keep.get("title"),
            "seasons": keep.get("seasons"),
            "episodes": keep.get("episodes"),
            "count": len(lst),
            "keep": {
                "id": keep.get("id"),
                "dest": keep.get("dest"),
                "src": keep.get("src"),
                "date": keep.get("date"),
                "score": _score(keep),
            },
            "candidates_to_review": [
                {"id": d.get("id"), "dest": d.get("dest"), "src": d.get("src"), "date": d.get("date"), "score": _score(d)}
                for d in drop
            ],
        })
    # sort by count
    dup_groups.sort(key=lambda g: g["count"], reverse=True)
    apply_delete = str(params.get("apply") or "").lower() in {"1", "true", "yes", "delete"}
    # NEVER auto-delete unless explicit; even then only report plan
    plan = []
    if apply_delete:
        for g in dup_groups:
            for c in g["candidates_to_review"]:
                plan.append({"action": "manual_review_delete", "transfer_id": c["id"], "path": c.get("dest")})
    return ok({
        "workflow": "duplicates",
        "title": title,
        "tmdbid": tmdbid,
        "transfer_count": len(items or []),
        "duplicate_groups": dup_groups,
        "duplicate_group_count": len(dup_groups),
        "apply_requested": apply_delete,
        "delete_plan": plan,
        "summary": (
            f"《{title or tmdbid}》整理记录 {len(items or [])} 条，发现 {len(dup_groups)} 组可能重复"
            + ("；已生成待人工确认删除计划（未执行删除）" if plan else "；默认只建议保留哪条")
        ),
        "note": "不自动删文件。保留规则：成功整理 > /links/ 路径 > 分辨率 > 较新记录。",
    })
