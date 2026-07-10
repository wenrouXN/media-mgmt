from __future__ import annotations

import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op, list_ops
from media_mgmt_lib.ops import api7899


def test_douyin_bilibili_tiktok_hybrid_complete():
    for sid in ("douyin", "bilibili", "tiktok", "hybrid"):
        info = list_ops(sid)
        assert info["complete"] is True, f"{sid} missing {info.get('missing')}"


def test_douyin_capabilities_lists_named_ops():
    r = call_op("douyin", "capabilities", {})
    assert r.get("success") is True
    names = {x["op"] for x in r.get("ops") or []}
    assert "comments" in names
    assert "user_posts" in names
    assert "hybrid_video" in names


def test_bilibili_capabilities_has_danmaku_parts():
    r = call_op("bilibili", "capabilities", {})
    names = {x["op"] for x in r.get("ops") or []}
    assert "danmaku" in names
    assert "parts" in names
    assert "playurl" in names


def test_raw_api_requires_path():
    r = call_op("douyin", "api", {})
    assert r.get("success") is False
    assert "path" in str(r.get("need"))


def test_hybrid_detect_platform():
    from media_mgmt_lib.ops.hybrid import detect_platform

    assert detect_platform("https://v.douyin.com/abc") == "douyin"
    assert detect_platform("https://www.bilibili.com/video/BV1xx") == "bilibili"
    assert detect_platform("https://www.tiktok.com/@x/video/1") == "tiktok"


def test_named_maps_non_empty():
    assert len(api7899.DOUYIN_NAMED) >= 10
    assert len(api7899.BILIBILI_NAMED) >= 10
    assert len(api7899.TIKTOK_NAMED) >= 5
