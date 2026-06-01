#!/usr/bin/env python3
"""HDHive provider: search resources and unlock 115 share links via CDP."""

import json, asyncio, sys, urllib.request
from typing import Any
import websockets

from media_mgmt_lib.config import section, load_json_config

CONFIG = load_json_config()
HDHIVE_CONFIG = section(CONFIG, "hdhive")
CLOAK_URL = HDHIVE_CONFIG.get("cloak_url") or CONFIG.get("cloak_url", "http://127.0.0.1:8080")
PROFILE_ID = HDHIVE_CONFIG.get("profile_id")
PROFILE_NAME = HDHIVE_CONFIG.get("profile_name") or CONFIG.get("hdhive_profile_name", "mdmgmt")


def list_cloak_profiles() -> list[dict[str, Any]]:
    resp = urllib.request.urlopen(f"{CLOAK_URL}/api/profiles", timeout=20)
    return json.loads(resp.read())


def resolve_profile_id() -> str:
    if PROFILE_ID:
        return str(PROFILE_ID)
    profiles = list_cloak_profiles()
    if PROFILE_NAME:
        for profile in profiles:
            if profile.get("name") == PROFILE_NAME:
                return str(profile["id"])
    if len(profiles) == 1:
        return str(profiles[0]["id"])
    names = ", ".join(f"{p.get('name')}({p.get('id')})" for p in profiles)
    raise RuntimeError(f"Cannot auto-select HDHive CloakManager profile. Set hdhive.profile_id or hdhive.profile_name. Available: {names}")


def ensure_profile_running(profile_id: str) -> None:
    try:
        status = urllib.request.urlopen(f"{CLOAK_URL}/api/profiles/{profile_id}/status", timeout=20)
        data = json.loads(status.read())
        if data.get("status") == "running":
            return
    except Exception:
        pass
    req = urllib.request.Request(f"{CLOAK_URL}/api/profiles/{profile_id}/launch", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=60).read()

async def get_ws(prefer_url: str | None = None):
    """Connect to a real page CDP target, never a service worker."""
    profile_id = resolve_profile_id()
    ensure_profile_running(profile_id)
    resp = urllib.request.urlopen(f"{CLOAK_URL}/api/profiles/{profile_id}/cdp/json")
    pages = json.loads(resp.read())
    page_targets = [pg for pg in pages if pg.get("type") == "page" and pg.get("webSocketDebuggerUrl")]
    if prefer_url:
        for pg in page_targets:
            if prefer_url in pg.get("url", ""):
                return await websockets.connect(pg["webSocketDebuggerUrl"], max_size=10*1024*1024)
    for pg in page_targets:
        url = pg.get("url", "")
        if "hdhive.com" in url and "115cdn" not in url:
            return await websockets.connect(pg["webSocketDebuggerUrl"], max_size=10*1024*1024)
    if page_targets:
        return await websockets.connect(page_targets[0]["webSocketDebuggerUrl"], max_size=10*1024*1024)
    raise RuntimeError("No browser page CDP target found; CloakManager returned only non-page targets")

_MID = [0]
async def cdp(ws, method, params=None):
    _MID[0] += 1
    msg = {"id": _MID[0], "method": method}
    if params: msg["params"] = params
    await ws.send(json.dumps(msg))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == _MID[0]: return r

async def val(ws, expr):
    r = await cdp(ws, "Runtime.evaluate", {"expression": expr})
    return r.get("result",{}).get("result",{}).get("value","")

async def navigate(ws, url, wait=8, scroll=8):
    await cdp(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(wait)
    await val(ws, "window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)
    for _ in range(scroll):
        await cdp(ws, "Runtime.evaluate", {"expression": "window.scrollBy(0, 500)"})
        await asyncio.sleep(0.4)
    await asyncio.sleep(2)

JS_CLICK_CONFIRM = """
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
        if (btns[i].innerText.trim() === '确定') { btns[i].click(); break; }
    }
"""
JS_CLICK_UNLOCK = """
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
        if (btns[i].innerText.trim() === '确定解锁') { btns[i].click(); break; }
    }
"""

async def search_titles(keyword):
    ws = await get_ws()
    try:
        await cdp(ws, "Page.navigate", {"url": "https://hdhive.com/"})
        await asyncio.sleep(5)
        await cdp(ws, "Input.dispatchKeyEvent", {"type":"keyDown","key":"k","code":"KeyK","modifiers":2})
        await cdp(ws, "Input.dispatchKeyEvent", {"type":"keyUp","key":"k","code":"KeyK"})
        await asyncio.sleep(1)
        await cdp(ws, "Input.insertText", {"text": keyword})
        await asyncio.sleep(3)
        await cdp(ws, "Input.dispatchKeyEvent", {"type":"keyDown","key":"Enter","code":"Enter"})
        await cdp(ws, "Input.dispatchKeyEvent", {"type":"keyUp","key":"Enter","code":"Enter"})
        await asyncio.sleep(3)
        raw = await val(ws, """
            var d = document.querySelector('[role="dialog"]');
            if (!d) { '[]'; } else {
                var links = d.querySelectorAll('a[href]');
                var out = [];
                for (var i = 0; i < links.length; i++) {
                    var h = links[i].href;
                    if ((h.includes('/tv/') || h.includes('/movie/')) && h.includes('hdhive.com')) {
                        var lines = (links[i].innerText||'').split('\\n').map(function(l){return l.trim()}).filter(Boolean);
                        out.push({
                            name: lines[0] || '',
                            year: (lines.find(function(l){return l.match(/^\\(\\d{4}\\)$/)}) || '').replace(/[()]/g,''),
                            type: h.includes('/tv/') ? '剧集' : '电影',
                            desc: (lines.find(function(l){return l.length > 15 && !l.match(/^\\(\\d{4}\\)$/)}) || '').substring(0,80),
                            url: h
                        });
                    }
                }
                JSON.stringify(out);
            }
        """)
        return json.loads(raw) if raw and raw != "[]" else []
    finally:
        await ws.close()


async def search_tmdb(media_kind: str, tmdbid: str):
    """Search HDHive by typed TMDB ID tag and return the matched media/resources."""
    kind = media_kind.lower()
    if kind in {"movie", "电影"}:
        search_type = "movie_tmdb_id"
    elif kind in {"tv", "series", "电视剧", "剧集"}:
        search_type = "tv_tmdb_id"
    else:
        raise ValueError("media_kind must be movie or tv")
    url = f"https://hdhive.com/search?query={tmdbid}&type={search_type}&page=1"
    ws = await get_ws()
    try:
        await navigate(ws, url, wait=6, scroll=2)
        raw = await val(ws, """
            var links = document.querySelectorAll('a[href*="/tmdb/"], a[href*="/tv/"], a[href*="/movie/"]');
            var out = [];
            links.forEach(function(a) {
                var h = a.href;
                var text = (a.innerText || '').trim().replace(/\s+/g, ' ');
                if (!h.includes('hdhive.com')) return;
                if (h.includes('/person/') || h.includes('themoviedb.org')) return;
                if (text || h.includes('/tmdb/')) out.push({name:text, url:h});
            });
            JSON.stringify(out);
        """)
        matches = json.loads(raw) if raw else []
        media_url = ""
        for item in matches:
            if f"/tmdb/{'movie' if search_type == 'movie_tmdb_id' else 'tv'}/{tmdbid}" in item.get("url", ""):
                media_url = item["url"]
                break
        if not media_url and matches:
            media_url = matches[0].get("url", "")
        if media_url and "/tmdb/" in media_url:
            await navigate(ws, media_url, wait=6, scroll=8)
            media_url = await val(ws, "location.href")
        resources = await _list_resources_on_current_page(ws)
        if not resources and media_url:
            await ws.close()
            resources = await list_resources(media_url)
            return {"found": bool(media_url), "search_url": url, "media_url": media_url, "matches": matches, "resources": resources}
        return {"found": bool(media_url), "search_url": url, "media_url": media_url, "matches": matches, "resources": resources}
    finally:
        try:
            await ws.close()
        except Exception:
            pass

async def _list_resources_on_current_page(ws):
    await val(ws, "window.scrollTo(0, 0)")
    await asyncio.sleep(1)
    for _ in range(6):
        await cdp(ws, "Runtime.evaluate", {"expression": "window.scrollBy(0, 800)"})
        await asyncio.sleep(0.3)
    await val(ws, """
        var tabs = document.querySelectorAll('button[role="tab"]');
        for (var i = 0; i < tabs.length; i++) {
            if ((tabs[i].innerText || '').includes('115')) { tabs[i].click(); break; }
        }
    """)
    await asyncio.sleep(2)
    for _ in range(4):
        await cdp(ws, "Runtime.evaluate", {"expression": "window.scrollBy(0, 800)"})
        await asyncio.sleep(0.3)
    raw = await val(ws, """
        var links = document.querySelectorAll('a[href*="/resource/115/"]');
        var out = [];
        links.forEach(function(a) {
            var lines = (a.innerText||'').split('\n').map(function(l){return l.trim()}).filter(Boolean);
            var tags = [];
            var cost = '';
            var desc = '';
            var size = '';
            var resolution = '';
            for (var i = 1; i < lines.length; i++) {
                var l = lines[i];
                if (l === '官组' || l === '已完结' || l === '疑似失效' || l === '免费' || l === 'VIP') { tags.push(l); }
                else if (l.includes('积分')) { cost = l; }
                else if (l.match(/^[\d.]+\s*[GTMB]/i)) { size = l; }
                else if (l.match(/^[1248]0?80P$|2160P|4K/i)) { resolution = l; }
                else if (l.length > 5 && !l.match(/^发布于/)) { if (!desc) desc = l; }
            }
            out.push({desc:desc, resolution:resolution, size:size, cost:cost, tags:tags.join(','), url:a.href});
        });
        JSON.stringify(out);
    """)
    return json.loads(raw) if raw else []
def pick_best_resource(resources):
    def key(r):
        tags = r.get("tags", "")
        desc = r.get("desc", "") + r.get("desc", "").lower()
        resolution = r.get("resolution") or ""
        cost = r.get("cost", "")
        is_gz = 1 if "官组" in tags else 0
        is_4k = 1 if any(k in desc for k in ["4K", "4k", "2160"]) or any(k in resolution for k in ["2160", "4K"]) else 0
        is_free = 1 if ("免费" in tags or cost == "" or cost == "免费") else 0
        is_bad = 1 if "疑似失效" in tags else 0
        return (-is_bad, is_gz, is_4k, is_free)
    return max(resources, key=key) if resources else None


async def list_resources(detail_url):
    ws = await get_ws()
    try:
        await navigate(ws, detail_url)
        await val(ws, """
            var tabs = document.querySelectorAll('button[role="tab"]');
            for (var i = 0; i < tabs.length; i++) {
                if (tabs[i].innerText.includes('115')) { tabs[i].click(); break; }
            }
        """)
        await asyncio.sleep(2)
        raw = await val(ws, """
            var links = document.querySelectorAll('a[href*="/resource/115/"]');
            var out = [];
            links.forEach(function(a) {
                var lines = (a.innerText||'').split('\\n').map(function(l){return l.trim()}).filter(Boolean);
                var tags = [];
                var cost = '';
                var desc = '';
                var size = '';
                for (var i = 1; i < lines.length; i++) {
                    var l = lines[i];
                    if (l === '官组') { tags.push('官组'); }
                    else if (l === '已完结') { tags.push('已完结'); }
                    else if (l === '疑似失效') { tags.push('疑似失效'); }
                    else if (l === '免费') { tags.push('免费'); }
                    else if (l === 'VIP') { tags.push('VIP'); }
                    else if (l.includes('积分')) { cost = l; }
                    else if (l.match(/^[\\d.]+\\s*[GTMB]/i)) { size = l; }
                    else if (l.length > 5 && !l.includes('积分') && !l.includes('免费') && !l.match(/^发布于/) && !l.match(/^[\\d.]+\\s*[GTMB]/i)) { if (!desc) desc = l; }
                }
                out.push({desc:desc, size:size, cost:cost, tags:tags.join(','), url:a.href});
            });
            JSON.stringify(out);
        """)
        return json.loads(raw) if raw else []
    finally:
        await ws.close()

async def unlock_share(resource_url):
    """Unlock one HDHive resource and return a 115 share URL with plaintext password."""
    ws = await get_ws()
    try:
        await cdp(ws, "Page.navigate", {"url": resource_url})
        await asyncio.sleep(5)

        # 检查页面文字，确认是否需要解锁
        page_text = await val(ws, "document.body.innerText")
        need_unlock = "确定解锁" in page_text

        if need_unlock:
            # 点击"确定解锁"按钮
            await val(ws, JS_CLICK_UNLOCK)
            await asyncio.sleep(2)
            # 点击确认对话框的"确定"
            await val(ws, JS_CLICK_CONFIRM)
            await asyncio.sleep(5)

        # 等待页面跳转完成，重新检查
        page_text = await val(ws, "document.body.innerText")

        # 如果跳转到了115协议确认页（有"确定"按钮且无115链接），先点确定
        if "分享服务协议" in page_text or "严禁利用" in page_text:
            await val(ws, JS_CLICK_CONFIRM)
            await asyncio.sleep(5)

        # 此时页面应该是115分享页，从 URL 中取密码
        cur_url = await val(ws, "location.href")
        if "/s/" in cur_url and "password=" in cur_url and "***" not in cur_url:
            return cur_url

        # 如果 URL 中密码为 ***，尝试取页面中的链接
        raw = await val(ws, """document.querySelector('a[href*="115.com/s/"], a[href*="115cdn.com/s/"]')?.href || ''""")
        if raw and "/s/" in raw and "***" not in raw:
            return raw

        # 兜底：如果还是 ***，可能是115协议确认页被弹窗遮挡
        # 再次检查并点击可能的确认按钮
        btns_text = await val(ws, """JSON.stringify(Array.from(document.querySelectorAll('button')).map(b=>b.innerText.trim()))""")
        if btns_text and "确定" in btns_text:
            await val(ws, JS_CLICK_CONFIRM)
            await asyncio.sleep(3)
            cur_url = await val(ws, "location.href")
            if "/s/" in cur_url and "password=" in cur_url and "***" not in cur_url:
                return cur_url

        return "unlock_failed"
    finally:
        await ws.close()

def parse_args(args):
    opts = {"select": None, "all": False}
    clean = []
    i = 0
    while i < len(args):
        if args[i] == "--select" and i+1 < len(args):
            opts["select"] = int(args[i+1]) - 1
            i += 2
        elif args[i] == "--all":
            opts["all"] = True
            i += 1
        else:
            clean.append(args[i])
            i += 1
    return clean, opts

def main(argv: list[str] | None = None) -> int:
    args, opts = parse_args(argv or sys.argv)
    if len(args) < 2:
        print("用法: python3 scripts/hdhive.py <search|resources|unlock> ...")
        return 1
    cmd = args[1]
    if cmd == "search":
        kw = args[2] if len(args) > 2 else ""
        if not kw:
            print("用法: python3 scripts/hdhive.py search <关键词> [--select N]")
            return 1
        results = asyncio.run(search_titles(kw))
        if opts["select"] is not None and opts["select"] < len(results):
            selected = results[opts["select"]]
            print(json.dumps({"selected": selected, "all": results}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    elif cmd == "resources":
        url = args[2] if len(args) > 2 else ""
        if not url:
            print("用法: python3 scripts/hdhive.py resources <url> [--select N] [--all]")
            return 1
        resources = asyncio.run(list_resources(url))
        if opts["all"]:
            print(json.dumps({"resources": resources}, ensure_ascii=False, indent=2))
        elif opts["select"] is not None and opts["select"] < len(resources):
            selected = resources[opts["select"]]
            print(json.dumps({"selected": selected, "all": resources}, ensure_ascii=False, indent=2))
        else:
            best = pick_best_resource(resources)
            print(json.dumps({"best": best, "all": resources}, ensure_ascii=False, indent=2))
    elif cmd == "tmdb":
        if len(args) < 4:
            print("用法: python3 scripts/hdhive.py tmdb <movie|tv> <tmdbid> [--select N] [--all]")
            return 1
        kind = args[2]
        tmdbid = args[3]
        result = asyncio.run(search_tmdb(kind, tmdbid))
        if opts["all"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif opts["select"] is not None and opts["select"] < len(result.get("resources", [])):
            selected = result["resources"][opts["select"]]
            print(json.dumps({"selected": selected, "result": result}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "unlock":
        url = args[2] if len(args) > 2 else ""
        if not url:
            print("用法: python3 scripts/hdhive.py unlock <url>")
            return 1
        print(json.dumps({"share_url": asyncio.run(unlock_share(url))}, ensure_ascii=False))
    else:
        print(f"未知命令: {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
