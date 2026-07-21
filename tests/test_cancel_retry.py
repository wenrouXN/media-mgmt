"""Unit tests for cancel + retry workflows (destructive / redownload paths)."""
from __future__ import annotations

from typing import Any

import pytest

from media_mgmt_lib.workflows import cancel as cancel_wf
from media_mgmt_lib.workflows import retry as retry_wf


def test_cancel_requires_filter():
    r = cancel_wf.run({})
    assert r.get("success") is False
    assert r.get("error") == "missing_param"
    assert "hash" in str(r.get("need") or "")


def test_cancel_dry_run_invokes_mp_api(monkeypatch):
    active = [
        {
            "hash": "abc123",
            "title": "Demo",
            "downloader": "QB",
            "media": {"title": "Demo"},
        }
    ]

    def fake_request(method, path, params=None, body=None):  # noqa: ANN001
        if method == "GET" and path == "/api/v1/download/":
            return active
        raise AssertionError(f"unexpected {method} {path}")

    import scripts.mp_api as mp_api

    monkeypatch.setattr(mp_api, "request", fake_request)
    r = cancel_wf.run({"hash": "abc123", "dry_run": True})
    assert r.get("success") is True
    assert r.get("workflow") == "cancel"
    res = r.get("result") or {}
    assert res.get("cancelled") == 1
    assert res.get("results")[0].get("dry_run") is True


def test_cancel_delete_files_flag(monkeypatch):
    active = [
        {
            "hash": "h1",
            "title": "千博士",
            "downloader": "QB",
            "media": {"title": "千博士"},
        }
    ]
    deleted: list[Any] = []

    def fake_request(method, path, params=None, body=None):  # noqa: ANN001
        if method == "GET" and path == "/api/v1/download/":
            return active
        if method == "DELETE":
            deleted.append((path, params))
            return {"success": True}
        raise AssertionError(f"unexpected {method} {path}")

    import scripts.mp_api as mp_api

    monkeypatch.setattr(mp_api, "request", fake_request)
    r = cancel_wf.run({"title": "千博士", "delete_files": True})
    assert r.get("success") is True
    assert deleted
    assert deleted[0][1].get("delete") == "true"


def test_cancel_failure_when_no_match(monkeypatch):
    def fake_request(method, path, params=None, body=None):  # noqa: ANN001
        if method == "GET" and path == "/api/v1/download/":
            return []
        raise AssertionError("no delete expected")

    import scripts.mp_api as mp_api

    monkeypatch.setattr(mp_api, "request", fake_request)
    r = cancel_wf.run({"hash": "nope", "dry_run": True})
    assert r.get("success") is False
    assert r.get("error") == "cancel_failed"
    assert (r.get("result") or {}).get("error") == "no_matching_active_download"


def test_retry_requires_title():
    r = retry_wf.run({})
    assert r.get("success") is False
    assert r.get("error") == "missing_param"


def test_retry_defaults_force_mp_search(monkeypatch):
    seen: list[dict[str, Any]] = []

    def fake_search(params):
        seen.append(dict(params))
        return {"success": True, "workflow": "search", "result_count": 0}

    monkeypatch.setattr(retry_wf.search_wf, "run", fake_search)
    r = retry_wf.run({"title": "X"})
    assert r.get("workflow") == "retry"
    assert seen and seen[0].get("force_mp_search") is True
    assert r.get("auto") is False


def test_retry_auto_calls_watch(monkeypatch):
    monkeypatch.setattr(
        retry_wf.search_wf,
        "run",
        lambda params: {"success": True, "workflow": "search"},
    )
    calls: list[dict[str, Any]] = []

    def fake_watch(params):
        calls.append(dict(params))
        return {"success": True, "workflow": "watch", "dry_run": True}

    monkeypatch.setattr(retry_wf.watch_wf, "run", fake_watch)
    r = retry_wf.run({"title": "X", "auto": True, "dry_run": True})
    assert calls and calls[0].get("prefer") == "pt"
    assert r.get("auto") is True
