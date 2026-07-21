# 网盘转存（NextFind OpenAPI）

## 何时用

- 用户说：转存网盘 / 走 115 / 云盘看 / NextFind
- 要 4K / STRM 网盘链路，而非本地 PT

## 主入口

```bash
# 推荐：一键 search → resources → pick → transfer
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=849869 \
  --param title=格杀福顺 \
  --param media_type=movie \
  --param dry_run=true

# 真转存去掉 dry_run
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=849869 \
  --param title=格杀福顺 \
  --param media_type=movie \
  --param transfer=true

# 别名（同 NextFind）
python3 scripts/media_ctl.py run hdhive --param q=格杀福顺 --param dry_run=true

# 分步
python3 scripts/media_ctl.py call nextfind search --param q=格杀福顺
python3 scripts/media_ctl.py call nextfind resources --param tmdbid=849869 --param media_type=movie
python3 scripts/media_ctl.py call nextfind transfer --param slug='...' --param dry_run=true
```

`watch` 默认 `prefer=auto` 会先试网盘（NextFind）；**明确要网盘时用 `run nextfind`**，不要先 PT。

凭据：workspace `.credentials/nextfind.env`（`NEXTFIND_BASE_URL` + `NEXTFIND_API_KEY`）。

## 成功判据

1. `success=true` 且有 `slug`（或 best_resource.slug）
2. 若 `transfer=true`：`transfer.success=true`（或 dry_run 的 `would_transfer`）
3. 字段：`path/source=nextfind_openapi`

## 已有明文 115 分享（不找源）

```bash
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=明文'
```

走 MoviePilot P115StrmHelper；**禁止** `password=***`。

## 失败与回落

| 现象 | 含义 | 动作 |
|------|------|------|
| `nextfind_not_configured` | 无密钥/URL | 补 `.credentials/nextfind.env` |
| `no_resources` / `no_search_results` | 无货 | `watch --prefer pt` |
| NextFind 健康失败 | OpenAPI 宕 | 修 nextfind 服务（8092） |
| 已有分享 `访问码错误` | 密码错/脱敏 | 重给明文 password |
| watch 内网盘失败 | 自动继续 PT | 看 `report.hdhive` / path |

## 硬规则

1. **网盘找源 = NextFind only**。pansou / Cloak 已退役。
2. 只 search 不算转存；必须 grab/transfer。
3. 已有明文 115 分享链 → `run share115`。
4. `scripts/hdhive.py` / `hdhive_grab.py` 已改为提示迁移，不再开浏览器。

## 与 watch 协同

- `prefer=auto|hdhive|nextfind`：网盘成功跳过 PT；失败继续 PT
- `prefer=pt` / `--skip-hdhive`：不走网盘
- `--hdhive-only`：只报网盘段
