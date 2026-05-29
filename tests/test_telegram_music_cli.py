from argparse import Namespace

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
