from media_mgmt_lib.torrent_pick import (
    extract_episode,
    filter_and_rank,
    matches_episode,
    pick_torrent,
    score_torrent,
    summarize_candidate,
)


def _item(title: str, *, site: str = "观众", seeders: int = 10, free: float = 1.0, enclosure: str | None = "https://x/a") -> dict:
    return {
        "torrent_info": {
            "title": title,
            "site_name": site,
            "seeders": seeders,
            "downloadvolumefactor": free,
            "enclosure": enclosure,
            "size": 1000,
        }
    }


def test_extract_episode_patterns():
    assert extract_episode("Agent Kim Reactivated S01E05 1080p") == 5
    assert extract_episode("金特务 第05集") == 5
    assert extract_episode("Show E5 720p") == 5


def test_matches_episode_and_range():
    assert matches_episode(_item("Show S01E05"), episode=5)
    assert not matches_episode(_item("Show S01E04"), episode=5)
    assert matches_episode(_item("Show S01E03-E05"), episode=5)


def test_pick_prefers_exact_episode_seeders_and_free():
    items = [
        _item("Show S01E05 720p", seeders=5, free=1.0),
        _item("Show S01E05 1080p", seeders=20, free=0.5, site="天空"),
        _item("Show S01E04 1080p", seeders=99, free=0.0),
    ]
    picked = pick_torrent(items, season=1, episode=5, prefer_resolution="1080p", site_priority=["天空", "观众"])
    assert picked["selected"] is not None
    assert "E05" in picked["selected"]["torrent_info"]["title"]
    assert "1080p" in picked["selected"]["torrent_info"]["title"]


def test_filter_and_rank_falls_back_when_no_episode_match():
    items = [_item("Show Complete S01", seeders=1)]
    ranked = filter_and_rank(items, episode=5)
    assert len(ranked) == 1


def test_score_penalizes_missing_enclosure():
    a = _item("Show S01E05 1080p", seeders=50, enclosure=None)
    b = _item("Show S01E05 1080p", seeders=5, enclosure="https://x/b")
    assert score_torrent(b, episode=5) > score_torrent(a, episode=5)


def test_summarize_candidate():
    s = summarize_candidate(_item("Show S01E05 1080p", site="天空", seeders=9))
    assert s["site_name"] == "天空"
    assert s["episode"] == 5
    assert s["enclosure"] is True
