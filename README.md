# media-mgmt

默认中文｜[English](README.en.md)

跨服务媒体编排 Skill：MoviePilot + HDHive/115 + 短视频 + 音乐 + 歌单 + doctor。  
Agent 入口是 **`SKILL.md` + `scripts/media_ctl.py`**，不是零散 CLI 手册。

> 仓库只提供脚本与工作流，不含账号、Cookie、session、媒体文件或第三方访问权限。

## 何时用

| 用户说法 | workflow |
|----------|----------|
| 我要看 / 第 N 集 | `run watch` |
| 咋还没有 / 缺集 / 有没有更新 | `run updates` |
| 库里有没有 | `run library` |
| 转存网盘 / 115 / HDHive | `run hdhive` |
| 抖音/B站/TikTok/红果链接 | `run link` |
| 听歌 | `run listen` |
| 公共歌单链接 | `run playlist` |
| 媒体挂了吗 | `run doctor` |

与 `moviepilot-cli` / `moviepilot-api` 的边界：自然语言编排走本 skill；只调 MP 本体 API 用后者。

## 控制面（优先）

```bash
cd /path/to/media-mgmt
python3 scripts/media_ctl.py list
python3 scripts/media_ctl.py workflows
python3 scripts/media_ctl.py run doctor
python3 scripts/media_ctl.py run watch --param title=片名 --param episode=5 --param dry_run=true
python3 scripts/media_ctl.py run updates --param title=片名
python3 scripts/media_ctl.py run hdhive --param tmdbid=ID --param media_type=movie --param transfer=true
```

- 固定场景 → `run <workflow>`
- 自由组合 → `call <service> <op>`
- 策略与参数 → `references/workflows.md`
- 精确命令 → `references/commands.md`

## 能力概览

- **MoviePilot**：认片、搜下、订阅、库内缺集、档期、追更、撤回、质量升级
- **HDHive → 115**：解锁分享并转存（P115StrmHelper）
- **短视频**：抖音 / B站 / TikTok / 红果（hybrid intent）
- **音乐**：Telegram bot 听/下；网易云/QQ/酷我/酷狗歌单解析（只元数据+queries）
- **盘搜 / 下载器**：经 catalog ops；QB/TR 经 MoviePilot 探活

## 目录

```text
SKILL.md                 Agent 入口（保持精简）
config.example.json      配置模板
references/              按需加载的策略与命令
  workflows.md
  commands.md
  hdhive-115.md
  link-intents.md
scripts/media_ctl.py     控制面
scripts/watch.py         看剧流水线
scripts/mp_api.py        MoviePilot REST 底层
media_mgmt_lib/          catalog + ops + workflows + providers
services/*.json          服务目录（无密钥）
tests/                   pytest
```

## 配置

```bash
cp config.example.json config.json
# 编辑本机 base_url / api_key / cloak / telegram 等
```

`config.json` 已被 gitignore。完整字段说明见 `config.example.json` 注释式键名；sections：

`pansou` · `moviepilot` · `hdhive` · `telegram_music` · `douyin` · `bilibili` · `playlist` · `hongguo`

## 依赖

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
```

Python 3.11+。按需外部服务：MoviePilot(+P115)、CloakBrowser profile、7899 短视频 API、Telegram session、盘搜。

## 安装到 Agent

```bash
git clone https://github.com/wenrouXN/media-mgmt.git media-mgmt
cd media-mgmt && cp config.example.json config.json
```

加载条件：用户要看/下载/听/转存/缺集诊断/短链处理时触发 `media-mgmt`。  
最小验证：`python3 scripts/media_ctl.py workflows` 有输出；`pytest -q` 通过。

## License

MIT。见 [LICENSE](LICENSE)。
