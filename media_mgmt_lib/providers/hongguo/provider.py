"""Hongguo short-drama provider for media-mgmt.

Uses the public SSR ``window._ROUTER_DATA`` surface of hongguoduanju.com
to parse series metadata and resolve episode media URLs.  Public episodes
(the first ``accessible_episode_cnt``) yield full MP4 URLs; locked episodes
return ``None`` so the caller can decide next steps.
"""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import parser as hg

_DEFAULT_DOWNLOAD_DIR = Path("/vol02/1000-0-8501d321/torrents/TV/短剧")


@dataclass
class HongguoRequest:
    url: str
    action: str = "parse"  # parse | download | info | list_episodes
    download_dir: Path | None = None
    episode: int | None = None  # 1-indexed; None = all accessible
    proxy: str | None = None
    timeout: float = hg.DEFAULT_TIMEOUT


@dataclass
class HongguoResult:
    success: bool
    action: str = ""
    series_id: str = ""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    intro: str = ""
    cover: str = ""
    episode_count: int = 0
    accessible_episode_count: int = 0
    chapters: list[dict[str, Any]] = field(default_factory=list)
    episodes: list[dict[str, Any]] = field(default_factory=list)
    file_path: Path | None = None
    file_size: int = 0
    error: str = ""


def _download_file(url: str, dest: Path, timeout: float, proxy: str | None = None) -> int:
    """Stream-download *url* to *dest*; return bytes written."""
    session = hg.make_session(proxy)
    try:
        resp = session.get(url, timeout=timeout, stream=True, allow_redirects=True)
        resp.raise_for_status()
        size = 0
        with open(dest, "wb") as fp:
            for chunk in resp.iter_content(65536):
                fp.write(chunk)
                size += len(chunk)
        return size
    finally:
        session.close()


def _sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name)
    name = name.strip(". ")
    return name[:max_len] if name else "hongguo_video"


class HongguoProvider:
    """High-level façade over the parser module."""

    # -- public API ----------------------------------------------------------

    def run(self, req: HongguoRequest) -> HongguoResult:
        action = req.action.lower()
        try:
            if action == "parse":
                return self._parse(req)
            if action == "info":
                return self._info(req)
            if action == "list_episodes":
                return self._list_episodes(req)
            if action == "download":
                return self._download(req)
            return HongguoResult(success=False, action=action, error=f"unknown action: {action}")
        except hg.ParseError as exc:
            return HongguoResult(success=False, action=action, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return HongguoResult(success=False, action=action, error=f"unexpected: {exc}")

    # -- internals -----------------------------------------------------------

    def _load_seed(self, req: HongguoRequest) -> tuple[dict[str, Any], str]:
        session = hg.make_session(req.proxy)
        try:
            series, referer, _ = hg.load_series_seed(session, req.url, timeout=req.timeout)
            return series, referer
        finally:
            session.close()

    def _parse(self, req: HongguoRequest) -> HongguoResult:
        series, _ = self._load_seed(req)
        chapters: list[dict[str, Any]] = []
        for i, vid in enumerate(series.get("chapter_ids", []), 1):
            chapters.append({"index": i, "vid": vid})
        return HongguoResult(
            success=True,
            action="parse",
            series_id=series["series_id"],
            title=series.get("title") or "",
            tags=series.get("tags") or [],
            intro=series.get("intro") or "",
            cover=series.get("cover") or "",
            episode_count=series.get("episode_count") or 0,
            accessible_episode_count=series.get("accessible_episode_count") or 0,
            chapters=chapters,
        )

    def _info(self, req: HongguoRequest) -> HongguoResult:
        return self._parse(req)

    def _list_episodes(self, req: HongguoRequest) -> HongguoResult:
        series, referer = self._load_seed(req)
        accessible = series.get("accessible_episode_count") or 0
        episodes: list[dict[str, Any]] = []
        for i, vid in enumerate(series.get("chapter_ids", []), 1):
            ep: dict[str, Any] = {"index": i, "vid": vid, "accessible": i <= accessible}
            episodes.append(ep)
        return HongguoResult(
            success=True,
            action="list_episodes",
            series_id=series["series_id"],
            title=series.get("title") or "",
            episode_count=series.get("episode_count") or 0,
            accessible_episode_count=accessible,
            episodes=episodes,
        )

    def _resolve_episode_url(
        self, series: dict[str, Any], referer: str, vid: str, req: HongguoRequest,
    ) -> dict[str, Any] | None:
        return hg.request_player_for_vid(
            req.proxy,
            series["series_id"],
            vid,
            timeout=req.timeout,
            referer=referer,
            validate_media=True,
            min_url_ttl=120,
        )

    def _download(self, req: HongguoRequest) -> HongguoResult:
        series, referer = self._load_seed(req)
        title = series.get("title") or series["series_id"]
        accessible = series.get("accessible_episode_count") or 0
        chapter_ids = series.get("chapter_ids") or []
        if not chapter_ids:
            return HongguoResult(success=False, action="download", error="no chapters found")

        dl_dir = req.download_dir or _DEFAULT_DOWNLOAD_DIR
        dl_dir.mkdir(parents=True, exist_ok=True)

        # Determine which episodes to download
        if req.episode is not None:
            idx = req.episode - 1
            if idx < 0 or idx >= len(chapter_ids):
                return HongguoResult(
                    success=False, action="download",
                    error=f"episode {req.episode} out of range (1-{len(chapter_ids)})",
                )
            targets = [(req.episode, chapter_ids[idx])]
        else:
            targets = [(i + 1, vid) for i, vid in enumerate(chapter_ids[:accessible])]

        if not targets:
            return HongguoResult(success=False, action="download", error="no accessible episodes")

        downloaded_paths: list[Path] = []
        for ep_idx, vid in targets:
            info = self._resolve_episode_url(series, referer, vid, req)
            if info is None or not info.get("url"):
                continue
            url = info["url"]
            ext = "mp4"
            suffix = f"E{ep_idx:02d}"
            fname = _sanitize(f"{title}-{suffix}") + f".{ext}"
            dest = dl_dir / fname
            size = _download_file(url, dest, req.timeout, req.proxy)
            downloaded_paths.append(dest)
            # Return first result as the main result
            if len(downloaded_paths) == 1:
                return HongguoResult(
                    success=True,
                    action="download",
                    series_id=series["series_id"],
                    title=title,
                    episode_count=series.get("episode_count") or 0,
                    accessible_episode_count=accessible,
                    file_path=dest,
                    file_size=size,
                )

        if downloaded_paths:
            return HongguoResult(
                success=True,
                action="download",
                series_id=series["series_id"],
                title=title,
                episode_count=series.get("episode_count") or 0,
                accessible_episode_count=accessible,
                file_path=downloaded_paths[-1],
            )
        return HongguoResult(success=False, action="download", error="could not resolve any episode URL")
