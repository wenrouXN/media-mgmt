"""Provider registry for media-mgmt."""

from __future__ import annotations

from media_mgmt_lib.providers.telegram_music.provider import TelegramMusicProvider


_REGISTRY = {
    "telegram_music": TelegramMusicProvider(),
}


def get_provider(name: str):
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown provider: {name}") from exc
