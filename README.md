# media-mgmt

默认中文文档｜[English](README.en.md)

media-mgmt 是一个媒体资源管理 Skill，用来把「搜索资源 → 解锁/转存 → 订阅 → 下载音乐」这类私有自动化流程收拢到统一 provider 架构里。

> 仓库只提供自动化脚本和 Skill 工作流，不包含账号、Cookie、Telegram session、媒体文件或任何第三方服务访问权限。

## 功能

- **盘搜搜索**：调用可配置的资源搜索服务，搜索 115 资源。
- **115 分享转存**：调用 MoviePilot `P115StrmHelper` 插件，把 115 分享链接转存到媒体库。
- **HDHive provider**：通过 CloakManager/CDP 搜索 HDHive、列出 115 资源、解锁分享链接，并可一键转存最佳资源。
- **MoviePilot 辅助**：通过 REST API 做媒体识别、搜索、订阅、下载路径查询和下载；不使用 MCP fallback。
- **Telegram Music provider**：通过 Telethon 给音乐 bot 发送 `/search <关键词>`，点击 inline callback button，下载返回的音频文件。
- **标准 provider 布局**：核心代码在 `media_mgmt_lib/providers/`，命令入口在 `scripts/`。

## 目录结构

```text
SKILL.md                         Skill 入口
config.example.json              公开配置模板
README.md                        中文文档（默认）
README.en.md                     英文文档
references/commands.md           命令片段和操作细节
scripts/hdhive.py                HDHive search/resources/unlock CLI
scripts/hdhive_grab.py           HDHive search→unlock→MoviePilot transfer CLI
scripts/telegram_music_bot.py    Telegram 音乐下载 CLI
media_mgmt_lib/                  共享库和 provider 实现
  providers/hdhive/              HDHive provider
  providers/telegram_music/      Telegram Music provider
```

## 使用前提

### 基础环境

- Python 3.11+
- Python 依赖：
  - `websockets`
  - `telethon`
  - `python-dotenv`
- 支持 Skill 的 agent 运行环境，或普通 shell + 本仓库目录

### 外部服务

按需配置即可，不用的 provider 可以留空：

- **盘搜服务**：提供 `POST /api/search`。
- **MoviePilot**：可访问 REST API，并启用 `P115StrmHelper` 插件。
- **CloakManager**：有一个已登录 HDHive 的浏览器 profile，并开启 CDP。
- **Telegram**：Telethon 用户会话，且该账号可访问配置的音乐 bot。
- **MoviePilot REST API**：用于媒体识别、站点搜索、订阅、下载路径查询和下载。


## 依赖与致谢

这个 Skill 是把多个后端和开源工具串起来的胶水层。真正提供能力的是下面这些项目/服务，使用前请分别准备账号、服务和合法访问权限。

| 依赖/项目 | 用途 | 使用前提 | 配置项 |
|---|---|---|---|
| 支持 Skill 的 agent/runtime | 运行 Skill、调度工具、按需发送文件 | 将本仓库安装为可加载的 skill | `SKILL.md` |
| Python / uv | 执行 provider 脚本；`uv run` 可复用已有依赖环境 | Python 3.11+；推荐用 uv 管理运行环境 | 无 |
| 盘搜后端 | 搜索 115 分享资源 | 有可访问的盘搜 API，提供 `POST /api/search` | `pansou.url` |
| 115 网盘 | 分享链接来源和转存目标 | 需要有效 115 分享链接；MoviePilot/P115StrmHelper 侧需有对应账号能力 | 通过 MoviePilot 间接配置 |
| MoviePilot | 媒体识别、订阅、插件承载 | MoviePilot 服务可访问；API Key 可用 | `moviepilot.base_url`, `moviepilot.api_key` |
| MoviePilot P115StrmHelper 插件 | 115 分享转存 | MoviePilot 已安装并启用 P115StrmHelper；插件内完成 115 账号相关配置 | `moviepilot.*` |
| MoviePilot REST API | 媒体识别、订阅、下载路径查询和下载 | MoviePilot 服务可访问；API Key 可用 | `moviepilot.base_url`, `moviepilot.api_key` |
| CloakManager / CloakBrowser | 管理可 CDP 控制的浏览器 profile | CloakManager 服务可访问；profile 可启动；代理按需配置 | `hdhive.cloak_url`, `hdhive.profile_name`, `hdhive.profile_id` |
| HDHive 账号 | 搜索、查看、解锁 HDHive 资源 | 浏览器 profile 内已登录 HDHive；账号有对应资源/积分/权限 | 通过 CloakManager profile 保存登录态 |
| Telegram API / Telethon | 自动化 Telegram 音乐 bot | Telegram API ID/Hash；用户 session；账号可访问目标 bot | `telegram_music.api_id`, `api_hash`, `session_string`/`session_name` |
| Telegram 音乐 bot | 返回搜索结果和音频文件 | bot 可用；其 inline button 协议未变 | `telegram_music.bot` |

感谢以上项目和服务提供底层能力；本仓库只负责把这些能力整理成可复用的 Skill/provider 工作流。

## 配置

复制模板：

```bash
cp config.example.json config.json
```

`config.json` 已被 `.gitignore` 忽略，所有本机地址、Token、session 都集中写这里，不要提交。

完整模板：

```json
{
  "pansou": {
    "url": "http://127.0.0.1:805"
  },
  "moviepilot": {
    "base_url": "http://127.0.0.1:3002",
    "api_key": "replace-with-your-moviepilot-api-key"
  },
  "hdhive": {
    "cloak_url": "http://127.0.0.1:8080",
    "profile_name": "mdmgmt",
    "profile_id": ""
  },
  "telegram_music": {
    "api_id": 123456,
    "api_hash": "replace-with-your-telegram-api-hash",
    "session_string": "replace-with-your-telegram-session-string",
    "session_name": "",
    "bot": "@music_v1bot",
    "download_dir": "./downloads/music",
    "button_index": 1,
    "search_timeout": 20,
    "download_timeout": 30,
    "poll_interval": 1
  }
}
```

### 配置项说明

| 配置项 | 必需 | 说明 |
|---|---:|---|
| `pansou.url` | 搜索时必需 | 盘搜服务地址，脚本会调用 `POST /api/search`。 |
| `moviepilot.base_url` | 转存/订阅/下载时必需 | MoviePilot 地址，例如 `http://127.0.0.1:3002`。 |
| `moviepilot.api_key` | 转存/订阅/下载时必需 | MoviePilot API Key；REST API 使用 query 参数 `apikey`。 |
| `hdhive.cloak_url` | HDHive 时必需 | CloakManager 地址。 |
| `hdhive.profile_name` | 推荐 | CloakManager profile 名。`profile_id` 为空时会按名字自动查找。 |
| `hdhive.profile_id` | 可选 | CloakManager profile ID。留空时自动按 `profile_name` 查找；只有一个 profile 时也可自动选择。 |
| `telegram_music.api_id` | 音乐下载必需 | Telegram API ID。 |
| `telegram_music.api_hash` | 音乐下载必需 | Telegram API Hash。 |
| `telegram_music.session_string` | 二选一 | Telethon StringSession。 |
| `telegram_music.session_name` | 二选一 | Telethon session 文件/名称；与 `session_string` 二选一。 |
| `telegram_music.bot` | 音乐下载必需 | 音乐 bot 用户名，例如 `@music_v1bot`。 |
| `telegram_music.download_dir` | 音乐下载必需 | 音乐文件保存目录。 |
| `telegram_music.button_index` | 可选 | 默认点击第几个 inline button，1 起。 |
| `telegram_music.search_timeout` | 可选 | 等待搜索结果的秒数。 |
| `telegram_music.download_timeout` | 可选 | 等待音频文件返回的秒数。 |
| `telegram_music.poll_interval` | 可选 | 轮询间隔秒数。 |

### HDHive profile 自动发现

`hdhive.profile_id` 不需要手工硬填：

1. 如果配置了 `profile_id`，直接使用。
2. 如果 `profile_id` 为空，会调用 CloakManager `/api/profiles`，按 `profile_name` 查找。
3. 如果只有一个 profile，也会自动选择。
4. 如果 profile 没启动，脚本会尝试调用 `/api/profiles/{id}/launch` 启动后再连 CDP。

这比把某个机器上的 profile id 写死在文档里靠谱多了。

## 安装到 Agent

把本仓库安装/复制到你的 agent 可加载 skill 目录，并按下文创建 `config.json`。Agent 只需要知道：当用户要搜索媒体、转存 115、解锁 HDHive、订阅 MoviePilot 或下载音乐时，加载这个 skill。

### 给 Agent AI 的自动安装提示词

如果你的 agent 支持从 GitHub 安装/同步 skill，可以直接把下面这段发给它：

```text
请安装这个 Skill：
https://github.com/wenrouXN/media-mgmt

安装要求：
1. 将仓库放到你的可加载 skills 目录，skill 名称保持 media-mgmt。
2. 读取 SKILL.md 作为触发入口。
3. 复制 config.example.json 为 config.json。
4. 引导我填写 config.json 中的 pansou、moviepilot、hdhive、telegram_music 配置。
5. 不要提交或外发 config.json、Telegram session、Cookie、API Key、下载的媒体文件。
6. 安装后运行最小验证：能读取 SKILL.md，能执行 scripts/telegram_music_bot.py --help 和 scripts/hdhive.py 的 usage。
```

### 手动安装

```bash
# 进入你的 agent skills 目录，例如：
cd /path/to/agent/skills

git clone https://github.com/wenrouXN/media-mgmt.git media-mgmt
cd media-mgmt
cp config.example.json config.json
```

然后按「配置」章节填写 `config.json`。

### 更新

```bash
cd /path/to/agent/skills/media-mgmt
git pull
```

## 使用方法

所有命令默认在仓库根目录执行。

### HDHive 搜索 / 资源 / 解锁

```bash
python3 scripts/hdhive.py search "稻草人"
python3 scripts/hdhive.py resources "https://hdhive.com/tmdb/tv/292121"
python3 scripts/hdhive.py unlock "https://hdhive.com/resource/115/..."
```

### HDHive 一键搜索 → 解锁 → MoviePilot 转存

```bash
python3 scripts/hdhive_grab.py "稻草人" --select 1
```

资源排序偏好：非疑似失效 > 官组 > 4K > 免费。

### Telegram 音乐下载

```bash
python3 scripts/telegram_music_bot.py --query "梁静茹 勇气"
```

该 provider 会发送一条消息：

```text
/search <关键词>
```

然后等待 bot 返回 inline buttons，并用 `callback_data` 点击目标按钮。不要给 bot 发文字 `1`，那会被当成新的搜索词。

### 盘搜和 MoviePilot 命令片段

见 [`references/commands.md`](references/commands.md)。

## License

MIT。见 [LICENSE](LICENSE)。
