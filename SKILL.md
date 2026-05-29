---
name: media-mgmt
description: "搜索媒体资源、转存 115 分享、订阅 MoviePilot、解锁 HDHive、下载 Telegram 音乐。"
---

# 媒体资源管理

Use when the user asks to search, transfer, subscribe, download, or unlock media resources.

## Default intent

- 用户直接发 115 分享链接+密码 → 自动转存到 MoviePilot P115StrmHelper，无需二次确认。
- 用户要找影视资源 → 先盘搜；盘搜不足时用 HDHive。
- 用户要订阅影视 → 用 MoviePilot；优先 mcporter/MCP 搜索识别，再添加订阅。
- 用户要下歌/音乐 → 用 Telegram Music provider，默认下载目录来自 `config.json`。

## Config

Runtime defaults live in local `config.json` at skill root. Public template: `config.example.json`.

Main sections:

- `pansou.url`
- `moviepilot.base_url`, `moviepilot.api_key`, optional `moviepilot.mcporter_server`
- `hdhive.cloak_url`, `hdhive.profile_name`, optional `hdhive.profile_id`
- `telegram_music.api_id`, `telegram_music.api_hash`, `telegram_music.session_string` or `session_name`, `telegram_music.bot`, `telegram_music.download_dir`

HDHive profile discovery: if `hdhive.profile_id` is empty, the provider finds a CloakManager profile by `hdhive.profile_name`; if only one profile exists, it uses that. It also tries to launch a stopped profile before CDP access.

## Workflows

### Search → 115 transfer

1. Search 盘搜 for 115 resources.
2. If the result already contains share URL + password, call P115StrmHelper transfer.
3. If user supplied the share URL directly, skip search and transfer immediately.

### HDHive unlock

1. Run `scripts/hdhive.py search` and choose the right title/year.
2. Run `scripts/hdhive.py resources`; accept auto-best unless the user asked for a specific release.
3. Run `scripts/hdhive.py unlock`, then transfer the returned 115 link through MoviePilot.

### MoviePilot subscription

1. Search/recognize media to get TMDB id, preferably via configured mcporter `moviepilot` server.
2. Add subscription through MoviePilot REST or mcporter.
3. Verify API success response.

### Telegram music

1. Run `scripts/telegram_music_bot.py --query "歌手 歌名"`.
2. Prefer default `button_index=1` unless the user specifies a version.
3. Return downloaded file path; if sending back to chat, use file attachment rather than media directive for FLAC.

## Critical caveats

- MoviePilot REST auth: `apikey` query parameter only; `X-Api-Key` header does not work here.
- HDHive blocks mainland IP; use the configured CloakManager profile/proxy.
- HDHive CDP needs `Page.navigate`, not reload; after search input press Enter; detail pages need scrolling to lazy-load resources.
- HDHive passwords are masked as `***`; click through the 115CDN confirmation page and read plaintext from URL.
- Telegram music bot selection uses inline `callback_data`; sending text `1` is wrong.

## Command reference

Load `references/commands.md` for exact curl/Python commands and examples.
