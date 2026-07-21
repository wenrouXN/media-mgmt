# media-mgmt 安装手册

面向：OpenClaw / 自托管环境。本 skill 是**媒体编排控制面**，不是「装完即用」的媒体中心。

策略真源：`SKILL.md`。变更说明不维护独立 CHANGELOG。

## 1. 运行时

| 项 | 要求 |
|----|------|
| Python | 主机 `python3` ≥ 3.10 |
| venv | **禁止** per-skill venv（与 OpenClaw 惯例一致） |
| 依赖 | `pip install --user --break-system-packages -r requirements.txt` |
| 工作目录 | skill 根目录执行 `scripts/media_ctl.py` |

```bash
cd /path/to/media-mgmt
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m pytest -q
```

## 2. 后端矩阵（真实依赖）

### 2.1 影视主链路（必须 / 强烈）

| 层级 | 后端 | 本 skill 中的身份 | 典型配置 | 用途 |
|------|------|-------------------|----------|------|
| **必须** | **MoviePilot** REST | service `moviepilot` | `MOVIEPILOT_BASE_URL` + `MOVIEPILOT_API_KEY`（例 `http://127.0.0.1:3002`） | 认片回落、PT 搜种/下载、整理历史、active/cancel、115 分享转存插件 |
| **必须** | **NextFind** Agent OpenAPI | service `nextfind` | `NEXTFIND_BASE_URL` + `NEXTFIND_API_KEY`（例 `http://127.0.0.1:8092`，prefix `/api/openapi`） | **库有没有（权威）**、网盘资源、unlock、transfer、订阅双写一侧 |
| **强烈** | **qBittorrent / Transmission** | 经 MP；catalog 名 `qbittorrent`/`transmission` | 在 MoviePilot 里配置下载器（名如 `QB`/`TR`） | 实际 PT 下载；`call moviepilot active` |
| **强烈** | 网盘存储 + MP 整理（如 115） | 无独立 service | MP 存储/整理设置 | 转存后落库；索引可能滞后于 transfer 记录 |

### 2.2 短链 / 盘点（可选）

| 后端 | service id | 配置段 | 说明 |
|------|------------|--------|------|
| **Douyin_TikTok_Download_API**（项目/进程名；本地 HTTP，默认端口 **7899**） | `douyin`、`tiktok`、`hybrid`、`bilibili` | `config.douyin.api_base_url`（bilibili 可单独 `config.bilibili.api_base_url`，默认同端口） | 抖音 / TikTok / B 站：`run link` → hybrid → 各平台 parse/download。**真实后端就是这套 API**，端口 7899 只是常见部署；**不是** NextFind / MoviePilot |
| 红果短剧站点 SSR | `hongguo` | 可选 proxy/timeout/download_dir | 直连 `hongguoduanju.com` 等公开页，无 apikey |

`hybrid` 与 `tiktok` 默认读 **同一** `douyin.api_base_url`（同一套 Douyin_TikTok_Download_API）。

### 2.3 其它可选

| 后端 | service id | 凭据 / 配置 | 用途 |
|------|------------|-------------|------|
| **CloudDrive2** gRPC | `clouddrive` | `CLOUDDRIVE_TOKEN` + URL（例 `19798`） | `run offline` 磁力/链接离线 |
| **Telegram Music Bot**（Telethon） | `telegram_music` | `TELEGRAM_API_ID` / `HASH` / `SESSION_STRING` + bot 名 | `run listen` |
| 公共歌单 HTTP | `playlist` | 无密钥；可选 proxy | 网易云/QQ/酷我/酷狗元数据 → listen queries |

### 2.4 不在本 skill 网盘路径里的东西

| 名称 | 说明 |
|------|------|
| 旧 Cloak 浏览器 HDHive 爬取 | **已删除**，无兼容入口 |
| pansou 盘搜 | **已删除** |
| `hdhive.txt` | 仅 **checkin-manager** 等站点登录用，**不是** media-mgmt 找源后端 |
| NextFind 返回的 `hdhive://` slug、`/hdhive/unlock` | **上游 OpenAPI 路径/资源 ID 形态**，不是本仓库 CLI 别名 |

## 3. 凭据

密钥只放 workspace `.credentials/`（见 `references/credentials.md`）。

**最小影视：**

```bash
# .credentials/moviepilot.env
MOVIEPILOT_BASE_URL=http://127.0.0.1:3002
MOVIEPILOT_API_KEY=***

# .credentials/nextfind.env
NEXTFIND_BASE_URL=http://127.0.0.1:8092
NEXTFIND_API_KEY=***
```

**短链（可选）：** 先部署 **Douyin_TikTok_Download_API**，再在 `config.json` 设 `douyin.api_base_url`（及可选 bilibili，默认 `http://127.0.0.1:7899`）。

**CloudDrive / 音乐（可选）：** `clouddrive.env`、`telegram_music.env`。

```bash
chmod 600 /path/to/workspace/.credentials/*.env
```

## 4. 非密配置

```bash
cp config.example.json config.json   # config.json 已 gitignore
# 按本机改端口与路径；勿写 api_key
```

## 5. 验证

```bash
python3 scripts/media_ctl.py run doctor
# 期望：moviepilot / nextfind 等核心 ok；未装的可选服务可 degraded

python3 scripts/media_ctl.py call nextfind health
python3 scripts/media_ctl.py call moviepilot clients

# 短链（需 Douyin_TikTok_Download_API 已起）
python3 scripts/media_ctl.py call hybrid parse --param url='https://v.douyin.com/...'

# 网盘干跑
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=ID --param title=片名 --param media_type=movie --param dry_run=true
```

### 成功判据（防假绿）

| 动作 | 至少读 |
|------|--------|
| 任意 run/call | 业务字段 + `error`/`warnings`，勿只看 `success` |
| 库有没有 | `authority=nextfind` + `exists` |
| 转存 | `slug` + **`result.transfer.success`**（顶层 `transfer` 可能只是请求开关布尔） |
| dry_run | `would_transfer` ≠ 已落盘 |

## 6. Agent / CLI 入口

| 入口 | 用途 |
|------|------|
| `SKILL.md` | 意图 → 唯一 workflow、硬规则 |
| `python3 scripts/media_ctl.py run <workflow>` | 固定剧本 |
| `python3 scripts/media_ctl.py call <service> <op>` | 单服务 op |
| `references/workflows.md` | 剧本参数 |
| `references/nextfind-115.md` | NextFind 转存 + 明文 115 分享 |
| `references/link-intents.md` | 短链/盘点 |

网盘找源/转存：**只** `run nextfind` / `call nextfind *`。无 `run hdhive`。
