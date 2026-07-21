# 固定 workflows（硬剧本）

入口：

```bash
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run <name> --param key=value
```

命中下表 → 必须 `run`。未命中 → `call` / `ops`。精确 CLI 见 `commands.md`。  
**返回字段纪律** → `SKILL.md` §0（必读 `warnings` / `state` / `authority` / `resource_authority`）。

## 准确用法（先读）

1. **一意图一主枪**：先 `updates`/`watch`/`nextfind`/`identify`/… 其中一个；失败再按 SKILL「失败怎么补一枪」。
2. **参数尽量满**：`title` + 已知则 `tmdbid` + 有集则 `episode`/`season` + 已知则 `media_type=tv|movie`。
3. **watch 同 tmdb 电影/剧**：TMDB 数字 id 可撞车；务必带用户标题；有集数会偏 TV。
4. **诊断不下**：`updates`/`library`/`identify`/`dry_run=true`。真下须用户意图明确。
5. **网盘**：`nextfind`（或别名 `hdhive`）+ 尽量 `media_type`；先 `dry_run=true`；可转存以 **resources 有 slug** 为准（`resource_authority=resources_op`）。旧 pansou/Cloak 已退役。不要先 PT。
6. **有没有**：`library` = NextFind only；MP 只 transfer/download 整理记录。

## 目录（21）

| name | 触发 | 必参 | 行为 |
|------|------|------|------|
| doctor | 媒体挂了吗 / 体检 | — | 全服务探活 + degraded + pipeline 口径 |
| identify | 这是哪部 / 先定 tmdb | title\|tmdbid | NextFind 优先，失败回落 MoviePilot |
| watch | 我要看 X 第 N 集 | title | identify→网盘?→PT 搜选下；`pick_n` 1-based；`site_name` 锁 |
| link | 短视频/B站/红果链接 | url | hybrid intent 分流 |
| share115 | 115 分享链(+密码) | share_url | transfer；已转存也算成功 |
| listen | 听/下歌 | q | 高置信可自动；多选须确认 |
| playlist | 公共歌单链接 | url | 元数据+queries；**不下歌** |
| search | 只搜不下 | title\|tmdbid | 默认 NF；读 `warnings`；PT 需 `force_mp_search` |
| status | 下好了吗/路径 | title\|tmdbid | active + transfer_history |
| subscribe | 订阅查/建 | title\|tmdbid | dual-write；返回 `state` |
| library | 库里有没有 | title\|tmdbid | **有没有=NextFind**；MP=整理记录 |
| updates | **咋还没有** / 有没有更新 | title\|tmdbid | 缺集+档期+订阅+fill_plan（诊断首选） |
| schedule | 播出日历 | title\|tmdbid | aired/upcoming/next |
| catchup | 追更计划/执行 | title\|tmdbid | 先 NF 补缺；`execute=true` 才执行 |
| duplicates | 重复留哪个 | title\|tmdbid | 建议 keep；不自动删 |
| nextfind | 转存网盘（主） | q\|title\|tmdbid | OpenAPI search→resources→transfer |
| hdhive | 转存网盘（别名） | q\|title\|tmdbid | 同 nextfind |
| offline | 磁力/CloudDrive 离线 | magnet\|url | CloudDrive AddOfflineFiles |
| retry | 失败换源 | title | search；auto 再 watch |
| upgrade | 升画质 / 质量升级 | title\|tmdbid | probe/dry 先；execute 网盘→PT |
| cancel | 下错了 | hash\|title\|tmdbid | 取消任务；可选 delete_files |

## 场景策略（agent）

### 缺集 / 咋还没有

1. **只先** `run updates`（一条出结论）
2. 可选 `run status` / `run search --param episode=N` / `watch --dry_run`
3. 未确认前禁止 `watch` 真下
4. 禁止发明 `mp_api search tmdb:ID` 位置参数或 `--episode`

### 防误下与撤回

- 风险（错年 / 过旧 / 缺 pubdate / 0~1 seeder）→ `safety_confirmation_required`；确认后 `force=true`
- 用户点站：`site_name` / `title_contains` / `page_url` 硬锁
- 用户点第 N：`pick_n=N`（1-based）
- 撤回：`run cancel`（可 `dry_run=true`；删文件 `delete_files=true`）

### 网盘转存

- 用户要网盘 → **先** `run nextfind`（或 `hdhive`），`media_type` + 先 dry
- **有 `warnings` 且 resources 空 → 不宣称可转存**
- 已有明文 115 链 → `run share115`
- 成功判据与排障 → `hdhive-115.md`

### 认片 / 有没有

- 模糊片名先 `run identify`，确认 `tmdb_id` 再 search/watch
- 有没有 → `run library`（`authority=nextfind`）；不要用 MP library_exists

### 订阅

- check：看 `state`（both / mp_only / nf_only / …）
- create：双写；`subscribe_partial` 须说明哪一侧失败

### 听歌 / 歌单

- 歌名 → `run listen`（`search_only=true` 只列；确认后 `button_index`）
- 歌单链接 → `run playlist` → 用户点下哪些再对 `queries[i]` 调 listen
- 无批量下载 op；Spotify 不支持

### 质量升级

- `dry_run`/`probe` 先；execute 先网盘再 PT；成功后再 `duplicates` 对比，确认后才删旧

## Agent 总则

1. 命中目录 → `media_ctl run ...`，勿手搓 MoviePilot JSON。  
2. 每次结果先读 `warnings` / `state` / `authority` / `error`。  
3. 未命中 → `call` / `ops`。  
4. 破坏性操作永远二次确认。  
5. 短链意图细节 → `link-intents.md`。
