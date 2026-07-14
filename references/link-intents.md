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
| 评论 | `comments`（需 aweme_id / bv_id） |
| 弹幕 | bilibili `danmaku`（先 parse 拿 cid） |
| 分 P / 播放地址 | `parts` / `playurl` |
| 主页 / 作品列表 | `user_profile` / `user_posts` |
| 直播 | `live_*` |
| 红果短剧 | hongguo `parse` / `info` / `list_episodes` / `download` |
| 任意上游 | `api --param path=/api/...` |

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
```

## Agent 顺序

1. 提取 URL  
2. `hybrid intent`（intent=用户原话）或上表选 op  
3. 缺 id → 先 parse  
4. 仍不够 → capabilities / raw api  
