# media-mgmt 命令手册

skill root 执行；主机 `python3`（无 per-skill venv）。  
路由与读结果纪律 → `SKILL.md`（§0 + 决策表）。固定剧本 → `workflows.md`。网盘判据 → `nextfind-115.md`；装机 → `INSTALL.md`。短链 → `link-intents.md`。

**准度清单**：带齐 `title`/`tmdbid`/`episode`/`media_type`；诊断加 `dry_run=true`；缺集只先 `run updates`；禁止 mp_api 发明参数。  
**结果必读**：`warnings` / `state` / `authority` / `resource_authority` / `error`（勿只看 success）。

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
```

## 控制面

```bash
python3 scripts/media_ctl.py list
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py health moviepilot
python3 scripts/media_ctl.py ops moviepilot
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run identify --param title=金特务
python3 scripts/media_ctl.py run watch --param title=金特务 --param episode=5 --param dry_run=true
python3 scripts/media_ctl.py run updates --param title=金特务：本色回归 --param tmdbid=296206
python3 scripts/media_ctl.py run library --param title=金特务：本色回归
python3 scripts/media_ctl.py run duplicates --param title=金特务：本色回归 --param tmdbid=296206
python3 scripts/media_ctl.py run nextfind --param tmdbid=849869 --param title=格杀福顺 --param media_type=movie --param transfer=true
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=明文'
python3 scripts/media_ctl.py run cancel --param title=金特务 --param episode=6 --param dry_run=true
python3 scripts/media_ctl.py run subscribe --param title=金特务 --param action=check
python3 scripts/media_ctl.py run catchup --param tmdbid=296206 --param execute=true --param max_download=3
python3 scripts/media_ctl.py run upgrade --param tmdbid=296206 --param episode=5 --param resolution=2160p --param hdr_mode=sdr --param require_chinese=true --param dry_run=true
python3 scripts/media_ctl.py run listen --param q='晴天 周杰伦'
python3 scripts/media_ctl.py run playlist --param url='https://music.163.com/#/playlist?id=...' --param limit=20
python3 scripts/media_ctl.py run link --param url='https://v.douyin.com/...' --param intent=下载
python3 scripts/media_ctl.py call hybrid intent --param url='https://v.douyin.com/...' --param intent=下载
python3 scripts/media_ctl.py call moviepilot clients
python3 scripts/media_ctl.py call moviepilot missing_episodes --param title=金特务：本色回归
```

## Watch 一键（底层流水线）

```bash
python3 scripts/watch.py "金部长" --episode 5 --yes
python3 scripts/watch.py "Agent Kim" --season 1 --episode 5 --prefer pt --dry-run
python3 scripts/watch.py status --tmdbid 296206 --episode 5
```

要点：agent 常用 `--yes` 仍受安全门限制；空 `GET /download/` ≠ 无下载器。

## MoviePilot REST（排障）

```bash
python3 scripts/mp_api.py identify "片名" --media-type tv --year 2026
python3 scripts/mp_api.py media-detail --tmdbid 299365 --media-type tv
python3 scripts/mp_api.py search --tmdbid 299365 --media-type tv --sites "6,19"
python3 scripts/mp_api.py clients
python3 scripts/mp_api.py active
python3 scripts/mp_api.py status --tmdbid 296206 --episode 5
python3 scripts/mp_api.py paths
python3 scripts/mp_api.py pick --results-json results.json --season 1 --episode 5 --resolution 1080p
python3 scripts/mp_api.py download --from-search-result candidate.json --media-json media.json --downloader QB --dry-run
python3 scripts/mp_api.py cancel --title "金特务" --episode 6 --dry-run
python3 scripts/mp_api.py subscribe --name "片名" --media-type tv --tmdbid 299365 --dry-run
```

### Endpoint 语义

- `GET /api/v1/download/` → **进行中任务**
- `GET /api/v1/download/clients` → **已配置下载器**
- `GET /api/v1/dashboard/downloader` → 速度/空间
- `POST /api/v1/download/` / `add` → 添加下载，须显式 `save_path`（或 `--media-json` 解析）
- `GET /api/v1/history/transfer` → 是否已整理/最终路径
- 认证：`apikey` **query param**（不要依赖 `X-Api-Key` header）

禁止：手搓残缺 torrent/media body；发明不存在的 CLI 参数。

## 网盘 / NextFind / 115

**主路径 NextFind OpenAPI**（不要先 PT）：

```bash
python3 scripts/media_ctl.py call nextfind health
# 用户说「下第N个」→ pick_n 从 1 起（第一个=1），不要用 pick_index=1
python3 scripts/media_ctl.py run watch --param title=片名 --param tmdbid=ID --param media_type=movie --param prefer=pt --param pick_n=1 --param force=true --param yes=true
# 点了「彩虹岛那个」→ 硬锁站点（重搜不乱序）；可叠加 pick_n / title_contains / page_url
python3 scripts/media_ctl.py run watch --param title=片名 --param tmdbid=ID --param prefer=pt --param site_name=彩虹岛 --param pick_n=1 --param force=true --param yes=true
# python3 scripts/media_ctl.py run watch ... --param title_contains=ltzww@CHDBits
# python3 scripts/media_ctl.py run watch ... --param page_url=details.php?id=332966
# 默认路径：MP base + 分类（如 /qbs/torrents/movies/日韩电影/）；仅当用户明确要求时才 save_path 覆盖

# 认片（title → tmdb）
python3 scripts/media_ctl.py call nextfind identify --param q=关键词 --param media_type=movie
python3 scripts/media_ctl.py run identify --param title=关键词 --param media_type=movie
# 强制 MoviePilot 认片：--param force_mp=true
# 订阅双写 + 补缺 dry
python3 scripts/media_ctl.py run subscribe --param title=关键词 --param action=check
python3 scripts/media_ctl.py run subscribe --param title=关键词 --param action=create --param dry_run=true
# 真双写：去掉 dry_run；真补缺：--param fill_execute=true
# 搜资源默认 NF（禁止默认 MP 二搜）
python3 scripts/media_ctl.py run search --param title=关键词 --param media_type=movie
python3 scripts/media_ctl.py run search --param title=关键词 --param force_mp_search=true
# 升级：probe=nf_fill dry；execute 真转存/下载
python3 scripts/media_ctl.py run upgrade --param title=关键词 --param media_type=movie --param probe=true
# 体检（含 nextfind pipeline）
python3 scripts/media_ctl.py run doctor
# 仅补缺（不订）：
python3 -c "from media_mgmt_lib.workflows.nf_fill import fill_missing; print(fill_missing({'title':'关键词','media_type':'movie','dry_run':True}))"
python3 scripts/media_ctl.py run nextfind --param q=关键词 --param media_type=movie --param dry_run=true
python3 scripts/media_ctl.py run nextfind --param q=关键词 --param dry_run=true
python3 scripts/media_ctl.py call nextfind grab --param q=关键词 --param dry_run=true
```

已有明文 115 分享：`run share115`（P115 插件直转，不经 Cloak）。  
**转存 API**：NextFind `POST /transfer`（`call nextfind transfer --param slug=...`）或一键 `grab`。  
成功/失败表 → `nextfind-115.md`。凭据 → `credentials.md`（nextfind.env）。

网盘找源统一 NextFind OpenAPI（见 `nextfind-115.md` / `INSTALL.md`）。

## 音乐

```bash
python3 scripts/media_ctl.py run listen --param q='梁静茹 勇气' --param search_only=true
python3 scripts/telegram_music_bot.py --query "梁静茹 勇气"
python3 scripts/playlist_parse.py --url 'https://y.qq.com/n/ryqq/playlist/...' --limit 10
```

TG：发 `/search <词>`；点 inline 必须用 `callback_data`，禁止发文字 `1`。

## 短视频 CLI

优先 `run link` / `call hybrid intent`。直调：

```bash
python3 scripts/douyin.py parse "https://v.douyin.com/xxx" --json
python3 scripts/douyin.py download "https://v.douyin.com/xxx"
python3 scripts/bilibili.py parse "https://www.bilibili.com/video/BVxxx" --json
python3 scripts/bilibili.py download "https://www.bilibili.com/video/BVxxx" --quality 80
python3 scripts/hongguo.py download 'https://novelquickapp.com/s/xxx' --episode 1
```

- 抖音/TikTok/B站依赖 7899 API（默认 `http://localhost:7899`）
- B站 DASH 合并需要 ffmpeg；Referer `https://www.bilibili.com`
- 红果默认目录见 config `hongguo.download_dir`；意图表 → `link-intents.md`

## 环境坑（速查）

- P115 与 MP 事件链不兼容 → 日志 `TransferRenameBuild`；先修插件
- identify 空 shell（title/type/tmdb 全 null）= 失败
