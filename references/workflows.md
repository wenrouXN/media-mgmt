# 固定 workflows（硬剧本）

入口：

```bash
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run <name> --param key=value
```

命中下表 → 必须 `run`。未命中 → `call` / `ops`。精确 CLI 见 `commands.md`。

## 准确用法（先读）

1. **一意图一主枪**：先 `updates`/`watch`/`hdhive`/… 其中一个；失败再按 SKILL「失败怎么补一枪」。
2. **参数尽量满**：`title` + 已知则 `tmdbid` + 有集则 `episode`/`season` + 已知则 `media_type=tv|movie`。
3. **watch 同 tmdb 电影/剧**：TMDB 数字 id 可撞车；务必带用户标题；有集数会偏 TV。
4. **诊断不下**：`updates`/`library`/`identify`/`dry_run=true`。真下须用户意图明确。
5. **网盘**：`hdhive` + `transfer=true` + 尽量 `media_type`；不要先 PT。

## 目录

| name | 触发 | 必参 | 行为 |
|------|------|------|------|
| identify | 这是哪部 / 先定 tmdbid | title\|tmdbid | 认片；默认不搜不下 |
| watch | 我要看 X 第 N 集 | title | identify→(HDHive?)→PT 搜选下→状态 |
| link | 短视频/B站/红果链接 | url | hybrid intent 分流 |
| share115 | 115 分享链(+密码) | share_url | transfer；已转存也算成功 |
| listen | 听/下歌 | q | 高置信可自动；多选须确认 |
| playlist | 公共歌单链接 | url | 元数据+queries；**不下歌** |
| doctor | 媒体挂了吗 | — | 全服务探活 |
| search | 只搜不下 | title\|tmdbid | identify+search+可选 episode 过滤 |
| status | 下好了吗/路径 | title\|tmdbid | active + transfer_history |
| subscribe | 订阅查/建 | title\|tmdbid | action=check\|create\|list |
| library | 库里有没有 | title\|tmdbid | mediaserver + 缺集 |
| updates | **咋还没有** / 有没有更新 | title\|tmdbid | 缺集+档期+订阅+可下/可订（诊断首选） |
| schedule | 播出日历 | title\|tmdbid | aired/upcoming/next |
| catchup | 追更计划/执行 | title\|tmdbid | 已播下、未播订；`execute=true` 才执行 |
| duplicates | 重复留哪个 | title\|tmdbid | 建议 keep；不自动删 |
| hdhive | 转存网盘 | q\|title\|tmdbid | grab→unlock→transfer |
| retry | 失败换源 | title | search；auto 再 watch |
| upgrade | 质量升级 | title\|tmdbid | 默认 HDHive→115，再 PT |
| cancel | 下错了 | hash\|title\|tmdbid | 取消任务；可选 delete_files |

## 场景策略（agent）

### 缺集 / 咋还没有

1. **只先** `run updates`（一条出结论）
2. 可选 `run status` / `run search --param episode=N` / `watch --dry_run`
3. 未确认前禁止 `watch --yes`
4. 禁止发明 `mp_api search tmdb:ID` 位置参数或 `--episode`

### 防误下与撤回

- 风险（错年 / 过旧 / 缺 pubdate / 0~1 seeder）→ `safety_confirmation_required`；确认后 `--force --yes`
- 撤回：`run cancel`（可 `dry_run=true` 预览；删文件 `delete_files=true`）

### 网盘转存

- 用户要网盘 → **先** `run hdhive`（`media_type` + `transfer=true`），不要先 PT
- 已有明文 115 链 → `run share115`
- 成功判据与排障 → `hdhive-115.md`

### 认片

- 模糊片名先 `run identify`，确认 `tmdb_id` 再 search/watch
- `select=N` 选候选；`continue_to=search|watch` 接着走

### 听歌 / 歌单

- 歌名 → `run listen`（`search_only=true` 只列；确认后 `button_index`）
- 歌单链接 → `run playlist` → 展示名/曲目数 → 用户点下哪些再对 `queries[i]` 调 listen
- 无批量下载 op；Spotify 不支持

### 质量升级

- 默认 prefer hdhive；`dry_run=true` 先计划；成功后再 `duplicates` 对比，确认后才删旧

### 库 / 重复

- `library` / `updates` / `duplicates`
- `duplicates apply=true` 只出 manual_review 计划，不执行删除

## Agent 总则

1. 命中目录 → `media_ctl run ...`，勿手搓 MoviePilot JSON。  
2. 未命中 → `call` / `ops` / `capabilities`。  
3. 破坏性操作永远二次确认。  
4. 短链意图细节 → `link-intents.md`。
