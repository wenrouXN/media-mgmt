import argparse
import json

import scripts.mp_api as mp_api


def test_choose_download_path_uses_moviepilot_category_config():
    media = {"type": "movie", "original_language": "es", "origin_country": ["ES"]}
    paths = [
        {
            "media_type": "电影",
            "media_category": "西语电影",
            "save_path": "/qbs/torrents/Movies/西语电影/",
            "priority": 1,
        },
        {
            "media_type": "电影",
            "media_category": "欧美电影",
            "save_path": "/qbs/torrents/Movies/欧美电影/",
            "priority": 2,
        },
    ]
    category_config = {
        "success": True,
        "data": {
            "movie": {
                "西语电影": {
                    "genre_ids": None,
                    "original_language": "es",
                    "origin_country": None,
                    "production_countries": None,
                    "release_year": None,
                },
                "欧美电影": {
                    "genre_ids": None,
                    "original_language": "en",
                    "origin_country": None,
                    "production_countries": None,
                    "release_year": None,
                },
            }
        },
    }

    resolved = mp_api.choose_download_path(media, paths, category_config)

    assert resolved["media_category"] == "西语电影"
    assert resolved["save_path"] == "/qbs/torrents/Movies/西语电影/"
    assert resolved["source"] == "exact"


def test_cmd_download_fetches_category_config_for_path_resolution(monkeypatch, capsys):
    calls = []

    def fake_request(method, path, params=None, body=None):
        calls.append((method, path, params, body))
        if path == "/api/v1/download/paths":
            return [
                {
                    "media_type": "电影",
                    "media_category": "西语电影",
                    "save_path": "/qbs/torrents/Movies/西语电影/",
                    "priority": 1,
                }
            ]
        if path == "/api/v1/media/category/config":
            return {
                "success": True,
                "data": {
                    "movie": {
                        "西语电影": {
                            "genre_ids": None,
                            "original_language": "es",
                            "origin_country": None,
                            "production_countries": None,
                            "release_year": None,
                        }
                    }
                },
            }
        raise AssertionError(f"unexpected request path: {path}")

    monkeypatch.setattr(mp_api, "request", fake_request)
    args = argparse.Namespace(
        media_json=json.dumps({"type": "movie", "original_language": "es", "origin_country": ["ES"]}),
        torrent_json=json.dumps({"title": "sample", "enclosure": "https://example.invalid/a.torrent"}),
        save_path=None,
        dry_run=True,
        downloader=None,
        tmdbid=None,
        doubanid=None,
    )

    mp_api.cmd_download(args)

    output = json.loads(capsys.readouterr().out)
    assert [call[1] for call in calls] == ["/api/v1/download/paths", "/api/v1/media/category/config"]
    assert output["save_path"] == "/qbs/torrents/Movies/西语电影/"
    assert output["resolved_path"]["media_category"] == "西语电影"
