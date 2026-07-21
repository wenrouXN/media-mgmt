"""library workflow: exists = NextFind; MP = organize history only."""
from __future__ import annotations

from typing import Any

from media_mgmt_lib.workflows import library as lib_wf


def test_library_exists_follows_nf_not_mp(monkeypatch):
    def fake_identify(params, title, tmdbid, mtype):
        return {
            "path": "nextfind_openapi",
            "selected": {
                "title": title or "Demo",
                "tmdb_id": 1,
                "type": "movie",
                "is_in_library": True,
                "local_episodes": 1,
            },
        }

    def fake_nf_library(tmdbid, media_type):
        return {
            "library_info": {
                "success": True,
                "data": [{"tmdb_id": "1", "is_in_library": True, "local_episodes": 1}],
            }
        }

    def fake_mp_transfer(title, tmdbid):
        return {"has_transfer_record": False, "transfer_count": 0, "sample": []}

    def fake_mp(*args, **kwargs):
        # missing_episodes or anything — should not drive exists
        return {"exists": False, "success": True}

    monkeypatch.setattr(lib_wf, "_identify", fake_identify)
    monkeypatch.setattr(lib_wf, "_nf_library", fake_nf_library)
    monkeypatch.setattr(lib_wf, "_mp_transfer_records", fake_mp_transfer)
    monkeypatch.setattr(lib_wf, "mp", fake_mp)

    r = lib_wf.run({"title": "Demo", "media_type": "movie"})
    assert r.get("exists") is True
    assert r.get("authority") == "nextfind"
    assert r.get("exists_mp") is None
    assert r.get("has_transfer_record") is False


def test_library_nf_down_no_mp_fallback(monkeypatch):
    def fake_identify(params, title, tmdbid, mtype):
        return {"path": "moviepilot", "selected": {"title": "X", "tmdb_id": 2, "type": "movie"}}

    def fake_nf_library(tmdbid, media_type):
        return {"error": "nextfind_not_configured"}

    monkeypatch.setattr(lib_wf, "_identify", fake_identify)
    monkeypatch.setattr(lib_wf, "_nf_library", fake_nf_library)
    monkeypatch.setattr(
        lib_wf,
        "_mp_transfer_records",
        lambda *a, **k: {"has_transfer_record": True, "transfer_count": 1, "sample": []},
    )
    monkeypatch.setattr(lib_wf, "mp", lambda *a, **k: {"exists": True})

    r = lib_wf.run({"title": "X", "media_type": "movie"})
    assert r.get("exists") is None
    assert r.get("authority") == "nextfind_unavailable"
    assert r.get("has_transfer_record") is True
