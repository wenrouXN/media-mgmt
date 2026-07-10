---
name: media-mgmt
description: "管理媒体服务与接口（MoviePilot/下载器/HDHive/115/音乐/抖音/B站），搜索下载影视、转存分享、订阅、解锁资源。用户说'我要看/找/下载/听'或管理媒体服务时使用。"
---

# 媒体资源管理

Use when managing media **services/APIs**, or when the user asks to search, transfer, subscribe, download, or unlock media.

## Architecture（服务目录 + Ops + Workflow）

```text
services/*.json          # service catalog（无密钥：能力/探活/ops 列表）
config.json              # 实例凭证与路径（gitignore）
media_mgmt_lib/catalog   # 加载目录 + 合并 config section
media_mgmt_lib/ops       # health + 每服务操作门面
scripts/media_ctl.py     # 控制面：list / health / call / watch
scripts/doctor.py        # 全服务探活
scripts/watch.py         # workflow：我要看 X 第 N 集
scripts/mp_api.py        # MoviePilot REST 底层客户端
providers/*              # 同质获取源（TG 音乐 / 抖音 / B 站）
```

**不是**全盘内容 Provider。异构服务走 catalog+ops；下载源 provider 只覆盖同质 fetcher。

## Control plane（优先）

```bash
cd /path/to/media-mgmt
.venv/bin/python scripts/media_ctl.py list
.venv/bin/python scripts/media_ctl.py health
.venv/bin/python scripts/doctor.py
.venv/bin/python scripts/media_ctl.py call moviepilot clients
.venv/bin/python scripts/media_ctl.py call moviepilot identify --param title=金特务
.venv/bin/python scripts/media_ctl.py call moviepilot transfer_share --param share_url='https://115.com/s/xxx?password=yyy'
.venv/bin/python scripts/media_ctl.py call hdhive search --param q=金特务
.venv/bin/python scripts/media_ctl.py call pansou search --param q=关键词
.venv/bin/python scripts/media_ctl.py call cloakbrowser list_profiles
.venv/bin/python scripts/media_ctl.py watch -- "片名" --episode 5 --yes
```

`media_ctl ops` / `media_ctl ops <service>` 查看声明与实现是否齐套。

### 抖音 / B站 / TikTok 链接（必看）

用户丢链接时用 **hybrid/intent**，不要只会 parse：

```bash
.venv/bin/python scripts/media_ctl.py call hybrid intent --param url='https://v.douyin.com/xxx' --param intent='下载'
.venv/bin/python scripts/media_ctl.py call douyin capabilities
.venv/bin/python scripts/media_ctl.py call bilibili capabilities
.venv/bin/python scripts/media_ctl.py call douyin api --param path=/api/douyin/web/fetch_video_comments --param aweme_id=...
```

完整意图表：`references/link-intents.md`。上游全量约 66 接口见 `http://localhost:7899/docs`；具名 ops 覆盖常用，其余走 `op=api`。

## Default intent

- 先问服务是否健康 → `doctor` / `media_ctl health`
- 用户直接发 115 分享链接+密码 → 自动转存到 MoviePilot P115StrmHelper，无需二次确认。
- 用户要找影视资源 → **workflow** `scripts/watch.py`（或 `media_ctl watch -- ...`）；不要手搓 MoviePilot JSON。
- 用户要订阅影视 → 先下载已有资源；确认未完结后再创建/更新订阅。
- 用户要下歌/音乐 → Telegram Music provider，目录来自 `config.json`。

## Config

- **服务元数据**：`services/<id>.json`（可入库）
- **运行时凭证**：本地 `config.json`（gitignore）。模板：`config.example.json`
- section 名与 service `config_section` 对齐：`moviepilot` / `hdhive` / `pansou` / `telegram_music` / `douyin` / `bilibili`

**Do not read config files before calling scripts.** Scripts load config themselves.

## Anti-detour checklist（强制）

1. **不要先读 config.json** — 直接跑脚本。
2. **先 doctor / clients** — 空的 `GET /api/v1/download/` 只表示无进行中任务，≠ 未配置下载器。
   - `media_ctl call moviepilot clients` 或 `mp_api.py clients`
3. **不要手搓残缺 download body** — 用 `watch.py` 或 `mp_api.py download --from-search-result`
4. **完整 `torrent_info` + `media_info`**（enclosure / tmdb_id 等）
5. **新剧搜索 fallback**：tmdb 搜空 → title / `SxxExx`
6. **完成判定**：查 `history/transfer`，不要只看 download list。

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
