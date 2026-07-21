"""Hard lock filters for PT pick (site_name / title / page_url)."""
from __future__ import annotations

from media_mgmt_lib.torrent_pick import filter_items_by_lock, site_matches


def _item(site: str, title: str, page: str = "") -> dict:
    return {
        "torrent_info": {
            "site_name": site,
            "title": title,
            "enclosure": "http://example/a.torrent",
            "seeders": 5,
            "page_url": page,
        }
    }


def test_site_matches_aliases():
    assert site_matches("彩虹岛", "chdbits")
    assert site_matches("彩虹岛", "CHD")
    assert site_matches("天空", "hdsky")
    assert site_matches("HDSky", "天空")
    assert not site_matches("天空", "彩虹岛")


def test_filter_by_site_name():
    items = [
        _item("彩虹岛", "Dr Cheon CHDBits Blu-ray"),
        _item("天空", "Dr Cheon HDSky BluRay"),
        _item("憨憨", "Dr Cheon WEB-DL"),
    ]
    locked = filter_items_by_lock(items, site_name="彩虹岛")
    assert len(locked) == 1
    assert locked[0]["torrent_info"]["site_name"] == "彩虹岛"

    locked2 = filter_items_by_lock(items, site_name="chdbits")
    assert len(locked2) == 1


def test_filter_by_title_contains():
    items = [
        _item("天空", "Dr Cheon BluRay JXN@HDSky"),
        _item("天空", "Dr Cheon x265 HDS"),
    ]
    locked = filter_items_by_lock(items, title_contains="JXN@HDSky")
    assert len(locked) == 1
    assert "JXN" in locked[0]["torrent_info"]["title"]


def test_filter_by_page_url():
    items = [
        _item("彩虹岛", "A", page="https://ptchdbits.co/details.php?id=332966"),
        _item("天空", "B", page="https://hdsky.me/details.php?id=377370"),
    ]
    locked = filter_items_by_lock(items, page_url="id=332966")
    assert len(locked) == 1
    assert locked[0]["torrent_info"]["site_name"] == "彩虹岛"


def test_filter_no_match_empty():
    items = [_item("天空", "x")]
    assert filter_items_by_lock(items, site_name="彩虹岛") == []
