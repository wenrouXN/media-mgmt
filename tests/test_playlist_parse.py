from __future__ import annotations

from media_mgmt_lib.playlist_parse import (
    SUPPORTED_PLATFORMS,
    PlaylistTrack,
    apply_limit,
    build_query,
    detect_platform,
    parse_playlist,
    _netease_track,
    _qq_track,
    _kuwo_track,
    _kugou_track,
    UnsupportedPlaylistURL,
    PlaylistParseError,
)
import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.ops import call_op
from media_mgmt_lib.workflows import list_workflows, run_workflow


def test_detect_platform():
    assert detect_platform("https://music.163.com/#/playlist?id=1") == "netease"
    assert detect_platform("https://y.qq.com/n/ryqq/playlist/123") == "qq"
    assert detect_platform("https://www.kuwo.cn/playlist_detail/99") == "kuwo"
    assert detect_platform("https://www.kugou.com/yy/special/single/1.html") == "kugou"
    assert detect_platform("https://open.spotify.com/playlist/abc") == "spotify"
    assert detect_platform("https://example.com/x") == "unknown"


def test_build_query_and_limit():
    assert build_query("晴天", "周杰伦") == "晴天 周杰伦"
    assert build_query("晴天", None) == "晴天"
    tracks = [
        PlaylistTrack(position=i, title=f"t{i}", artist="a")
        for i in range(1, 6)
    ]
    limited, truncated = apply_limit(tracks, 2)
    assert truncated is True
    assert len(limited) == 2
    limited2, truncated2 = apply_limit(tracks, 10)
    assert truncated2 is False
    assert len(limited2) == 5


def test_track_mappers():
    n = _netease_track(
        {
            "id": 11,
            "name": "晴天",
            "ar": [{"name": "周杰伦"}],
            "al": {"name": "叶惠美", "picUrl": "http://x"},
            "dt": 269000,
        },
        1,
    )
    assert n is not None
    assert n.title == "晴天"
    assert n.artist == "周杰伦"
    assert n.album == "叶惠美"
    assert n.duration == 269
    assert n.query() == "晴天 周杰伦"

    q = _qq_track(
        {
            "mid": "m1",
            "title": "稻香",
            "singer": [{"name": "周杰伦"}],
            "album": {"title": "魔杰座", "mid": "ALB"},
            "interval": 223,
        },
        2,
    )
    assert q is not None
    assert q.artist == "周杰伦"
    assert "ALB" in (q.cover_url or "")

    k = _kuwo_track(
        {"musicrid": "MUSIC_9", "name": "演员", "artist": "薛之谦", "duration": 200},
        1,
    )
    assert k is not None
    assert k.external_id == "9"

    g = _kugou_track(
        {
            "hash": "abc",
            "songname": "海阔天空",
            "singername": "Beyond",
            "duration": 326,
        },
        1,
    )
    assert g is not None
    assert g.title == "海阔天空"


def test_unsupported_empty_and_spotify(monkeypatch):
    try:
        parse_playlist("")
        assert False, "expected error"
    except UnsupportedPlaylistURL as e:
        assert e.code == "unsupported_url"

    class FakeClient:
        def head(self, *a, **k):
            raise RuntimeError("skip")

        def get(self, url, **k):
            class R:
                url = "https://open.spotify.com/playlist/x"
                def raise_for_status(self):
                    return None
            return R()

        def close(self):
            return None

    try:
        parse_playlist("https://open.spotify.com/playlist/x", client=FakeClient())
        assert False
    except UnsupportedPlaylistURL as e:
        assert "Spotify" in str(e) or e.code == "unsupported_url"


def test_ops_and_workflow_registered():
    names = {w["name"] for w in list_workflows()}
    assert "playlist" in names
    cap = call_op("playlist", "capabilities", {})
    assert cap.get("success") is True
    assert "netease" in (cap.get("platforms") or [])
    missing = run_workflow("playlist", {})
    assert missing.get("success") is False
    assert missing.get("error") == "missing_param"


def test_ops_parse_with_mock(monkeypatch):
    from media_mgmt_lib import playlist_parse as pp

    def fake_parse(url, **kwargs):
        from media_mgmt_lib.playlist_parse import ParsedPlaylist, PlaylistTrack

        return ParsedPlaylist(
            platform="netease",
            external_id="1",
            name="测试歌单",
            source_url=url,
            tracks=[
                PlaylistTrack(position=1, title="晴天", artist="周杰伦", external_id="11"),
                PlaylistTrack(position=2, title="稻香", artist="周杰伦", external_id="12"),
            ],
            track_count=2,
        )

    monkeypatch.setattr(pp, "parse_playlist", fake_parse)
    # ops imports parse_playlist at module level — patch ops.playlist too
    import media_mgmt_lib.ops.playlist as ops_pl

    monkeypatch.setattr(ops_pl, "parse_playlist", fake_parse)
    r = call_op("playlist", "parse", {"url": "https://music.163.com/#/playlist?id=1", "limit": 1})
    # fake ignores limit unless we re-apply — still success
    assert r.get("success") is True
    assert r.get("platform") == "netease"
    assert r.get("queries")
    w = run_workflow("playlist", {"url": "https://music.163.com/#/playlist?id=1"})
    assert w.get("success") is True
    assert w.get("workflow") == "playlist"
    assert "晴天" in (w.get("queries") or [""])[0]
