"""Bilibili provider for media-mgmt."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BilibiliRequest:
    url: str
    action: str = "parse"
    download_dir: Path | None = None
    api_base_url: str = "http://localhost:7899"
    quality: int = 80
    timeout: float = 120.0


@dataclass
class BilibiliResult:
    success: bool
    action: str
    title: str = ""
    author: str = ""
    description: str = ""
    stats: dict = field(default_factory=dict)
    duration: int = 0
    bvid: str = ""
    aid: int = 0
    cid: int = 0
    pages: list = field(default_factory=list)
    file_path: Path | None = None
    file_size: int = 0
    file_format: str = ""
    raw_data: dict = field(default_factory=dict)
    error: str = ""


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}


def _api_get(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(url: str, dest: Path, timeout: float) -> int:
    """Stream download a file, return bytes written."""
    req = urllib.request.Request(url, headers=_HEADERS)
    size = 0
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
    return size


def _resolve_short_url(url: str, timeout: float = 10.0) -> str:
    """Resolve b23.tv short URLs to full bilibili.com URLs."""
    if "b23.tv" not in url:
        return url
    req = urllib.request.Request(url, headers=_HEADERS)
    req.method = "HEAD"
    # urllib doesn't auto-redirect HEAD, use GET with limited read
    req2 = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req2, timeout=timeout) as resp:
        return resp.url


def _extract_bvid(url: str) -> str:
    """Extract BV ID from a bilibili URL."""
    # Match BV followed by alphanumeric chars
    m = re.search(r'(BV[a-zA-Z0-9]+)', url)
    if m:
        return m.group(1)
    raise ValueError(f"Cannot extract BV ID from URL: {url}")


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "untitled"


class BilibiliProvider:
    provider_name = "bilibili"

    async def run(self, request: BilibiliRequest) -> BilibiliResult:
        if request.action == "download":
            return self.download(request.url, request.download_dir, request.api_base_url, request.quality, request.timeout)
        return self.parse(request.url, request.api_base_url, request.timeout)

    def parse(self, url: str, api_base_url: str, timeout: float) -> BilibiliResult:
        try:
            real_url = _resolve_short_url(url)
            bvid = _extract_bvid(real_url)

            api_url = f"{api_base_url.rstrip('/')}/api/bilibili/web/fetch_one_video?bv_id={urllib.parse.quote(bvid)}"
            data = _api_get(api_url, timeout)

            # API may wrap in "data" (possibly double-nested)
            video = data.get("data", data)
            # Handle double-nesting: {code, data: {code, data: {actual video}}}
            if isinstance(video, dict) and "data" in video and isinstance(video.get("data"), dict) and "bvid" in video.get("data", {}):
                video = video["data"]

            # Extract fields - handle nested structures
            title = video.get("title", "")
            desc = video.get("desc", "") or video.get("description", "")

            # Author
            author = ""
            owner = video.get("owner", {})
            if isinstance(owner, dict):
                author = owner.get("name", "")
            if not author:
                upper = video.get("upper", video.get("author", ""))
                author = upper if isinstance(upper, str) else ""

            # Stats
            stat = video.get("stat", video.get("stat_v2", {}))
            stats = {}
            if isinstance(stat, dict):
                for key, label in [("view", "view"), ("danmaku", "danmaku"), ("like", "like"),
                                   ("coin", "coin"), ("favorite", "favorite"), ("share", "share"),
                                   ("reply", "reply")]:
                    val = stat.get(key)
                    if val is not None:
                        stats[label] = val

            # Duration
            duration = video.get("duration", 0)
            if isinstance(duration, str):
                try:
                    duration = int(duration)
                except ValueError:
                    duration = 0

            # BV/AID/CID
            aid = video.get("aid", video.get("aid", 0))
            cid = video.get("cid", 0)
            # If cid is 0, try pages
            pages_raw = video.get("pages", [])
            pages = []
            if isinstance(pages_raw, list):
                for p in pages_raw:
                    pages.append({
                        "cid": p.get("cid", 0),
                        "page": p.get("page", 0),
                        "part": p.get("part", ""),
                        "duration": p.get("duration", 0),
                    })
                if not cid and pages:
                    cid = pages[0].get("cid", 0)

            return BilibiliResult(
                success=True,
                action="parse",
                title=title,
                author=author,
                description=desc,
                stats=stats,
                duration=duration,
                bvid=bvid,
                aid=aid if isinstance(aid, int) else 0,
                cid=cid if isinstance(cid, int) else 0,
                pages=pages,
                raw_data=data,
            )
        except Exception as exc:
            return BilibiliResult(success=False, action="parse", error=str(exc))

    def download(self, url: str, download_dir: Path | None, api_base_url: str, quality: int, timeout: float) -> BilibiliResult:
        try:
            if download_dir is None:
                download_dir = Path.cwd()
            download_dir.mkdir(parents=True, exist_ok=True)

            # Parse to get metadata
            parse_result = self.parse(url, api_base_url, timeout)
            if not parse_result.success:
                return BilibiliResult(success=False, action="download", error=f"Parse failed: {parse_result.error}")

            bvid = parse_result.bvid
            cid = parse_result.cid
            if not cid:
                return BilibiliResult(success=False, action="download", error="Cannot determine cid")

            # Get play URL (DASH)
            play_api = f"{api_base_url.rstrip('/')}/api/bilibili/web/fetch_video_playurl?bv_id={urllib.parse.quote(bvid)}&cid={cid}"
            play_data = _api_get(play_api, timeout)

            # Handle double-nesting in play URL response
            play_inner = play_data.get("data", play_data)
            if isinstance(play_inner, dict) and "data" in play_inner and isinstance(play_inner.get("data"), dict) and "dash" in play_inner.get("data", {}):
                play_inner = play_inner["data"]

            dash = play_inner.get("dash")
            if not dash or not isinstance(dash, dict):
                # Try durl fallback
                durl = play_inner.get("durl", [])
                if durl and isinstance(durl, list) and len(durl) > 0:
                    video_url = durl[0].get("url", "")
                    if video_url:
                        name = _sanitize_filename(f"{parse_result.title}-{parse_result.author}")
                        out_path = download_dir / f"{name}.mp4"
                        size = _download_file(video_url, out_path, timeout)
                        return BilibiliResult(
                            success=True, action="download",
                            file_path=out_path, file_size=size, file_format="mp4",
                            title=parse_result.title, author=parse_result.author,
                        )
                return BilibiliResult(success=False, action="download", error="No DASH or durl data in play URL response")

            # Find best video stream matching requested quality
            video_streams = dash.get("video", [])
            audio_streams = dash.get("audio", [])

            if not video_streams:
                return BilibiliResult(success=False, action="download", error="No video streams available")

            # Pick video stream: exact quality or closest lower
            selected_video = None
            video_streams_sorted = sorted(video_streams, key=lambda s: s.get("bandwidth", 0), reverse=True)
            for stream in video_streams_sorted:
                if stream.get("id", 0) == quality:
                    selected_video = stream
                    break
            if not selected_video:
                # Pick closest <= quality
                for stream in video_streams_sorted:
                    if stream.get("id", 0) <= quality:
                        selected_video = stream
                        break
            if not selected_video:
                selected_video = video_streams_sorted[-1]  # lowest

            selected_audio = audio_streams[0] if audio_streams else None

            video_url = selected_video.get("baseUrl", selected_video.get("base_url", ""))
            audio_url = selected_audio.get("baseUrl", selected_audio.get("base_url", "")) if selected_audio else ""

            if not video_url:
                return BilibiliResult(success=False, action="download", error="No video URL in selected stream")

            name = _sanitize_filename(f"{parse_result.title}-{parse_result.author}")
            out_path = download_dir / f"{name}.mp4"

            tmp_dir = Path(tempfile.mkdtemp(prefix="bili_dl_"))
            tmp_video = tmp_dir / "video.m4s"
            tmp_audio = tmp_dir / "audio.m4s"

            try:
                # Download video stream
                v_size = _download_file(video_url, tmp_video, timeout)

                if audio_url:
                    # Download audio stream
                    _download_file(audio_url, tmp_audio, timeout)

                    # Merge with ffmpeg
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(tmp_video),
                        "-i", str(tmp_audio),
                        "-c", "copy",
                        str(out_path),
                    ]
                    proc = subprocess.run(cmd, capture_output=True, timeout=300)
                    if proc.returncode != 0:
                        stderr = proc.stderr.decode("utf-8", errors="replace")
                        return BilibiliResult(success=False, action="download",
                                             error=f"ffmpeg merge failed: {stderr[:500]}")
                    file_size = out_path.stat().st_size
                else:
                    # No audio, just rename video
                    tmp_video.rename(out_path)
                    file_size = v_size

                return BilibiliResult(
                    success=True, action="download",
                    file_path=out_path, file_size=file_size, file_format="mp4",
                    title=parse_result.title, author=parse_result.author,
                )
            finally:
                # Cleanup temp files
                for f in [tmp_video, tmp_audio]:
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    tmp_dir.rmdir()
                except Exception:
                    pass

        except Exception as exc:
            return BilibiliResult(success=False, action="download", error=str(exc))
