# HDHive → 115 转存

## 何时用

- 用户说：转存网盘 / 走 115 / HDHive / 云盘看
- 想要 4K / 网盘 STRM 链路，而不是本地 PT 下载

## 主入口（推荐）

```bash
python3 scripts/media_ctl.py run hdhive \
  --param tmdbid=849869 \
  --param title=格杀福顺 \
  --param media_type=movie \
  --param transfer=true
```

也可用关键词：

```bash
python3 scripts/media_ctl.py run hdhive --param q=格杀福顺 --param transfer=true
```

`watch` 默认 `prefer=auto` 也会先试 HDHive grab；**仅当用户明确要网盘**时，优先直接 `run hdhive`，不要先 PT。

## 成功判据

必须同时满足：

1. unlock 得到 115 share URL，且密码为**明文**（不是真实 `password=***`）
2. P115 插件返回 `code == 0`，或 msg 含「已经转存 / 已存在」

成功响应关键字段：

- `success: true`
- `result.transfer.code: 0`
- `result.transfer.msg: 转存成功`
- `result.transfer.data.media_info.title / tmdb_id`
- `result.transfer.data.save_parent.path`（常见 `/share/unsorted`）

## 失败与回落

| 现象 | 含义 | 动作 |
|------|------|------|
| `masked_or_invalid_share_password` | unlock 真的吐了 `***` | 重试 unlock；检查 CDP page target |
| `transfer_failed` + `访问码错误` | 密码错 / 被脱敏后传入 | 不要传 masked URL；重新 unlock |
| `transfer_failed` + `参数错误` | 常见：P115 插件加载失败/不兼容 | 查 MoviePilot 日志 `P115StrmHelper` / `TransferRenameBuild`；升/降插件 |
| `no_results` / `no_resources` | HDHive 无货 | 回落 PT：`watch --prefer pt` |
| watch 里 hdhive 失败 | 自动继续 PT | 看 `report.hdhive` + `note` |

## 硬规则（防绕路）

1. **禁止**把日志/摘要里的 `password=***` 当成真实密码再转存。输出脱敏 ≠ unlock 失败。
2. **禁止** `code=-1` 当成功。
3. **禁止**只跑 `hdhive search` 就声称已转存；必须 grab/transfer。
4. **禁止**在插件明确不兼容时反复改 `115.com`/`115cdn.com` URL 形状装忙。
5. 用户要网盘时，先 `run hdhive`；只有用户接受本地种 / hdhive 失败时才 PT。
6. PT 与 115 可能并存；成功转存后若用户不要重复本地任务，再 `run cancel`。

## 底层命令（排障）

```bash
# 搜 TMDB 页
python3 scripts/hdhive.py tmdb movie 849869
# 资源列表
python3 scripts/hdhive.py resources "https://hdhive.com/tmdb/movie/849869"
# 解锁（返回明文 115 链接）
python3 scripts/hdhive.py unlock "https://hdhive.com/resource/115/..."
# 一键
python3 scripts/hdhive_grab.py "格杀福顺" --select 1
# 已有明文分享链
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=明文'
```

Unlock 页面步骤：确定解锁 → 确认对话框确定 → 115 协议页确定 → 从 `location.href` / HTML 恢复明文密码。

## 插件兼容检查

MoviePilot 日志关键词：

```text
加载插件 p115strmhelper 失败
ChainEventType.TransferRenameBuild
Did you mean: TransferRename?
```

出现上述错误时：

1. 升级/回退 **P115StrmHelper** 到与当前 MoviePilot 匹配的版本
2. 重启/重载插件后，用任意已知 115 链 `run share115` 冒烟
3. 再跑 `run hdhive ... transfer=true`

## watch 协同

- `prefer=auto`：hdhive 成功 → 跳过 PT；失败 → PT
- `prefer=hdhive`：同上，但更偏向网盘
- `prefer=pt` / `--skip-hdhive`：不走网盘
- `--hdhive-only`：只报 hdhive 结果，不 PT

识别侧：仅 tmdb_id 时会电影/电视剧双试，避免电影空壳导致 PT 也 0 结果。
