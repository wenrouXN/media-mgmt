---
name: media-mgmt
description: "搜索影视资源、转存 115 分享、订阅 MoviePilot、解锁 HDHive、搜索并下载音乐/歌曲、解析下载抖音/Bilibili 视频。当用户说'我要看/找/下载/听'某部影视或歌曲，或发送抖音/Bilibili 链接时使用。"
---

# 媒体资源管理

Use when the user asks to search, transfer, subscribe, download, or unlock media resources.

## Default intent

- 用户直接发 115 分享链接+密码 → 自动转存到 MoviePilot P115StrmHelper，无需二次确认。
- 用户要找影视资源 → 先识别媒体，再按媒体类型用 TMDB ID 搜 HDHive；HDHive 无资源时直接用 MoviePilot REST API 搜索并下载。
- 用户要订阅影视 → 先下载已有资源；确认未完结后再用 MoviePilot REST API 创建/更新订阅。
- 用户要下歌/音乐 → 用 Telegram Music provider，默认下载目录来自 `config.json`。

## Config

Runtime defaults live in local `config.json` at skill root. Public template: `config.example.json`.

Main sections:

- `pansou.url`
- `moviepilot.base_url`, `moviepilot.api_key`
- `hdhive.cloak_url`, `hdhive.profile_name`, optional `hdhive.profile_id`
- `telegram_music.api_id`, `telegram_music.api_hash`, `telegram_music.session_string` or `session_name`, `telegram_music.bot`, `telegram_music.download_dir`
- `douyin.api_base_url`, `douyin.download_dir`, `douyin.timeout`
- `bilibili.api_base_url`, `bilibili.download_dir`, `bilibili.quality`, `bilibili.timeout`

HDHive profile discovery: if `hdhive.profile_id` is empty, the provider finds a CloakManager profile by `hdhive.profile_name`; if only one profile exists, it uses that. It also tries to launch a stopped profile before CDP access.

## Workflows

### Watch request: identify → HDHive → MoviePilot API → subscribe

When the user says “我要看 X” or asks to find/watch/download a film/series:

1. **Identify first**: use MoviePilot/TMDB REST API to determine title, media type, year, TMDB ID, original title/aliases, season, completion status, total/current episodes.
2. **Search HDHive by typed TMDB tag**:
   - movie → `https://hdhive.com/search?query=<tmdbid>&type=movie_tmdb_id&page=1`
   - TV/series → `https://hdhive.com/search?query=<tmdbid>&type=tv_tmdb_id&page=1`
   - Do not use ordinary keyword search first when a TMDB ID is known.
3. **Hunt 115 first**: open the matched HDHive media page, switch to the 115 tab, list resources, pick by user preference, unlock, and transfer via MoviePilot P115StrmHelper.
4. **Only if HDHive has no usable 115 resource**, use MoviePilot REST API for PT search/download. Do not use MCP as fallback.
5. **Before downloading**, call `GET /api/v1/download/paths` and `GET /api/v1/media/category/config`, compute a concrete `save_path`, and pass it explicitly to the download API.
6. **Subscribe last**: if the media is not completed, create/update a MoviePilot subscription after existing resources are handled.

### HDHive unlock

1. Connect CDP to a real `type=page` target; never attach to `service_worker`.
2. Run `scripts/hdhive.py tmdb <movie|tv> <tmdbid>` to find the HDHive media page/resources.
3. Run `scripts/hdhive.py unlock <resource_url>`.
4. After unlock/confirm, extract the plaintext 115 URL from `location.href`, page text, or `a[href*="115"]` / `a[href*="115cdn"]`; do not rely on navigation only.

### MoviePilot REST API

1. Use REST API directly for media identify/search/download/subscription.
2. Search PT resources with `GET /api/v1/search/media/{mediaid}` or `GET /api/v1/search/title`.
3. Download with `POST /api/v1/download/` or `POST /api/v1/download/add`, always passing explicit `save_path`.
4. Create/update subscriptions with `/api/v1/subscribe/`.
5. MCP/mcporter is not part of this workflow.

### Telegram music

1. Run `.venv/bin/python3 scripts/telegram_music_bot.py --query "歌手 歌名"`.
   - **搜索词格式**：建议"歌名 歌手"或"歌手 歌名"均可，bot 对顺序不敏感。
   - **必须使用 `.venv/bin/python3`**，确保 telethon 等依赖可用。
2. `button_index=1` 是网易云搜索排序第一的结果，不一定是原版（可能是 Live、翻唱等）。如需指定版本，先看搜索结果列表，用 `--button-index N` 选择。
3. Return downloaded file path; if sending back to chat, use file attachment rather than media directive for FLAC.

### 抖音解析与下载

当用户发送抖音链接（含 `douyin.com` 或 `v.douyin.com`）时：

1. **解析优先**：调 `scripts/douyin.py parse <url> --json` 获取元数据
2. **AI 解读**：基于返回的标题/描述/章节/统计，用 AI 做内容解读
3. **按需下载**：
   - 用户说"下载视频" → `scripts/douyin.py download <url>`
   - 用户说"下载里面的歌" → 解析 chapter 中的曲目列表 → 逐首调 Telegram Music Bot
4. **自动触发**：链接匹配 `douyin\.com|iesdouyin\.com` → 自动走抖音流程

### Bilibili 解析与下载

当用户发送 Bilibili 链接（含 `bilibili.com` 或 `b23.tv`）时：

1. **解析优先**：调 `scripts/bilibili.py parse <url> --json` 获取元数据
2. **AI 解读**：基于返回的标题/UP主/统计/评论，用 AI 做内容解读
3. **按需下载**：
   - 用户说"下载视频" → `scripts/bilibili.py download <url>`
   - 指定画质 → `--quality 120` (4K) / `80` (1080P) / `64` (720P)
4. **自动触发**：链接匹配 `bilibili\.com|b23\.tv` → 自动走 Bilibili 流程
5. **下载原理**：API 返回 DASH 视频流+音频流 → ffmpeg 合并为 mp4

## Critical caveats

- MoviePilot REST auth: `apikey` query parameter works reliably in this environment.
- HDHive blocks mainland IP; use the configured CloakManager profile/proxy.
- HDHive TMDB search requires the correct search tag: `movie_tmdb_id` for movies, `tv_tmdb_id` for series.
- HDHive CDP must attach to a `type=page` target, not `service_worker`; otherwise `document` is unavailable.
- HDHive passwords may be masked as `***`; after unlock, read the plaintext share URL from `location.href`, page text, or 115/115cdn links.
- MoviePilot download path: never call download without explicit `save_path`; compute it from `/api/v1/download/paths` + media category.
- Telegram music bot selection uses inline `callback_data`; sending text `1` is wrong.
- Bilibili 下载需要 ffmpeg 合并音视频流（本机已安装 ffmpeg 5.1.6）
- Bilibili 下载需要设置 Referer: https://www.bilibili.com
- 抖音 `/api/download` 直接返回 mp4，不需要额外处理
- 部分抖音接口（收藏/喜欢）需要 cookie，当前 provider 不支持 cookie 认证
- Bilibili 短链 b23.tv 需要先解析重定向获取真实 URL

## Dependencies & Setup

### Douyin_TikTok_Download_API (抖音/Bilibili/TikTok 解析后端)

抖音和 Bilibili provider 依赖 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 作为解析后端。

**Docker 部署（推荐）：**
```bash
docker run -d --name douyin-api \
  -p 7899:8080 \
  -v /path/to/config.yaml:/Douyin_TikTok_Download_API/config.yaml \
  evil0ctal/douyin_tiktok_download_api
```

**或直接部署：**
```bash
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git
cd Douyin_TikTok_Download_API
pip install -r requirements.txt
python main.py
```

**重要配置：**
- 默认端口 8080（映射到 config.json 中的 `7899`）
- 抖音需要在 `config.yaml` 中配置浏览器 Cookie，否则解析会被风控拦截
- Bilibili 部分功能也可能需要 Cookie
- 项目支持抖音/TikTok/Bilibili/快手四平台

### Telegram Music Bot (音乐下载)

```bash
cd /path/to/media-mgmt
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# requirements.txt: telethon, python-dotenv, websockets
```

必须使用 `.venv/bin/python3` 运行，确保 telethon 等依赖可用。

### ffmpeg (Bilibili 视频下载)

Bilibili 下载需要 ffmpeg 合并 DASH 音视频流。本机已安装 ffmpeg 5.1.6。

## Command reference

Load `references/commands.md` for exact curl/Python commands and examples. Prefer the REST/API scripts in this skill over MCP/mcporter.
