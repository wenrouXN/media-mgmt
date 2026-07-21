# Credentials（共享密钥）

## 原则

- **密钥**放 workspace `.credentials/`，跨 skill/agent 复用
- skill `config.json` 只放非密默认（路径、超时、bot 名、profile）
- 禁止把 token / api_key / session 写进 git 或记忆层

## 文件（KEY=value，chmod 600）

| 文件 | 用途 | 关键键 |
|------|------|--------|
| `moviepilot.env` | MoviePilot REST | `MOVIEPILOT_API_KEY`（兼 `API_KEY`）、可选 `MOVIEPILOT_BASE_URL` |
| `clouddrive.env` | CloudDrive 离线 | `CLOUDDRIVE_TOKEN`（兼 `TOKEN`）、可选 URL/DEFAULT_FOLDER |
| `telegram_music.env` | TG 音乐 | `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION_STRING` |
| `hdhive.txt` | HDHive 登录（**checkin-manager 等**，非 media-mgmt 网盘） | `email` / `password` |
| `nextfind.env` | NextFind OpenAPI（网盘找源/转存） | `NEXTFIND_API_KEY`、可选 `NEXTFIND_BASE_URL` |

路径解析顺序：

1. `MEDIA_MGMT_CREDENTIALS_DIR` / `OPENCLAW_CREDENTIALS_DIR`
2. skill 内 `.credentials/`
3. 向上找 workspace `.credentials/`
4. 本机 main workspace 固定路径

## 注入优先级（secret 字段）

1. 进程环境变量  
2. `.credentials` 对应文件  
3. skill `config.json` 遗留值（兼容，不推荐）

`load_json_config()` 自动 `inject_secrets()`。

## 示例

```bash
# workspace/.credentials/moviepilot.env
MOVIEPILOT_BASE_URL=http://127.0.0.1:3002
MOVIEPILOT_API_KEY=your-key

# workspace/.credentials/clouddrive.env
CLOUDDRIVE_URL=http://127.0.0.1:19798
CLOUDDRIVE_TOKEN=your-api-token
CLOUDDRIVE_DEFAULT_FOLDER=/115open/download/中转

# workspace/.credentials/telegram_music.env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...
TELEGRAM_SESSION_STRING=...

# workspace/.credentials/nextfind.env
NEXTFIND_BASE_URL=http://127.0.0.1:8092
NEXTFIND_API_KEY=your-openapi-key
```

## 运维

```bash
chmod 600 ~/.…/workspace/.credentials/*.env
# 体检（密钥从 credentials 注入，config.json 可无 api_key）
python3 scripts/media_ctl.py call moviepilot health
python3 scripts/media_ctl.py call clouddrive health
python3 scripts/media_ctl.py call nextfind health
```

实现：`media_mgmt_lib/credentials.py`。
