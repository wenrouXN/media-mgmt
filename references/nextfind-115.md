# 网盘转存（NextFind）

产品说明与安装：[NextFind 介绍](https://wiki.nextemby.com/#/nextfind_intro)

## 何时用

- 要走网盘 / 115 / 云盘观看链路（而非本地 PT 下载）
- 查库是否已有、检索网盘资源并转存

## 凭据

在 workspace `.credentials/nextfind.env` 中配置：

- `NEXTFIND_BASE_URL`：你的 NextFind 访问地址  
- `NEXTFIND_API_KEY`：Agent OpenAPI 密钥  

详见 `INSTALL.md` 与 `references/credentials.md`。

## 命令示例

```bash
# 干跑：search → 选源 → 预览转存
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=<TMDB_ID> \
  --param title=<片名> \
  --param media_type=movie \
  --param dry_run=true

# 真转存
python3 scripts/media_ctl.py run nextfind \
  --param tmdbid=<TMDB_ID> \
  --param title=<片名> \
  --param media_type=movie \
  --param transfer=true

# 分步
python3 scripts/media_ctl.py call nextfind search --param q=<关键词>
python3 scripts/media_ctl.py call nextfind resources --param tmdbid=<TMDB_ID> --param media_type=movie
python3 scripts/media_ctl.py call nextfind transfer --param slug='...' --param dry_run=true
```

`watch` 默认会先尝试 NextFind；**明确只要网盘时优先 `run nextfind`**，不要先走 PT。

## 如何判断成功

1. 有资源标识：`slug`（或候选中的 slug）  
2. 若请求了转存：看 **转存结果** 是否成功（例如结果对象里的 success）；**不要**把请求参数里的 `transfer=true` 当成「已经转存完成」  
3. 干跑只有预览 / would_transfer，不代表文件已在盘上  

## 已有明文 115 分享（不找源）

```bash
python3 scripts/media_ctl.py run share115 --param share_url='https://115.com/s/xxx?password=真实密码'
```

经 MoviePilot 的 115 相关能力处理。请使用真实提取码，不要用 `***` 占位脱敏串。

## 失败时

| 情况 | 建议 |
|------|------|
| 未配置 / 鉴权失败 | 检查 `nextfind.env` 与 NextFind 是否开启 OpenAPI |
| 无资源 | 换关键词/TMDB，或改走 `watch` 的 PT 路径 |
| 服务不可达 | 按 [官方介绍](https://wiki.nextemby.com/#/nextfind_intro) 检查部署与地址 |
| 115 访问码错误 | 使用明文正确密码重试 |
| watch 网盘失败 | 默认会继续尝试 PT；可查看结果中的 nextfind 段 |

## 与 watch 的参数

- `prefer=auto|nextfind|nf`：网盘成功则跳过 PT  
- `prefer=pt` 或 `skip_nextfind=true`：不走网盘  
- `nextfind_only=true`：只跑网盘段  

## 规则摘要

1. 网盘找源与转存走 **NextFind**  
2. 仅 search 不算转存完成  
3. 已有明文 115 分享链用 `run share115`  
