"""Service health + pipeline notes + degraded capability map."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.ops.health import check_all
from media_mgmt_lib.workflows._util import ok


def _truthy(v: Any) -> bool:
    return str(v or "").lower() in {"1", "true", "yes"}


def run(params: dict[str, Any]) -> dict[str, Any]:
    report = check_all()
    services = report.get("services") or []
    bad = [s for s in services if not s.get("success")]
    by_id = {
        str(s.get("service") or s.get("id") or ""): s
        for s in services
        if isinstance(s, dict)
    }

    pipeline: dict[str, Any] = {
        "netdisk_primary": "nextfind_openapi",
        "hdhive_alias": True,
        "pansou_retired": True,
        "cloak_hdhive_retired": True,
        "search_default": "nextfind (force_mp_search for MP)",
        "subscribe": "dual_write MP+NF",
        "fill": "workflows.nf_fill.fill_missing",
        "path_policy": "exact MP path, else base + infer_category (e.g. …/日韩电影/)",
        "pick_policy": "pick_n 1-based for user speech; pick_index 0-based CLI only",
        "agent_must_read": [
            "warnings",
            "consistency",
            "state",
            "resource_authority",
            "authority",
            "error",
            "degraded",
        ],
        "notes": [
            "SKILL.md §0: never conclude from success=true alone",
            "subscribe states: both|mp_only|nf_only|none|nf_down|mp_down|partial",
            "library: 有没有=NextFind；MP 只读 transfer/download 整理记录",
            "search: resource_authority=resources_op; warning nf_search_hint_but_resources_empty",
            "nf_no_pt_in_results: NF resources 无 PT 行时 PT 走 fallback",
            "force_mp_search / force_mp: 显式允许 MP 重搜/认片",
            "pick_n=1 means first candidate; site_name locks before rank",
        ],
    }

    degraded: list[dict[str, Any]] = []
    nf_detail = None
    try:
        import media_mgmt_lib.ops.nextfind  # noqa: F401
        from media_mgmt_lib.ops import call_op

        h = call_op("nextfind", "health", {})
        q = call_op("nextfind", "quota", {}) if h.get("success") else None
        nf_detail = {
            "health": {
                "success": h.get("success"),
                "error": h.get("error"),
                "status": h.get("status"),
            },
            "quota": {
                "success": (q or {}).get("success"),
                "summary": (q or {}).get("summary") or (q or {}).get("data"),
            }
            if q
            else None,
        }
        pipeline["nextfind_ok"] = bool(h.get("success"))
        if not h.get("success"):
            degraded.append(
                {
                    "capability": "netdisk_search_grab_subscribe_nf",
                    "reason": "nextfind_down",
                    "impact": "网盘/认片/双写订阅 NF 侧不可用；可 force_mp_search / force_mp",
                    "workaround": "run search --param force_mp_search=true; subscribe 可能 partial",
                }
            )
    except Exception as e:  # noqa: BLE001
        nf_detail = {"error": str(e)}
        pipeline["nextfind_ok"] = False
        degraded.append(
            {
                "capability": "netdisk_search_grab_subscribe_nf",
                "reason": f"nextfind_exception:{e}",
                "impact": "NextFind 管线异常",
            }
        )

    # clouddrive → offline workflow
    cd = by_id.get("clouddrive") or {}
    pipeline["clouddrive_ok"] = bool(cd.get("success"))
    if not cd.get("success"):
        degraded.append(
            {
                "capability": "offline_magnet",
                "reason": cd.get("error") or cd.get("status") or "clouddrive_down",
                "impact": "run offline / 磁力离线不可用",
                "workaround": "PT watch 或 NextFind transfer；修 protobuf/token 后 doctor 复检",
            }
        )

    mp = by_id.get("moviepilot") or {}
    pipeline["moviepilot_ok"] = bool(mp.get("success")) if mp else None
    if mp and not mp.get("success"):
        degraded.append(
            {
                "capability": "pt_download_subscribe_library",
                "reason": mp.get("error") or "moviepilot_down",
                "impact": "PT 下种/订阅/库查询失败",
            }
        )

    # optional deep check: can clouddrive ops import?
    import_notes: list[str] = []
    try:
        import media_mgmt_lib.ops.clouddrive  # noqa: F401

        import_notes.append("clouddrive_ops_import_ok")
    except Exception as e:  # noqa: BLE001
        import_notes.append(f"clouddrive_ops_import_failed:{e}")
        if not any(d.get("capability") == "offline_magnet" for d in degraded):
            degraded.append(
                {
                    "capability": "offline_magnet",
                    "reason": f"import_failed:{e}",
                    "impact": "clouddrive ops 未注册",
                    "workaround": "升级 protobuf 至与 gencode 匹配（>=7.35）",
                }
            )

    summary = f"{report.get('ok')}/{report.get('total')} services ok"
    if not report.get("success"):
        summary += f"; down: {[s.get('service') for s in bad]}"
    if pipeline.get("nextfind_ok") is True:
        summary += "; nextfind ok (pipeline primary)"
    elif pipeline.get("nextfind_ok") is False:
        summary += "; nextfind DOWN — netdisk/subscribe_nf degraded"
    if degraded:
        caps = [d.get("capability") for d in degraded]
        summary += f"; degraded={caps}"

    payload = {
        "workflow": "doctor",
        "ok": report.get("ok"),
        "total": report.get("total"),
        "all_ok": bool(report.get("success")) and not degraded,
        "failures": [
            {
                "service": s.get("service"),
                "status": s.get("status"),
                "error": s.get("error"),
            }
            for s in bad
        ],
        "services": services,
        "nextfind": nf_detail,
        "pipeline": pipeline,
        "degraded": degraded,
        "import_notes": import_notes,
        "summary": summary,
    }
    if _truthy(params.get("verbose")):
        payload["raw_report"] = report
    return ok(payload)
