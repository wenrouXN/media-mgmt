"""Library presence: NextFind = 有没有; MoviePilot = 整理/转移记录 only."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.nf_evidence import norm_media_type, parse_in_library
from media_mgmt_lib.workflows._util import fail, mp, ok


def _norm_type(v: Any) -> str:
    return norm_media_type(v, default="tv")


def _identify(params: dict[str, Any], title: Any, tmdbid: Any, mtype: Any) -> dict[str, Any]:
    """Prefer NextFind identify; fall back to MP for title resolution only."""
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if call_op("nextfind", "health", {}).get("success"):
            r = call_op(
                "nextfind",
                "identify",
                {
                    "title": title,
                    "q": title,
                    "tmdbid": tmdbid,
                    "media_type": mtype,
                    "year": params.get("year"),
                    "select": params.get("select") or 1,
                },
            )
            if r.get("success") and (r.get("selected") or {}).get("tmdb_id"):
                return {
                    "path": "nextfind_openapi",
                    "selected": r.get("selected"),
                    "candidates": r.get("candidates") or [],
                }
    except Exception:  # noqa: BLE001
        pass
    identified = mp("identify", title=title, tmdbid=tmdbid, media_type=mtype, year=params.get("year"))
    selected = identified.get("selected") if isinstance(identified, dict) else None
    return {
        "path": "moviepilot",
        "selected": selected if isinstance(selected, dict) else None,
        "raw": identified,
    }


def _nf_library(tmdbid: Any, media_type: str) -> dict[str, Any] | None:
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        if not call_op("nextfind", "health", {}).get("success"):
            return {"error": "nextfind_not_configured"}
        info = call_op("nextfind", "library_info", {"tmdbid": tmdbid, "media_type": media_type})
        filt = None
        try:
            filt = call_op("nextfind", "local_library_filter", {"status": "missing"})
        except Exception:  # noqa: BLE001
            filt = None
        return {"library_info": info, "local_library_filter": filt}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def _parse_nf_in_library(nf: dict[str, Any] | None, media: dict[str, Any] | None) -> bool | None:
    li = nf.get("library_info") if isinstance(nf, dict) else None
    return parse_in_library(li if isinstance(li, dict) else None, media)


def _mp_transfer_records(title: Any, tmdbid: Any) -> dict[str, Any]:
    """MoviePilot = organize/transfer history only (not library_exists for 有没有)."""
    out: dict[str, Any] = {
        "transfer_history": None,
        "download_history": None,
        "has_transfer_record": False,
        "transfer_count": 0,
        "download_count": 0,
        "sample": [],
    }
    try:
        th = mp("transfer_history", title=title, tmdbid=tmdbid, page=1, count=30)
        out["transfer_history"] = th
        rows: list[Any] = []
        if isinstance(th, dict):
            data = th.get("data")
            if isinstance(data, dict):
                inner = data.get("data") if isinstance(data.get("data"), dict) else data
                if isinstance(inner, dict) and isinstance(inner.get("list"), list):
                    rows = inner["list"]
                elif isinstance(inner, list):
                    rows = inner
            elif isinstance(data, list):
                rows = data
        # filter soft-match title/tmdb if API returned mixed page
        filtered = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            blob = str(row.get("title") or "") + str(row.get("src") or "") + str(row.get("dest") or "")
            tid = row.get("tmdbid") or row.get("tmdb_id")
            ok_row = False
            if tmdbid and tid is not None and str(tid) == str(tmdbid):
                ok_row = True
            if title and title in blob:
                ok_row = True
            if ok_row or (not tmdbid and not title):
                filtered.append(row)
        # if filter emptied but API already scoped by title, keep rows
        use = filtered if (tmdbid or title) and filtered else (filtered or rows)
        out["transfer_count"] = len(use)
        out["has_transfer_record"] = len(use) > 0
        out["sample"] = [
            {
                "title": r.get("title"),
                "tmdbid": r.get("tmdbid") or r.get("tmdb_id"),
                "src": r.get("src") or r.get("source") or r.get("path"),
                "dest": r.get("dest") or r.get("target"),
                "date": r.get("date") or r.get("time") or r.get("created_at"),
                "status": r.get("status") or r.get("state"),
            }
            for r in use[:8]
            if isinstance(r, dict)
        ]
    except Exception as e:  # noqa: BLE001
        out["transfer_error"] = str(e)

    try:
        dh = mp("download_history", title=title, tmdbid=tmdbid, page=1, count=20)
        out["download_history"] = dh
        drows: list[Any] = []
        if isinstance(dh, dict):
            data = dh.get("data")
            if isinstance(data, list):
                drows = data
            elif isinstance(data, dict) and isinstance(data.get("list"), list):
                drows = data["list"]
        matched = []
        for row in drows:
            if not isinstance(row, dict):
                continue
            tid = row.get("tmdbid") or row.get("tmdb_id")
            if tmdbid and tid is not None and str(tid) == str(tmdbid):
                matched.append(row)
            elif title and title in str(row.get("title") or ""):
                matched.append(row)
        out["download_count"] = len(matched)
        if matched and not out["sample"]:
            out["sample"] = [
                {
                    "title": r.get("title"),
                    "tmdbid": r.get("tmdbid"),
                    "path": r.get("path"),
                    "date": r.get("date"),
                    "kind": "download_history",
                }
                for r in matched[:5]
            ]
    except Exception as e:  # noqa: BLE001
        out["download_error"] = str(e)

    return out


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Check library presence + optional MP organize history.

    User policy (2026-07-20):
      - **有没有** → NextFind only (`exists` / `exists_nf`)
      - **MoviePilot** → transfer/download 整理记录 only（不用 library_exists 当有没有）
      - NF 不可用 → exists=null, authority=nextfind_unavailable（不回落 MP 库查询）
    """
    title = params.get("title") or params.get("q")
    tmdbid = params.get("tmdbid") or params.get("tmdb_id")
    if not title and not tmdbid:
        return fail("missing_param", need="title|tmdbid")
    mtype = params.get("mtype") or params.get("media_type") or "电视剧"
    skip_mp_history = str(params.get("skip_mp_history") or "").lower() in {"1", "true", "yes"}

    idr = _identify(params, title, tmdbid, mtype)
    media = idr.get("selected") if isinstance(idr.get("selected"), dict) else None
    if isinstance(media, dict):
        title = media.get("title") or title
        tmdbid = media.get("tmdb_id") or media.get("tmdbid") or tmdbid
        mtype = media.get("type") or media.get("media_type") or mtype

    # TV missing episodes still via MP tooling (schedule/lack), not for 有没有
    missing = None
    if str(mtype) in {"电视剧", "tv", "TV", "动漫"} or (media or {}).get("type") in {"电视剧", "tv"}:
        missing = mp("missing_episodes", title=title, tmdbid=tmdbid, media_type=mtype, media=media)

    nf = _nf_library(tmdbid, _norm_type(mtype)) if tmdbid else None
    nf_down = isinstance(nf, dict) and bool(nf.get("error"))
    nf_in_lib = _parse_nf_in_library(None if nf_down else nf, media if idr.get("path") == "nextfind_openapi" else None)
    if nf_in_lib is None and idr.get("path") == "nextfind_openapi" and not nf_down:
        nf_in_lib = _parse_nf_in_library(None, media)

    if nf_down:
        exists = None
        authority = "nextfind_unavailable"
    elif nf_in_lib is not None:
        exists = bool(nf_in_lib)
        authority = "nextfind"
    else:
        # NF up but no signal → treat as 无
        exists = False
        authority = "nextfind"

    # MP: 整理记录 only
    mp_org: dict[str, Any]
    if skip_mp_history:
        mp_org = {"skipped": True, "has_transfer_record": False}
    else:
        mp_org = _mp_transfer_records(title, tmdbid)

    summary = f"库中{'有' if exists else ('未知' if exists is None else '无')}《{title}》"
    summary += f"（有没有=NextFind/{authority}"
    if nf_in_lib is not None:
        summary += f" NF={'有' if nf_in_lib else '无'}"
    if mp_org.get("has_transfer_record"):
        summary += f"；MP整理记录={mp_org.get('transfer_count')}条"
    else:
        summary += "；MP整理记录=无"
    summary += f"；identify={idr.get('path')}）"
    if isinstance(missing, dict) and missing.get("summary"):
        summary += f"；{missing.get('summary')}"

    return ok(
        {
            "workflow": "library",
            "media": {"title": title, "tmdb_id": tmdbid, "type": mtype},
            "identify_path": idr.get("path"),
            "authority": authority,
            "exists": exists,
            "exists_nf": nf_in_lib,
            # legacy field: no longer means Emby/MP library_exists
            "exists_mp": None,
            "dual_source_conflict": False,
            "moviepilot_organize": mp_org,
            "has_transfer_record": bool(mp_org.get("has_transfer_record")),
            "missing": missing,
            "nextfind": nf,
            "summary": summary,
            "note": (
                "有没有=NextFind；MoviePilot 只提供 transfer/download 整理记录，不用 library_exists 判定在库。"
                if authority != "nextfind_unavailable"
                else "NextFind 不可用：exists=null，请先 doctor/nextfind health；不回落 MP 库查询。"
            ),
        }
    )
