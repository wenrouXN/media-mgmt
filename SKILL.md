---
name: media-mgmt
description: "跨服务媒体编排（认片/搜下/缺集诊断/115·HDHive 转存/短链/歌单/体检）。用户说要看、第N集、咋还没更新、库里有没有、转存网盘、听歌、解析歌单、丢抖音B站TikTok红果115链接时用。一律 media_ctl workflows；禁止手搓 MoviePilot JSON/mp_api 发明参数。"
---

# 媒体资源管理

**一条原则**：先定意图 → 只跑 **一个** 主 workflow → 不够再补第二枪。禁止扫射。

边界：自然语言编排用本 skill。只调 MP REST/CLI → `moviepilot-api`/`moviepilot-cli`。升级重启 MP → `moviepilot-update`。  
运行：skill root + 主机 `python3`（禁 per-skill venv）。**禁止先读 config.json**。

## 1. 决策表（先查这里）

| 用户意图 | 只跑这个 | 必参 | 默认第二枪（可选） |
|----------|----------|------|-------------------|
| 媒体挂了吗 | `run doctor` | — | `call moviepilot clients` |
| 这是哪部 / 先定 tmdb | `run identify` | title | 确认后再 watch/search |
| **我要看 / 第 N 集** | `run watch` | title；有集数加 episode | 先 `dry_run=true`；确认后去掉 dry_run（workflow 默认可下） |
| **咋还没有 / 缺集 / 有没有更新** | **`run updates`** | title 或 tmdbid | status / search / watch dry_run |
| 库里有没有 | `run library` | title 或 tmdbid | — |
| 重复留哪个 | `run duplicates` | title 或 tmdbid | 不自动删 |
| 转存网盘 / HDHive / 115 找源 | `run hdhive` | tmdbid+media_type 或 title；`transfer=true` | 失败再 `watch --prefer pt` |
| 已有 115 分享+明文密码 | `run share115` | share_url（禁 `password=***`） | — |
| **磁力离线 / CloudDrive 离线** | **`run offline`** | magnet 或 url；可选 save_path | 默认目录见 config `clouddrive.default_folder` |
| 下错了 / 取消下载 | `run cancel` | title/tmdbid/hash；可 episode | 先 `dry_run=true`；删文件 `delete_files=true` |
| 订阅 / 追更 | `run subscribe` / `run catchup` | title 或 tmdbid | catchup 执行要 `execute=true` |
| 质量升级 4K/中字 | `run upgrade` | title 或 tmdbid | 先 `dry_run=true` |
| 听歌 | `run listen` | q | 多选用 button_index；search_only=true 只列 |
| 公共歌单链接 | `run playlist` | url | 要下再对 queries 调 listen（无批量下） |
| 抖音/B站/TikTok/红果链接 | `run link` | url + intent | 细节 → `references/link-intents.md` |
| **盘点/片单/视频里提到的影视** | **先 parse** + 内容抽取 | url | 穷尽元数据；不够再下载+ASR/OCR（**禁止先整段下载**） |

未命中上表 → `media_ctl workflows` 或 `call <svc> <op>`；**不要**直接 mp_api 手搓。

## 2. 准确参数（效率+正确率）

```bash
# 高频骨架（skill root）
python3 scripts/media_ctl.py run <workflow> --param k=v
python3 scripts/media_ctl.py call <service> <op> --param k=v
```

**写参纪律**（少错）：

1. **已知 tmdb 就带上**：`--param tmdbid=296206`，并保留 `title` 作标题对齐（watch 靠标题消歧同 id 电影/剧）。
2. **电视剧第 N 集**：必须 `--param episode=N`；有季就 `season`。有 episode 时系统会偏 TV 认片。
3. **类型已知就写死**：`--param media_type=tv` 或 `movie`（hdhive 转存强烈建议带）。
4. **诊断默认不下**：`updates` / `library` / `identify` / `watch`+`dry_run=true`。
5. **真要下**：去掉 dry_run；用户未点头禁止当成功。风险种要 `--param force=true` 且用户确认。
5b. **PT 剧集质量默认**：优先 **4K/2160p + SDR**（有种）；没有则退到**有种的最高分辨率**（1080→720…）。电影默认 1080p。可 `--param resolution=… --param hdr_mode=…` 覆盖。
6. **网盘**：`run hdhive ... --param transfer=true`，不要先 PT。
7. **缺集**：**只先 updates**；禁止 identify+library+subscribe 连打。
8. **盘点/片单**：**先 parse 穷尽**（desc/hashtag/`chapter_list`）；不够再下载+ASR。禁止先整段下载。

### 复制即用

```bash
python3 scripts/media_ctl.py run updates --param title=片名 --param tmdbid=ID
python3 scripts/media_ctl.py run watch --param title=片名 --param tmdbid=ID --param episode=5 --param media_type=tv --param dry_run=true
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
5. HDHive 成功 = 明文 unlock **且** transfer `code==0`（或已转存）。`***` / 裸 `code=-1` 不算成功。
6. P115 `TransferRenameBuild`/恒「参数错误」→ 修插件，别改 URL 形状。
7. tmdb 认片：双类型试探 + 标题打分；空 shell=失败。detail → watch 实现已修，仍建议带 title+episode/media_type。
8. 完成看 `history/transfer`，不只 active downloads。
9. 破坏性操作二次确认。
10. **盘点/片单**：先 parse 穷尽元数据；不够再下载+ASR。禁止先整段下载。
11. **磁力离线**：`run offline` 成功 = CloudDrive `AddOfflineFiles` 成功，不是 qB active。路径须支持离线。
12. **PT 剧集选种**：`4K SDR 优先 → 否则有种最高质量`；零做种最后才考虑。

## 4. 失败怎么补一枪（别重开全套）

| 现象 | 下一枪 |
|------|--------|
| identify 多候选 | `identify --param select=N` 或用户确认 tmdb 后再 watch |
| watch `no_resources` | `run updates`；或 `run search --param episode=N`；新剧考虑 subscribe |
| watch 认片标题不对 | 补 `media_type` + 正确 title；重跑 dry_run |
| hdhive 失败要本地种 | `run watch --param prefer=pt`（或 skip_hdhive） |
| 转存密码/参数错误 | 见 `references/hdhive-115.md`，先 share115 冒烟 |
| 短链只解析不够 | `run link` + 明确 intent=下载/评论/… |
| 盘点只有 hashtag / 届次 chapter | 先声明 API 天花板 → 下载+ASR（可 OCR/评论交叉）→ identify；见 link-intents |
| 盘点误先整段下载 | 补跑 parse 归档字段；下次禁止倒序 |
| 磁力离线失败 | 查 `clouddrive health`；路径是否支持离线；见 clouddrive-offline |

## 5. 按需加载

| 需要 | 读 |
|------|----|
| 19 个剧本目录与场景策略 | `references/workflows.md` |
| 精确 CLI / REST / 环境坑 | `references/commands.md` |
| 网盘成功判据 / P115 | `references/hdhive-115.md` |
| **CloudDrive 磁力离线** | `references/clouddrive-offline.md` |
| **共享密钥 .credentials** | `references/credentials.md` |
| 短链意图表 / 红果 / **盘点内容抽取** | `references/link-intents.md` |

默认：**本文件决策表 + 一枪 run**。细节不够再开 ref。

## 6. 架构 / 依赖

`services/*.json` 目录 · `config.json` 凭证(gitignore) · `scripts/media_ctl.py` 控制面 · `media_mgmt_lib/`。  
`python3 -m pip install --user --break-system-packages -r requirements.txt`  
模板：`config.example.json`。
