"""Telegram music provider for media-mgmt."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from media_mgmt_lib.music_pick import decide_auto_download, rank_candidates
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


def resolve_button_choice(
    buttons: list[dict[str, Any]],
    *,
    button_index: int = 1,
    button_text: str | None = None,
) -> dict[str, Any]:
    if not buttons:
        raise RuntimeError("No callback buttons found on result message")

    if button_text:
        for btn in buttons:
            if btn.get("text") == button_text:
                return btn
        # fuzzy: normalized contains
        from media_mgmt_lib.music_pick import normalize_text

        target = normalize_text(button_text)
        for btn in buttons:
            if target and target in normalize_text(str(btn.get("text") or "")):
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

    async def search_candidates(self, request: ProviderRunRequest) -> dict[str, Any]:
        """Send /search and return ranked button candidates (no download)."""
        ensure_runtime_dependencies()
        api_id, api_hash, session_string, session_name = load_creds(request)
        client = build_client(api_id, api_hash, session_string, session_name)
        await client.start()
        try:
            baseline = await client.get_messages(request.bot, limit=1)
            last_id = baseline[0].id if baseline else 0
            search_message = build_search_message(request.query)
            await client.send_message(request.bot, search_message)
            result_msg = await wait_for_new_bot_message_with_buttons(
                client, request.bot, last_id, request.search_timeout, request.poll_interval
            )
            buttons = extract_callback_buttons(result_msg.reply_markup)
            ranked = rank_candidates(request.query, buttons)
            decision = decide_auto_download(request.query, ranked)
            # strip raw callback data from public candidates if bytes-like noise; keep index/text/score
            public = []
            for c in ranked:
                public.append(
                    {
                        "index": c["index"],
                        "text": c["text"],
                        "score": c["score"],
                        "exact": c.get("exact"),
                        "token_coverage": c.get("token_coverage"),
                        "reasons": c.get("reasons"),
                    }
                )
            return {
                "success": True,
                "query": request.query,
                "bot": request.bot,
                "result_message_id": result_msg.id,
                "result_text": (result_msg.message or result_msg.text or "")[:500],
                "candidates": public,
                "candidate_count": len(public),
                "decision": {
                    "auto": decision.get("auto"),
                    "needs_confirm": decision.get("needs_confirm"),
                    "confidence": decision.get("confidence"),
                    "reason": decision.get("reason"),
                    "gap": decision.get("gap"),
                    "suggested": decision.get("selected"),
                },
                "buttons_raw_count": len(buttons),
            }
        finally:
            await client.disconnect()

    async def download_choice(self, request: ProviderRunRequest) -> dict[str, Any]:
        """Search again (or rely on fresh search) and download a specific button choice."""
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
            await client.send_message(request.bot, search_message)
            result_msg = await wait_for_new_bot_message_with_buttons(
                client, request.bot, last_id, request.search_timeout, request.poll_interval
            )
            buttons = extract_callback_buttons(result_msg.reply_markup)
            ranked = rank_candidates(request.query, buttons)

            target = resolve_button_choice(
                buttons,
                button_index=request.button_index,
                button_text=request.button_text or None,
            )
            await client(
                GetBotCallbackAnswerRequest(peer=request.bot, msg_id=result_msg.id, data=target["data"])
            )
            file_msg = await wait_for_new_file_message(
                client, request.bot, result_msg.id, request.download_timeout, request.poll_interval
            )
            out_path = download_dir / infer_download_filename(file_msg)
            saved = await file_msg.download_media(file=out_path)
            path = Path(saved) if saved else out_path
            return {
                "success": True,
                "query": request.query,
                "path": str(path),
                "chosen": {"text": target.get("text"), "index": next((i for i, b in enumerate(buttons, 1) if b is target or b.get("text") == target.get("text")), request.button_index)},
                "candidates": [
                    {"index": c["index"], "text": c["text"], "score": c["score"]} for c in ranked[:10]
                ],
                "caption": (file_msg.text or "")[:300] if getattr(file_msg, "text", None) else None,
            }
        finally:
            await client.disconnect()

    async def run(self, request: ProviderRunRequest) -> Path:
        """Backward-compatible: search + download with optional auto policy.

        If button_text/button_index explicitly set by caller beyond defaults, honor them.
        For policy-aware behavior, prefer search_candidates + download_choice via ops.
        """
        result = await self.download_choice(request)
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "download_failed")
        return Path(result["path"])
