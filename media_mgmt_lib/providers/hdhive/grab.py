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


def transfer_share_to_moviepilot(share_url: str) -> dict:
    creds = moviepilot_credentials(CONFIG)
    if not creds.get("BASE_URL") or not creds.get("API_KEY"):
        raise RuntimeError("Missing moviepilot.base_url or moviepilot.api_key in config")
    query = urllib.parse.urlencode({"apikey": creds["API_KEY"], "share_url": share_url})
    req = urllib.request.Request(
        f"{creds['BASE_URL']}/api/v1/plugin/P115StrmHelper/add_transfer_share?{query}"
    )
    return json.loads(urllib.request.urlopen(req).read())


def pick_best_resource(resources: list[dict]) -> dict | None:
    def score(resource: dict):
        tags = resource.get("tags", "")
        desc = resource.get("desc", "")
        cost = resource.get("cost", "")
        is_official = 1 if "官组" in tags else 0
        is_4k = 1 if any(key in desc for key in ["4K", "4k", "2160"]) else 0
        is_free = 1 if ("免费" in tags or cost == "" or cost == "免费") else 0
        is_bad = 1 if "疑似失效" in tags else 0
        return (-is_bad, is_official, is_4k, is_free)

    return max(resources, key=score) if resources else None


async def get_first_cdp_ws_url() -> str:
    profile_id = resolve_profile_id()
    ensure_profile_running(profile_id)
    resp = urllib.request.urlopen(f"{CLOAK_URL}/api/profiles/{profile_id}/cdp/json")
    pages = json.loads(resp.read())
    return pages[0]["webSocketDebuggerUrl"]


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
