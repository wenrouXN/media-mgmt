#!/usr/bin/env python3
"""HDHive end-to-end provider: search → choose resource → unlock → transfer to MoviePilot."""

from __future__ import annotations

import argparse
import asyncio
import json
import urllib.parse
import urllib.request

import websockets

from media_mgmt_lib.config import load_json_config, moviepilot_credentials
from media_mgmt_lib.providers.hdhive.provider import CLOAK_URL, cdp, ensure_profile_running, list_resources, resolve_profile_id, search_titles, val

CONFIG = load_json_config()


def _is_usable_115_share(share_url: str) -> bool:
    text = (share_url or "").strip()
    if not text or "/s/" not in text or "***" in text:
        return False
    parsed = urllib.parse.urlparse(text)
    qs = urllib.parse.parse_qs(parsed.query)
    pwd = (qs.get("password") or [""])[0]
    return bool(pwd) and "*" not in pwd


def transfer_share_to_moviepilot(share_url: str) -> dict:
    """Back-compat re-export; implementation lives in media_mgmt_lib.transfer_share."""
    from media_mgmt_lib.transfer_share import transfer_share_to_moviepilot as _transfer

    return _transfer(share_url, CONFIG)


def pick_best_resource(
    resources: list[dict],
    *,
    resolution: str | None = None,
    require_chinese: bool = False,
    hdr_mode: str = "any",
) -> dict | None:
    """Pick HDHive resource via shared quality_pref ranker."""
    from media_mgmt_lib.quality_pref import pick_best_resource as _pick

    return _pick(
        resources,
        resolution=resolution,
        require_chinese=require_chinese,
        hdr_mode=hdr_mode or "any",
    )


async def get_first_cdp_ws_url() -> str:
    profile_id = resolve_profile_id()
    ensure_profile_running(profile_id)
    resp = urllib.request.urlopen(f"{CLOAK_URL}/api/profiles/{profile_id}/cdp/json")
    pages = json.loads(resp.read())
    page_targets = [page for page in pages if page.get("type") == "page" and page.get("webSocketDebuggerUrl")]
    for page in page_targets:
        url = page.get("url", "")
        if "hdhive.com" in url and "115cdn" not in url:
            return page["webSocketDebuggerUrl"]
    if page_targets:
        return page_targets[0]["webSocketDebuggerUrl"]
    raise RuntimeError("No browser page CDP target found; CloakManager returned only non-page targets")


async def unlock_share_in_existing_page(ws, resource_url: str) -> str:
    await cdp(ws, "Page.navigate", {"url": resource_url})
    await asyncio.sleep(5)
    url = await val(ws, "location.href")
    if "115.com/s/" in url and "password=" in url and "***" not in url:
        return url

    await val(ws, "var b=document.querySelectorAll('button');for(var i=0;i<b.length;i++){if(b[i].innerText.trim()==='确定解锁'){b[i].click();break;}}")
    await asyncio.sleep(6)
    url = await val(ws, "location.href")
    if "115.com/s/" in url and "password=" in url and "***" not in url:
        return url

    await val(ws, "var b=document.querySelectorAll('button');for(var i=0;i<b.length;i++){if(b[i].innerText.trim()==='确定'){b[i].click();break;}}")
    await asyncio.sleep(4)
    url = await val(ws, "location.href")
    if "115.com/s/" in url and "password=" in url and "***" not in url:
        return url

    await val(ws, "var a=document.querySelector('a[href*=\"115.com/s/\"],a[href*=\"115cdn.com/s/\"]');if(a)a.click()")
    await asyncio.sleep(4)
    await val(ws, "var b=document.querySelectorAll('button');for(var i=0;i<b.length;i++){if(b[i].innerText.trim()==='确定'){b[i].click();break;}}")
    await asyncio.sleep(2)
    return await val(ws, "location.href")


async def grab_and_transfer(keyword: str, select: int = 1) -> None:
    ws_url = await get_first_cdp_ws_url()
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        print(f"Search: {keyword}")
        results = await search_titles(keyword)
        if not results:
            print("No results found")
            return
        for idx, result in enumerate(results[:10], start=1):
            print(f"  {idx}. [{result['type']}] {result['name']} ({result['year']})")

        targets = [results[select - 1]] if select > 1 and select <= len(results) else results
        chosen = None
        best = None
        for result in targets:
            print(f"\nInspect: [{result['type']}] {result['name']} ({result['year']})")
            resources = await list_resources(result["url"])
            if resources is None:
                print("  Page not ready, skip")
                continue
            if not resources:
                print("  No 115 resources, skip")
                continue
            best = pick_best_resource(resources)
            print(f"  Best: {best['desc']} | {best['size']} | {best['cost'] or 'free'} | {best['tags']}")
            chosen = result
            break

        if not chosen or not best:
            print("No selectable 115 resource")
            return

        print(f"\nSelected: [{chosen['type']}] {chosen['name']} -> {best['desc']}")
        share_url = await unlock_share_in_existing_page(ws, best["url"])
        if not share_url or "unlock_failed" in share_url or "***" in share_url:
            print(f"Unlock failed: {share_url}")
            return
        print(f"Share URL: {share_url}")

        result = transfer_share_to_moviepilot(share_url)
        if result.get("code") == 0:
            media_info = result.get("data", {}).get("media_info", {})
            save_path = result.get("data", {}).get("save_parent", {}).get("path", "")
            print(f"Transfer succeeded: {media_info.get('title', '')} -> {save_path}")
        else:
            print(f"Transfer result: {result.get('msg', 'unknown')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search HDHive, unlock the best 115 resource, and transfer it to MoviePilot")
    parser.add_argument("keyword", help="Media title keyword")
    parser.add_argument("--select", type=int, default=1, help="1-based search-result index to prefer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    asyncio.run(grab_and_transfer(args.keyword, args.select))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
