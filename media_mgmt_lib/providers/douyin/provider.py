"""Douyin provider for media-mgmt."""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DouyinRequest:
    url: str
    action: str = "parse"
    download_dir: Path | None = None
    api_base_url: str = "http://localhost:7899"
    timeout: float = 60.0


@dataclass
class DouyinResult:
    success: bool
    action: str
    title: str = ""
    author: str = ""
    description: str = ""
    stats: dict = field(default_factory=dict)
    chapter_abstract: str = ""
    tags: list = field(default_factory=list)
    duration: int = 0
    music_title: str = ""
    music_url: str = ""
    file_path: Path | None = None
    file_size: int = 0
    file_format: str = ""
    raw_data: dict = field(default_factory=dict)
    error: str = ""


def _api_get(url: str, timeout: float) -> dict:
    """GET request returning parsed JSON."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """Remove characters that are unsafe for filenames."""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "untitled"


class DouyinProvider:
    provider_name = "douyin"

    async def run(self, request: DouyinRequest) -> DouyinResult:
        if request.action == "download":
            return self.download(request.url, request.download_dir, request.api_base_url, request.timeout)
        return self.parse(request.url, request.api_base_url, request.timeout)

    def parse(self, url: str, api_base_url: str, timeout: float) -> DouyinResult:
        try:
            api_url = f"{api_base_url.rstrip('/')}/api/hybrid/video_data?url={urllib.parse.quote(url, safe='')}"
            data = _api_get(api_url, timeout)

            # API may wrap in "data" or return directly
            video = data.get("data", data)

            desc = video.get("desc", "") or video.get("description", "")
            author_info = video.get("author", {})
            if isinstance(author_info, dict):
                author = author_info.get("nickname", "") or author_info.get("name", "")
            else:
                author = str(author_info) if author_info else ""

            # Stats
            stats = {}
            for key in ("digg_count", "comment_count", "share_count", "collect_count"):
                val = video.get(key)
                if val is not None:
                    stats[key] = val
            # Also try nested stats
            if not stats:
                raw_stats = video.get("statistics", video.get("stats", {}))
                if isinstance(raw_stats, dict):
                    stats = {
                        "likes": raw_stats.get("digg_count", 0),
                        "comments": raw_stats.get("comment_count", 0),
                        "shares": raw_stats.get("share_count", 0),
                        "collects": raw_stats.get("collect_count", 0),
                    }

            # Tags
            tags = []
            text_extra = video.get("text_extra", [])
            if isinstance(text_extra, list):
                for item in text_extra:
                    tag = item.get("hashtag_name", "")
                    if tag:
                        tags.append(tag)

            # Music
            music_info = video.get("music", {})
            music_title = music_info.get("title", "") if isinstance(music_info, dict) else ""
            music_url = music_info.get("play_url", {}).get("uri", "") if isinstance(music_info, dict) and isinstance(music_info.get("play_url"), dict) else ""
            if not music_url and isinstance(music_info, dict):
                music_url = music_info.get("play_url", "") if isinstance(music_info.get("play_url"), str) else ""

            # Duration
            duration = video.get("duration", 0)
            if isinstance(duration, str):
                try:
                    duration = int(duration)
                except ValueError:
                    duration = 0

            return DouyinResult(
                success=True,
                action="parse",
                title=video.get("title", "") or desc[:80],
                author=author,
                description=desc,
                stats=stats,
                chapter_abstract=video.get("chapter_abstract", ""),
                tags=tags,
                duration=duration,
                music_title=music_title,
                music_url=music_url,
                raw_data=data,
            )
        except Exception as exc:
            return DouyinResult(success=False, action="parse", error=str(exc))

    def download(self, url: str, download_dir: Path | None, api_base_url: str, timeout: float) -> DouyinResult:
        try:
            if download_dir is None:
                download_dir = Path.cwd()
            download_dir.mkdir(parents=True, exist_ok=True)

            # First parse to get title/author for filename
            parse_result = self.parse(url, api_base_url, timeout)
            if parse_result.success:
                name = _sanitize_filename(f"{parse_result.title}-{parse_result.author}")
            else:
                name = "douyin_video"

            api_url = f"{api_base_url.rstrip('/')}/api/download?url={urllib.parse.quote(url, safe='')}"
            req = urllib.request.Request(api_url)

            out_path = download_dir / f"{name}.mp4"
            # Avoid collision
            counter = 1
            while out_path.exists():
                out_path = download_dir / f"{name}_{counter}.mp4"
                counter += 1

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                file_size = 0
                with open(out_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        file_size += len(chunk)

            return DouyinResult(
                success=True,
                action="download",
                file_path=out_path,
                file_size=file_size,
                file_format="mp4",
                title=parse_result.title if parse_result.success else "",
                author=parse_result.author if parse_result.success else "",
            )
        except Exception as exc:
            return DouyinResult(success=False, action="download", error=str(exc))
