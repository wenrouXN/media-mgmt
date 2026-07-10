# 固定 workflows（硬剧本）

入口：

```bash
.venv/bin/python scripts/media_ctl.py workflows
.venv/bin/python scripts/media_ctl.py run <name> --param key=value
```

固定场景必须走 `run`；其它需求 agent 用 `call` ops 自由组合。

| name | 触发 | 必参 | 行为 |
|------|------|------|------|
| watch | 我要看 X 第 N 集 | title | identify→搜→选→下→状态 |
| link | 抖音/B站/TikTok 链接 | url | hybrid intent 分流 |
| share115 | 115 分享链(+密码) | share_url | transfer_share，已转存也算成功 |
| listen | 听/下 歌名 | q | telegram_music search_download |
| doctor | 媒体挂了吗 | — | 全服务探活 |
| search | 有没有资源（只搜） | title\|tmdbid | identify + search + pick，不下 |
| status | 下好了吗/路径 | title\|tmdbid | status + transfer_history |
| subscribe | 订阅查/建 | title\|tmdbid | action=check\|create\|list |
| library | 库里有没有 | title\|tmdbid | mediaserver exists + 缺集 |
| updates | 有没有更新 | title\|tmdbid | library + missing_episodes + 订阅缺集 |
| duplicates | 是否重复、留哪个 | title\|tmdbid | 按 SxxExx 分组，建议 keep；**不自动删** |
| hdhive | HDHive 资源 | q\|title | grab（可 transfer） |
| retry | 失败换源 | title | search；auto=true 再 watch |

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
