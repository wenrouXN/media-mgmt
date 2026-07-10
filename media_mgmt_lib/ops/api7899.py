"""Douyin/TikTok/Bilibili Download API (localhost:7899) client + named ops registry."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from media_mgmt_lib.config import load_json_config, section

DEFAULT_BASE = "http://localhost:7899"

# Named operations: op_name -> (method, path_template, required_params, notes)
# path_template can include {param} placeholders; remaining params become query/body.
DOUYIN_NAMED: dict[str, dict[str, Any]] = {
    "video": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_one_video",
        "need": ["aweme_id"],
        "summary": "单视频详情（需 aweme_id）",
        "intents": ["详情", "信息", "元数据"],
    },
    "hybrid_video": {
        "method": "GET",
        "path": "/api/hybrid/video_data",
        "need": ["url"],
        "summary": "混合解析：直接丢抖音/TikTok/B站链接",
        "intents": ["解析", "链接", "信息"],
        "aliases": ["parse"],
    },
    "download": {
        "method": "GET",
        "path": "/api/download",
        "need": ["url"],
        "summary": "在线下载（抖音|TikTok|B站）到文件流",
        "intents": ["下载", "保存"],
        "stream": True,
    },
    "comments": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_video_comments",
        "need": ["aweme_id"],
        "summary": "视频评论列表",
        "intents": ["评论"],
    },
    "comment_replies": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_video_comment_replies",
        "need": ["item_id", "comment_id"],
        "summary": "某条评论的回复",
        "intents": ["评论回复"],
    },
    "user_profile": {
        "method": "GET",
        "path": "/api/douyin/web/handler_user_profile",
        "need": ["sec_user_id"],
        "summary": "用户资料",
        "intents": ["主页", "用户", "博主"],
    },
    "user_posts": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_post_videos",
        "need": ["sec_user_id"],
        "summary": "用户投稿作品",
        "intents": ["作品列表", "主页视频"],
    },
    "user_likes": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_like_videos",
        "need": ["sec_user_id"],
        "summary": "用户喜欢作品",
        "intents": ["喜欢", "点赞列表"],
    },
    "user_collections": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_collection_videos",
        "need": ["cookie"],
        "summary": "用户收藏（需 cookie）",
        "intents": ["收藏"],
    },
    "user_mix": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_mix_videos",
        "need": ["mix_id"],
        "summary": "合辑作品",
        "intents": ["合辑", "系列"],
    },
    "live_by_webcast": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_live_videos",
        "need": ["webcast_id"],
        "summary": "直播流（webcast_id）",
        "intents": ["直播"],
    },
    "live_by_room": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_user_live_videos_by_room_id",
        "need": ["room_id"],
        "summary": "直播流（room_id）",
        "intents": ["直播间"],
    },
    "live_gifts": {
        "method": "GET",
        "path": "/api/douyin/web/fetch_live_gift_ranking",
        "need": ["room_id"],
        "summary": "直播间送礼榜",
        "intents": ["礼物榜"],
    },
    "get_aweme_id": {
        "method": "GET",
        "path": "/api/douyin/web/get_aweme_id",
        "need": ["url"],
        "summary": "从分享链接提取 aweme_id",
        "intents": ["提取id"],
    },
    "get_sec_user_id": {
        "method": "GET",
        "path": "/api/douyin/web/get_sec_user_id",
        "need": ["url"],
        "summary": "从用户主页链接提取 sec_user_id",
        "intents": ["提取用户id"],
    },
    "update_cookie": {
        "method": "POST",
        "path": "/api/hybrid/update_cookie",
        "need": [],
        "summary": "更新 hybrid cookie（body 见上游文档）",
        "intents": ["cookie"],
        "body_from_params": True,
    },
}

BILIBILI_NAMED: dict[str, dict[str, Any]] = {
    "video": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_one_video",
        "need": ["bv_id"],
        "summary": "单视频详情",
        "intents": ["详情", "信息", "解析"],
        "aliases": ["parse"],
    },
    "playurl": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_video_playurl",
        "need": ["bv_id", "cid"],
        "summary": "播放地址/清晰度流",
        "intents": ["播放地址", "清晰度"],
    },
    "parts": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_video_parts",
        "need": ["bv_id"],
        "summary": "分 P 列表",
        "intents": ["分P", "多P"],
    },
    "comments": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_video_comments",
        "need": ["bv_id"],
        "summary": "视频评论",
        "intents": ["评论"],
    },
    "comment_reply": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_comment_reply",
        "need": ["bv_id", "rpid"],
        "summary": "评论回复",
        "intents": ["评论回复"],
    },
    "danmaku": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_video_danmaku",
        "need": ["cid"],
        "summary": "弹幕",
        "intents": ["弹幕"],
    },
    "bv_to_aid": {
        "method": "GET",
        "path": "/api/bilibili/web/bv_to_aid",
        "need": ["bv_id"],
        "summary": "BVid → aid",
        "intents": ["转aid"],
    },
    "user_profile": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_user_profile",
        "need": ["uid"],
        "summary": "用户资料",
        "intents": ["用户", "主页"],
    },
    "user_posts": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_user_post_videos",
        "need": ["uid"],
        "summary": "用户投稿",
        "intents": ["作品列表"],
    },
    "user_dynamic": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_user_dynamic",
        "need": ["uid"],
        "summary": "用户动态",
        "intents": ["动态"],
    },
    "user_collections": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_user_collection_videos",
        "need": ["folder_id"],
        "summary": "收藏夹内视频",
        "intents": ["收藏夹视频"],
    },
    "collect_folders": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_collect_folders",
        "need": ["uid"],
        "summary": "用户收藏夹列表",
        "intents": ["收藏夹"],
    },
    "popular": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_com_popular",
        "need": [],
        "summary": "综合热门",
        "intents": ["热门"],
    },
    "live_room": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_live_room_detail",
        "need": ["room_id"],
        "summary": "直播间信息",
        "intents": ["直播间"],
    },
    "live_stream": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_live_videos",
        "need": ["room_id"],
        "summary": "直播视频流",
        "intents": ["直播流"],
    },
    "live_areas": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_all_live_areas",
        "need": [],
        "summary": "直播分区列表",
        "intents": ["直播分区"],
    },
    "live_streamers": {
        "method": "GET",
        "path": "/api/bilibili/web/fetch_live_streamers",
        "need": ["area_id"],
        "summary": "分区在播主播",
        "intents": ["在播"],
    },
    "download": {
        "method": "GET",
        "path": "/api/download",
        "need": ["url"],
        "summary": "通用下载接口（也支持 B 站链接）",
        "intents": ["下载"],
        "stream": True,
    },
    "hybrid_video": {
        "method": "GET",
        "path": "/api/hybrid/video_data",
        "need": ["url"],
        "summary": "混合解析链接",
        "intents": ["解析"],
    },
}

TIKTOK_NAMED: dict[str, dict[str, Any]] = {
    "video": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_one_video",
        "need": ["itemId"],
        "summary": "TikTok 单视频（web itemId）",
        "intents": ["详情"],
    },
    "video_app": {
        "method": "GET",
        "path": "/api/tiktok/app/fetch_one_video",
        "need": ["aweme_id"],
        "summary": "TikTok 单视频（app aweme_id）",
        "intents": ["详情app"],
    },
    "comments": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_post_comment",
        "need": ["aweme_id"],
        "summary": "评论列表",
        "intents": ["评论"],
    },
    "comment_replies": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_post_comment_reply",
        "need": ["item_id", "comment_id"],
        "summary": "评论回复",
        "intents": ["评论回复"],
    },
    "user_profile": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_user_profile",
        "need": ["uniqueId"],
        "summary": "用户资料 uniqueId",
        "intents": ["用户"],
    },
    "user_posts": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_user_post",
        "need": ["secUid"],
        "summary": "用户投稿",
        "intents": ["作品列表"],
    },
    "user_likes": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_user_like",
        "need": ["secUid"],
        "summary": "用户点赞",
        "intents": ["喜欢"],
    },
    "user_fans": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_user_fans",
        "need": ["secUid"],
        "summary": "粉丝列表",
        "intents": ["粉丝"],
    },
    "user_follow": {
        "method": "GET",
        "path": "/api/tiktok/web/fetch_user_follow",
        "need": ["secUid"],
        "summary": "关注列表",
        "intents": ["关注"],
    },
    "hybrid_video": {
        "method": "GET",
        "path": "/api/hybrid/video_data",
        "need": ["url"],
        "summary": "混合解析链接",
        "intents": ["解析"],
        "aliases": ["parse"],
    },
    "download": {
        "method": "GET",
        "path": "/api/download",
        "need": ["url"],
        "summary": "下载",
        "intents": ["下载"],
        "stream": True,
    },
}

HYBRID_NAMED: dict[str, dict[str, Any]] = {
    "video_data": {
        "method": "GET",
        "path": "/api/hybrid/video_data",
        "need": ["url"],
        "summary": "一条链接解析（抖音/TikTok/B站）",
        "intents": ["解析", "链接", "信息", "详情"],
        "aliases": ["parse", "video"],
    },
    "download": {
        "method": "GET",
        "path": "/api/download",
        "need": ["url"],
        "summary": "在线下载文件流",
        "intents": ["下载", "保存"],
        "stream": True,
    },
    "update_cookie": {
        "method": "POST",
        "path": "/api/hybrid/update_cookie",
        "need": [],
        "summary": "更新 cookie",
        "body_from_params": True,
    },
}


def base_url(cfg: dict[str, Any] | None = None, section_name: str = "douyin") -> str:
    cfg = cfg if cfg is not None else load_json_config()
    # prefer matching section, then douyin, bilibili, hybrid
    for name in (section_name, "douyin", "bilibili", "hybrid", "tiktok"):
        sec = section(cfg, name)
        if sec.get("api_base_url"):
            return str(sec["api_base_url"]).rstrip("/")
    return DEFAULT_BASE


def extract_bvid(url_or_id: str) -> str | None:
    m = re.search(r"(BV[a-zA-Z0-9]+)", url_or_id or "")
    return m.group(1) if m else None


def extract_room_id(text: str) -> str | None:
    m = re.search(r"live\.bilibili\.com/(\d+)", text or "")
    if m:
        return m.group(1)
    m = re.search(r"room_id=(\d+)", text or "")
    return m.group(1) if m else None


def normalize_params_for_service(service: str, params: dict[str, Any]) -> dict[str, Any]:
    """Auto-fill ids from url when possible."""
    p = dict(params)
    url = str(p.get("url") or p.get("link") or "")
    if service in {"bilibili", "hybrid"} and url:
        bvid = extract_bvid(url)
        if bvid and not p.get("bv_id"):
            p["bv_id"] = bvid
        rid = extract_room_id(url)
        if rid and not p.get("room_id"):
            p["room_id"] = rid
    # accept aweme_id alias
    if p.get("aweme_id") is None and p.get("item_id"):
        p["aweme_id"] = p["item_id"]
    if p.get("bv_id") is None and p.get("bvid"):
        p["bv_id"] = p["bvid"]
    if p.get("itemId") is None and p.get("item_id"):
        p["itemId"] = p["item_id"]
    return p


def request_api(
    *,
    base: str,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    timeout: float = 60.0,
    stream_to: str | None = None,
) -> dict[str, Any]:
    params = {k: v for k, v in (params or {}).items() if v is not None and v != "" and not str(k).startswith("_")}
    method = method.upper()
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json,*/*"}
    if method == "GET":
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    else:
        # POST JSON body
        data = json.dumps(params or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if stream_to:
                from pathlib import Path

                out = Path(stream_to)
                out.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with open(out, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        size += len(chunk)
                return {
                    "success": True,
                    "streamed": True,
                    "path": str(out),
                    "bytes": size,
                    "content_type": resp.headers.get("Content-Type"),
                    "url": url.split("?")[0],
                }
            raw = resp.read().decode("utf-8", "replace")
            code = resp.status
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = raw[:2000]
        return {"success": True, "http_status": code, "data": body, "url": url.split("?")[0]}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace") if hasattr(e, "read") else str(e)
        try:
            detail = json.loads(err) if err else err
        except json.JSONDecodeError:
            detail = err[:800]
        return {"success": False, "http_status": e.code, "error": "http_error", "detail": detail, "url": url.split("?")[0]}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": "request_failed", "detail": str(e), "url": url.split("?")[0]}


def call_named(
    named_map: dict[str, dict[str, Any]],
    op_name: str,
    params: dict[str, Any],
    *,
    base: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    # resolve alias
    meta = named_map.get(op_name)
    if not meta:
        for name, m in named_map.items():
            if op_name in (m.get("aliases") or []):
                meta = m
                op_name = name
                break
    if not meta:
        return {
            "success": False,
            "error": "unknown_op",
            "op": op_name,
            "available": sorted(named_map.keys()),
            "hint": "Use op=api with path=/api/... for raw endpoint, or op=capabilities",
        }
    need = list(meta.get("need") or [])
    missing = [k for k in need if not params.get(k)]
    if missing:
        return {
            "success": False,
            "error": "missing_param",
            "need": missing,
            "op": op_name,
            "summary": meta.get("summary"),
            "path": meta.get("path"),
        }
    # only pass relevant-ish params: all params except internal
    call_params = dict(params)
    stream_to = call_params.pop("save_path", None) or call_params.pop("download_path", None)
    if meta.get("stream") and not stream_to:
        # for stream endpoints without save_path, return JSON error hint rather than dumping binary to stdout
        # still allow raw by save_path
        return {
            "success": False,
            "error": "missing_param",
            "need": ["save_path"],
            "hint": "download/stream ops require save_path to write the file",
            "op": op_name,
            "path": meta["path"],
        }
    if meta.get("stream"):
        return request_api(
            base=base,
            method=meta["method"],
            path=meta["path"],
            params=call_params,
            timeout=timeout,
            stream_to=str(stream_to),
        )
    return request_api(
        base=base,
        method=meta["method"],
        path=meta["path"],
        params=call_params,
        timeout=timeout,
    )


def call_raw_api(base: str, params: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    path = params.get("path") or params.get("endpoint")
    if not path:
        return {"success": False, "error": "missing_param", "need": ["path"], "hint": "path like /api/douyin/web/fetch_one_video"}
    method = str(params.get("method") or "GET").upper()
    # strip control keys
    q = {k: v for k, v in params.items() if k not in {"path", "endpoint", "method", "save_path", "download_path", "timeout", "url"} or k == "url"}
    # keep url if present for hybrid endpoints
    control = {"path", "endpoint", "method", "save_path", "download_path", "timeout"}
    q = {k: v for k, v in params.items() if k not in control}
    stream_to = params.get("save_path") or params.get("download_path")
    return request_api(base=base, method=method, path=str(path), params=q, timeout=timeout, stream_to=stream_to)


def capabilities(named_map: dict[str, dict[str, Any]], service: str) -> dict[str, Any]:
    ops = []
    for name, meta in sorted(named_map.items()):
        ops.append(
            {
                "op": name,
                "summary": meta.get("summary"),
                "method": meta.get("method"),
                "path": meta.get("path"),
                "need": meta.get("need") or [],
                "intents": meta.get("intents") or [],
                "aliases": meta.get("aliases") or [],
            }
        )
    return {
        "success": True,
        "service": service,
        "ops": ops,
        "raw_escape_hatch": "call op=api --param path=/api/... --param method=GET",
        "link_intents": "see references/link-intents.md",
    }
