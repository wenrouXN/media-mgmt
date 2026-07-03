import asyncio
import json

import pytest

from media_mgmt_lib.providers.hdhive import grab


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_get_first_cdp_ws_url_chooses_page_target(monkeypatch):
    monkeypatch.setattr(grab, "resolve_profile_id", lambda: "profile-id")
    monkeypatch.setattr(grab, "ensure_profile_running", lambda profile_id: None)
    monkeypatch.setattr(
        grab.urllib.request,
        "urlopen",
        lambda url: FakeResponse(
            [
                {"type": "service_worker", "webSocketDebuggerUrl": "ws://service-worker"},
                {"type": "page", "url": "https://hdhive.com/movie/1", "webSocketDebuggerUrl": "ws://page"},
            ]
        ),
    )

    assert asyncio.run(grab.get_first_cdp_ws_url()) == "ws://page"


def test_get_first_cdp_ws_url_rejects_non_page_targets(monkeypatch):
    monkeypatch.setattr(grab, "resolve_profile_id", lambda: "profile-id")
    monkeypatch.setattr(grab, "ensure_profile_running", lambda profile_id: None)
    monkeypatch.setattr(
        grab.urllib.request,
        "urlopen",
        lambda url: FakeResponse(
            [
                {"type": "service_worker", "webSocketDebuggerUrl": "ws://service-worker"},
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="No browser page CDP target"):
        asyncio.run(grab.get_first_cdp_ws_url())
