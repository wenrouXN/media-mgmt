from __future__ import annotations

import json
from pathlib import Path

from media_mgmt_lib.catalog import catalog_summary, list_service_ids, load_service
from media_mgmt_lib.ops.health import check_service


ROOT = Path(__file__).resolve().parents[1]


def test_services_dir_has_core_services():
    ids = list_service_ids()
    for req in (
        "moviepilot",
        "hdhive",
        "nextfind",
        "telegram_music",
        "douyin",
        "bilibili",
        "qbittorrent",
        "clouddrive",
    ):
        assert req in ids
    assert "pansou" not in ids
    assert "cloakbrowser" not in ids


def test_load_moviepilot_service_shape():
    svc = load_service("moviepilot")
    assert svc.id == "moviepilot"
    assert "health" in svc.ops
    assert "base_url" in svc.required_config
    assert svc.health.get("type") == "http_get"


def test_catalog_summary_configured_flags():
    rows = catalog_summary()
    assert isinstance(rows, list) and rows
    mp = next(r for r in rows if r["id"] == "moviepilot")
    assert "configured" in mp
    assert "ops" in mp


def test_health_moviepilot_live_or_skips_cleanly():
    svc = load_service("moviepilot")
    result = check_service(svc)
    assert result["service"] == "moviepilot"
    assert "status" in result
    # if config present in this environment, should be ok
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8")) if (ROOT / "config.json").exists() else {}
    if cfg.get("moviepilot", {}).get("base_url") and cfg.get("moviepilot", {}).get("api_key"):
        assert result.get("success") is True
