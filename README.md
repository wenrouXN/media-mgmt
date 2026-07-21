# media-mgmt

默认中文｜[English](README.en.md)

跨服务**媒体编排** skill：认片、缺集诊断、NextFind 网盘转存、PT 下载、短链解析、歌单与听歌。

- 对话策略：`SKILL.md`
- **安装与上游组件**：`INSTALL.md`
- 命令行：`python3 scripts/media_ctl.py run|call|workflows|list`

> 编排层，不是一体机。  
> 网盘找源 / 转存 / 库是否存在：以 **NextFind** 为准（见 [NextFind 介绍](https://wiki.nextemby.com/#/nextfind_intro)）。

## 快速开始

1. 按 [`INSTALL.md`](INSTALL.md) 部署 MoviePilot、NextFind 等，并配置 `.credentials/`  
2. 安装本 skill 依赖并验收：

```bash
cd /path/to/media-mgmt
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 scripts/media_ctl.py run doctor
```

## 文档索引

| 需要 | 文档 |
|------|------|
| 安装、依赖、验收 | [`INSTALL.md`](INSTALL.md) |
| 意图路由与规则 | `SKILL.md` |
| 工作流参数 | `references/workflows.md` |
| CLI 示例 | `references/commands.md` |
| 网盘与 115 分享 | `references/nextfind-115.md` |
| 凭据文件约定 | `references/credentials.md` |
| 短链 / 盘点 | `references/link-intents.md` |
| 磁力离线 | `references/clouddrive-offline.md` |

自然语言编排用本 skill；需要裸调 MoviePilot API 时用 `moviepilot-api` / `moviepilot-cli`。

## 安全

不提交密钥与媒体。模板：`config.example.json`。密钥仅放 workspace `.credentials/`。

## 许可

MIT · `LICENSE`
