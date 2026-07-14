# HDHive → 115 转存

## 何时用

- 用户说：转存网盘 / 走 115 / HDHive / 云盘看
- 要 4K / STRM 网盘链路，而非本地 PT

## 主入口

```bash
python3 scripts/media_ctl.py run hdhive \
  --param tmdbid=849869 \
  --param title=格杀福顺 \
  --param media_type=movie \
  --param transfer=true

# 或关键词
python3 scripts/media_ctl.py run hdhive --param q=格杀福顺 --param transfer=true

# 已有明文 115 链
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=明文'
```

`watch` 默认 `prefer=auto` 会先试 HDHive；**明确要网盘时直接 `run hdhive`**，不要先 PT。

## 成功判据（同时满足）

1. unlock 得到 115 share URL，密码为**明文**（不是真实 `password=***`）
2. P115 返回 `code == 0`，或 msg 含「已经转存 / 已存在」

关键字段：`success=true`、`result.transfer.code=0`、`save_parent.path`（常见 `/share/unsorted`）。

## 失败与回落

| 现象 | 含义 | 动作 |
|------|------|------|
| `masked_or_invalid_share_password` | unlock 真吐 `***` | 重试 unlock；检查 CDP page target |
| `访问码错误` | 密码错/脱敏后传入 | 重新 unlock；禁止传 masked |
| `参数错误` | 多为 P115 插件不兼容 | 查 MP 日志；升/降 P115StrmHelper |
| `no_results` / `no_resources` | 无货 | 回落 `watch --prefer pt` |
| watch 内 hdhive 失败 | 自动继续 PT | 看 `report.hdhive` |

## 硬规则

1. 日志里的 `password=***` 可能是脱敏展示，≠ unlock 失败；以 transfer `code` 为准。
2. `code=-1` 不算成功（「已经转存」类文案除外）。
3. 只 search 不算转存；必须 grab/transfer。
4. 插件不兼容时禁止反复改 `115.com`/`115cdn.com` URL 形状。
5. 成功转存后若不要重复本地任务 → `run cancel`。

## 排障 CLI

```bash
python3 scripts/hdhive.py tmdb movie 849869
python3 scripts/hdhive.py resources "https://hdhive.com/tmdb/movie/849869"
python3 scripts/hdhive.py unlock "https://hdhive.com/resource/115/..."
python3 scripts/hdhive_grab.py "格杀福顺" --select 1
```

Unlock 页：确定解锁 → 确认 → 115 协议确定 → `location.href` / HTML 取明文密码。

## 插件兼容

MP 日志：

```text
加载插件 p115strmhelper 失败
ChainEventType.TransferRenameBuild
Did you mean: TransferRename?
```

处理：匹配版本 P115StrmHelper → 重载 → `run share115` 冒烟 → 再 `run hdhive`。

## 与 watch 协同

- `prefer=auto|hdhive`：成功跳过 PT；失败继续 PT
- `prefer=pt` / `--skip-hdhive`：不走网盘
- `--hdhive-only`：只报 hdhive
- 仅 tmdb_id 时电影/剧双试，避免空壳导致 0 结果
