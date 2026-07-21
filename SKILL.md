---
name: media-mgmt
description: "跨服务媒体编排（认片/搜下/缺集诊断/NextFind网盘转存/短链/歌单/体检）。用户说要看、第N集、咋还没更新、库里有没有、转存网盘、听歌、解析歌单、丢抖音B站TikTok红果115链接时用。一律 media_ctl workflows；禁止手搓 MoviePilot JSON/mp_api 发明参数。"
---

# 媒体资源管理

**一条原则**：先定意图 → 只跑 **一个** 主 workflow → 不够再补第二枪。禁止扫射。

边界：自然语言编排用本 skill。只调 MP REST/CLI → `moviepilot-api`/`moviepilot-cli`。升级重启 MP → `moviepilot-update`。  
运行：skill root + 主机 `python3`（禁 per-skill venv）。**禁止先读 config.json**。

## 0. 读结果（强制 · 正确率）

每次 `run`/`call` 后必须读返回 JSON 的这些字段再下结论，**禁止只看 success=true**：

| 字段 | 含义 |
|------|------|
| `warnings` | 如 `nf_search_hint_but_resources_empty`：界面/搜索有提示但 **resources 空** → 勿盲 grab |
| `consistency` | NF 证据一致性；`ok=false` 时先说明再动作 |
| `state`（subscribe） | `both` / `mp_only` / `nf_only` / `none` / `nf_down` / `mp_down` |
| `resource_authority` | 可转存以 **`resources_op`** 为准，不是 search 提示数 |
| `authority`（library） | 有没有权威：`nextfind` 或 `nextfind_unavailable`（后者 `exists=null`，**禁止**用 MP 当有没有） |
| `error` | 命名错误：`lock_no_match` / `subscribe_partial` / `safety_confirmation_required` 等 |

## 1. 决策表（先查这里）

### 1A · 影视 / 库 / 网盘 / 订阅

| 用户意图 | 只跑这个 | 必参 | 默认第二枪（可选） |
|----------|----------|------|-------------------|
| 媒体挂了吗 / 体检 | `run doctor` | — | 看 `degraded` + `agent_must_read` |
| 这是哪部 / 先定 tmdb | `run identify` | title | 默认 NextFind，失败回落 MP |
| **我要看 / 第 N 集** | `run watch` | title；有集数加 episode | 先 `dry_run=true` |
| **咋还没有 / 缺集 / 有没有更新** | **`run updates`** | title 或 tmdbid | fill_plan dry；catchup 先 NF |
| 库里有没有 | `run library` | title 或 tmdbid | **有没有=NextFind only** |
| 重复留哪个 | `run duplicates` | title 或 tmdbid | 不自动删 |
| **转存网盘 / 115 找源** | **`run nextfind`** 或 `run hdhive` | tmdbid+media_type 或 title；先 dry | resources 空禁盲 grab |
| 已有 115 分享+明文密码 | `run share115` | share_url（禁 `password=***`） | — |
| **磁力离线** | **`run offline`** | magnet 或 url | CloudDrive 离线 |
| 下错了 / 取消 | `run cancel` | title/tmdbid/hash | dry_run 先；删文件 delete_files |
| 订阅 / 追更 | `run subscribe` / `run catchup` | title 或 tmdbid | 双写看 `state` |
| 搜资源 | `run search` | title 或 tmdbid | 默认 NF；读 `warnings` |
| 升画质 / 4K中字 | `run upgrade` | title 或 tmdbid | dry/probe 先 |

### 1B · 听歌 / 歌单 / 短链（非影视主链）

| 用户意图 | 只跑这个 | 必参 | 备注 |
|----------|----------|------|------|
| 听歌 | `run listen` | q | **禁止走 watch**；多选 button_index |
| 公共歌单 | `run playlist` | url | 只元数据；要对 queries 再 listen |
| 抖音/B站/TikTok/红果 | `run link` | url + intent | 见 link-intents |
| **盘点/片单里的影视** | 先 parse | url | 穷尽元数据后再 identify；**禁止先整段下载** |

未命中 → `media_ctl workflows` 或 `call <svc> <op>`；**不要**直接 mp_api 手搓。

## 2. 准确参数（效率+正确率）

```bash
# 高频骨架（skill root）
python3 scripts/media_ctl.py run <workflow> --param k=v
python3 scripts/media_ctl.py call <service> <op> --param k=v
```

**写参纪律**（少错）：

1. **已知 tmdb 就带上**：`--param tmdbid=296206`，并保留 `title` 作标题对齐（watch 靠标题消歧同 id 电影/剧）。
2. **电视剧第 N 集**：必须 `--param episode=N`；有季就 `season`。有 episode 时系统会偏 TV 认片。
3. **类型已知就写死**：`--param media_type=tv` 或 `movie`（网盘转存强烈建议带）。
4. **诊断默认不下**：`updates` / `library` / `identify` / `watch`+`dry_run=true`。
5. **真要下**：去掉 dry_run；用户未点头禁止当成功。风险种要 `--param force=true` 且用户确认。
5a. **用户点第 N 个**：必须 `pick_n=N`（**1-based**，第一个=1）。禁止把「第一个」写成 `pick_index=1`（那是 0-based 的第二个）。CLI 直接调 `scripts/watch.py` 才用 `--pick-index`（0-based）。
5a2. **用户点了具体站/标题**：真下时加锁——`site_name=彩虹岛`（别名 chdbits 可）或 `title_contains=关键词` 或 `page_url=…details?id=`。只给 pick_n 不够稳。
5b. **下载路径**：优先 MP 精确路径（media_type+分类）；若只有通用 base（如 `电影→/qbs/torrents/movies/`），**按 infer_category 拼二级目录**（如 `…/日韩电影/`）。用户显式 `save_path` 最高优先。
5c. **PT 质量默认**：
   - **剧集**：优先 **4K/2160p + SDR**（有种）；没有则**有种最高分辨率**。
   - **电影**：排除原盘（**允许 REMUX**）；优先**高质量特效字幕**；否则**最高质量中文**。
   - 覆盖：`resolution` / `hdr_mode` / `allow_disc=true` / `no_fx_sub=true` / `no_require_chinese=true`。
6. **网盘 = NextFind OpenAPI only**：`run nextfind` / `run hdhive`（别名）/ `watch` 网盘段；`prefer=nextfind|nf|hdhive|auto` 均可。转存以 **resources 有 slug** 为准。旧 pansou/Cloak 路径已退役。不要先 PT。
7. **缺集**：**只先 updates**；禁止 identify+library+subscribe 连打。
8. **盘点/片单**：**先 parse 穷尽**（desc/hashtag/`chapter_list`）；不够再下载+ASR。禁止先整段下载。

### 复制即用

```bash
python3 scripts/media_ctl.py run updates --param title=片名 --param tmdbid=ID
python3 scripts/media_ctl.py run watch --param title=片名 --param tmdbid=ID --param episode=5 --param media_type=tv --param dry_run=true
python3 scripts/media_ctl.py run nextfind --param tmdbid=ID --param title=片名 --param media_type=movie --param dry_run=true
python3 scripts/media_ctl.py run hdhive --param tmdbid=ID --param title=片名 --param media_type=movie --param transfer=true
python3 scripts/media_ctl.py run offline --param magnet='magnet:?xt=urn:btih:...' --param save_path='/115open/download/中转'
python3 scripts/media_ctl.py run link --param url='https://...' --param intent=下载
python3 scripts/media_ctl.py run doctor
```

更多命令 → `references/commands.md`。全剧本参数 → `references/workflows.md`。

## 3. 硬规则（违反=错用）

1. 不读 config.json；脚本自加载。密钥在 workspace `.credentials/*.env`，见 `references/credentials.md`。
2. 空下载列表 ≠ 无下载器 → `call moviepilot clients`。
3. 禁止残缺 download body / 发明 mp_api 参数（无 `search tmdb:ID` 位置参、无 mp_api `--episode`）。
4. 防误下：年+pubdate+seeders；`safety_confirmation_required` 须用户确认后 force。
5. **网盘成功判据**：`success` + 有 `slug`；真转存看 `transfer.success`（或 dry_run `would_transfer`）。share115 明文密码：`code==0` 或「已转存」。`password=***` 不算成功。**有 warnings 含 resources 空时禁止宣称可转存。**
6. P115 `TransferRenameBuild`/恒「参数错误」→ 修插件，别改 URL 形状（share115 路径）。
7. tmdb 认片：双类型试探 + 标题打分；空 shell=失败。detail → watch 实现已修，仍建议带 title+episode/media_type。
8. 完成看 `history/transfer`，不只 active downloads。
9. 破坏性操作二次确认。
10. **盘点/片单**：先 parse 穷尽元数据；不够再下载+ASR。禁止先整段下载。
11. **磁力离线**：`run offline` 成功 = CloudDrive `AddOfflineFiles` 成功，不是 qB active。路径须支持离线。
12. **PT 选种**：剧集 `4K SDR → 有种最高质量`；电影 `非原盘(允许REMUX) → 特效字幕 → 最高质量中文`；零做种最后才考虑。
13. **有没有 = NextFind only**；MP 只整理/转移记录。`authority=nextfind_unavailable` 时存在性未知，不说「库里有/没有」。

## 4. 失败怎么补一枪（别重开全套）

| 现象 | 下一枪 |
|------|--------|
| identify 多候选 | `identify --param select=N` 或用户确认 tmdb 后再 watch |
| watch `no_resources` | `run updates`；或 `run search --param episode=N`；新剧考虑 subscribe |
| search `warnings` 含 resources 空 | 勿 grab；可 `force_mp_search=true` 走 PT，或换片名/tmdb |
| watch 认片标题不对 | 补 `media_type` + 正确 title；重跑 dry_run |
| nextfind 网盘失败要本地种 | `run watch --param prefer=pt`（或 skip_hdhive） |
| 已有 115 分享转存失败 | 见 `references/hdhive-115.md`，核对明文 password + share115 |
| subscribe `state=mp_only`/`nf_only` | 补写失败侧；勿当 dual ok |
| 短链只解析不够 | `run link` + 明确 intent=下载/评论/… |
| 盘点只有 hashtag / 届次 chapter | 先声明 API 天花板 → 下载+ASR → identify；见 link-intents |
| 磁力离线失败 | 查 `clouddrive health`；路径是否支持离线；见 clouddrive-offline |

## 5. 按需加载

| 需要 | 读 |
|------|----|
| 21 个剧本目录与场景策略 | `references/workflows.md` |
| 精确 CLI / REST / 环境坑 | `references/commands.md` |
| 网盘 / NextFind / share115 | `references/hdhive-115.md` |
| NextFind 凭据 | `references/credentials.md`（nextfind.env） |
| **CloudDrive 磁力离线** | `references/clouddrive-offline.md` |
| **共享密钥 .credentials** | `references/credentials.md` |
| 短链意图表 / 红果 / **盘点内容抽取** | `references/link-intents.md` |

默认：**§0 读结果 + 决策表 + 一枪 run**。细节不够再开 ref。

## 6. 架构 / 依赖

`services/*.json` · `config.json`(gitignore) · `scripts/media_ctl.py` 控制面 · `media_mgmt_lib/`：

| 模块 | 职责 |
|------|------|
| `nf_evidence` / `result_gate` | 有没有权威、一致性 warning、grab 硬挡、agent_must_read |
| `watch_*` | stages / identify / search / actions / pipeline / **run**（无 subprocess） |
| `workflows/*` | 固定剧本；`watch`/`cancel` 直接调 lib |
| `scripts/watch.py` | 薄 CLI 接线 |

`python3 -m pip install --user --break-system-packages -r requirements.txt`  
模板：`config.example.json`。
