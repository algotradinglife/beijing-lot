# 澳客 `下载sp()` 修复与验证记录

日期：2026-07-16  
状态：`parser_repaired_live_history_blocked_non_production`

## 1. 结论

原工作簿中的 `下载sp()` 不是当前可运行的数据链：宏引用了已不存在的 `Sheet1`，
两处 `Call 下载sp` 均被注释，而且依赖固定等待、HTML 字符串位置和静默
`On Error Resume Next`。这会把页面改版、空页和 WAF 都吞掉，无法证明拿到的是
赛前 SP。

本次已将其修复为独立 Python 等价实现：

```text
src/okooo_prekick_sp.py
scripts/scrape_okooo_prekick_sp.py
```

原 772MB `beidan.xlsm` 没有被改写。Excel COM 只读探针打开大文件时卡住，相关探针
进程已终止；在不能稳定备份和保存前，不直接修改二进制 VBA 工程。

## 2. 修复内容

- 使用 DOM 解析 `tr[matchid]`，不再按裸字符串位置切割；
- 支持比分、半全场、亚盘和大小球四个旧宏路径；
- 保存完整历史行，不只留下初盘/即时/10h 三个覆盖值；
- 10h 规则固定为 `minutes_before_kickoff >= 600` 中最接近 600 的一行；
- 匿名 403/405 标记为 `auth_required_or_waf_blocked`，不再推断端点失效；
- 支持专用、持久化的已登录 Chrome profile，程序不读取或输出 Cookie；
- 保存原始 HTML、标准化 CSV、manifest 和 `SHA256SUMS`；
- manifest 固定 `execution_enabled=false`、`roi_authorized=false`；
- `/change/14/` 中 `14` 已确认为威廉希尔公司代码；新采集包固定记录
  `provider_name=william_hill`、`market_data_class=bookmaker_odds_history` 和
  `official_beidan_sp=false`。它是威廉希尔盘口历史，不能当作北单官方销售 SP。

## 3. 命令

最小实网探针：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py capture \
  --issue 26075 --match-limit 1 \
  --markets correct_score half_full --allow-partial
```

首次使用先打开专用登录窗口，由用户手工完成澳客登录：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py login
```

登录后关闭专用窗口，再复用该 profile 采集：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py capture \
  --issue 26075 --match-limit 1 \
  --markets correct_score half_full --allow-partial \
  --chrome-user-data-dir \
  /mnt/c/Users/hhusl/AppData/Local/OkoooCollectorProfile
```

检查浏览器保存的列表页：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py inspect-issue \
  PAGE.html --issue 26075
```

检查历史页并输出严格 10h 选择：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py inspect-history PAGE.html \
  --source-url SOURCE_URL
```

复验采集包：

```bash
.venv/bin/python scripts/scrape_okooo_prekick_sp.py verify BUNDLE_DIR
```

## 4. 实网验证

在 2026-07-16 23:04 CST，Windows Chrome 成功打开澳客 26075 单场列表页，DOM
解析得到 #1-#25 共 25 场；例如 #19 对应澳客 match_id `1324064`，主客队为
蒙特利尔/多伦多FC。

匿名临时 Chrome 随后对目标路径收到 HTTP 405。根据用户补充，这些页面需要登录，
因此该结果只说明匿名会话未获授权，不说明端点失效。对 #19 验证的四个旧宏路径均为
`405 / 2657 bytes`：

- `/cs/change/14/`；
- `/htft/change/14/`；
- `/ah/change/14/`；
- `/overunder/change/14/`。

当前最小审计包：

```text
results/data_collection/okooo_prekick_sp_v1/26075/
6cb3e58f094706358c50a77c2b76444f403dfccd965bb9b8af0e4fe11fb71c8b
```

其状态为 `partial_blocked`，`SHA256SUMS` 文件摘要为
`93dabc488b422162778fd4b99eabdb110a8bab6db47557a07c41dd27821d2a37`。
该包是匿名探针，只有未授权/WAF 原文和失败记录，`selected_10h_rows=0`，不会进入
研究或生产数据。
该不可变包生成时尚未确认代码 14 的语义，因此旧 manifest 保留原记录；后续已根据
用户提供的供应商资料确认为威廉希尔，不回写旧包。

## 5. 验收边界

已验证：列表解析、完整历史行解析、严格 10h 选择、箭头清洗、WAF 拒绝、不可变包
及篡改拒绝。

尚未验证：已登录澳客当前实页历史表的成功响应、澳客威廉希尔选项与北单官方选项逐项
一致性。因此该来源目前只能保持禁用，不能补写 26071 等历史 ROI 数据。
