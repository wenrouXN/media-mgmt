"""Fixed media workflows. Agent free-form work should use ops; these are the hard scripts."""
from __future__ import annotations

from typing import Any, Callable

from media_mgmt_lib.workflows import doctor as w_doctor
from media_mgmt_lib.workflows import identify as w_identify
from media_mgmt_lib.workflows import watch as w_watch
from media_mgmt_lib.workflows import link as w_link
from media_mgmt_lib.workflows import share115 as w_share115
from media_mgmt_lib.workflows import listen as w_listen
from media_mgmt_lib.workflows import playlist as w_playlist
from media_mgmt_lib.workflows import search as w_search
from media_mgmt_lib.workflows import status as w_status
from media_mgmt_lib.workflows import subscribe as w_subscribe
from media_mgmt_lib.workflows import library as w_library
from media_mgmt_lib.workflows import updates as w_updates
from media_mgmt_lib.workflows import schedule as w_schedule
from media_mgmt_lib.workflows import catchup as w_catchup
from media_mgmt_lib.workflows import duplicates as w_duplicates
from media_mgmt_lib.workflows import hdhive as w_hdhive
from media_mgmt_lib.workflows import retry as w_retry
from media_mgmt_lib.workflows import upgrade as w_upgrade
from media_mgmt_lib.workflows import cancel as w_cancel

WorkflowFn = Callable[[dict[str, Any]], dict[str, Any]]

REGISTRY: dict[str, dict[str, Any]] = {
    "identify": {
        "fn": w_identify.run,
        "summary": "先认片：title→tmdb_id（可多候选确认；默认识别后停下）",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "watch": {
        "fn": w_watch.run,
        "summary": "我要看 X 第 N 集：识别→搜→选→下→状态",
        "need": ["title"],
        "fixed": True,
    },
    "link": {
        "fn": w_link.run,
        "summary": "抖音/B站/TikTok 链接 + 意图",
        "need": ["url"],
        "fixed": True,
    },
    "share115": {
        "fn": w_share115.run,
        "summary": "115 分享链接(+密码)转存到 MoviePilot",
        "need": ["share_url"],
        "fixed": True,
    },
    "listen": {
        "fn": w_listen.run,
        "summary": "听歌/下歌",
        "need": ["q"],
        "fixed": True,
    },
    "playlist": {
        "fn": w_playlist.run,
        "summary": "公共歌单链接解析（网易云/QQ/酷我/酷狗）→曲目+listen queries",
        "need": ["url"],
        "fixed": True,
    },
    "doctor": {
        "fn": w_doctor.run,
        "summary": "媒体服务体检",
        "need": [],
        "fixed": True,
    },
    "search": {
        "fn": w_search.run,
        "summary": "只搜资源候选，不下载",
        "need": ["title"],
        "fixed": True,
    },
    "status": {
        "fn": w_status.run,
        "summary": "下载/整理进度与路径",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "subscribe": {
        "fn": w_subscribe.run,
        "summary": "查询/创建订阅；搜不到时可建议订阅",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "library": {
        "fn": w_library.run,
        "summary": "媒体库有没有这部/这集",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "updates": {
        "fn": w_updates.run,
        "summary": "有没有更新：库缺集 + TMDB档期 + 已播可下/未播改订计划",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "schedule": {
        "fn": w_schedule.run,
        "summary": "TMDB 播出日历：已播/未播/下一集日期",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "catchup": {
        "fn": w_catchup.run,
        "summary": "追更计划：已播缺集先下，未播订阅（execute=true 才执行）",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "duplicates": {
        "fn": w_duplicates.run,
        "summary": "整理历史里同集多版本，给保留建议（默认只报告）",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "hdhive": {
        "fn": w_hdhive.run,
        "summary": "HDHive 搜→解锁→可选转存",
        "need": ["q|title"],
        "fixed": True,
    },
    "retry": {
        "fn": w_retry.run,
        "summary": "下载失败换源重试（半自动：给候选+可再下）",
        "need": ["title"],
        "fixed": True,
    },
    "upgrade": {
        "fn": w_upgrade.run,
        "summary": "库内质量升级：默认 HDHive→115，再 PT；支持 4K/中文/SDR 过滤",
        "need": ["title|tmdbid"],
        "fixed": True,
    },
    "cancel": {
        "fn": w_cancel.run,
        "summary": "下错撤回：取消活动下载（hash/title/tmdb/episode）",
        "need": ["hash|title|tmdbid"],
        "fixed": True,
    },
}


def list_workflows() -> list[dict[str, Any]]:
    out = []
    for name, meta in sorted(REGISTRY.items()):
        out.append({
            "name": name,
            "summary": meta.get("summary"),
            "need": meta.get("need"),
            "fixed": bool(meta.get("fixed")),
        })
    return out


def run_workflow(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    if name not in REGISTRY:
        return {
            "success": False,
            "error": "unknown_workflow",
            "available": sorted(REGISTRY),
            "hint": "media_ctl workflows / media_ctl run <name>",
        }
    try:
        result = REGISTRY[name]["fn"](params)
        if isinstance(result, dict):
            result.setdefault("workflow", name)
            result.setdefault("fixed", True)
            return result
        return {"success": True, "workflow": name, "data": result}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "workflow": name, "error": "workflow_exception", "detail": str(e)}
