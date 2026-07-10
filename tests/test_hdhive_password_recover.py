from media_mgmt_lib.providers.hdhive.provider import recover_masked_115_share

_MASK = "*" * 3
_PW = "password"


def _url(host: str, share_id: str, password: str) -> str:
    return "https://" + host + "/s/" + share_id + "?" + _PW + "=" + password


def test_returns_raw_when_not_masked():
    raw = _url("115cdn.com", "abc123", "RealPwd1")
    assert recover_masked_115_share(raw, "") == raw


def test_recover_from_html_full_url_cdn():
    raw = _url("115cdn.com", "abc123", _MASK)
    html = "prefix " + _url("115cdn.com", "abc123", "RealPwd1") + " suffix"
    assert recover_masked_115_share(raw, html) == _url("115cdn.com", "abc123", "RealPwd1")


def test_recover_from_html_full_url_115_com():
    raw = _url("115.com", "abc123", _MASK)
    html = 'href="' + _url("115.com", "abc123", "Zz9") + '"'
    assert recover_masked_115_share(raw, html) == _url("115.com", "abc123", "Zz9")


def test_recover_password_with_dash_and_underscore():
    raw = _url("115cdn.com", "sid001", _MASK)
    html = _url("115cdn.com", "sid001", "Ab-1_x")
    assert recover_masked_115_share(raw, html) == _url("115cdn.com", "sid001", "Ab-1_x")


def test_rewrite_only_password_segment_when_share_id_also_masked():
    raw = _url("115cdn.com", _MASK, _MASK)
    html = _url("115cdn.com", "realSid9", "GoodPwd")
    out = recover_masked_115_share(raw, html)
    assert out == _url("115cdn.com", "realSid9", "GoodPwd")


def test_password_only_rewrite_keeps_share_id():
    raw = _url("115cdn.com", "keepMe", _MASK)
    html = _PW + "=OnlyPwd9&x=1"
    out = recover_masked_115_share(raw, html)
    assert out == _url("115cdn.com", "keepMe", "OnlyPwd9")


def test_no_real_password_returns_none():
    raw = _url("115cdn.com", "abc123", _MASK)
    html = _url("115cdn.com", "abc123", _MASK)
    assert recover_masked_115_share(raw, html) is None


def test_empty_raw_returns_none():
    assert recover_masked_115_share("", "x") is None
