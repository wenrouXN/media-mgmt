# media-mgmt command reference

All commands assume the skill root:

```bash
cd /path/to/media-mgmt
```

Runtime defaults are in local `config.json`.

## 盘搜搜索

```bash
PANSOU_URL=$(python3 - <<'PY'
from media_mgmt_lib.config import load_json_config, get_nested
print(get_nested(load_json_config(), 'pansou.url'))
PY
)
curl -s -X POST "$PANSOU_URL/api/search" \
  -H "Content-Type: application/json" \
  -d '{"kw":"<关键词>","cloud_types":["115"]}'
# result: data.merged_by_type["115"]
```

## 115 分享转存（MoviePilot P115StrmHelper）

认证必须走 query param，不要用 `X-Api-Key` header。

```bash
python3 - <<'PY'
import urllib.parse, urllib.request
from media_mgmt_lib.config import load_json_config, moviepilot_credentials
cfg = load_json_config()
creds = moviepilot_credentials(cfg)
share_url = '<含密码的完整分享链接>'
query = urllib.parse.urlencode({'apikey': creds['API_KEY'], 'share_url': share_url})
print(urllib.request.urlopen(f"{creds['BASE_URL'].rstrip()}/api/v1/plugin/P115StrmHelper/add_transfer_share?{query}").read().decode())
PY
# success: {"code":0,"msg":"转存成功"}
# already done is also possible: {"code":-1,"msg":"你已经转存过该文件"}
```

## MoviePilot REST API

```bash
python3 scripts/mp_api.py identify "新进职员姜会长" --media-type tv --year 2026
python3 scripts/mp_api.py media-detail --tmdbid 299365 --media-type tv
python3 scripts/mp_api.py search --tmdbid 299365 --media-type tv --sites "6,19"
python3 scripts/mp_api.py paths
python3 scripts/mp_api.py category
python3 scripts/mp_api.py resolve-path '{"type":"tv","original_language":"ko","origin_country":["KR"]}'
```

下载必须显式传 `save_path`，或传 `--media-json` 让脚本自动计算。先 dry-run：

```bash
python3 scripts/mp_api.py download \
  --torrent-json '{"title":"...","enclosure":"https://..."}' \
  --media-json '{"type":"tv","original_language":"ko","origin_country":["KR"]}' \
  --dry-run
```

确认无误后去掉 `--dry-run` 才会真正添加下载：

```bash
python3 scripts/mp_api.py download \
  --torrent-json '<TorrentInfo JSON 或文件路径>' \
  --media-json '<MediaInfo JSON 或文件路径>'
```

订阅也先 dry-run：

```bash
python3 scripts/mp_api.py subscribe \
  --name "新进社员姜会长" \
  --media-type tv \
  --year 2026 \
  --tmdbid 299365 \
  --sites "6,19" \
  --resolution 1080p \
  --dry-run
```

常用接口：

- `GET /api/v1/media/search` / `GET /api/v1/media/recognize`：识别媒体和 TMDB ID。
- `GET /api/v1/media/{mediaid}`：按 TMDB/mediaid 查媒体详情。
- `GET /api/v1/search/media/{mediaid}`：按 `tmdb:<id>` 精确搜站点资源。
- `GET /api/v1/download/paths`：查询可直接用于 `save_path` 的下载路径。
- `GET /api/v1/media/category/config`：查询媒体分类策略。
- `POST /api/v1/download/` / `POST /api/v1/download/add`：添加下载，必须显式传 `save_path`。
- `GET /api/v1/subscribe/media/{mediaid}` / `POST /api/v1/subscribe/`：查询/创建订阅。

不要把 MCP/mcporter 当作 fallback；API 不支持时直接报告缺口。

## HDHive

```bash
python3 scripts/hdhive.py tmdb tv 299365              # 按剧集 TMDB ID 搜索
python3 scripts/hdhive.py tmdb movie 123456            # 按电影 TMDB ID 搜索
python3 scripts/hdhive.py search "关键词"              # 关键词搜索，仅在无 TMDB ID 时使用
python3 scripts/hdhive.py resources "<detail_url>"     # 资源列表，自动选最佳
python3 scripts/hdhive.py resources "<url>" --select N # 手动选第 N 个
python3 scripts/hdhive.py unlock "<resource_url>"      # 解锁获取 115 链接
python3 scripts/hdhive_grab.py "关键词" --select N     # 一键搜索→解锁→转存
```

Unlock 三步：点「确定解锁」→ 点确认对话框「确定」→ 点 115 协议确认页「确定」→ 取 `location.href` 明文密码。

自动选资源逻辑：`(-疑似失效, 官组, 4K, 免费)` 元组排序。

## Telegram 音乐下载

> **运行环境**：所有命令必须使用 `.venv/bin/python3`，确保 telethon 等依赖可用。

```bash
.venv/bin/python3 scripts/telegram_music_bot.py --query "梁静茹 勇气"
```

Override defaults only when needed:

```bash
python3 scripts/telegram_music_bot.py \
  --query "梁静茹 勇气" \
  --button-index 1 \
  --download-dir ./downloads/music
```

关键：发送 `/search <关键词>` 触发搜索；inline 按钮必须用 `callback_data`，不能发文字 `1`。

## 抖音解析与下载

```bash
# 解析视频元数据（含章节/chapters）
.venv/bin/python3 scripts/douyin.py parse "https://v.douyin.com/xxx" --json

# 下载视频
.venv/bin/python3 scripts/douyin.py download "https://v.douyin.com/xxx"
```

依赖 Douyin_TikTok_Download_API 后端（默认 `http://localhost:7899`）。

## Bilibili 解析与下载

```bash
# 解析视频元数据
.venv/bin/python3 scripts/bilibili.py parse "https://www.bilibili.com/video/BVxxx" --json

# 下载视频（默认 1080P）
.venv/bin/python3 scripts/bilibili.py download "https://www.bilibili.com/video/BVxxx"

# 指定画质：120=4K, 80=1080P, 64=720P
.venv/bin/python3 scripts/bilibili.py download "https://www.bilibili.com/video/BVxxx" --quality 120
```

下载原理：API 返回 DASH 视频流+音频流 → ffmpeg 合并为 mp4。需要设置 Referer: https://www.bilibili.com
