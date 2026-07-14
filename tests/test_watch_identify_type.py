
import json
import scripts.watch as watch
import scripts.mp_api as mp_api


def test_media_shell_usable():
    assert not watch._media_shell_usable({})
    assert not watch._media_shell_usable({"title": None, "tmdb_id": None})
    assert watch._media_shell_usable({"tmdb_id": 1})
    assert watch._media_shell_usable({"title": "X"})


def test_fetch_tmdb_detail_retries_movie_when_tv_shell(monkeypatch):
    calls = []

    def fake_request(method, path, params=None, body=None):
        calls.append(params.get("type_name") if params else None)
        if params and params.get("type_name") == "电视剧":
            return {"title": None, "tmdb_id": None, "type": None}
        if params and params.get("type_name") == "电影":
            return {"title": "格杀福顺", "tmdb_id": 849869, "type": "电影", "year": "2023"}
        raise AssertionError(params)

    monkeypatch.setattr(mp_api, "request", fake_request)
    detail = watch._fetch_tmdb_detail(849869, title="格杀福顺", year="2023", media_type=None)
    assert detail["title"] == "格杀福顺"
    assert detail["type"] == "电影"
    assert calls == ["电影", "电视剧"] or calls[0] in {"电影", "电视剧"}


def test_fetch_tmdb_detail_prefers_title_match_over_first_shell(monkeypatch):
    """Same numeric TMDB id can resolve to different movie/tv works."""

    def fake_request(method, path, params=None, body=None):
        if params and params.get("type_name") == "电影":
            return {
                "title": "喜剧中心帕米拉·安德森吐槽大会",
                "tmdb_id": 296206,
                "type": "电影",
                "year": "2005",
            }
        if params and params.get("type_name") == "电视剧":
            return {
                "title": "金特务：本色回归",
                "original_title": "김부장",
                "tmdb_id": 296206,
                "type": "电视剧",
                "year": "2026",
            }
        raise AssertionError(params)

    monkeypatch.setattr(mp_api, "request", fake_request)
    detail = watch._fetch_tmdb_detail(
        296206,
        title="金特务：本色回归",
        year=None,
        media_type=None,
        prefer_tv=True,
    )
    assert detail["title"] == "金特务：本色回归"
    assert detail["type"] == "电视剧"


def test_identify_media_with_tmdbid_movie(monkeypatch):
    def fake_request(method, path, params=None, body=None):
        if path.startswith("/api/v1/media/tmdb:"):
            if params and params.get("type_name") == "电视剧":
                return {"title": None, "tmdb_id": None}
            return {"title": "格杀福顺", "tmdb_id": 849869, "type": "电影", "year": "2023"}
        raise AssertionError(path)

    monkeypatch.setattr(mp_api, "request", fake_request)
    media = watch.identify_media("格杀福顺", None, None, 849869)
    assert media["tmdb_id"] == 849869
    assert media["title"] == "格杀福顺"


def test_identify_media_episode_prefers_tv_for_shared_tmdbid(monkeypatch):
    def fake_request(method, path, params=None, body=None):
        if path.startswith("/api/v1/media/tmdb:"):
            if params and params.get("type_name") == "电影":
                return {
                    "title": "Comedy Central Roast of Pamela Anderson",
                    "tmdb_id": 296206,
                    "type": "电影",
                    "year": "2005",
                }
            return {
                "title": "金特务：本色回归",
                "tmdb_id": 296206,
                "type": "电视剧",
                "year": "2026",
            }
        raise AssertionError(path)

    monkeypatch.setattr(mp_api, "request", fake_request)
    media = watch.identify_media("金特务：本色回归", None, None, 296206, episode=1)
    assert media["type"] == "电视剧"
    assert media["title"] == "金特务：本色回归"
