# media-mgmt

默认中文｜[English](README.en.md)

**Agent / 人类入口：`SKILL.md`**（决策表 + §0 读结果 + 硬规则）。  
控制面：`python3 scripts/media_ctl.py run|call|workflows|list`。

本目录是实现与测试；策略真源不在本 README。

```bash
cd /path/to/media-mgmt
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run updates --param title=片名
python3 scripts/media_ctl.py run nextfind --param tmdbid=ID --param media_type=movie --param dry_run=true
```

| 需要 | 读 |
|------|-----|
| 意图路由 / 纪律 | `SKILL.md` |
| 21 剧本参数 | `references/workflows.md` |
| CLI 细节 | `references/commands.md` |
| 网盘 / 115 | `references/hdhive-115.md` |
| 凭据 | `references/credentials.md` |
| 短链 | `references/link-intents.md` |
| 磁力离线 | `references/clouddrive-offline.md` |

边界：自然语言编排 → 本 skill；只调 MP REST/CLI → `moviepilot-api` / `moviepilot-cli`。

> 仓库不含账号、Cookie、媒体文件。配置模板 `config.example.json`；密钥在 workspace `.credentials/`。
