"""Public playlist metadata parser (netease / qq / kuwo / kugou).

Parse-only: no audio download. Spotify intentionally unsupported in v1.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

QQ_MUSIC_HOSTS = {
    "y.qq.com",
    "i.y.qq.com",
    "m.y.qq.com",
    "c.y.qq.com",
    "c6.y.qq.com",
    "music.qq.com",
}
NETEASE_MUSIC_HOSTS = {
    "music.163.com",
    "y.music.163.com",
    "m.music.163.com",
    "3g.music.163.com",
    "163cn.tv",
}
KUWO_MUSIC_HOSTS = {"kuwo.cn", "www.kuwo.cn", "m.kuwo.cn", "mobile.kuwo.cn"}
KUGOU_MUSIC_HOSTS = {"www.kugou.com", "m.kugou.com", "kugou.com", "h5.kugou.com"}
SPOTIFY_MUSIC_HOSTS = {"open.spotify.com", "spotify.link", "play.spotify.com", "spotify.com"}

SUPPORTED_PLATFORMS = ("netease", "qq", "kuwo", "kugou")


class PlaylistParseError(RuntimeError):
    def __init__(self, message: str, *, code: str = "parse_failed") -> None:
        super().__init__(message)
        self.code = code


class UnsupportedPlaylistURL(PlaylistParseError):
    def __init__(self, message: str = "暂不支持该歌单链接。") -> None:
        super().__init__(message, code="unsupported_url")


@dataclass
class PlaylistTrack:
    position: int
    title: str
    artist: str | None = None
    album: str | None = None
    duration: int | None = None
    external_id: str = ""
    cover_url: str | None = None

    def query(self) -> str:
        parts = [self.title.strip()]
        if self.artist and str(self.artist).strip():
            parts.append(str(self.artist).strip())
        return " ".join(p for p in parts if p)


@dataclass
class ParsedPlaylist:
    platform: str
    external_id: str
    name: str
    source_url: str
    owner_name: str | None = None
    description: str | None = None
    cover_url: str | None = None
    tracks: list[PlaylistTrack] = field(default_factory=list)
    track_count: int = 0
    truncated: bool = False

    def queries(self) -> list[str]:
        return [t.query() for t in self.tracks]

    def to_result(self) -> dict[str, Any]:
        tracks = [asdict(t) for t in self.tracks]
        return {
            "success": True,
            "platform": self.platform,
            "playlist": {
                "name": self.name,
                "external_id": self.external_id,
                "owner_name": self.owner_name,
                "description": self.description,
                "cover_url": self.cover_url,
                "source_url": self.source_url,
                "track_count": self.track_count,
            },
            "tracks": tracks,
            "queries": self.queries(),
            "truncated": self.truncated,
            "summary": (
                f"{self.platform} 歌单《{self.name}》{self.track_count} 首"
                + (f"（返回 {len(self.tracks)}）" if self.truncated else "")
            ),
            "supported_platforms": list(SUPPORTED_PLATFORMS),
        }


def detect_platform(url: str) -> str:
    hostname = _hostname(url)
    if _host_matches(hostname, NETEASE_MUSIC_HOSTS):
        return "netease"
    if _host_matches(hostname, QQ_MUSIC_HOSTS):
        return "qq"
    if _host_matches(hostname, KUWO_MUSIC_HOSTS):
        return "kuwo"
    if _host_matches(hostname, KUGOU_MUSIC_HOSTS):
        return "kugou"
    if _host_matches(hostname, SPOTIFY_MUSIC_HOSTS):
        return "spotify"
    return "unknown"


def build_query(title: str, artist: str | None = None) -> str:
    return PlaylistTrack(position=0, title=title, artist=artist).query()


def apply_limit(tracks: list[PlaylistTrack], limit: int | None) -> tuple[list[PlaylistTrack], bool]:
    if limit is None:
        return tracks, False
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return tracks, False
    if n < 0:
        n = 0
    if len(tracks) <= n:
        return tracks, False
    return tracks[:n], True


def parse_playlist(
    playlist_url: str,
    *,
    proxy_url: str | None = None,
    limit: int | None = None,
    timeout: float = 30,
    client: Any | None = None,
) -> ParsedPlaylist:
    if httpx is None:
        raise PlaylistParseError("httpx is required: pip install httpx", code="parse_failed")

    url = (playlist_url or "").strip()
    if not url:
        raise UnsupportedPlaylistURL("歌单链接不能为空。")

    owns = client is None
    if client is None:
        kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
        if proxy_url:
            kwargs["proxy"] = proxy_url
        client = httpx.Client(**kwargs)
    try:
        resolved = _resolve_url(client, url)
        resolved = _preserve_original_fragment(resolved, url)
        platform = detect_platform(resolved)
        if platform == "spotify":
            raise UnsupportedPlaylistURL(
                "Spotify 歌单首版不支持；请用网易云/QQ/酷我/酷狗公开链接。"
            )
        if platform == "unknown":
            raise UnsupportedPlaylistURL(
                "暂不支持该歌单链接。支持: " + ", ".join(SUPPORTED_PLATFORMS)
            )
        if platform == "netease":
            parsed = _parse_netease(client, resolved)
        elif platform == "qq":
            parsed = _parse_qq(client, resolved)
        elif platform == "kuwo":
            parsed = _parse_kuwo(client, resolved)
        else:
            parsed = _parse_kugou(client, resolved)

        fetched = len(parsed.tracks)
        # Prefer platform-declared total when larger than fetched page
        full_count = max(int(parsed.track_count or 0), fetched)
        limited, truncated = apply_limit(parsed.tracks, limit)
        for i, t in enumerate(limited, start=1):
            t.position = i
        parsed.tracks = limited
        parsed.track_count = full_count
        parsed.truncated = truncated or (len(limited) < full_count)
        return parsed
    except PlaylistParseError:
        raise
    except Exception as e:  # noqa: BLE001
        raise PlaylistParseError(str(e), code="http_error") from e
    finally:
        if owns:
            client.close()


def _resolve_url(client: Any, playlist_url: str) -> str:
    try:
        response = client.head(playlist_url, follow_redirects=True)
        response.raise_for_status()
        return str(response.url)
    except Exception:
        response = client.get(playlist_url, follow_redirects=True)
        response.raise_for_status()
        return str(response.url)


def _parse_qq(client: Any, playlist_url: str) -> ParsedPlaylist:
    parsed = urlparse(playlist_url)
    playlist_id = _first_query_value(parsed.query, "id") or _path_id(parsed.path)
    if not playlist_id:
        raise PlaylistParseError("无法识别 QQ 音乐歌单 ID。")
    response = client.get(
        "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg",
        headers={"Referer": f"https://y.qq.com/n/ryqq/playlist/{playlist_id}"},
        params={
            "disstid": playlist_id,
            "type": "1",
            "json": "1",
            "utf8": "1",
            "onlysong": "0",
            "format": "json",
        },
    )
    response.raise_for_status()
    payload = response.json()
    playlist_data = _safe_get(payload, ["cdlist", 0], {}) or {}
    raw_tracks = (
        _safe_get(playlist_data, ["songlist"], [])
        or _safe_get(playlist_data, ["list"], [])
        or _safe_get(payload, ["songlist"], [])
        or []
    )
    tracks = [
        t
        for t in (
            _qq_track(item, index)
            for index, item in enumerate(raw_tracks, start=1)
            if isinstance(item, dict)
        )
        if t is not None
    ]
    return ParsedPlaylist(
        platform="qq",
        external_id=str(playlist_id),
        name=_optional_string(playlist_data.get("dissname")) or f"playlist-{playlist_id}",
        source_url=playlist_url,
        owner_name=_optional_string(_safe_get(playlist_data, ["nick"], None)),
        description=_optional_string(playlist_data.get("desc")),
        cover_url=_optional_string(playlist_data.get("logo")),
        tracks=tracks,
        track_count=len(tracks),
    )


def _parse_netease(client: Any, playlist_url: str) -> ParsedPlaylist:
    parsed = urlparse(playlist_url)
    playlist_id = (
        _fragment_query_value(parsed.fragment, "id")
        or _first_query_value(parsed.query, "id")
        or _path_id(parsed.path)
    )
    if not playlist_id:
        raise PlaylistParseError("无法识别网易云音乐歌单 ID。")
    response = client.post(
        "https://music.163.com/api/v6/playlist/detail",
        data={"id": playlist_id},
        headers={"Referer": "https://music.163.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    playlist_data = payload.get("playlist") if isinstance(payload.get("playlist"), dict) else {}
    raw_tracks = playlist_data.get("tracks") if isinstance(playlist_data, dict) else []
    track_ids = [
        item.get("id")
        for item in (playlist_data.get("trackIds") or [])
        if isinstance(item, dict) and item.get("id")
    ]
    # detail.tracks is often only first page; hydrate all via trackIds when longer
    if track_ids and (not raw_tracks or len(track_ids) > len(raw_tracks or [])):
        raw_tracks = _netease_track_details(client, track_ids)
    tracks = [
        t
        for t in (
            _netease_track(item, index)
            for index, item in enumerate(raw_tracks or [], start=1)
            if isinstance(item, dict)
        )
        if t is not None
    ]
    api_count = _optional_int(playlist_data.get("trackCount")) or len(tracks)
    return ParsedPlaylist(
        platform="netease",
        external_id=str(playlist_id),
        name=_optional_string(playlist_data.get("name")) or f"playlist-{playlist_id}",
        source_url=playlist_url,
        owner_name=_optional_string(_safe_get(playlist_data, ["creator", "nickname"], None)),
        description=_optional_string(playlist_data.get("description")),
        cover_url=_optional_string(playlist_data.get("coverImgUrl")),
        tracks=tracks,
        track_count=max(api_count, len(tracks)),
    )


def _netease_track_details(client: Any, track_ids: list[object]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    for offset in range(0, len(track_ids), 500):
        ids = track_ids[offset : offset + 500]
        response = client.post(
            "https://interface3.music.163.com/api/v3/song/detail",
            data={"c": json.dumps([{"id": item, "v": 0} for item in ids])},
            headers={"Referer": "https://music.163.com/"},
        )
        response.raise_for_status()
        payload = response.json()
        page_tracks = payload.get("songs") if isinstance(payload, dict) else []
        tracks.extend(item for item in page_tracks if isinstance(item, dict))
    return tracks


def _parse_kuwo(client: Any, playlist_url: str) -> ParsedPlaylist:
    parsed = urlparse(playlist_url)
    playlist_id = _first_query_value(parsed.query, "id") or _path_id(parsed.path)
    if not playlist_id:
        raise PlaylistParseError("无法识别酷我音乐歌单 ID。")
    raw_tracks: list[dict[str, Any]] = []
    first_payload: dict[str, Any] = {}
    page = 1
    while True:
        response = client.get(
            "https://m.kuwo.cn/newh5app/wapi/api/www/playlist/playListInfo",
            params={"pid": playlist_id, "pn": page, "rn": 100},
        )
        response.raise_for_status()
        payload = response.json()
        music_list = _safe_get(payload, ["data", "musicList"], []) or []
        if not isinstance(music_list, list) or not music_list:
            break
        if not first_payload:
            first_payload = copy.deepcopy(payload)
        raw_tracks.extend(item for item in music_list if isinstance(item, dict))
        total = _optional_int(_safe_get(payload, ["data", "total"], 0)) or 0
        if total <= len(raw_tracks):
            break
        page += 1
        if page > 50:
            break
    deduped = list({str(item.get("musicrid") or item.get("MUSICRID")): item for item in raw_tracks}.values())
    tracks = [
        t
        for t in (
            _kuwo_track(item, index)
            for index, item in enumerate(deduped, start=1)
            if isinstance(item, dict)
        )
        if t is not None
    ]
    return ParsedPlaylist(
        platform="kuwo",
        external_id=str(playlist_id),
        name=_optional_string(_safe_get(first_payload, ["data", "name"], None))
        or f"playlist-{playlist_id}",
        source_url=playlist_url,
        cover_url=_optional_string(_safe_get(first_payload, ["data", "img"], None)),
        tracks=tracks,
        track_count=len(tracks),
    )


def _parse_kugou(client: Any, playlist_url: str) -> ParsedPlaylist:
    parsed = urlparse(playlist_url)
    if "special/single/" not in parsed.path and "songlist" not in parsed.path:
        # still try path id, but warn via error if missing
        pass
    playlist_id = _first_query_value(parsed.query, "id") or _path_id(parsed.path)
    if not playlist_id:
        raise PlaylistParseError(
            '无法识别酷狗歌单 ID。需要类似 "https://www.kugou.com/yy/special/single/6914288.html"。'
        )
    headers = {
        "User-Agent": "Android9-AndroidPhone-11239-18-0-playlist-wifi",
        "Host": "gatewayretry.kugou.com",
        "x-router": "pubsongscdn.kugou.com",
        "mid": "239526275778893399526700786998289824956",
        "dfid": "-",
        "clienttime": str(int(time.time())),
    }
    raw_tracks: list[dict[str, Any]] = []
    first_payload: dict[str, Any] = {}
    page = 1
    while True:
        api_url = (
            "http://gatewayretry.kugou.com/v2/get_other_list_file"
            f"?specialid={playlist_id}&need_sort=1&module=CloudMusic&clientver=11239"
            f"&pagesize=300&specalidpgc={playlist_id}&userid=0&page={page}"
            "&type=0&area_code=1&appid=1005"
        )
        response = client.get(f"{api_url}&signature={_kugou_signature(api_url)}", headers=headers)
        response.raise_for_status()
        payload = response.json()
        page_tracks = _safe_get(payload, ["data", "info"], []) or []
        if not isinstance(page_tracks, list) or not page_tracks:
            break
        if not first_payload:
            first_payload = copy.deepcopy(payload)
        raw_tracks.extend(item for item in page_tracks if isinstance(item, dict))
        total = _optional_int(_safe_get(payload, ["data", "count"], 0)) or 0
        if total <= len(raw_tracks):
            break
        page += 1
        if page > 50:
            break
    deduped = list({str(item.get("hash") or item.get("FileHash")): item for item in raw_tracks}.values())
    tracks = [
        t
        for t in (
            _kugou_track(item, index)
            for index, item in enumerate(deduped, start=1)
            if isinstance(item, dict)
        )
        if t is not None
    ]
    name = _kugou_playlist_name(client, playlist_url, str(playlist_id))
    return ParsedPlaylist(
        platform="kugou",
        external_id=str(playlist_id),
        name=name,
        source_url=playlist_url,
        tracks=tracks,
        track_count=len(tracks),
    )


def _kugou_playlist_name(client: Any, playlist_url: str, playlist_id: str) -> str:
    try:
        response = client.get(
            playlist_url,
            headers={"referer": "https://www.kugou.com/songlist/"},
        )
        response.raise_for_status()
        match = re.search(r"var\s+specialInfo\s*=\s*(\{.*?\});", response.text, re.S)
        if match:
            payload = json.loads(match.group(1))
            name = _optional_string(payload.get("name"))
            if name:
                return name
    except Exception:
        pass
    return f"playlist-{playlist_id}"


def _qq_track(item: dict[str, Any], position: int) -> PlaylistTrack | None:
    external_id = _optional_string(item.get("mid") or item.get("songmid") or item.get("id"))
    title = _optional_string(item.get("title") or item.get("songname"))
    if not title:
        return None
    singers = item.get("singer") if isinstance(item.get("singer"), list) else []
    album = item.get("album") if isinstance(item.get("album"), dict) else {}
    album_mid = _optional_string(album.get("mid") or item.get("albummid"))
    artist = ", ".join(
        str(s.get("name")).strip()
        for s in singers
        if isinstance(s, dict) and s.get("name")
    ) or None
    return PlaylistTrack(
        position=position,
        title=title,
        artist=artist,
        album=_optional_string(album.get("title") or item.get("albumname")),
        duration=_optional_int(item.get("interval")),
        external_id=external_id or "",
        cover_url=(
            f"https://y.gtimg.cn/music/photo_new/T002R800x800M000{album_mid}.jpg"
            if album_mid
            else None
        ),
    )


def _netease_track(item: dict[str, Any], position: int) -> PlaylistTrack | None:
    external_id = _optional_string(item.get("id"))
    title = _optional_string(item.get("name"))
    if not title:
        return None
    artists = _safe_get(item, ["ar"], []) or _safe_get(item, ["artists"], []) or []
    album = _safe_get(item, ["al"], {}) or _safe_get(item, ["album"], {}) or {}
    artist = ", ".join(
        str(a.get("name")).strip()
        for a in artists
        if isinstance(a, dict) and a.get("name")
    ) or None
    return PlaylistTrack(
        position=position,
        title=title,
        artist=artist,
        album=_optional_string(album.get("name")) if isinstance(album, dict) else None,
        duration=_millis_to_seconds(item.get("dt") or item.get("duration")),
        external_id=external_id or "",
        cover_url=_optional_string(album.get("picUrl")) if isinstance(album, dict) else None,
    )


def _kuwo_track(item: dict[str, Any], position: int) -> PlaylistTrack | None:
    external_id = _optional_string(item.get("MUSICRID") or item.get("musicrid"))
    title = _optional_string(item.get("SONGNAME") or item.get("name") or item.get("songName"))
    if not title:
        return None
    eid = (external_id or "").removeprefix("MUSIC_")
    return PlaylistTrack(
        position=position,
        title=title,
        artist=_optional_string(item.get("ARTIST") or item.get("artist")),
        album=_optional_string(item.get("ALBUM") or item.get("album")),
        duration=_optional_int(item.get("DURATION") or item.get("duration")),
        external_id=eid,
        cover_url=_optional_string(
            item.get("hts_MVPIC") or item.get("albumpic") or item.get("pic")
        ),
    )


def _kugou_track(item: dict[str, Any], position: int) -> PlaylistTrack | None:
    external_id = _optional_string(item.get("hash") or item.get("FileHash"))
    title = _optional_string(
        item.get("songname")
        or item.get("SongName")
        or item.get("songname_original")
        or item.get("OriSongName")
        or item.get("filename")
        or item.get("FileName")
        or item.get("name")
        or item.get("Name")
    )
    if not title:
        return None
    singers = item.get("singerinfo") or item.get("Singers") or []
    artist = _optional_string(item.get("singername") or item.get("SingerName")) or ", ".join(
        str(s.get("name")).strip()
        for s in singers
        if isinstance(s, dict) and s.get("name")
    ) or None
    return PlaylistTrack(
        position=position,
        title=title,
        artist=artist,
        album=_optional_string(
            item.get("album_name")
            or item.get("AlbumName")
            or _safe_get(item, ["albuminfo", "name"], None)
        ),
        duration=_optional_int(item.get("duration") or item.get("Duration"))
        or _millis_to_seconds(item.get("timelen")),
        external_id=external_id or "",
        cover_url=_optional_string(
            _safe_get(item, ["trans_param", "union_cover"], None)
            or item.get("cover_url")
            or item.get("Image")
        ),
    )


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _preserve_original_fragment(resolved_url: str, original_url: str) -> str:
    resolved = urlparse(resolved_url)
    original = urlparse(original_url.strip())
    if resolved.fragment or not original.fragment:
        return resolved_url
    if _hostname(resolved_url) != _hostname(original_url):
        return resolved_url
    return urlunparse(resolved._replace(fragment=original.fragment))


def _host_matches(hostname: str, candidates: Iterable[str]) -> bool:
    return any(hostname == item or hostname.endswith(f".{item}") for item in candidates)


def _path_id(path: str) -> str | None:
    tail = path.strip("/").split("/")[-1] if path.strip("/") else ""
    tail = tail.removesuffix(".html").removesuffix(".htm")
    return _optional_string(tail)


def _first_query_value(query: str, key: str) -> str | None:
    values = parse_qs(query, keep_blank_values=False).get(key)
    if not values:
        return None
    return _optional_string(values[0])


def _fragment_query_value(fragment: str, key: str) -> str | None:
    if not fragment:
        return None
    # music.163.com/#/playlist?id=xxx
    if "?" in fragment:
        _, q = fragment.split("?", 1)
        return _first_query_value(q, key)
    return _first_query_value(fragment, key)


def _kugou_signature(api_url: str) -> str:
    query = api_url.split("?", 1)[1]
    raw = (
        "OIlwieks28dk2k092lksi2UIkp"
        + "".join(sorted(query.split("&")))
        + "OIlwieks28dk2k092lksi2UIkp"
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _safe_get(source: object, path: list[object], default: object = None) -> Any:
    value = source
    for key in path:
        if isinstance(key, int):
            if not isinstance(value, list) or len(value) <= key:
                return default
            value = value[key]
            continue
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _millis_to_seconds(value: object) -> int | None:
    millis = _optional_int(value)
    if millis is None:
        return None
    return int(millis / 1000) if millis > 10000 else millis
