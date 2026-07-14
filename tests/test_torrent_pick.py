from datetime import datetime, timedelta, timezone

from media_mgmt_lib.torrent_pick import (
    extract_episode,
    extract_title_year,
    filter_and_rank,
    matches_episode,
    pick_torrent,
    pubdate_age_days,
    score_torrent,
    summarize_candidate,
    year_match_score,
)


def _item(
    title: str,
    *,
    site: str = "观众",
    seeders: int = 10,
    free: float = 1.0,
    enclosure: str | None = "https://x/a",
    pubdate: str | None = None,
) -> dict:
    ti = {
        "title": title,
        "site_name": site,
        "seeders": seeders,
        "downloadvolumefactor": free,
        "enclosure": enclosure,
        "size": 1000,
    }
    if pubdate is not None:
        ti["pubdate"] = pubdate
    return {"torrent_info": ti}


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


def test_extract_title_year():
    assert extract_title_year("The Dream Life of Mr Kim S01E06 2025 1080p NF WEB-DL") == 2025
    assert extract_title_year("Blossoms of Power S01E01 2026 2160p") == 2026


def test_year_match_prefers_correct_year():
    wrong = _item("Show S01E06 2024 1080p", seeders=99, pubdate="2026-07-10 10:00:00")
    right = _item("Show S01E06 2025 1080p", seeders=5, pubdate="2026-07-10 10:00:00")
    picked = pick_torrent([wrong, right], episode=6, media_year=2025, prefer_resolution="1080p")
    assert "2025" in picked["selected"]["torrent_info"]["title"]
    assert year_match_score(wrong, 2025) == 0
    assert year_match_score(right, 2025) == 2


def test_fresh_pubdate_beats_old_seed():
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    old = _item(
        "Show S01E06 2025 1080p",
        seeders=50,
        pubdate=(now - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    fresh = _item(
        "Show S01E06 2025 1080p",
        seeders=3,
        pubdate=(now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    picked = pick_torrent([old, fresh], episode=6, media_year=2025, now=now, prefer_resolution="1080p")
    assert pubdate_age_days(picked["selected"], now=now) < 5


def test_needs_confirm_on_old_or_low_seeders():
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    old = _item(
        "Show S01E06 2025 1080p",
        seeders=1,
        pubdate=(now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    picked = pick_torrent([old], episode=6, media_year=2025, now=now)
    assert picked["needs_confirm"] is True
    assert "low_seeders" in picked["confirm_reasons"]
    assert "pubdate_old" in picked["confirm_reasons"]
