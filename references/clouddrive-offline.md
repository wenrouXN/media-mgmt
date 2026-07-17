# CloudDrive 磁力离线

## 何时用

- 用户丢 **magnet** / 说「离线下载 / CloudDrive / 网盘离线」
- 已知磁力，要进 **115 等网盘离线**（不是本机 qB）

不要用本路径：

- 115 **分享转存** → `run hdhive` / `run share115`
- 本机 PT 下载 → `run watch --prefer pt`

## 配置

**Token** → workspace `.credentials/clouddrive.env`（见 `credentials.md`）  
**非密默认** → skill `config.json` → `clouddrive`：

| 字段 | 说明 |
|------|------|
| `url` 或 `host`+`port` | CloudDrive gRPC，本机常见 `http://127.0.0.1:19798` |
| `default_folder` | 默认离线目录 |
| `save_paths` | 可选路径列表 |
| `timeout` / `insecure` | 默认 30s / true |

`.credentials/clouddrive.env` 示例：

```bash
CLOUDDRIVE_URL=http://127.0.0.1:19798
CLOUDDRIVE_TOKEN=your-api-token
CLOUDDRIVE_DEFAULT_FOLDER=/115open/download
```

本机常用默认目录：`/115open/download`。

## 主入口

```bash
# 体检
python3 scripts/media_ctl.py call clouddrive health

# 离线（用默认目录）
python3 scripts/media_ctl.py run offline --param magnet='magnet:?xt=urn:btih:...'

# 指定目录
python3 scripts/media_ctl.py run offline \
  --param magnet='magnet:?xt=urn:btih:...' \
  --param save_path='/115open/download' \
  --param title=片名

# 底层 op
python3 scripts/media_ctl.py call clouddrive add_offline \
  --param urls='magnet:?xt=...' \
  --param to_folder='/115open/download'

python3 scripts/media_ctl.py call clouddrive list_offline \
  --param path='/115open/download'
```

## 成功判据

1. gRPC `AddOfflineFiles` 返回 `success=true`
2. `to_folder` / `save_path` 落在 **支持离线** 的网盘路径（CloudDrive `canOfflineDownload`）
3. 任务出现在 CloudDrive 离线列表 / 目标目录，**不是** qB active

失败机读错误（常见）：

| error | 含义 |
|-------|------|
| `auth_failed` | token/账密无效 |
| `path_not_offlineable` | 目录不支持离线 |
| `quota` | 离线配额不足 |
| `rpc_error` | 连不上 CloudDrive / 协议错误 |
| `missing_param` | 缺 magnet 或路径 |

## 与 HDHive 边界

| 能力 | workflow |
|------|----------|
| HDHive 解锁 115 **分享** → 转存 | `hdhive` / `share115` |
| **磁力** → CloudDrive 离线 | `offline` |
| PT 本机种 | `watch prefer=pt` |

## 依赖

```bash
python3 -m pip install --user --break-system-packages 'grpcio>=1.60' 'protobuf>=4.25'
```

实现：`media_mgmt_lib/providers/clouddrive/`（gRPC stub + client）。
