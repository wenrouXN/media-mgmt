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

## MoviePilot 订阅

MoviePilot 搜索/识别/订阅辅助建议用 mcporter/MCP；先在 `config.json` 里设置 `moviepilot.mcporter_server`。

```bash
mcporter call moviepilot.search-media keyword="<关键词>" type=media
# Then add subscription with MoviePilot REST or mcporter using the recognized TMDB id.
```

## HDHive

```bash
python3 scripts/hdhive.py search "关键词"              # 搜索，返回年份/简介/url
python3 scripts/hdhive.py resources "<detail_url>"     # 资源列表，自动选最佳
python3 scripts/hdhive.py resources "<url>" --select N # 手动选第 N 个
python3 scripts/hdhive.py unlock "<resource_url>"      # 解锁获取 115 链接
python3 scripts/hdhive_grab.py "关键词" --select N     # 一键搜索→解锁→转存
```

Unlock 三步：点「确定解锁」→ 点确认对话框「确定」→ 点 115 协议确认页「确定」→ 取 `location.href` 明文密码。

自动选资源逻辑：`(-疑似失效, 官组, 4K, 免费)` 元组排序。

## Telegram 音乐下载

```bash
python3 scripts/telegram_music_bot.py --query "梁静茹 勇气"
```

Override defaults only when needed:

```bash
python3 scripts/telegram_music_bot.py \
  --query "梁静茹 勇气" \
  --button-index 1 \
  --download-dir ./downloads/music
```

关键：发送 `/search <关键词>` 触发搜索；inline 按钮必须用 `callback_data`，不能发文字 `1`。
