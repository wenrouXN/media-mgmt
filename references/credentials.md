# 凭据说明

## 原则

- **密钥**放在 OpenClaw workspace 的 `.credentials/` 目录，勿提交 Git  
- skill 的 `config.json` 只放非密钥项（地址占位、超时、路径、bot 名等）  
- 不要把 token / api_key / session 写进记忆或对外截图  

## 文件一览

| 文件 | 用途 | 主要变量 |
|------|------|----------|
| `moviepilot.env` | MoviePilot REST | `MOVIEPILOT_BASE_URL`、`MOVIEPILOT_API_KEY` |
| `nextfind.env` | NextFind OpenAPI | `NEXTFIND_BASE_URL`、`NEXTFIND_API_KEY` |
| `clouddrive.env` | CloudDrive 离线 | `CLOUDDRIVE_URL`、`CLOUDDRIVE_TOKEN`、可选默认目录 |
| `telegram_music.env` | Telegram 听歌 | `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`、`TELEGRAM_SESSION_STRING` |
| `hdhive.txt` | **其他 skill**（如签到）用的登录信息，**不是** media-mgmt 网盘后端 | 按对应 skill 说明 |

路径查找顺序（由近到远）：

1. 环境变量 `MEDIA_MGMT_CREDENTIALS_DIR` / `OPENCLAW_CREDENTIALS_DIR`  
2. 本 skill 目录下的 `.credentials/`  
3. 向上查找 workspace `.credentials/`  

密钥字段优先级：进程环境变量 → 凭据文件 →（不推荐）config.json 遗留字段。

## 示例模板（请改成你的地址与密钥）

```bash
# moviepilot.env
MOVIEPILOT_BASE_URL=http://127.0.0.1:<MoviePilot端口>
MOVIEPILOT_API_KEY=***

# nextfind.env
NEXTFIND_BASE_URL=http://127.0.0.1:<NextFind地址>
NEXTFIND_API_KEY=***

# clouddrive.env
CLOUDDRIVE_URL=http://127.0.0.1:<CloudDrive端口>
CLOUDDRIVE_TOKEN=***
CLOUDDRIVE_DEFAULT_FOLDER=/path/you/use

# telegram_music.env
TELEGRAM_API_ID=***
TELEGRAM_API_HASH=***
TELEGRAM_SESSION_STRING=***
```

NextFind 产品说明：[官方介绍](https://wiki.nextemby.com/#/nextfind_intro)

## 权限与检查

```bash
chmod 600 /path/to/workspace/.credentials/*.env

python3 scripts/media_ctl.py call moviepilot health
python3 scripts/media_ctl.py call nextfind health
# 若已配置：
python3 scripts/media_ctl.py call clouddrive health
```

实现细节见 `media_mgmt_lib/credentials.py`。完整装机流程见 `INSTALL.md`。
