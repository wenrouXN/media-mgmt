# 链接意图路由（agent 必读）

用户丢来抖音 / B 站 / TikTok 链接时：**不要只 parse**。先识别平台，再按用户说的意图选 op。

## 统一入口（优先）

```bash
python3 scripts/media_ctl.py call hybrid intent --param url='<链接>' --param intent='下载'
python3 scripts/media_ctl.py call hybrid parse --param url='<链接>'
python3 scripts/media_ctl.py call hybrid capabilities
```

`hybrid.intent` 会自动分流到 douyin / bilibili / tiktok。

## 平台识别

| URL 特征 | service |
|----------|---------|
| `douyin.com` / `v.douyin.com` / `iesdouyin.com` | douyin |
| `bilibili.com` / `b23.tv` | bilibili |
| `tiktok.com` | tiktok |
| 说不清 | hybrid.parse（7899 hybrid 接口） |

## 意图 → op

| 用户说法 | 优先 op |
|----------|---------|
| 解析 / 这是什么 / 信息 / 标题 | `parse` 或 `hybrid_video` |
| 下载 / 保存 / 下下来 | `download`（provider 落盘，带文件名） |
| 评论 | `comments`（抖音需 aweme_id；B 站需 bv_id，可从 url 抽） |
| 弹幕 | bilibili `danmaku`（先 parse 拿 cid） |
| 分 P | bilibili `parts` |
| 播放地址 / 清晰度 | bilibili `playurl` |
| 用户主页 / 博主 | `user_profile` / `get_sec_user_id` |
| 作品列表 | `user_posts` |
| 直播 | `live_*` / bilibili `live_room` |
| 任意上游接口 | `api --param path=/api/...` |

## 查能力

```bash
python3 scripts/media_ctl.py call douyin capabilities
python3 scripts/media_ctl.py call bilibili capabilities
python3 scripts/media_ctl.py call tiktok capabilities
python3 scripts/media_ctl.py ops douyin
```

## 原始 7899 全量（逃逸舱）

本地服务 OpenAPI：`http://localhost:7899/docs`（约 66 条）。

```bash
python3 scripts/media_ctl.py call douyin api \
  --param path=/api/douyin/web/fetch_user_post_videos \
  --param sec_user_id=MS4wLjAB...
```

## Agent 决策顺序

1. 从消息提取 URL  
2. `hybrid intent`（带用户原话当 intent）或按上表选 op  
3. 缺 id（aweme_id/bv_id/cid）→ 先 parse / get_aweme_id  
4. 仍不够 → `capabilities` 或 `api` 查上游  
