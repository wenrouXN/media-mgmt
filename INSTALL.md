# media-mgmt 安装说明

media-mgmt 是一个 **媒体编排 skill**：把「认片、查库、搜源、网盘转存、下载、订阅、短链、听歌」接到你自己已部署的服务上。  
它 **不是** 一体机媒体中心，也 **不会** 替你安装 MoviePilot / NextFind 等上游软件。

- 策略与意图路由：见 `SKILL.md`
- 常用命令：见 `references/commands.md`
- 本页只讲：**环境、依赖服务、配置、验收**

---

## 你需要准备什么

### 影视主链路（推荐完整装齐）

| 组件 | 作用 | 文档 / 获取 |
|------|------|-------------|
| **MoviePilot** | 搜索种子、下载、整理、订阅、115 分享转存等 | [GitHub](https://github.com/jxxghp/MoviePilot) · [安装 Wiki](https://wiki.movie-pilot.org/install) |
| **NextFind** | 库内是否已有、网盘资源检索与转存（本 skill 的网盘主路径） | [NextFind 介绍](https://wiki.nextemby.com/#/nextfind_intro) |
| **下载器** | qBittorrent 或 Transmission，在 MoviePilot 中配置 | [qBittorrent](https://github.com/qbittorrent/qBittorrent) · [Transmission](https://github.com/transmission/transmission) |
| **媒体库 / 网盘** | 本地库或 115 等存储，按 MoviePilot / NextFind 各自文档配置 | 随你的存储方案 |

最小可验收：MoviePilot + NextFind 均可访问，并已写入下方凭据。

### 可选能力

| 组件 | 作用 | 文档 / 获取 |
|------|------|-------------|
| **Douyin_TikTok_Download_API** | 抖音 / TikTok / B 站链接解析与下载 | [GitHub](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) |
| **CloudDrive2** | 磁力 / 链接离线下载到网盘 | [官网下载](https://www.clouddrive2.com/download.html) · [Docker 镜像](https://hub.docker.com/r/cloudnas/clouddrive2) |
| **Telegram 搜歌 Bot + Telethon** | 听歌搜索与下载 | [Telethon](https://github.com/LonamiWebs/Telethon) · API：[my.telegram.org](https://my.telegram.org) |
| 歌单解析 / 红果短剧 | 直连公开页面，无需独立服务 | 见 `references/link-intents.md`、`references/commands.md` |

上游版本、镜像名、端口以 **官方文档** 为准；请勿把他人环境的地址或端口当标准。

---

## 1. 安装本 skill 运行时

要求：

- Python 3.10+
- 在 skill 根目录执行命令（或把该目录加入你的 OpenClaw skill 路径）

```bash
cd /path/to/media-mgmt
python3 -m pip install --user --break-system-packages -r requirements.txt
```

可选自检：

```bash
python3 -m pytest -q
```

---

## 2. 配置凭据（密钥）

密钥放在 **OpenClaw workspace** 的 `.credentials/` 下（不要提交到 Git）。细则见 `references/credentials.md`。

### 2.1 影视必配

**MoviePilot** — 文件名：`moviepilot.env`

```bash
MOVIEPILOT_BASE_URL=http://127.0.0.1:<你的 MoviePilot 端口>
MOVIEPILOT_API_KEY=<在 MoviePilot 中创建的 API Key>
```

**NextFind** — 文件名：`nextfind.env`

```bash
NEXTFIND_BASE_URL=http://127.0.0.1:<你的 NextFind 访问地址>
NEXTFIND_API_KEY=<在 NextFind 中启用 Agent OpenAPI 后生成的 Key>
```

安装与能力说明以官方为准：  
[NextFind 介绍](https://wiki.nextemby.com/#/nextfind_intro)

权限建议：

```bash
chmod 600 /path/to/workspace/.credentials/*.env
```

### 2.2 可选凭据

| 文件 | 何时需要 |
|------|----------|
| `clouddrive.env`（`CLOUDDRIVE_URL` + `CLOUDDRIVE_TOKEN`） | 使用 `run offline` |
| `telegram_music.env`（API ID / Hash / Session 等） | 使用 `run listen` |

---

## 3. 非密钥配置

```bash
cp config.example.json config.json
```

按本机修改服务地址与下载目录。`config.json` 已在 `.gitignore` 中，**不要** 写入 API Key / Token / Session。

短链能力示例字段：

- `douyin.api_base_url`：Douyin_TikTok_Download_API 的根地址  
- `bilibili.api_base_url`：通常与上面同一实例  

CloudDrive / 听歌等见 `config.example.json` 内注释字段。

---

## 4. 建议部署顺序

1. 安装并启动 **MoviePilot**，配置下载器与媒体库。  
2. 按 [NextFind 介绍](https://wiki.nextemby.com/#/nextfind_intro) 安装 **NextFind**，开启 Agent OpenAPI，记下 Base URL 与 API Key。  
3. 写入 `moviepilot.env`、`nextfind.env`。  
4. 安装本 skill 依赖（第 1 节）。  
5. 执行第 5 节验收。  
6. 如需短链 / 离线 / 听歌，再装对应可选服务并补配置。

---

## 5. 验收

在 skill 根目录：

```bash
# 服务连通性
python3 scripts/media_ctl.py run doctor

# 分别探活（可选）
python3 scripts/media_ctl.py call nextfind health
python3 scripts/media_ctl.py call moviepilot clients
```

网盘干跑（不会真转存）：

```bash
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=<TMDB数字ID> \
  --param title=<片名> \
  --param media_type=movie \
  --param dry_run=true
```

短链（需已部署 Douyin_TikTok_Download_API）：

```bash
python3 scripts/media_ctl.py call hybrid parse --param url='https://v.douyin.com/...'
```

### 如何判断成功

| 你在做 | 应看到 |
|--------|--------|
| 查库 | 结果标明以 NextFind 为准，并给出是否在库 |
| 转存 | 有资源标识（slug），且 **转存结果对象** 表示成功；不要把请求参数里的 `transfer=true` 当成「已转存」 |
| 干跑 | 仅预览/would_transfer，不代表文件已落盘 |
| 体检 | 已配置的服务为健康；未安装的可选服务可降级，不影响主链路 |

更多网盘说明：`references/nextfind-115.md`。

---

## 6. 日常怎么用

| 入口 | 用途 |
|------|------|
| 对话 + OpenClaw 加载本 skill | 自然语言（「有没有 XX」「转存到网盘」等） |
| `python3 scripts/media_ctl.py run <工作流>` | 固定剧本（watch / nextfind / library …） |
| `python3 scripts/media_ctl.py call <服务> <操作>` | 单服务调用 |
| `references/workflows.md` | 各工作流参数 |
| `references/nextfind-115.md` | 网盘转存与 115 分享 |
| `references/link-intents.md` | 短链与盘点 |

网盘找源与转存请使用 **`run nextfind` / `call nextfind …`**，不要走已移除的旧路径。

---

## 7. 常见问题

**Q：只装了 MoviePilot 行不行？**  
A：可以搜种下载，但「库里有没有」、网盘转存等以 NextFind 为权威的能力会不可用或不完整。

**Q：NextFind 装在哪、端口多少？**  
A：以 [官方介绍](https://wiki.nextemby.com/#/nextfind_intro) 与你的部署为准；把实际 Base URL 与 Key 写入 `nextfind.env` 即可。

**Q：短链解析失败？**  
A：确认 Douyin_TikTok_Download_API 已启动，且 `config.json` 中 `api_base_url` 指向正确地址；浏览器可先打开该服务的 `/docs`。

**Q：密钥写进 config.json 了？**  
A：请移到 `.credentials/*.env` 并轮换已泄露的密钥。

**Q：和 moviepilot-cli / moviepilot-api 什么关系？**  
A：本 skill 做跨服务编排；需要直接调 MoviePilot 裸 API 时用那些 skill，不要在对话里手搓未声明参数。

---

## 8. 安全与范围

- 仓库 **不包含** 账号、Cookie、媒体文件。  
- 不要在 Issue / 截图中暴露你的 API Key、内网地址与路径。  
- 本仓库 **不提供** 上游服务的生产 Compose 模板，避免把环境细节写进 skill。  
- 遵守各上游项目的许可证与使用条款。
