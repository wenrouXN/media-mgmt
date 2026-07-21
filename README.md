# media-mgmt

**Status:** production OpenClaw skill · self-hosted  
默认中文｜[English](README.en.md)

跨服务**媒体编排**：认片、缺集、NextFind 网盘转存、PT 下载、短链盘点、歌单。  
**Agent 策略真源：`SKILL.md`**。控制面：`python3 scripts/media_ctl.py run|call|workflows|list`。

> 编排器，不是装完即用的媒体中心。  
> 网盘找源/转存/库有没有 = **NextFind OpenAPI only**。

## 快速开始

```bash
cd /path/to/media-mgmt
python3 -m pip install --user --break-system-packages -r requirements.txt
# 配置 workspace .credentials/ + 可选 config.json → 见 INSTALL.md
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run nextfind --param tmdbid=ID --param media_type=movie --param dry_run=true
python3 -m pytest -q
```

**完整装机 / 后端矩阵 / 凭据：** [`INSTALL.md`](INSTALL.md)

## 文档

| 需要 | 读 |
|------|-----|
| 装机与后端 | `INSTALL.md` |
| 意图路由 / 硬规则 | `SKILL.md` |
| 剧本参数 | `references/workflows.md` |
| CLI | `references/commands.md` |
| NextFind + 115 分享 | `references/nextfind-115.md` |
| 凭据 | `references/credentials.md` |
| 短链盘点 | `references/link-intents.md` |
| 磁力离线 | `references/clouddrive-offline.md` |

边界：自然语言编排 → 本 skill；裸 MP API → `moviepilot-api` / `moviepilot-cli`。

## 成功判据（摘要）

- 库有没有：`authority=nextfind` + `exists`
- 转存：`slug` + **`result.transfer.success`**（勿把顶层布尔 `transfer` 当结果）
- 诊断默认 `dry_run=true`

## 安全

仓库不含账号/Cookie/媒体。密钥在 workspace `.credentials/`。模板：`config.example.json`。

## 许可

MIT · `LICENSE`
