"""Unit tests for nf_evidence + watch_pick pure helpers."""
from __future__ import annotations

from media_mgmt_lib.nf_evidence import (
    classify_resources,
    consistency_report,
    is_netdisk_item,
    is_pt_item,
    nf_subscribe_active,
    parse_in_library,
    subscribe_state,
)
from media_mgmt_lib.watch_pick import apply_lock_and_pick, map_pick_n_to_index


def test_parse_in_library_from_list():
    li = {
        "success": True,
        "data": [{"tmdb_id": "129", "is_in_library": True, "local_episodes": 1}],
    }
    assert parse_in_library(li, None) is True
    assert parse_in_library({"success": True, "data": {"is_in_library": False}}, None) is False


def test_classify_and_consistency_warning():
    items = [
        {"slug": "hdhive://a", "source_type": "hdhive"},
        {"enclosure": "http://x", "seeders": 3, "site": "彩虹岛"},
    ]
    c = classify_resources(items)
    assert c["netdisk_count"] == 1
    assert c["pt_count"] == 1
    w = consistency_report(search_hint_count=2, resources_count=0)
    assert "nf_search_hint_but_resources_empty" in w["warnings"]
    assert w["ok"] is False


def test_subscribe_state_machine():
    assert subscribe_state(mp=True, nf=True) == "both"
    assert subscribe_state(mp=True, nf=False) == "mp_only"
    assert subscribe_state(mp=False, nf=True) == "nf_only"
    assert subscribe_state(mp=False, nf=False) == "none"
    assert subscribe_state(mp=False, nf=False, nf_err=True) == "nf_down"


def test_nf_subscribe_active_list():
    info = {
        "success": True,
        "data": [{"tmdb_id": "129", "title": "千与千寻", "is_in_library": True}],
    }
    assert nf_subscribe_active(info, 129) is True
    assert nf_subscribe_active({"success": True, "data": []}, 129) is False


def test_map_pick_n():
    assert map_pick_n_to_index(1) == 0
    assert map_pick_n_to_index(3) == 2
    try:
        map_pick_n_to_index(0)
        assert False
    except ValueError:
        pass


def test_apply_lock_and_pick_site():
    items = [
        {
            "torrent_info": {
                "site_name": "彩虹岛",
                "title": "Dr Cheon CHDBits Blu-ray",
                "enclosure": "http://a",
                "seeders": 10,
                "size": 100,
            }
        },
        {
            "torrent_info": {
                "site_name": "天空",
                "title": "Dr Cheon HDSky BluRay",
                "enclosure": "http://b",
                "seeders": 20,
                "size": 100,
            }
        },
    ]
    r = apply_lock_and_pick(items, site_name="彩虹岛", pick_index=0, exclude_disc=False)
    assert r["success"] is True
    assert r["lock"]["matched"] == 1
    assert r["selected"]["site_name"] == "彩虹岛"

    miss = apply_lock_and_pick(items, site_name="不存在的站")
    assert miss["error"] == "lock_no_match"


def test_is_netdisk_115_url():
    assert is_netdisk_item({"media_url": "https://115cdn.com/s/xxx"})
    assert not is_pt_item({"media_url": "https://115cdn.com/s/xxx"})
