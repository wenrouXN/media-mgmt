"""Tests for shared .credentials injection."""
from __future__ import annotations

from pathlib import Path

from media_mgmt_lib.credentials import (
    SECRET_MAP,
    inject_secrets,
    load_kv_file,
    redact_config_for_log,
    resolve_credentials_dir,
)
from media_mgmt_lib.config import load_json_config


def test_load_kv_file(tmp_path: Path):
    p = tmp_path / "x.env"
    p.write_text("# c\nFOO=bar\nBAZ= qux \n", encoding="utf-8")
    kvs = load_kv_file(p)
    assert kvs["FOO"] == "bar"
    assert kvs["BAZ"] == "qux"


def test_inject_secrets_prefers_file_over_config(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MOVIEPILOT_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("MOVIEPILOT_BASE_URL", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    file_key = "FILE_KEY_VALUE"
    config_key = "CONFIG_KEY_VALUE"
    (tmp_path / "moviepilot.env").write_text(
        f"MOVIEPILOT_API_KEY={file_key}\nMOVIEPILOT_BASE_URL=http://from-file\n",
        encoding="utf-8",
    )
    cfg = {
        "moviepilot": {
            "base_url": "http://from-config",
            "api_key": config_key,
        }
    }
    out = inject_secrets(cfg, cred_dir=tmp_path)
    assert out["moviepilot"]["api_key"] == file_key
    # optional only fills when empty
    assert out["moviepilot"]["base_url"] == "http://from-config"
    # must not mutate global SECRET_MAP
    assert "base_url" not in SECRET_MAP["moviepilot"]


def test_inject_secrets_env_wins(tmp_path: Path, monkeypatch):
    file_token = "FILE_TOKEN_VALUE"
    env_token = "ENV_TOKEN_VALUE"
    (tmp_path / "clouddrive.env").write_text(
        f"CLOUDDRIVE_TOKEN={file_token}\n", encoding="utf-8"
    )
    monkeypatch.setenv("CLOUDDRIVE_TOKEN", env_token)
    out = inject_secrets({"clouddrive": {}}, cred_dir=tmp_path)
    assert out["clouddrive"]["token"] == env_token


def test_redact_only_secret_fields():
    secret_key = "SECRET_KEY_VALUE"
    secret_token = "SECRET_TOKEN_VALUE"
    cfg = {
        "moviepilot": {"base_url": "http://x", "api_key": secret_key},
        "clouddrive": {"url": "http://y", "token": secret_token},
    }
    red = redact_config_for_log(cfg)
    assert red["moviepilot"]["base_url"] == "http://x"
    assert red["moviepilot"]["api_key"] == "***"
    assert red["clouddrive"]["url"] == "http://y"
    assert red["clouddrive"]["token"] == "***"


def test_resolve_credentials_dir_exists():
    d = resolve_credentials_dir()
    assert d.name == ".credentials" or d.exists()


def test_live_load_injects_when_files_present():
    """If this host has migrated env files, secrets appear after load."""
    d = resolve_credentials_dir()
    has_mp = (d / "moviepilot.env").exists()
    has_cd = (d / "clouddrive.env").exists()
    cfg = load_json_config()
    if has_mp:
        assert (cfg.get("moviepilot") or {}).get("api_key")
    if has_cd:
        assert (cfg.get("clouddrive") or {}).get("token")
