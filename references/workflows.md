# 固定 workflows（硬剧本）

入口：

```bash
.venv/bin/python scripts/media_ctl.py workflows
.venv/bin/python scripts/media_ctl.py run <name> --param key=value
```

固定场景必须走 `run`；其它需求 agent 用 `call` ops 自由组合。

| name | 触发 | 必参 | 行为 |
|------|------|------|------|
| identify | 这是哪部 / 先定 tmdbid | title\|tmdbid | 认片返回 tmdb_id+候选；默认**不搜不下载** |
| watch | 我要看 X 第 N 集 | title | identify→搜→选→下→状态 |
| link | 抖音/B站/TikTok 链接 | url | hybrid intent 分流 |
| share115 | 115 分享链(+密码) | share_url | transfer_share，已转存也算成功 |
| listen | 听/下 歌名 | q | 搜候选打分；高置信自动下，多选必须确认 |
| doctor | 媒体挂了吗 | — | 全服务探活 |
| search | 有没有资源（只搜） | title\|tmdbid | identify + search + pick，不下 |
| status | 下好了吗/路径 | title\|tmdbid | status + transfer_history |
| subscribe | 订阅查/建 | title\|tmdbid | action=check\|create\|list |
| library | 库里有没有 | title\|tmdbid | mediaserver exists + 缺集 |
| updates | 有没有更新 | title\|tmdbid | 库缺集 + TMDB档期 + 已播可下/未播改订 |
| schedule | 播出日历 | title\|tmdbid | aired/upcoming/next air_date |
| catchup | 追更计划/执行 | title\|tmdbid | 已播缺集先下，未播订阅 |
| duplicates | 是否重复、留哪个 | title\|tmdbid | 按 SxxExx 分组，建议 keep；**不自动删** |
| hdhive | HDHive 资源 | q\|title | grab（可 transfer） |
| retry | 失败换源 | title | search；auto=true 再 watch |

## 追更（已播下 / 未播订）

```bash
# 只看计划
.venv/bin/python scripts/media_ctl.py run catchup --param tmdbid=296206 --param title=金特务：本色回归

# 执行：下已播缺集 + 建订阅
.venv/bin/python scripts/media_ctl.py run catchup --param tmdbid=296206 --param execute=true --param max_download=3

# 日历
.venv/bin/python scripts/media_ctl.py run schedule --param tmdbid=296206
```

`updates` 已内嵌 catchup 计划（不执行）。

## 听歌候选策略

```bash
# 只列候选
.venv/bin/python scripts/media_ctl.py run listen --param q='晴天 周杰伦' --param search_only=true

# 策略下载：高置信直接下；多选返回 needs_confirm + candidates
.venv/bin/python scripts/media_ctl.py run listen --param q='晴天 周杰伦'

# 用户确认后
.venv/bin/python scripts/media_ctl.py run listen --param q='晴天 周杰伦' --param button_index=2

# 强制头名（不推荐默认）
.venv/bin/python scripts/media_ctl.py run listen --param q='晴天' --param force=true
```

规则：`exact` / 单候选 / top 分高且与第二名分差大 → auto；否则必须确认。

## 先定 tmdbid（推荐搜源前）

```bash
# 只认片，停下给你确认
.venv/bin/python scripts/media_ctl.py run identify --param title=金特务

# 多候选时选第 N 个
.venv/bin/python scripts/media_ctl.py run identify --param title=金特务 --param select=2

# 确认后继续搜（仍不下）/ 直接看
.venv/bin/python scripts/media_ctl.py run identify --param title=金特务 --param continue_to=search
.venv/bin/python scripts/media_ctl.py run identify --param tmdbid=296206 --param continue_to=watch --param episode=5 --param dry_run=true
```

Agent 规则：模糊片名先 `run identify`，确认 `tmdb_id` 后再 `search`/`watch`。

## 你关心的库/更新/重复

```bash
# 库里有没有
.venv/bin/python scripts/media_ctl.py run library --param title=金特务：本色回归

# 有没有更新（缺哪些集）
.venv/bin/python scripts/media_ctl.py run updates --param title=金特务：本色回归

# 同集多版本，建议保留谁（仅报告）
.venv/bin/python scripts/media_ctl.py run duplicates --param title=金特务：本色回归 --param tmdbid=296206
```

`duplicates` 保留打分：整理成功 > `/links/` 路径 > 分辨率 > 较新记录。  
`apply=true` 只生成 **manual_review_delete 计划**，不执行删除。

## Agent 规则

1. 命中上表 → `media_ctl run ...`，不要手搓 API JSON。  
2. 未命中 → `call` / `ops` / `capabilities` 自由发挥。  
3. 破坏性操作（删库文件、清历史）永远二次确认。  
