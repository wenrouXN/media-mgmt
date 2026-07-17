# 链接意图路由

用户丢抖音 / B站 / TikTok / 红果链接：**不要只 parse**。先识别平台，再按意图选 op。

## 统一入口

```bash
python3 scripts/media_ctl.py call hybrid intent --param url='<链接>' --param intent='下载'
python3 scripts/media_ctl.py run link --param url='<链接>' --param intent=下载
python3 scripts/media_ctl.py call hybrid parse --param url='<链接>'
python3 scripts/media_ctl.py call hybrid capabilities
```

`hybrid.intent` 分流到 douyin / bilibili / tiktok / **hongguo**。

## 平台

| URL 特征 | service |
|----------|---------|
| douyin.com / v.douyin.com / iesdouyin.com | douyin |
| bilibili.com / b23.tv | bilibili |
| tiktok.com | tiktok |
| hongguoduanju.com / novelquickapp.com | hongguo |
| 说不清 | hybrid.parse |

## 意图 → op

| 用户说法 | 优先 op |
|----------|---------|
| 解析 / 这是什么 / 标题 | `parse` / `hybrid_video` |
| 下载 / 保存 | `download` |
| **盘点 / 片单 / 视频里提到的 / 口播清单** | **先 parse 穷尽字段**；不够再下载+ASR/OCR（见「内容抽取」） |
| 评论 | `comments`（需 aweme_id / bv_id） |
| 弹幕 | bilibili `danmaku`（先 parse 拿 cid） |
| 分 P / 播放地址 | `parts` / `playurl` |
| 主页 / 作品列表 | `user_profile` / `user_posts` |
| 直播 | `live_*` |
| 红果短剧 | hongguo `parse` / `info` / `list_episodes` / `download` |
| 任意上游 | `api --param path=/api/...` |

## 内容抽取（盘点 / 片单）

### API 天花板（实测，douyin_tiktok_api / hybrid）

douyin / hybrid **只有** 元数据 + 下载，**没有** 口播 ASR / 画面 OCR / 「盘点片单」专用接口。

| 字段 | 常见内容 | 能否当全片单 |
|------|----------|--------------|
| `desc` / `item_title` / `preview_title` | 标题 + 少量 hashtag | 否（通常只有几部 tag） |
| `text_extra[].hashtag_name` | 话题标签 | 否（常 1–5 个） |
| `chapter_list` | 章节：届次/段落名（如「2007年第十三届」） | **否**：`detail` 常空，**无剧名** |
| `series_info` / `mix_info` | 合集名、第 N 集 | 否（合集壳，不是本集清单） |
| `comments` | 观众贴的半截名单 | **辅助交叉**；不全、可掺视频未提的剧 |

用户要「视频里提到的所有影视」「盘点片单」「口播清单」时：

- **不要**假设 parse 结果 = 全量清单  
- **不要**因为「有 douyin API」就停在 hashtag  
- **不要**一上来整段 `intent=下载` 再回头看元数据  

### 默认路由（按顺序，一步够就停）

1. **先 parse（禁止跳过）**  
   ```bash
   python3 scripts/media_ctl.py call hybrid parse --param url='...'
   # 等价：run link intent=解析；或 fetch_one_video（aweme_id）
   ```  
   必扫字段：`desc` / `item_title` / `caption` / `text_extra` hashtag / `chapter_list`（含 `detail`）/ 其它文本。  
   - 若已是可用影视名列表（≥3 个明确片名，或 desc/detail 明显是完整盘点）→ **直接用**，不必下载。  
   - 若只有标题 + 少量 hashtag + 届次章节 → **明确说「API 天花板到这」**，再进下一步。

2. **可选：评论交叉（非权威）**  
   ```bash
   python3 scripts/media_ctl.py call douyin get_aweme_id --param url='...'
   python3 scripts/media_ctl.py call douyin comments --param aweme_id=...
   ```  
   仅作补漏/对照；**禁止**把评论名单当全量或 tmdb 真源。

3. **字段不够 → 下载 + 内容侧抽取**  
   - `run link` intent=下载（或复用已有本地 mp4）  
   - **优先 ASR**：抽音轨 → `voice-chat` ASR（口播盘点主源）  
   - ASR 仍缺 / 画面字卡为主：ffmpeg 抽帧 + `image` OCR  
     （帧文件放 **workspace 可访问目录**；`image` 工具常拒 `/tmp`）  
   - `chapter_list.timestamp` 可作抽帧锚点（届次切换点），**不能**替代片名列表。

4. **校准名单**  
   - 模糊片名用搜索核实（例：口播「凤凰男」→《假如生活欺骗了你》）  
   - 每部 `run identify`（带 `media_type`）拿 tmdb，再 `library` / `hdhive`  
   - **禁止** 用错名候选当成功（例：潜伏→恋爱潜伏、蜗居→蜗居宅急变）

5. **查库 / 转存 / 下载**  
   - 库里有的报已有  
   - 缺的优先 `run hdhive ... transfer=true`  
   - 影巢 `no_results` / `no_resources` → 问或按用户意图 `watch prefer=pt skip_hdhive`  
   - 老剧 PT 可能 `safety_confirmation_required`：用户明确要下后才 `force` + 合理 `pick_index`

### 不要做的事

- 盘点意图下 **先整段下载、后 parse**（顺序反了）  
- 把 1–5 个 hashtag 或空 `chapter_list.detail` 当成全盘点  
- 把评论半截名单当权威全量  
- 无本地文件盲调 OCR  
- 把 ASR 原文直接当已验证 tmdb 清单（必须 identify）  
- 影巢失败不告知就默认 PT（除非用户已说「用 PT」）

### 复制即用（盘点）

```bash
# 1) 元数据天花板
python3 scripts/media_ctl.py call hybrid parse --param url='https://v.douyin.com/...'

# 2) 不够再下 + ASR（agent 侧：ffmpeg 抽音轨 + voice_chat asr）
python3 scripts/media_ctl.py run link --param url='https://v.douyin.com/...' --param intent=下载

# 3) 每部校准后查库/转存
python3 scripts/media_ctl.py run identify --param title=片名 --param media_type=tv
python3 scripts/media_ctl.py run library --param title=片名 --param tmdbid=ID --param media_type=tv
python3 scripts/media_ctl.py run hdhive --param title=片名 --param tmdbid=ID --param media_type=tv --param transfer=true
```

## 红果短剧

| 项 | 说明 |
|----|------|
| 域名 | hongguoduanju.com、novelquickapp.com（短链 302→SSR） |
| 默认目录 | config `hongguo.download_dir`（例：`.../torrents/TV/短剧`） |
| 命名 | `{标题}-E{集号}.mp4` |
| 限制 | 公开 SSR；锁定集可能无完整 URL |

```bash
python3 scripts/media_ctl.py call hybrid intent --param url='https://novelquickapp.com/s/xxx' --param intent='下载'
python3 scripts/media_ctl.py call hongguo download --param url='...' --param episode=1
python3 scripts/hongguo.py download 'https://novelquickapp.com/s/xxx' --episode 1
```

## 查能力 / 逃逸舱

```bash
python3 scripts/media_ctl.py call douyin capabilities
python3 scripts/media_ctl.py call bilibili capabilities
python3 scripts/media_ctl.py call hongguo capabilities
python3 scripts/media_ctl.py ops douyin
# OpenAPI: http://localhost:7899/docs
python3 scripts/media_ctl.py call douyin api --param path=/api/douyin/web/fetch_user_post_videos --param sec_user_id=...
python3 scripts/media_ctl.py call douyin api --param path=/api/douyin/web/fetch_one_video --param aweme_id=...
```

## Agent 顺序

1. 提取 URL  
2. 普通意图：`hybrid intent`（intent=用户原话）或上表选 op  
3. 缺 id → 先 parse  
4. **盘点/片单类** → 「内容抽取」：parse 穷尽 →（可选评论）→ 不够再下载+ASR/OCR → identify → library/hdhive/pt  
5. 仍不够 → capabilities / raw api  
