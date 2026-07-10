from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

def run(params: dict[str, Any]) -> dict[str, Any]:
    if not params.get("title") and not params.get("tmdbid"):
        return fail("missing_param", need="title|tmdbid")
    st = mp("status", title=params.get("title"), tmdbid=params.get("tmdbid"), episode=params.get("episode"), count=params.get("count") or 20)
    th = mp("transfer_history", title=params.get("title"), count=params.get("count") or 20)
    return ok({
        "workflow": "status",
        "download_status": st,
        "transfer_history": th,
        "state": st.get("state") if isinstance(st, dict) else None,
        "summary": f"state={st.get('state') if isinstance(st, dict) else 'unknown'}",
    })
