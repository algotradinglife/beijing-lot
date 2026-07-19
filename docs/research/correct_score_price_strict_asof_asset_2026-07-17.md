# 正确比分赛前价格严格 as-of 资产

## 目标与边界

本链路为策略研究补充外部公司“正确比分”价格时间序列，使比分分布能够进行
EV/q、Top-1/2/3 深度筛选和严格收益回放。

固定边界：

- `execution_enabled=false`；
- `frontend_selectable=false`；
- `roi_authorized=false`；
- 不写正式策略、票据或 `release manifest`；
- 500 北单 `playid=42` 的停售后终值只可作结算或覆盖审计；
- 当前页面静态价格、无源时间戳历史卡片和赛后回补不得进入赛前价格输入；
- 26076 起做前瞻采集，历史期只按真实可得性回补，缺失必须保留。

## 数据源与标识

首选源为澳客外部公司正确比分变动页：

```text
https://www.okooo.com/soccer/match/{okooo_match_id}/cs/change/14/
```

公司代码 `14` 是澳客自己的 provider ID 空间，对应 William Hill；不能与
Nowscore 三合一接口的公司 ID 混用。每场同时保存：

- `provider=okooo`；
- `provider_match_id`：澳客比赛 ID；
- `nowscore_provider_match_id`：项目既有 Nowscore 稳定比赛 ID；
- `(issue, match_idx)`：跨源审计连接键；
- 源主客队、开赛文本和本地标准开赛时间。

当前 26076 实测：期次列表和比赛映射可抓，#1 映射为澳客 `1338614`；正确比分
历史直达页返回站点 405。同一浏览会话按“比赛页 → 比分页 → 历史页”导航可进入
登录检查，说明路由有效，但专用 profile 尚未完成账号登录。未登录/405 均按
`source_blocked` 或 `login_required` 保存，不回退到 500 终值。

### Nowscore 前向补充源

Nowscore 的“所有公司”1X2 页面可确认 William Hill 行，但该公司 ID 只属于
Euro 1X2 命名空间，不能据此把分析页波胆标为 William Hill。分析页当前公开的
波胆面板标题是 `Crown全指数`，生产适配固定使用：

- `provider=nowscore`；
- `bookmaker_key=crown`；
- `provider_company_id=3`（分析页公司命名空间）；
- 分析上下文：`live.nowscore.com/analysis/{provider_match_id}cn.html`；
- 波胆价格：`live.nowscore.com/analysis/odds/{provider_match_id}.htm`。

两个页面在同一捕获批次内保存并分别计算 SHA-256。分析页的“最后更新”保存为
`source_page_global_explicit_hkt`，其作用域明确为 `analysis_page_global`，不能冒充
波胆市场独立更新时间。赔率页提供 25 个精确比分。当前页面不提供“主胜其他、
平其他、客胜其他”三类尾部价格，因此只能形成
`incomplete_outcome_schema/missing_tail_outcomes` 前向观测，不能成为完整快照。

## 不可变采集包

代码入口：

```text
src/correct_score_price_history.py
scripts/manage_correct_score_price_history.py
```

目录：

```text
results/data_collection/correct_score_price_history_v1/<issue>/<capture_batch_id>/
```

每包包含原始页面、`mapping_inventory.csv`、`page_inventory.csv`、
`snapshots.csv`、`prices.csv`、`manifest.json` 与 `SHA256SUMS`。

追加键是 `capture_batch_id`，禁止按 `(issue, match_idx)` 覆盖旧包。原始响应、整页
哈希、原始行哈希和规范化 outcome schema 哈希都被 manifest 绑定。

## 完整性与时间戳等级

一条完整向量必须满足：

- 至少 18 个可识别比分结果；
- 主胜、平局、客胜三组均存在；
- `home_other`、`draw_other`、`away_other` 三类尾部项均存在；
- outcome code 唯一；
- 所有价格为有效十进制赔率；
- 源更新时间严格早于开赛时间。

时间戳等级从高到低：

1. `source_explicit_hkt`：源页面给出完整年月日时分秒；
2. `source_month_day_inferred_year`：源给月日时分，按与开赛时间最近的年份归一；
3. `source_relative_to_kickoff_derived`：仅有“赛前 N 分钟”，用标准开赛时间推导；
4. `source_time_unparseable`：不得进入严格回放。

所有等级都保留 `source_time_raw`。历史回补不能把抓取时间伪装成源更新时间。

## Segment 严格回放

回放目录：

```text
results/research/correct_score_price_segment_replay_v1/<issue>/segment_<n>/<replay_id>/
```

选择规则：

```text
latest complete pregame vector where snapshot_ts_hkt <= segment.freeze_at
```

输出包含 `selected_snapshots.csv`、`selected_prices.csv`、
`missing_matches.csv`、`manifest.json` 与 `SHA256SUMS`。每条记录保留
`minutes_to_kickoff` 和 `snapshot_staleness_minutes`。验证器拒绝 post-freeze
快照、capture 摘要不一致和文件篡改。

## 自动协调

```text
scripts/live_correct_score_price_refresh_loop.py
scripts/chrome_dump_via_cdp.mjs
ops/systemd/user/beidanlot-correct-score-price-refresh.service
```

- `prefreeze`：`freeze_at - 10min`；
- `freeze`：冻结点到冻结后 20 分钟；
- `prefreeze_observation`：冻结前 24 小时进入滚动观测，每 30 分钟一个幂等桶；
- 滚动协调 checkpoint 版本为 `correct_score_price_v2`；失败桶不覆盖，修复后以新版本重试；
- 每场最多抓取 3 次；只有 25 个精确比分价格全部有效才停止该场重试；
- 每次尝试的分析页、赔率页、错误、行数和 SHA-256 都保留在不可变包中；
- `operational_observation_complete=true` 只表示检查点已完成观测，用于阻止重复
  late recovery；它不改变严格 `status=partial`，也不授权 replay、EV 或 ROI；
- `late_recovery`：最长到冻结后 120 分钟；
- 源阻断重试退避 60 分钟；
- freeze/late recovery 抓取后自动基于已验证 capture 包生成 replay。
- replay 只能在 segment 的绝对 `freeze_at` 已发生后发布；提前构建会被拒绝。
- 运行日志和状态从文件资产派生；本链路不写共享 SQLite。

浏览器助手只在 `127.0.0.1` 打开临时 CDP 端口，并在同一会话依次访问比赛页、
比分页和历史页。专用 profile 登录后必须关闭可见窗口，避免与 systemd 采集进程争用。

运行状态标签页使用 `correct_score_price_history` 覆盖项。只有包含完整赛前比分向量的
SHA-256 包才计入覆盖；`source_blocked` 会显示告警。

## 26076 首次验收

首份单场源审计包：

```text
results/data_collection/correct_score_price_history_v1/26076/
0a54940c87c91ce2cd329c64cbf9861470bc47242abb8a9406e11cdce7969750/
```

- manifest/SHA-256：通过；
- 澳客/Nowscore 双 ID：已保存；
- 历史页：`source_blocked`；
- 完整快照：0；
- 执行和 ROI 授权：均为 false。

Segment #1 回放明确为 24/24 缺失，开赛倒计时覆盖 35–605 分钟，没有使用
500 静态或终值 SP 补洞。Segment #2 及后续由自动检查点继续前瞻采集。

2026-07-18 07:56 HKT 已在 segment #2 冻结前发布 Nowscore/Crown 全段观测包：

```text
results/data_collection/correct_score_price_history_v1/26076/
6e7df74e07673f440675f373455d297363f77b75ced0f98056323a9d35ee1bfe/
```

- 17/17 场有双原始页面；
- 17 条源时间明确的波胆快照、425 条精确比分价格；
- `SHA256SUMS` 摘要：
  `38fe2fe99daca04394e4ffe096dadeafac8a6757524191fe23a23dad8e018590`；
- 完整含尾部快照：0/17；
- 17 场均为 `missing_tail_outcomes`，不得进入 Top-k、EV/q 或 ROI。

滚动协调 v2 于 08:03 HKT 完成首个自动桶：

- segment #2：17 条快照、425 条精确比分价格，摘要
  `88c41ad7c2ff6b37f979c9b56c0972bdf99475d6d4571874166e55432995b419`；
- segment #3：22 条快照、546 条精确比分价格，摘要
  `2d1fd7acd8166379e778550e8c0bf4c8aac0d53999f2c044cb8f516cf1bdee08`；
- segment #3 理论 25 项覆盖应为 550 条，缺少的 4 个空价格按
  `missing_exact_score_outcomes` 处理，不能标记为全向量观测覆盖；
- 两包严格完整快照仍为 0，安全标志均为 false。

稳定性收口后的历史资产回归：

- Segment #2 `prefreeze` 与 `freeze` 的 17/17、425/425 包均被识别为
  operationally observed，不再重复 late recovery；
- Segment #3 的 22/22、546/550 包仍被判定为缺失，继续进入后续观测桶；
- Segment #4 的 15/15、375/375 包被识别为完整精确比分观测；
- Segment #2 freeze replay 的 17 场 `missing_reason` 均为
  `missing_tail_outcomes`，并同时保留 `source_timestamp_scope=analysis_page_global`。

收口验收单场 #64 的不可变包为
`b18a69eb6dfe80cd088ff265f96c580df6c2a6f06bfee0362ea71fcaaaca74d9`：
首次尝试即获得 25 项，`operational_observation_complete=true`、严格
`status=partial`，包摘要为
`6fa03ee8dd23ca64bf7750e48e48c3bc603d133008a0849f8012586a068d6ba4`。
验证器同时交叉校验 `attempts_json` 引用的每个原始文件及其声明哈希。

## 操作命令

```bash
.venv/bin/python scripts/manage_correct_score_price_history.py capture \
  --issue 26076 --segment-idx 2 --provider nowscore \
  --bookmaker-key crown --provider-company-id 3 --allow-partial

.venv/bin/python scripts/manage_correct_score_price_history.py replay \
  --issue 26076 --segment-idx 2 --capture-bundle <capture_dir>...

.venv/bin/python scripts/manage_correct_score_price_history.py verify <bundle_dir>
```

生产侧只发布研究资产和缺失审计。策略侧必须再次校验 replay manifest 与
`SHA256SUMS`，并保持当前非执行状态。
