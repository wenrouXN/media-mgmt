---
name: media-mgmt
description: "搜索影视资源、转存 115 分享、订阅 MoviePilot、解锁 HDHive、搜索并下载音乐/歌曲、解析下载抖音/Bilibili 视频。当用户说'我要看/找/下载/听'某部影视或歌曲，或发送抖音/Bilibili 链接时使用。"
---

# 媒体资源管理

Use when the user asks to search, transfer, subscribe, download, or unlock media resources.

## Default intent

- 用户直接发 115 分享链接+密码 → 自动转存到 MoviePilot P115StrmHelper，无需二次确认。
- 用户要找影视资源 → **优先一条命令** `scripts/watch.py`；不要手搓 MoviePilot JSON。
- 用户要订阅影视 → 先下载已有资源；确认未完结后再用 MoviePilot REST API 创建/更新订阅。
- 用户要下歌/音乐 → 用 Telegram Music provider，默认下载目录来自 `config.json`。

## Config

Runtime defaults live in local `config.json` at skill root. Public template: `config.example.json`.

**Do not read config files before calling scripts.** All scripts load their own config via `load_json_config()` internally. Just call the script directly; if config is missing or wrong, the script will report the error.

Main sections:

- `pansou.url`
- `moviepilot.base_url`, `moviepilot.api_key`
- `hdhive.cloak_url`, `hdhive.profile_name`, optional `hdhive.profile_id`
- `telegram_music.api_id`, `telegram_music.api_hash`, `telegram_music.session_string` or `session_name`, `telegram_music.bot`, `telegram_music.download_dir`
- `douyin.api_base_url`, `douyin.download_dir`, `douyin.timeout`
- `bilibili.api_base_url`, `bilibili.download_dir`, `bilibili.quality`, `bilibili.timeout`

## Anti-detour checklist（强制）

1. **不要先读 config.json** — 直接跑脚本。
2. **不要猜有没有下载器** — `GET /api/v1/download/` 是**进行中任务**；空列表 ≠ 未配置。查客户端用：
   - `python3 scripts/mp_api.py clients`
   - 或 `GET /api/v1/download/clients`
3. **不要手搓残缺 download body** — 用：
   - `python3 scripts/watch.py "片名" --episode N --yes`
   - 或 `mp_api.py download --from-search-result ... --media-json ...`
4. **必须透传完整 `torrent_info`**（含 `enclosure` / `site_name` / cookie 字段）+ 完整 `media_info`（`type`/`title`/`tmdb_id`）。
5. **新剧搜索 fallback**：`search/media/tmdb:id` 可能为空 → 立刻 title 搜 / 加 `SxxExx`，不要空转。
6. **完成判定**：active 空了要查 `history/transfer`，不要只看 download list。

## Workflows

### Watch request（默认主路径）

用户说「我要看 X / 第 N 集」时：

```bash
cd /path/to/media-mgmt
.venv/bin/python3 scripts/watch.py "金部长" --episode 5 --yes
.venv/bin/python3 scripts/watch.py "Agent Kim Reactivated" --season 1 --episode 5 --prefer pt --yes
.venv/bin/python3 scripts/watch.py status --tmdbid 296206 --episode 5
```

`watch.py` 固定流水线：

1. **identify** — `recognize` / `media/search` / `media/tmdb:{id}`，拿到完整 `media_info`
2. **HDHive（可选）** — 默认 `prefer=auto`；可用 `--skip-hdhive` / `--prefer pt` / `--hdhive-only`
3. **PT 搜索 fallback 矩阵**
   1. `GET /api/v1/search/media/tmdb:{id}`
   2. `GET /api/v1/search/title`（中/英/原名）
   3. title + `SxxExx` / `E0N` / `第N集`
4. **pick** — seeders > 免费/半价 > 分辨率 > 站点优先级；过滤目标集
5. **download** — 完整 `media_in` + 完整 `torrent_in` + 解析后的 `save_path` + 默认 `QB`
6. **status** — active downloads + transfer history，输出整理路径

常用参数：

| 参数 | 含义 |
|------|------|
| `--yes` / `--auto` | 自动下载 top1（agent 默认加） |
| `--dry-run` | 只识别/搜索/选种，不真正下载 |
| `--pick-index N` | 选候选列表第 N 个 |
| `--wait SEC` | 下载后轮询状态 |
| `--subscribe` | 未完结时给订阅建议/创建 |
| `--downloader QB` | 指定下载器 |

### 低层 MoviePilot REST（仅排障）

```bash
.venv/bin/python3 scripts/mp_api.py identify "金特务" --media-type tv
.venv/bin/python3 scripts/mp_api.py clients          # 下载器列表 + dashboard
.venv/bin/python3 scripts/mp_api.py active           # 进行中任务
.venv/bin/python3 scripts/mp_api.py status --tmdbid 296206 --episode 5
.venv/bin/python3 scripts/mp_api.py pick --results-json candidates.json --episode 5
.venv/bin/python3 scripts/mp_api.py download \
  --from-search-result candidate.json \
  --media-json media.json \
  --downloader QB
```

Endpoint 语义：

| Endpoint | 含义 |
|----------|------|
| `GET /api/v1/download/` | **进行中任务** |
| `GET /api/v1/download/clients` | **已配置下载器** |
| `GET /api/v1/dashboard/downloader` | 速度/空间健康度 |
| `POST /api/v1/download/` | 含完整 `media_in` 的添加下载 |
| `POST /api/v1/download/add` | 不含完整 media 的添加下载 |
| `GET /api/v1/history/transfer` | 是否已整理/最终路径 |

失败提示：

- `validation_failed` → 缺 `enclosure`/`tmdb_id` 等，回到 `watch.py`
- HTTP 500 on download → 多半 media/torrent 不完整
- `任务添加失败` → 查 `clients`、种子链接、换候选源
- 搜索 0 结果 → 资源未出，建议订阅

### HDHive unlock

1. Connect CDP to a real `type=page` target; never attach to `service_worker`.
2. Run `scripts/hdhive.py tmdb <movie|tv> <tmdbid>` to find the HDHive media page/resources.
3. Run `scripts/hdhive.py unlock <resource_url>`. The script handles password masking and returns a plaintext 115 share URL.
4. Pass the returned URL directly to `transfer_share_to_moviepilot()`.

### Telegram music

1. Run `.venv/bin/python3 scripts/telegram_music_bot.py --query "歌手 歌名"`.
2. `button_index=1` 不一定是原版；需要时用 `--button-index N`。
3. Return downloaded file path; if sending back to chat, use file attachment rather than media directive for FLAC.

### 抖音 / Bilibili

- 抖音链接 → `scripts/douyin.py parse|download`
- Bilibili 链接 → `scripts/bilibili.py parse|download`（需 ffmpeg）

## Critical caveats

- MoviePilot REST auth: `apikey` query parameter works reliably in this environment.
- HDHive blocks mainland IP; use the configured CloakManager profile/proxy.
- HDHive TMDB search requires the correct search tag: `movie_tmdb_id` for movies, `tv_tmdb_id` for series.
- HDHive CDP must attach to a `type=page` target, not `service_worker`.
- MoviePilot download path: never call download without explicit `save_path`; `watch.py` / `mp_api.py download --media-json` resolve it.
- Empty `GET /download/` ≠ missing downloader.
- Telegram music bot selection uses inline `callback_data`; sending text `1` is wrong.
- Bilibili 下载需要 ffmpeg 合并音视频流；Referer: `https://www.bilibili.com`

## Dependencies & Setup

### Douyin_TikTok_Download_API

```bash
docker run -d --name douyin-api -p 7899:8080 evil0ctal/douyin_tiktok_download_api
```

### Telegram Music Bot

```bash
cd /path/to/media-mgmt
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

必须使用 `.venv/bin/python3` 运行。

## Command reference

Load `references/commands.md` for exact commands and examples. Prefer `watch.py` over raw API/MCP.
