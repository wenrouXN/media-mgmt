---
name: media-mgmt
description: "管理媒体服务与资源链路（MoviePilot/下载器/HDHive/115/音乐/抖音/B站/TikTok）：认片(tmdb)、搜下影视、订阅、库内是否已有/缺集更新/播出档期追更/质量升级、重复整理建议、下载进度、115转存、短链处理、听歌候选确认、公共歌单链接解析(网易云/QQ/酷我/酷狗)、服务体检。用户说我要看/找/下载/听、解析歌单、有没有更新、库里有没有、是不是重复、画质不好/要4K中字、这是哪部、丢抖音/B站/115/歌单链接，或管理媒体服务时使用。"
---

# 媒体资源管理

Use when managing media **services/APIs**, or when the user asks to search, transfer, subscribe, download, or unlock media.

## Architecture（服务目录 + Ops + Workflow）

```text
services/*.json          # service catalog（无密钥：能力/探活/ops 列表）
config.json              # 实例凭证与路径（gitignore）
media_mgmt_lib/catalog   # 加载目录 + 合并 config section
media_mgmt_lib/ops       # health + 每服务操作门面
media_mgmt_lib/workflows # 固定剧本（硬流程）
scripts/media_ctl.py     # 控制面：list / health / call / workflows / run
scripts/doctor.py        # 全服务探活
scripts/watch.py         # watch 底层流水线
scripts/mp_api.py        # MoviePilot REST 底层客户端
providers/*              # 同质获取源（TG 音乐 / 抖音 / B 站）
```

**不是**全盘内容 Provider。异构服务走 catalog+ops；**固定场景走 workflows**；其余 agent 自由调 ops。

## Control plane（优先）

```bash
cd /path/to/media-mgmt
python3 scripts/media_ctl.py list
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run library --param title=金特务：本色回归
python3 scripts/media_ctl.py run updates --param title=金特务：本色回归
python3 scripts/media_ctl.py run duplicates --param title=金特务：本色回归 --param tmdbid=296206
python3 scripts/media_ctl.py run watch --param title=金特务 --param episode=5 --param dry_run=true
python3 scripts/media_ctl.py run link --param url='https://v.douyin.com/xxx' --param intent=下载
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=***'
python3 scripts/media_ctl.py call moviepilot clients
```

### 固定 workflows

| name | 场景 |
|------|------|
| identify | 先认片定 tmdb_id |
| watch | 我要看 X 第 N 集 |
| link | 短视频/B站链接 + 意图 |
| share115 | 115 分享转存 |
| listen | 听歌/下歌 |
| playlist | 公共歌单链接解析 → 曲目 + listen queries |
| doctor | 服务体检 |
| search | 只搜候选 |
| status | 下载/整理进度 |
| subscribe | 查/建订阅 |
| library | 库里有没有 |
| updates | 有没有更新/缺集+档期计划 |
| schedule | TMDB 播出日历 |
| catchup | 已播先下、未播订阅 |
| upgrade | 质量升级（HDHive→115 优先） |
| duplicates | 同集多版本，建议保留谁（默认不删） |
| hdhive | HDHive 搜解锁转存 |
| retry | 失败换源重试 |

详情：`references/workflows.md`。`media_ctl ops` 查服务操作；非上表场景 → agent 自由 `call` ops。

### 抖音 / B站 / TikTok 链接（必看）

用户丢链接时用 **hybrid/intent**，不要只会 parse：

```bash
python3 scripts/media_ctl.py call hybrid intent --param url='https://v.douyin.com/xxx' --param intent='下载'
python3 scripts/media_ctl.py call douyin capabilities
python3 scripts/media_ctl.py call bilibili capabilities
python3 scripts/media_ctl.py call douyin api --param path=/api/douyin/web/fetch_video_comments --param aweme_id=...
```

完整意图表：`references/link-intents.md`。上游全量约 66 接口见 `http://localhost:7899/docs`；具名 ops 覆盖常用，其余走 `op=api`。

## Default intent

- 先问服务是否健康 → `doctor` / `media_ctl health`
- 用户直接发 115 分享链接+密码 → `media_ctl run share115`（自动转存，无需二次确认）。
- 模糊片名先 `media_ctl run identify` 定 tmdb_id，确认后再 search/watch。
- 用户要找/看影视 → `media_ctl run watch`（内部也会 identify）；不要手搓 MoviePilot JSON。
- **「咋还没有 / 缺集 / 有没有更新 / 第 N 集呢」→ 只跑 `run updates`（首选）**；需要下载队列再补 `run status`；要证明源站有没有货再 `run search --param episode=N` 或 `run watch --param dry_run=true`。**禁止**先 identify+library+subscribe 全量连打。
- 「库里有没有」→ `run library`。
- 「是不是重复、留哪个」→ `run duplicates`（只建议，不自动删）。
- 用户要订阅影视 → `run subscribe`；先下已有资源，未完结再订。
- 用户要下歌/音乐 → `run listen`（高置信直接下，多选需确认；`button_index` 确认后下）。
- **公共歌单链接**（网易云/QQ/酷我/酷狗）→ `run playlist`（只解析元数据 + `queries`）；要下某几首再对 `queries[i]` 调 `run listen`，**不要**假装有批量下载 op。
- 抖音/B站/TikTok 链接 → `run link`（intent=下载/解析/评论…）。

### 缺集诊断路由（强制）

用户说「第 N 集咋还没有 / 怎么还没更新」时：

```bash
# 1) 一条 updates 出结论：库缺集 + 档期 + 订阅 + 已播可下/未播改订
python3 scripts/media_ctl.py run updates --param title=金特务 --param tmdbid=296206

# 2) 可选：有没有在下 / 最近整理到哪
python3 scripts/media_ctl.py run status --param tmdbid=296206 --param episode=6

# 3) 可选：源站有没有这集（不下）
python3 scripts/media_ctl.py run search --param tmdbid=296206 --param title=金特务：本色回归 --param episode=6
# 或
python3 scripts/media_ctl.py run watch --param tmdbid=296206 --param title=金特务：本色回归 --param episode=6 --param dry_run=true --param skip_hdhive=true
```

结论模板：已入库到哪 / 缺哪集 / 是否已播 / 订阅状态 / 有无下载任务 / 源站有无货。  
**未确认下载前不要 `--yes`。** search/watch 失败时不要发明 `mp_api` 参数；修 workflow 或换 `run updates`。

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
7. **诊断场景只先跑一个 workflow** — `updates` 优先；失败再补 `status`/`search`，禁止 identify+library+subscribe 扫射。
8. **禁止发明 mp_api CLI 参数** — `search` 不支持位置参数 `tmdb:ID`，也不支持 `--episode`；集数过滤走 `run search --param episode=N` 或 `pick`。
9. **watch 卡住** — stderr 有 `[watch] stage=...` 进度；HDHive 默认 90s 超时后继续 PT；workflow 默认总超时 420s。

## Workflows

### Watch request（默认主路径）

用户说「我要看 X / 第 N 集」时：

```bash
cd /path/to/media-mgmt
python3 scripts/watch.py "金部长" --episode 5 --yes
python3 scripts/watch.py "Agent Kim Reactivated" --season 1 --episode 5 --prefer pt --yes
python3 scripts/watch.py status --tmdbid 296206 --episode 5
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
python3 scripts/mp_api.py identify "金特务" --media-type tv
python3 scripts/mp_api.py clients          # 下载器列表 + dashboard
python3 scripts/mp_api.py active           # 进行中任务
python3 scripts/mp_api.py status --tmdbid 296206 --episode 5
python3 scripts/mp_api.py pick --results-json candidates.json --episode 5
python3 scripts/mp_api.py download \
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

1. Run `python3 scripts/telegram_music_bot.py --query "歌手 歌名"`.
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

**不用 per-skill 虚拟环境。** 统一用系统/用户级 `python3`（`~/.local` site-packages）。

```bash
# 首次或依赖变更时（Debian/PEP668 环境）
python3 -m pip install --user --break-system-packages -r requirements.txt

# 日常直接跑
python3 scripts/media_ctl.py run doctor
```

### Douyin_TikTok_Download_API

```bash
docker run -d --name douyin-api -p 7899:8080 evil0ctal/douyin_tiktok_download_api
```

### Telegram Music Bot

依赖见 `requirements.txt`（telethon 等），装到用户级 Python 后：

```bash
python3 scripts/telegram_music_bot.py --query "歌手 歌名"
```

## Command reference

Load `references/commands.md` for exact commands and examples. Prefer `watch.py` over raw API/MCP.
