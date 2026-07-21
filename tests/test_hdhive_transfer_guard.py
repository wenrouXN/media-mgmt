"""share115 / transfer_share guards (no Cloak)."""
from __future__ import annotations

from media_mgmt_lib import transfer_share as ts


def _url(pwd: str) -> str:
    return "https://115cdn.com/s/abc?" + "password=" + pwd


MASKED = _url("*" * 3)
PLAIN = _url("Ab12x")


def test_is_usable_115_share():
    assert not ts._is_usable_115_share(MASKED)
    assert not ts._is_usable_115_share("https://115cdn.com/s/abc")
    assert ts._is_usable_115_share(PLAIN)


def test_transfer_refuses_masked_password(monkeypatch):
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not call plugin with masked password")

    monkeypatch.setattr(ts.urllib.request, "urlopen", boom)
    out = ts.transfer_share_to_moviepilot(MASKED, cfg={"moviepilot": {"base_url": "http://x", "api_key": "k"}})
    assert out["code"] == -1
    assert out["msg"] == "masked_or_invalid_share_password"
    assert called["n"] == 0
