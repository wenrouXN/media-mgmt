from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows import search as search_wf
from media_mgmt_lib.workflows import watch as watch_wf
from media_mgmt_lib.workflows._util import fail, ok


def run(params: dict[str, Any]) -> dict[str, Any]:
    """Re-list resources then optional redownload.

    Retry intent is usually PT/re-pick after a bad grab, so search defaults to
    force_mp_search unless caller already set a source preference.
    """
    title = params.get("title")
    if not title:
        return fail("missing_param", need="title")

    search_params = dict(params)
    # Retry almost always wants PT candidates; default force_mp_search unless NF-only forced.
    prefer = str(params.get("prefer") or "").lower()
    if prefer not in {"netdisk", "nextfind", "nf"} and not params.get("force_mp_search"):
        search_params.setdefault("force_mp_search", True)

    searched = search_wf.run(search_params)
    auto = str(params.get("auto") or params.get("yes") or "").lower() in {"1", "true", "yes"}
    downloaded = None
    if auto:
        watch_params = {
            **params,
            "yes": True,
            "skip_nextfind": params.get("skip_nextfind", True),
            "prefer": params.get("prefer") or "pt",
        }
        # map pick_n if provided
        downloaded = watch_wf.run(watch_params)
    return ok(
        {
            "workflow": "retry",
            "search": searched,
            "redownload": downloaded,
            "auto": auto,
            "summary": "listed candidates"
            + ("; redownload attempted" if auto else "; pass auto=true to download top pick"),
        }
    )
