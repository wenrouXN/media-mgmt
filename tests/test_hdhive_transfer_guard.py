from media_mgmt_lib.providers.hdhive import grab
from media_mgmt_lib.ops import hdhive as hdhive_ops


def _url(pwd: str) -> str:
    return "https://115cdn.com/s/abc?" + "password=" + pwd


MASKED = _url("*" * 3)
PLAIN = _url("Ab12x")


def test_is_usable_115_share():
    assert not grab._is_usable_115_share(MASKED)
    assert not grab._is_usable_115_share("https://115cdn.com/s/abc")
    assert grab._is_usable_115_share(PLAIN)


def test_transfer_refuses_masked_password(monkeypatch):
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("should not call plugin with masked password")

    monkeypatch.setattr(grab.urllib.request, "urlopen", boom)
    out = grab.transfer_share_to_moviepilot(MASKED)
    assert out["code"] == -1
    assert out["msg"] == "masked_or_invalid_share_password"
    assert called["n"] == 0


def test_transfer_ok_helper():
    assert hdhive_ops._transfer_ok({"code": 0, "msg": "转存成功"})
    assert hdhive_ops._transfer_ok({"code": -1, "msg": "已经转存过了"})
    assert not hdhive_ops._transfer_ok({"code": -1, "msg": "访问码错误"})
    assert not hdhive_ops._transfer_ok({"error": "x"})
    assert not hdhive_ops._share_url_ok(MASKED)
    assert hdhive_ops._share_url_ok(PLAIN)
