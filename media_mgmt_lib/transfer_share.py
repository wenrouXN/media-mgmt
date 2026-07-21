"""Plaintext 115 share → MoviePilot P115StrmHelper (no Cloak / no NextFind)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from media_mgmt_lib.config import load_json_config, moviepilot_credentials


def _is_usable_115_share(share_url: str) -> bool:
    text = (share_url or "").strip()
    if not text or "/s/" not in text or "***" in text:
        return False
    parsed = urllib.parse.urlparse(text)
    qs = urllib.parse.parse_qs(parsed.query)
    pwd = (qs.get("password") or [""])[0]
    return bool(pwd) and "*" not in pwd


def transfer_share_to_moviepilot(share_url: str, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Transfer a plaintext 115 share URL via P115StrmHelper.

    Refuses masked passwords (password=***) which always become 访问码错误.
    """
    conf = cfg if cfg is not None else load_json_config()
    creds = moviepilot_credentials(conf)
    if not creds.get("BASE_URL") or not creds.get("API_KEY"):
        raise RuntimeError("Missing moviepilot.base_url or moviepilot.api_key in config")
    if not _is_usable_115_share(share_url):
        return {
            "code": -1,
            "msg": "masked_or_invalid_share_password",
            "data": None,
            "share_url": share_url,
            "hint": "Need plaintext ?password=; password=*** cannot be transferred",
        }
    normalized = share_url.replace("https://115cdn.com/", "https://115.com/").replace(
        "http://115cdn.com/", "http://115.com/"
    )
    query = urllib.parse.urlencode({"apikey": creds["API_KEY"], "share_url": normalized})
    req = urllib.request.Request(
        f"{creds['BASE_URL'].rstrip('/')}/api/v1/plugin/P115StrmHelper/add_transfer_share?{query}"
    )
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=60).read())
    except Exception as e:  # noqa: BLE001
        return {"code": -1, "msg": str(e), "data": None, "error": str(e)}
    if not isinstance(payload, dict):
        return {"code": -1, "msg": "invalid_plugin_response", "data": payload}
    return payload
