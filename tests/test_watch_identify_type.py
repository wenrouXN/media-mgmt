
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
