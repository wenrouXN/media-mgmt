"""Provider registry for media-mgmt."""

from __future__ import annotations

from media_mgmt_lib.providers.telegram_music.provider import TelegramMusicProvider
from media_mgmt_lib.providers.douyin.provider import DouyinProvider
from media_mgmt_lib.providers.bilibili.provider import BilibiliProvider
from media_mgmt_lib.providers.hongguo.provider import HongguoProvider


_REGISTRY = {
    "telegram_music": TelegramMusicProvider(),
    "douyin": DouyinProvider(),
    "bilibili": BilibiliProvider(),
    "hongguo": HongguoProvider(),
}


def get_provider(name: str):
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown provider: {name}") from exc
