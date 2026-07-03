from argparse import Namespace
import json

from media_mgmt_lib.providers.telegram_music.cli import resolve_runtime_settings, build_request


def ns(**overrides):
    base = dict(
        config=None,
        api_id=None,
        api_hash=None,
        session_string=None,
        session_name=None,
        bot=None,
        query="宋雨琦 radio",
        button_index=None,
        button_text=None,
        download_dir=None,
        search_timeout=None,
        download_timeout=None,
        poll_interval=None,
    )
    base.update(overrides)
    return Namespace(**base)


def test_config_defaults_are_preserved_when_cli_button_text_omitted():
    settings = resolve_runtime_settings(ns())
    assert settings["button_index"] == 1
    assert settings["button_text"] == ""
    req = build_request(settings)
    assert req.button_index == 1
    assert req.button_text == ""


def test_explicit_config_overrides_default_config_when_cli_value_omitted(tmp_path):
    override = {
        "telegram_music": {
            "api_id": 999999,
            "api_hash": "override-hash",
            "session_string": "override-session",
            "bot": "@override_bot",
            "download_dir": str(tmp_path / "music"),
            "button_index": 2,
            "search_timeout": 3,
            "download_timeout": 4,
            "poll_interval": 5,
        }
    }
    override_path = tmp_path / "telegram-config.json"
    override_path.write_text(json.dumps(override), encoding="utf-8")

    settings = resolve_runtime_settings(ns(config=str(override_path)))

    assert settings["api_id"] == 999999
    assert settings["api_hash"] == "override-hash"
    assert settings["session_string"] == "override-session"
    assert settings["bot"] == "@override_bot"
    assert settings["download_dir"] == str(tmp_path / "music")
    assert settings["button_index"] == 2
    assert settings["search_timeout"] == 3
    assert settings["download_timeout"] == 4
    assert settings["poll_interval"] == 5
