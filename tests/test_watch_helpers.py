import argparse
import json

import scripts.mp_api as mp_api
from media_mgmt_lib.torrent_pick import pick_torrent


def test_validate_torrent_and_media():
    assert mp_api.validate_torrent_info({"title": "a", "enclosure": "http://x"}) == []
    assert "enclosure" in mp_api.validate_torrent_info({"title": "a"})
    assert mp_api.validate_media_info({"type": "电视剧", "title": "X", "tmdb_id": 1}, require_full=True) == []
    assert "tmdb_id|douban_id" in mp_api.validate_media_info({"type": "电视剧", "title": "X"}, require_full=True)


def test_extract_torrent_and_media_from_wrappers():
    search = {"torrent_info": {"title": "t", "enclosure": "e", "site_name": "s"}, "media_info": {"type": "电视剧", "title": "M", "tmdb_id": 9}}
    assert mp_api.extract_torrent_info(search)["title"] == "t"
    assert mp_api.extract_media_info({"media_info": {"title": "M"}})["title"] == "M"
    assert mp_api.extract_media_info({"selected": {"title": "S"}, "source": "media-search"})["title"] == "S"


def test_cmd_download_validation_fails_fast(monkeypatch, capsys):
    calls = []

    def fake_request(method, path, params=None, body=None):
        calls.append(path)
        raise AssertionError("should not call API on validation failure")

    monkeypatch.setattr(mp_api, "request", fake_request)
    args = argparse.Namespace(
        media_json=json.dumps({"type": "tv"}),  # incomplete
        torrent_json=json.dumps({"title": "only-title"}),  # missing enclosure
        from_search_result=None,
        save_path="/tmp",
        dry_run=False,
        downloader=None,
        tmdbid=None,
        doubanid=None,
    )
    try:
        mp_api.cmd_download(args)
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "validation_failed"
    assert "enclosure" in out["missing_torrent_fields"]
    assert calls == []


def test_cmd_download_from_search_result_dry_run(monkeypatch, capsys):
    def fake_request(method, path, params=None, body=None):
        if path == "/api/v1/download/paths":
            return [{"media_type": "电视剧", "media_category": "日韩剧", "save_path": "/qbs/torrents/TV/日韩剧/", "priority": 1}]
        if path == "/api/v1/media/category/config":
            return {"success": True, "data": {"tv": {"日韩剧": {"original_language": "ko", "origin_country": "KR"}}}}
        raise AssertionError(path)

    monkeypatch.setattr(mp_api, "request", fake_request)
    search = {
        "torrent_info": {
            "title": "Agent Kim Reactivated S01E05 1080p",
            "enclosure": "https://example.invalid/a.torrent",
            "site_name": "观众",
            "seeders": 10,
        }
    }
    media = {
        "type": "电视剧",
        "title": "金特务：本色回归",
        "tmdb_id": 296206,
        "original_language": "ko",
        "origin_country": ["KR"],
    }
    args = argparse.Namespace(
        media_json=json.dumps(media),
        torrent_json=None,
        from_search_result=json.dumps(search),
        save_path=None,
        dry_run=True,
        downloader="QB",
        tmdbid=None,
        doubanid=None,
    )
    mp_api.cmd_download(args)
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] is True
    assert out["save_path"].endswith("日韩剧/")
    assert out["torrent_in"]["title"].startswith("Agent Kim")


def test_pick_integrates_with_mp_api_cmd(monkeypatch, capsys):
    items = [
        {"torrent_info": {"title": "Show S01E04", "enclosure": "http://a", "site_name": "A", "seeders": 9}},
        {"torrent_info": {"title": "Show S01E05 1080p", "enclosure": "http://b", "site_name": "B", "seeders": 3}},
    ]
    args = argparse.Namespace(
        results_json=json.dumps(items),
        season=1,
        episode=5,
        resolution="1080p",
        site_priority=None,
        top=3,
    )
    mp_api.cmd_pick(args)
    out = json.loads(capsys.readouterr().out)
    assert out["selected_summary"]["episode"] == 5
    assert "E05" in out["selected_summary"]["title"]


def test_pick_torrent_topn():
    items = [
        {"torrent_info": {"title": "S01E05 a", "enclosure": "http://a", "site_name": "A", "seeders": 1}},
        {"torrent_info": {"title": "S01E05 b", "enclosure": "http://b", "site_name": "B", "seeders": 5}},
    ]
    picked = pick_torrent(items, episode=5, top_n=2)
    assert len(picked["candidates"]) == 2
