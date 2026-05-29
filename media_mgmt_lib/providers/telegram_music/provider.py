"""Telegram music provider for media-mgmt."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from media_mgmt_lib.provider_base import ProviderRunRequest

try:
    from dotenv import load_dotenv
    from telethon import TelegramClient, sessions
    from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
except ImportError:
    load_dotenv = None
    TelegramClient = None
    sessions = None
    GetBotCallbackAnswerRequest = None


def ensure_runtime_dependencies() -> None:
    if load_dotenv is None or TelegramClient is None or sessions is None or GetBotCallbackAnswerRequest is None:
        raise RuntimeError(
            "Missing dependencies: telethon and/or python-dotenv. "
            "Run this script inside an environment with these packages installed."
        )


def is_message_after(*, message_id: int, after_id: int) -> bool:
    return message_id > after_id


def extract_callback_buttons(reply_markup: Any) -> list[dict[str, Any]]:
    buttons: list[dict[str, Any]] = []
    if not reply_markup:
        return buttons
    for row in getattr(reply_markup, "rows", []):
        for btn in getattr(row, "buttons", []):
            data = getattr(btn, "data", None)
            if data:
                buttons.append({"text": getattr(btn, "text", ""), "data": data})
    return buttons


def resolve_button_choice(buttons: list[dict[str, Any]], *, button_index: int = 1, button_text: str | None = None) -> dict[str, Any]:
    if not buttons:
        raise RuntimeError("No callback buttons found on result message")

    if button_text:
        for btn in buttons:
            if btn.get("text") == button_text:
                return btn
        raise RuntimeError(f"Button text not found: {button_text}")

    if button_index < 1 or button_index > len(buttons):
        raise RuntimeError(f"Button index out of range: {button_index}")
    return buttons[button_index - 1]


def build_search_message(query: str) -> str:
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        raise RuntimeError("Query cannot be empty")
    if normalized.startswith("/search"):
        suffix = normalized[len("/search"):].strip()
        if not suffix:
            raise RuntimeError("Query cannot be empty")
        return f"/search {suffix}"
    return f"/search {normalized}"


def load_creds(request: ProviderRunRequest):
    api_id = request.api_id
    api_hash = request.api_hash
    session_string = request.session_string
    session_name = request.session_name
    if not api_id or not api_hash:
        raise RuntimeError("Missing Telegram api_id/api_hash in config")
    if not session_string and not session_name:
        raise RuntimeError("Need Telegram session_string or session_name in config")
    return int(api_id), api_hash, session_string, session_name


def build_client(api_id: int, api_hash: str, session_string: str, session_name: str):
    assert sessions is not None and TelegramClient is not None
    if session_string:
        session = sessions.StringSession(session_string)
    else:
        session = session_name
    return TelegramClient(session, api_id, api_hash)


async def wait_for_new_bot_message_with_buttons(client, bot: str, after_id: int, timeout: float, poll_interval: float):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msgs = await client.get_messages(bot, limit=10)
        candidates = [m for m in msgs if (not m.out) and is_message_after(message_id=m.id, after_id=after_id) and m.reply_markup]
        if candidates:
            return max(candidates, key=lambda m: m.id)
        await asyncio.sleep(poll_interval)
    raise TimeoutError("Timed out waiting for bot search result with inline buttons")


async def wait_for_new_file_message(client, bot: str, after_id: int, timeout: float, poll_interval: float):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msgs = await client.get_messages(bot, limit=10)
        candidates = [m for m in msgs if (not m.out) and is_message_after(message_id=m.id, after_id=after_id) and m.file]
        if candidates:
            return max(candidates, key=lambda m: m.id)
        await asyncio.sleep(poll_interval)
    raise TimeoutError("Timed out waiting for bot file response")


def infer_download_filename(file_msg: Any) -> str:
    if getattr(file_msg.file, "name", None):
        return file_msg.file.name
    ext = "bin"
    if getattr(file_msg.file, "mime_type", None):
        mime = file_msg.file.mime_type
        if "/" in mime:
            ext = mime.split("/", 1)[1].replace("mpeg", "mp3")
    return f"telegram-bot-file-{file_msg.id}.{ext}"


class TelegramMusicProvider:
    provider_name = "telegram_music"

    async def run(self, request: ProviderRunRequest) -> Path:
        ensure_runtime_dependencies()
        assert GetBotCallbackAnswerRequest is not None

        api_id, api_hash, session_string, session_name = load_creds(request)
        download_dir = Path(request.download_dir)
        download_dir.mkdir(parents=True, exist_ok=True)

        client = build_client(api_id, api_hash, session_string, session_name)
        await client.start()
        try:
            baseline = await client.get_messages(request.bot, limit=1)
            last_id = baseline[0].id if baseline else 0

            search_message = build_search_message(request.query)
            print(f"[1/4] send search: {search_message}")
            await client.send_message(request.bot, search_message)

            print("[2/4] wait for inline result")
            result_msg = await wait_for_new_bot_message_with_buttons(
                client, request.bot, last_id, request.search_timeout, request.poll_interval
            )
            print(f"result message id={result_msg.id}")

            buttons = extract_callback_buttons(result_msg.reply_markup)
            print("available buttons:")
            for idx, btn in enumerate(buttons, start=1):
                print(f"  {idx}. text={btn['text']} data={btn['data']!r}")

            target = resolve_button_choice(buttons, button_index=request.button_index, button_text=request.button_text or None)

            print(f"[3/4] click button: {target['text']}")
            await client(GetBotCallbackAnswerRequest(peer=request.bot, msg_id=result_msg.id, data=target["data"]))

            print("[4/4] wait for returned file")
            file_msg = await wait_for_new_file_message(
                client, request.bot, result_msg.id, request.download_timeout, request.poll_interval
            )

            out_path = download_dir / infer_download_filename(file_msg)
            saved = await file_msg.download_media(file=out_path)
            print(f"downloaded: {saved}")
            if file_msg.text:
                print("caption:")
                print(file_msg.text)
            return Path(saved) if saved else out_path
        finally:
            await client.disconnect()
