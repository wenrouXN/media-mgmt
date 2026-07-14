# 固定 workflows（硬剧本）

入口：

```bash
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run <name> --param key=value
```

固定场景必须走 `run`；其它需求 agent 用 `call` ops 自由组合。

| name | 触发 | 必参 | 行为 |
|------|------|------|------|
| identify | 这是哪部 / 先定 tmdbid | title\|tmdbid | 认片返回 tmdb_id+候选；默认**不搜不下载** |
| watch | 我要看 X 第 N 集 | title | identify→搜→选→下→状态 |
| link | 抖音/B站/TikTok 链接 | url | hybrid intent 分流 |
| share115 | 115 分享链(+密码) | share_url | transfer_share，已转存也算成功 |
| listen | 听/下 歌名 | q | 搜候选打分；高置信自动下，多选必须确认 |
| playlist | 公共歌单链接 | url | 解析网易云/QQ/酷我/酷狗 → tracks + queries；**不下歌** |
| doctor | 媒体挂了吗 | — | 全服务探活 |
| search | 有没有资源（只搜） | title\|tmdbid | identify + search + 可选 episode 过滤 + pick，不下 |
| status | 下好了吗/路径 | title\|tmdbid | status + transfer_history |
| subscribe | 订阅查/建 | title\|tmdbid | action=check\|create\|list |
| library | 库里有没有 | title\|tmdbid | mediaserver exists + 缺集 |
| updates | 有没有更新 / **咋还没有** | title\|tmdbid | 库缺集 + TMDB档期 + 订阅 + 已播可下/未播改订（诊断首选） |
| schedule | 播出日历 | title\|tmdbid | aired/upcoming/next air_date |
| catchup | 追更计划/执行 | title\|tmdbid | 已播缺集先下，未播订阅 |
| duplicates | 是否重复、留哪个 | title\|tmdbid | 按 SxxExx 分组，建议 keep；**不自动删** |
| hdhive | 转存网盘 / HDHive / 115 | q\|title\|tmdbid | grab=搜→选→解锁→转存；`media_type`+`transfer=true` |
| retry | 失败换源 | title | search；auto=true 再 watch |
| upgrade | 库内质量升级 | title\|tmdbid | 默认 HDHive→115，再 PT；4K/中文/SDR |
| cancel | 下错了/取消下载 | hash\|title\|tmdbid | 取消活动下载任务；可选 delete_files |

## 防误下与撤回

选种会看 **title year** 与 **pubdate**。风险项（错年/过旧/缺发布日/0~1 seeder）在 `--yes` 时也会返回 `safety_confirmation_required`，需用户确认后 `--force --yes`。

```bash
# 预览要撤哪个
python3 scripts/media_ctl.py run cancel --param title=金特务：本色回归 --param episode=6 --param dry_run=true
# 真撤（只删任务）
python3 scripts/media_ctl.py run cancel --param title=金特务：本色回归 --param episode=6
# 连文件一起删
python3 scripts/media_ctl.py run cancel --param hash=20f6d1dc --param delete_files=true
```

## 缺集诊断（咋还没有）

```bash
# 首选：一条出结论
python3 scripts/media_ctl.py run updates --param title=金特务：本色回归 --param tmdbid=296206

# 可选：下载/整理状态
python3 scripts/media_ctl.py run status --param tmdbid=296206 --param episode=6

# 可选：源站有没有这集（episode 在 workflow 内过滤，不是 mp_api --episode）
python3 scripts/media_ctl.py run search --param tmdbid=296206 --param title=金特务：本色回归 --param episode=6
```

Agent 规则：诊断先 `updates`；未确认下载前禁止 `watch --yes`；不要发明 `mp_api search tmdb:ID` 位置参数。

## 网盘转存（HDHive → 115）

```bash
# 电影示例
python3 scripts/media_ctl.py run hdhive \
  --param tmdbid=849869 \
  --param title=格杀福顺 \
  --param media_type=movie \
  --param transfer=true

# 已有明文 115 链
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=abcd'
```

成功：`success=true` 且 transfer `code=0`（或已经转存）。  
失败：`masked_or_invalid_share_password` / `参数错误`（先查 P115 插件兼容）/ 无资源回落 PT。  
详情：`references/hdhive-115.md`。

Agent 规则：用户要网盘时**先 hdhive**，不要先 PT 再绕；禁止把脱敏 `password=***` 或 `code=-1` 当成功。

## 追更（已播下 / 未播订）

```bash
# 只看计划
python3 scripts/media_ctl.py run catchup --param tmdbid=296206 --param title=金特务：本色回归

# 执行：下已播缺集 + 建订阅
python3 scripts/media_ctl.py run catchup --param tmdbid=296206 --param execute=true --param max_download=3

# 日历
python3 scripts/media_ctl.py run schedule --param tmdbid=296206
```

`updates` 已内嵌 catchup 计划（不执行）。

## 公共歌单解析

```bash
# 解析公开歌单（只元数据）
python3 scripts/media_ctl.py run playlist --param url='https://music.163.com/#/playlist?id=...'

# 限返回前 20 首
python3 scripts/media_ctl.py run playlist --param url='...' --param limit=20

# ops
python3 scripts/media_ctl.py call playlist parse --param url='...'
python3 scripts/media_ctl.py call playlist capabilities

# CLI
python3 scripts/playlist_parse.py --url 'https://y.qq.com/n/ryqq/playlist/...' --limit 10
```

输出含 `tracks` 与 `queries`（`title artist`）。用户要下载时 agent 自行对 `queries` 循环 `run listen`；本 workflow 不批量下。Spotify 首版不支持。

## 听歌候选策略

```bash
# 只列候选
python3 scripts/media_ctl.py run listen --param q='晴天 周杰伦' --param search_only=true

# 策略下载：高置信直接下；多选返回 needs_confirm + candidates
python3 scripts/media_ctl.py run listen --param q='晴天 周杰伦'

# 用户确认后
python3 scripts/media_ctl.py run listen --param q='晴天 周杰伦' --param button_index=2

# 强制头名（不推荐默认）
python3 scripts/media_ctl.py run listen --param q='晴天' --param force=true
```

规则：`exact` / 单候选 / top 分高且与第二名分差大 → auto；否则必须确认。

## 先定 tmdbid（推荐搜源前）

```bash
# 只认片，停下给你确认
python3 scripts/media_ctl.py run identify --param title=金特务

# 多候选时选第 N 个
python3 scripts/media_ctl.py run identify --param title=金特务 --param select=2

# 确认后继续搜（仍不下）/ 直接看
python3 scripts/media_ctl.py run identify --param title=金特务 --param continue_to=search
python3 scripts/media_ctl.py run identify --param tmdbid=296206 --param continue_to=watch --param episode=5 --param dry_run=true
```

Agent 规则：模糊片名先 `run identify`，确认 `tmdb_id` 后再 `search`/`watch`。

## 你关心的库/更新/重复

```bash
# 库里有没有
python3 scripts/media_ctl.py run library --param title=金特务：本色回归

# 有没有更新（缺哪些集）
python3 scripts/media_ctl.py run updates --param title=金特务：本色回归

# 同集多版本，建议保留谁（仅报告）
python3 scripts/media_ctl.py run duplicates --param title=金特务：本色回归 --param tmdbid=296206
```

`duplicates` 保留打分：整理成功 > `/links/` 路径 > 分辨率 > 较新记录。  
`apply=true` 只生成 **manual_review_delete 计划**，不执行删除。

## Agent 规则

1. 命中上表 → `media_ctl run ...`，不要手搓 API JSON。  
2. 未命中 → `call` / `ops` / `capabilities` 自由发挥。  
3. 破坏性操作（删库文件、清历史）永远二次确认。  


## 质量升级（4K / 中文 / SDR）

默认：**先 HDHive 解锁 115 转存**，失败再 PT。不自动删旧版本。

```bash
# 计划（不下）
python3 scripts/media_ctl.py run upgrade \
  --param tmdbid=296206 --param title=金特务：本色回归 --param episode=5 \
  --param resolution=2160p --param hdr_mode=sdr --param require_chinese=true \
  --param prefer=hdhive --param dry_run=true

# 执行
python3 scripts/media_ctl.py run upgrade \
  --param tmdbid=296206 --param episode=5 --param execute=true \
  --param resolution=2160p --param hdr_mode=sdr --param require_chinese=true
```

成功后：`run duplicates` 对比新旧，确认后再删旧源。
