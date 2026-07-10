from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok
from media_mgmt_lib.workflows import search as search_wf
from media_mgmt_lib.workflows import watch as watch_wf

def run(params: dict[str, Any]) -> dict[str, Any]:
    title = params.get("title")
    if not title:
        return fail("missing_param", need="title")
    # 1) show candidates
    searched = search_wf.run(params)
    # 2) if auto, re-run watch with yes
    auto = str(params.get("auto") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    downloaded = None
    if auto:
        downloaded = watch_wf.run({**params, "yes": True, "skip_hdhive": params.get("skip_hdhive", True)})
    return ok({
        "workflow": "retry",
        "search": searched,
        "redownload": downloaded,
        "auto": auto,
        "summary": "listed candidates" + ("; redownload attempted" if auto else "; pass auto=true to download top pick"),
    })
