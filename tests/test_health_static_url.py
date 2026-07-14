
from media_mgmt_lib.catalog import Service
from media_mgmt_lib.ops import health as health_mod


def test_resolve_url_static_catalog_url():
    svc = Service(
        id="hongguo",
        name="Hongguo",
        kind="content_provider",
        description="",
        config_section="hongguo",
        required_config=[],
        ops=["health"],
        health={"type": "http_get", "url": "https://hongguoduanju.com", "ok_status": [200, 301, 302]},
        raw={},
    )
    url = health_mod._resolve_url(svc, {}, svc.health)
    assert url == "https://hongguoduanju.com"


def test_resolve_url_static_with_path():
    url = health_mod._resolve_url(
        Service(
            id="x", name="x", kind="x", description="", config_section="x",
            required_config=[], ops=[], health={}, raw={},
        ),
        {},
        {"url": "https://example.com", "path": "status"},
    )
    assert url == "https://example.com/status"


def test_check_service_uses_static_url(monkeypatch):
    svc = Service(
        id="hongguo",
        name="Hongguo",
        kind="content_provider",
        description="",
        config_section="hongguo",
        required_config=[],
        ops=["health"],
        health={"type": "http_get", "url": "https://hongguoduanju.com", "ok_status": [200, 301, 302]},
        raw={},
    )

    def fake_http_get(url, timeout=8.0):
        assert url == "https://hongguoduanju.com"
        return 200, "ok", "ok"

    monkeypatch.setattr(health_mod, "_http_get", fake_http_get)
    result = health_mod.check_service(svc, root_config={})
    assert result["success"] is True
    assert result["status"] == "ok"
    assert result["error"] != "no_url" if "error" in result else True
