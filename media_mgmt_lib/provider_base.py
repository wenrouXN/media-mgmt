"""Base provider contracts for media-mgmt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class ProviderRunRequest:
    bot: str
    query: str
    download_dir: Path
    api_id: int | None = None
    api_hash: str = ""
    session_string: str = ""
    session_name: str = ""
    button_index: int = 1
    button_text: str = ""
    search_timeout: float = 20.0
    download_timeout: float = 30.0
    poll_interval: float = 1.0


class BaseMediaProvider(Protocol):
    provider_name: str

    async def run(self, request: ProviderRunRequest) -> Path:
        ...
