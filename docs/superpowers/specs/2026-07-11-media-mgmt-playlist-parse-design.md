# media-mgmt 公共歌单解析设计

日期：2026-07-11  
状态：approved（用户确认范围：只解析；批量听由 agent 自主调 `listen`）

## 1. 目标

在 `media-mgmt` skill 中补充「公共歌单链接 → 曲目元数据列表」能力，对齐 MusicPilot 公共歌单解析链路的**用户价值**，但不引入 MusicPilot 运行时、不 fork 其 GPL 模块。

成功标准：

1. 用户给出网易云 / QQ 音乐 / 酷我（可选酷狗）公开歌单链接时，一条 workflow/ops 返回歌单信息 + 曲目表。
2. 输出附带可直接喂给 `run listen` 的 `queries`（`title artist`）。
3. **不**自动批量下载；agent 需要时再循环调用现有 `listen`。
4. 不依赖已部署的 MusicPilot / Spotify OAuth。

## 2. 非目标

- 批量自动下载整张歌单（不做 workflow 内循环 `listen`）。
- 对照 Navidrome / 本地音乐库做缺歌补全。
- 持久化歌单表、订阅同步、定时刷新。
- Spotify 公开/私有歌单（TOTP + Web Player 易碎，首版不做）。
- 抓取或转存任何平台音频流。
- 复制 MusicPilot `public_playlist.py` 整文件（避免 GPL-3.0 模块级引入与脆弱 Spotify 逻辑）。

## 3. 方案选择

| 方案 | 描述 | 结论 |
|------|------|------|
| A | 搬迁 MusicPilot 解析模块 | 否：许可与维护成本 |
| **B** | skill 内自写轻量解析器 + ops/workflow | **采用** |
| C | 调外部 MusicPilot API | 否：当前无部署依赖 |

## 4. 架构

沿用 media-mgmt 现有分层：catalog + ops + workflows + 可选 CLI。

```text
services/playlist.json                 # 无密钥服务目录项
media_mgmt_lib/playlist_parse.py       # 纯解析：域名路由 + 平台实现
media_mgmt_lib/ops/playlist.py         # op: parse / capabilities
media_mgmt_lib/workflows/playlist.py   # workflow: playlist
scripts/playlist_parse.py              # CLI，stdout JSON
```

数据流：

```text
url (+ optional proxy/limit)
  → resolve redirects
  → detect platform by hostname
  → platform-specific public API parse
  → normalize tracks
  → build queries[]
  → JSON result
```

与现有能力边界：

| 用户输入 | 路由 |
|----------|------|
| 歌单链接 | `run playlist` / `call playlist parse` |
| 歌手+歌名 | `run listen`（不变） |
| 抖音/B站/TikTok | `run link`（不变） |

## 5. 组件职责

### 5.1 `playlist_parse.py`（核心）

- 无 I/O 副作用除 HTTP 外；不写文件、不读 `config.json` 密钥。
- 提供：
  - `parse_playlist(url, *, proxy_url=None, limit=None, client=None) -> ParsedPlaylist`
  - 异常：`UnsupportedPlaylistURL`、`PlaylistParseError`
- 平台实现（首版）：
  1. **网易云**（必须）：`music.163.com` 等；`POST /api/v6/playlist/detail`；曲目不足时用 trackIds + `/api/v3/song/detail` 分批补全。
  2. **QQ 音乐**（必须）：`y.qq.com` 等；`fcg_ucc_getcdinfo_byids_cp.fcg` + `disstid`。
  3. **酷我**（必须）：`kuwo.cn`；playlist info 分页。
  4. **酷狗**（应做，可次优先）：要求 `.../special/single/{id}.html` 类路径；失败信息写清 URL 形态。
  5. **Spotify**：明确 `unsupported`，错误信息提示首版不支持。

### 5.2 `ops/playlist.py`

- `capabilities`：列出支持平台与参数。
- `parse`：读 `url`/`link`；可选 `proxy`（params 或 `config.playlist.proxy`）；可选 `limit`；调用核心解析；返回统一 dict。
- 在 `ops/bootstrap.py` 注册 import。

### 5.3 `workflows/playlist.py`

- 固定剧本：校验 `url` → `call_op("playlist", "parse", ...)` → 包装 `workflow=playlist` + `summary`。
- 注册进 `workflows/__init__.py` REGISTRY，`need: ["url"]`。

### 5.4 `scripts/playlist_parse.py`

- CLI：`--url`、`--proxy`、`--limit`、`--json`（默认 stdout 一整块 JSON）。
- 供排障与 `ops` 子进程路径（若 ops 选择 subprocess；优先进程内 import）。

### 5.5 `services/playlist.json`

- `id: playlist`，描述「公共歌单元数据解析」，`config_section: playlist`（可选，仅 proxy）。
- ops 列表：`parse`、`capabilities`。

## 6. 统一输出契约

```json
{
  "success": true,
  "workflow": "playlist",
  "platform": "netease",
  "playlist": {
    "name": "string",
    "external_id": "string",
    "owner_name": "string|null",
    "description": "string|null",
    "cover_url": "string|null",
    "source_url": "string",
    "track_count": 42
  },
  "tracks": [
    {
      "position": 1,
      "title": "晴天",
      "artist": "周杰伦",
      "album": "叶惠美",
      "duration": 269,
      "external_id": "string",
      "cover_url": "string|null"
    }
  ],
  "queries": ["晴天 周杰伦"],
  "truncated": false,
  "summary": "netease 歌单《…》42 首"
}
```

规则：

- `queries[i]` 由 `tracks[i]` 生成：有 artist 则 `f"{title} {artist}"`，否则仅 `title`；空白折叠。
- `limit` 若截断：`truncated=true`，`track_count` 仍为解析到的全量（若 API 可知）或截断前长度；`tracks`/`queries` 为截断后列表。实现取明确口径：**`playlist.track_count` = 截断前总曲目；`len(tracks)` 为返回条数；`truncated = len(tracks) < track_count`**。
- 失败：`success=false`，`error` 为稳定枚举字符串：
  - `missing_param`
  - `unsupported_url`
  - `parse_failed`
  - `http_error`
  - 附 `detail`、可选 `need` / `supported_platforms`

## 7. 配置

`config.example.json` 可选段（全部可选）：

```json
{
  "playlist": {
    "proxy": null,
    "timeout": 30,
    "default_limit": null
  }
}
```

- 无密钥。不配也能跑。
- params 覆盖 config：`proxy`、`timeout`、`limit`。

## 8. 依赖

- `requirements.txt` 增加 `httpx`（用户级 `pip install --user --break-system-packages`，无 per-skill venv）。
- 不新增 telethon 以外的重依赖。

## 9. 文档改动

- `SKILL.md` description 与 Default intent：歌单链接 → `run playlist`。
- workflows 表增加 `playlist`。
- `references/workflows.md`、`references/commands.md` 增加示例。
- README 中文/英文各补一句能力说明。

## 10. 测试

- `tests/test_playlist_parse.py`：
  - 域名路由（网易云/QQ/酷我/酷狗/未知/Spotify unsupported）。
  - 用 fixture JSON 测 track 映射与 `queries` 生成。
  - `limit` 截断与 `truncated` 标志。
- 默认不访问外网。可选 `@pytest.mark.live` 手工测真链。

## 11. Agent 使用约定（写进 SKILL）

1. 用户丢歌单链接 → `run playlist`，展示歌单名 + 曲目数 + 前若干曲。
2. 用户说「都下了 / 下前 N 首 / 下第 x 首」→ agent **自行**对对应 `queries` 调 `run listen`；不要假装 skill 有批量下载 op。
3. 不自动对整表 `listen`，除非用户明确要求下载。

## 12. 实现顺序

1. 核心 `playlist_parse.py` + 单测  
2. ops + service catalog + bootstrap  
3. workflow 注册  
4. CLI  
5. SKILL / references / README / requirements  
6. 本地 dry：`media_ctl workflows` 可见 `playlist`；fixture 测试通过  

## 13. 许可与归属

- 实现为 skill 内原创代码，可参考公开 API 行为与业界常见字段映射，**不**整文件复制 MusicPilot 源码。
- MusicPilot 仅作产品行为参考（公开链接 → 元数据列表）。
