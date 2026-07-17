"""Unit tests for CloudDrive offline (mocked gRPC)."""
from __future__ import annotations

from media_mgmt_lib.providers.clouddrive.client import (
    CloudDriveConfig,
    CloudDriveClient,
    _redact_magnet,
)
from media_mgmt_lib.workflows import list_workflows, run_workflow
import media_mgmt_lib.ops.bootstrap  # noqa: F401
from media_mgmt_lib.catalog import list_service_ids, load_service


def test_clouddrive_service_declared():
    assert "clouddrive" in list_service_ids()
    svc = load_service("clouddrive")
    assert "add_offline" in svc.ops
    assert "health" in svc.ops


def test_offline_workflow_registered():
    names = {w["name"] for w in list_workflows()}
    assert "offline" in names


def test_config_from_url_and_save_paths():
    conf = CloudDriveConfig.from_dict(
        {
            "url": "http://192.168.1.68:19798",
            "token": "x",
            "save_paths": [{"path": "/115open/download/av", "label": "AV"}],
        }
    )
    assert conf.host == "192.168.1.68"
    assert conf.port == 19798
    assert conf.default_folder == "/115open/download/av"
    assert conf.target == "192.168.1.68:19798"


def test_redact_magnet():
    m = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=foo"
    out = _redact_magnet(m)
    assert out.startswith("magnet:?xt=urn:btih:")
    assert "dn=foo" not in out


def test_offline_workflow_missing_magnet():
    r = run_workflow("offline", {})
    assert r.get("success") is False or r.get("error") == "missing_param" or (
        isinstance(r.get("error"), str)
    )
    # fail() shape
    assert r.get("error") == "missing_param" or r.get("need") == "magnet|urls|url" or (
        (r.get("result") or {}).get("error") == "missing_param"
        if isinstance(r.get("result"), dict)
        else r.get("error") == "missing_param"
    )


def test_add_offline_missing_urls(monkeypatch):
    conf = CloudDriveConfig.from_dict(
        {"host": "127.0.0.1", "port": 19798, "token": "t", "default_folder": "/x"}
    )
    client = CloudDriveClient(conf)
    out = client.add_offline("")
    assert out["success"] is False
    assert out["error"] == "missing_param"
