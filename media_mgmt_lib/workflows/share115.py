from __future__ import annotations
from typing import Any
from media_mgmt_lib.workflows._util import fail, ok, mp

def run(params: dict[str, Any]) -> dict[str, Any]:
    share_url = params.get("share_url") or params.get("url") or params.get("link")
    password = params.get("password")
    if not share_url:
        return fail("missing_param", need="share_url")
    # append password if separate
    if password and "password=" not in str(share_url):
        sep = "&" if "?" in str(share_url) else "?"
        share_url = f"{share_url}{sep}password={password}"
    # Guard: never hand password=*** to the plugin (always becomes 访问码错误).
    text = str(share_url)
    if "***" in text or ("password=" in text.lower() and "*" in text.split("password=", 1)[-1][:8]):
        return fail(
            "masked_or_invalid_share_password",
            share_url=text.split("password=")[0] + ("password=***" if "password=" in text else ""),
            hint="Need plaintext 115 password; re-run HDHive unlock or provide password explicitly",
        )
    result = mp("transfer_share", share_url=share_url)
    code = None
    msg = None
    if isinstance(result.get("result"), dict):
        code = result["result"].get("code")
        msg = result["result"].get("msg")
    success = bool(result.get("success"))
    already = msg and "已经转存" in str(msg)
    return ok({
        "workflow": "share115",
        "share_url": share_url.split("password=")[0] + ("password=***" if "password=" in str(share_url) else ""),
        "success": success or already,
        "already": bool(already),
        "result": result,
        "summary": msg or ("转存成功" if success else result.get("error") or "转存失败"),
    })
