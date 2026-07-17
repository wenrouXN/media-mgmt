from __future__ import annotations

from media_mgmt_lib.quality_pref import (
    has_chinese,
    has_fx_subtitle,
    has_hdr,
    is_original_disc,
    matches_quality,
    parse_quality_params,
    quality_score,
)
from media_mgmt_lib.torrent_pick import pick_torrent


def _item(title: str, seeders: int = 10) -> dict:
    return {
        "torrent_info": {
            "title": title,
            "site_name": "观众",
            "seeders": seeders,
            "downloadvolumefactor": 0,
            "enclosure": "https://x/a",
            "size": 1000,
        }
    }


def test_chinese_and_hdr_detection():
    assert has_chinese("Show 中字 2160p")
    assert has_chinese("Show.CHS.1080p")
    assert not has_chinese("Show English only 1080p")
    assert has_hdr("Show 2160p HDR10")
    assert has_hdr("Show DV DoVi")
    assert not has_hdr("Show 2160p SDR")


def test_matches_4k_sdr_chinese():
    ok = "金特务 S01E05 2160p SDR 中字"
    bad_hdr = "金特务 S01E05 2160p HDR10 中字"
    bad_res = "金特务 S01E05 1080p 中字"
    bad_lang = "金特务 S01E05 2160p SDR"
    assert matches_quality(ok, resolution="2160p", require_chinese=True, hdr_mode="sdr")
    assert not matches_quality(bad_hdr, resolution="2160p", require_chinese=True, hdr_mode="sdr")
    assert not matches_quality(bad_res, resolution="2160p", require_chinese=True, hdr_mode="sdr")
    assert not matches_quality(bad_lang, resolution="2160p", require_chinese=True, hdr_mode="sdr")


def test_pick_prefers_quality_match():
    items = [
        _item("Show S01E05 1080p 中字", seeders=99),
        _item("Show S01E05 2160p HDR 中字", seeders=50),
        _item("Show S01E05 2160p SDR 中字", seeders=20),
        _item("Show S01E05 2160p SDR", seeders=80),
    ]
    picked = pick_torrent(
        items,
        season=1,
        episode=5,
        prefer_resolution="2160p",
        require_chinese=True,
        hdr_mode="sdr",
        top_n=4,
    )
    assert picked["selected"] is not None
    title = picked["selected"]["torrent_info"]["title"]
    assert "2160p" in title and "SDR" in title and "中字" in title


def test_parse_quality_params():
    p = parse_quality_params({"resolution": "4k", "lang": "zh", "hdr_mode": "sdr"})
    assert p["resolution"] == "2160p"
    assert p["require_chinese"] is True
    assert p["hdr_mode"] == "sdr"
    q = quality_score("x 2160p 中字 SDR", resolution="2160p", require_chinese=True, hdr_mode="sdr")
    assert q["matches_hard"] is True
    assert q["score"] >= 50


def test_fallback_best_seeded_resolution():
    """No 4K SDR match: pick highest resolution among seeded torrents."""
    items = [
        _item("Show S01E05 720p 中字", seeders=99),
        _item("Show S01E05 1080p 中字", seeders=5),
        _item("Show S01E05 2160p HDR 中字", seeders=0),  # better res but dead
        _item("Show S01E05 480p", seeders=50),
    ]
    picked = pick_torrent(
        items,
        season=1,
        episode=5,
        prefer_resolution="2160p",
        require_chinese=False,
        hdr_mode="sdr",
        top_n=4,
    )
    assert picked["selected"] is not None
    title = picked["selected"]["torrent_info"]["title"]
    # preferred 4K SDR missing; among seeded, 1080p wins over 720/480; zero-seed 4K loses
    assert "1080p" in title


def test_prefer_seeded_4k_sdr_over_more_seeders_1080():
    items = [
        _item("Show S01E05 1080p 中字", seeders=200),
        _item("Show S01E05 2160p SDR 中字", seeders=3),
    ]
    picked = pick_torrent(
        items,
        season=1,
        episode=5,
        prefer_resolution="2160p",
        require_chinese=True,
        hdr_mode="sdr",
    )
    title = picked["selected"]["torrent_info"]["title"]
    assert "2160p" in title and "SDR" in title


def test_disc_and_fx_detection():
    assert is_original_disc("Movie 2024 UHD BluRay REMUX")
    assert is_original_disc("电影 蓝光原盘 BD50")
    assert not is_original_disc("Movie 2024 2160p WEB-DL 中字")
    assert has_fx_subtitle("Movie 2024 1080p 特效字幕")
    assert has_fx_subtitle("Movie 2024 1080p ASS 内封")
    assert not has_fx_subtitle("Movie 2024 1080p 中字")


def test_movie_prefers_fx_sub_over_plain_chinese_higher_res():
    items = [
        _item("Movie 2024 2160p 中字", seeders=50),
        _item("Movie 2024 1080p 特效字幕 中字", seeders=8),
        _item("Movie 2024 UHD BluRay REMUX 中字", seeders=99),
    ]
    picked = pick_torrent(
        items,
        prefer_resolution="",
        require_chinese=True,
        prefer_fx_sub=True,
        exclude_disc=True,
        top_n=3,
    )
    title = picked["selected"]["torrent_info"]["title"]
    assert "特效字幕" in title
    assert "REMUX" not in title


def test_movie_fallback_best_chinese_when_no_fx():
    items = [
        _item("Movie 2024 720p 中字", seeders=40),
        _item("Movie 2024 2160p 中字", seeders=5),
        _item("Movie 2024 1080p English", seeders=80),
        _item("Movie 2024 BD50 原盘 中字", seeders=90),
    ]
    picked = pick_torrent(
        items,
        prefer_resolution="",
        require_chinese=True,
        prefer_fx_sub=True,
        exclude_disc=True,
        top_n=4,
    )
    title = picked["selected"]["torrent_info"]["title"]
    assert "2160p" in title and "中字" in title
    assert "原盘" not in title and "English" not in title
