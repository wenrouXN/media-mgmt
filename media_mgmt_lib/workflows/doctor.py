from __future__ import annotations
from typing import Any
from media_mgmt_lib.ops.health import check_all
from media_mgmt_lib.workflows._util import ok

def run(params: dict[str, Any]) -> dict[str, Any]:
    report = check_all()
    bad = [s for s in (report.get("services") or []) if not s.get("success")]
    return ok({
        "workflow": "doctor",
        "ok": report.get("ok"),
        "total": report.get("total"),
        "all_ok": bool(report.get("success")),
        "failures": [{"service": s.get("service"), "status": s.get("status"), "error": s.get("error")} for s in bad],
        "services": report.get("services"),
        "summary": f"{report.get('ok')}/{report.get('total')} services ok" + ("" if report.get("success") else f"; down: {[s.get('service') for s in bad]}"),
    })
