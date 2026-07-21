"""result_gate + grab hard block + watch_pipeline."""
from __future__ import annotations

from media_mgmt_lib.result_gate import (
    decorate_agent_result,
    grab_resources_gate,
)
from media_mgmt_lib.watch_pipeline import is_tv_media, pick_for_watch, quality_policy


def test_decorate_surfaces_warnings():
    r = decorate_agent_result(
        {
            "success": True,
            "warnings": ["nf_search_hint_but_resources_empty"],
            "resource_authority": "resources_op",
        }
    )
    assert "warnings" in r["agent_must_read_keys"]
    assert "resource_authority" in r["agent_must_read_keys"]
    assert "Agent: read fields" in (r.get("summary") or r.get("agent_note") or "")


def test_grab_gate_blocks_empty_resources():
    g = grab_resources_gate(resources=[], search_hint_count=3, force_grab=True)
    assert g is not None
    assert g["success"] is False
    assert g["error"] == "nf_search_hint_but_resources_empty"
    assert g.get("force_grab_ignored") is True


def test_grab_gate_allows_with_resources():
    assert grab_resources_gate(resources=[{"slug": "x"}]) is None


def test_quality_policy_movie_defaults():
    p = quality_policy(is_tv=False)
    assert p["exclude_disc"] is True
    assert p["require_chinese"] is True
    assert p["prefer_fx_sub"] is True


def test_quality_policy_tv_4k():
    p = quality_policy(is_tv=True)
    assert p["prefer_resolution"] == "2160p"
    assert p["hdr_mode"] == "sdr"


def test_is_tv_from_episode():
    assert is_tv_media(None, 5, {"type": "movie"}) is True
    assert is_tv_media("movie", None, None) is False


def test_pick_for_watch_lock():
    items = [
        {
            "torrent_info": {
                "site_name": "彩虹岛",
                "title": "Demo CHDBits",
                "enclosure": "http://a",
                "seeders": 5,
                "size": 1,
            }
        },
        {
            "torrent_info": {
                "site_name": "天空",
                "title": "Demo HDSky",
                "enclosure": "http://b",
                "seeders": 9,
                "size": 1,
            }
        },
    ]
    r = pick_for_watch(items, site_name="彩虹岛", media_type="movie", allow_disc=True)
    assert r.get("error") != "lock_no_match"
    assert r.get("selected")
    assert r["selected"]["site_name"] == "彩虹岛"
