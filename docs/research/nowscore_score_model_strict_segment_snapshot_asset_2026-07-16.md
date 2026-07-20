# Nowscore/Titan 比分模型严格分段快照资产

日期：2026-07-16
状态：`research_snapshot_complete_execution_disabled`

## 1. 目标与边界

为比分模型回放保存 Euro 1X2 和 O/U 的追加式历史序列，并以
`segment_decision_windows.freeze_at` 为唯一绝对决策时点，选择每场每市场在冻结前
最后一条完整赛前快照。

本资产固定：

- `execution_enabled=false`；
- `roi_authorized=false`；
- `formal_strategy_input=false`；
- `ticket_output_enabled=false`；
- 禁止读取或混入 500 历史回补的中奖项终值。

抓取发生在赛后，但源记录自带历史时间，因此分类为
`third_party_timestamped_archive`，不能表述为当时由本地实时采集器观测到的 forward
快照。

## 2. Excel VBA 来源审计

原 `beidan.xlsm` 的主更新宏不是从澳客填充 Euro/O/U：

| 市场 | Excel VBA 实际端点 | 说明 |
| --- | --- | --- |
| Euro 1X2 | `https://1x2d.titan007.com/{provider_match_id}.js` | 多公司完整变化序列 |
| O/U | `https://m.titan007.com/HandicapDataInterface.ashx` | `oddskind=1` 表示大小球 |
| 比赛映射 | `cp.nowscore.com` | 提供稳定 Nowscore/Titan provider match ID |

Titan007 与 Nowscore/捷报属于同一数据体系，但接口编号空间不同。首个验收源固定为
威廉希尔：

- 稳定内部键：`bookmaker_key=william_hill`；
- Euro JS provider company ID：`115`；
- Titan O/U `companyid`：`9`；
- 澳客旧 `/change/14/` 中的 `14` 也是威廉希尔，但属于澳客编号空间，不能与前两者
  直接比较或替换。

旧宏 `下载sp()` 的澳客路径用于比分、半全场、亚盘和大小球，并且在主下载流程中的
两处调用均已被注释。它不是当前 Excel Euro/O/U 宽表的主来源。

## 3. 不可变采集资产

入口：

```text
src/nowscore_score_model_history.py
scripts/manage_nowscore_score_model_history.py
```

每次 capture 生成唯一 `capture_batch_id` 目录，禁止按 `(issue, match_idx)` 覆盖：

```text
results/data_collection/nowscore_score_model_history_v1/<issue>/<capture_batch_id>/
  raw/*.js
  raw/*.json
  snapshots.csv
  page_inventory.csv
  manifest.json
  SHA256SUMS
```

每条快照至少保存：issue、match_idx、provider match ID、bookmaker key、源公司编号、
市场、源时间、抓取时间、完整赔率向量、O/U 盘口线、源 URL、完整性、phase、原始载荷
SHA-256、原始记录 SHA-256、时间戳规范化结果和 capture batch ID。

O/U 请求先访问 Nowscore 三合一页面建立会话，再调用 Excel 同源 Titan 接口；直接匿名
调用出现 WAF 文本时必须拒绝，不能按空历史处理。

## 4. 严格回放

回放按 `(match_idx, bookmaker_key, market_key)` 执行：

1. 验证 capture bundle 全部 SHA-256；
2. 仅保留 `phase=pregame` 且 `complete=1` 的记录；
3. 仅保留 `snapshot_ts_hkt <= freeze_at_hkt`；
4. 选择时间最大的记录；
5. 输出 `minutes_to_kickoff`、`snapshot_staleness_minutes`、规范化结果和 raw 追溯链；
6. 无候选时输出 `missing_legs.csv`，区分历史缺失、全部晚于冻结、仅滚球、仅不完整、
   冻结不早于开赛等原因。

verify 除目录哈希外，还会重新验证 replay 引用的 capture bundle 摘要、raw 文件摘要和
`snapshot_ts <= freeze_at`。因此网页当前可查询但未落入哈希 capture bundle 的数据，
不能进入回放。

## 5. 26074 首次验收

采集包：

```text
results/data_collection/nowscore_score_model_history_v1/26074/
d7426bc9842e9f2c41e88f65a363c4dc56829df3aed9dcdf48819e9dfa8d9044
```

- 29 场，Euro/O/U 共 58/58 个原始响应成功；
- 2676 条历史记录，其中 1060 条完整赛前记录；
- `SHA256SUMS` 摘要：
  `4097ffa0f9e1fc149b4b4b5ba419b3503696cebd4ca9a520410b390f05ddfd4c`。

| Segment | freeze_at HKT | 场次 | 选中腿 | 缺失 | 距开赛范围 |
| --- | --- | ---: | ---: | ---: | ---: |
| #3 | 2026-07-12 17:55 | 15 | 30/30 | 0 | 35–305 分钟 |
| #4 | 2026-07-13 00:40 | 14 | 28/28 | 0 | 35–1850 分钟 |

验收复现了此前报告的倒计时范围，但这次结论建立在本地不可变 raw 资产上，而不是页面
可用性上。

canonical replay：

```text
results/research/nowscore_score_model_segment_replay_v1/26074/segment_3/
522f17f756a22f7d4f4abf30c3f2506129fb6326712565041c72e8ace8c9a24f

results/research/nowscore_score_model_segment_replay_v1/26074/segment_4/
9ee47c2734b22f8e95f727867ce53e2bcb27755580149919c50bf3506156c606
```

两包 `SHA256SUMS` 摘要分别为
`540ecd379d404c92464d178f91733431959206391c1a941ed46d5b099a0cd140` 和
`c9b58559555825fa995fabdff17182c3b3e797e83007557827fc2260b6b6031c`。

快照陈旧度仍需作为模型质量信号：

| Segment | 市场 | 中位陈旧度 | 最大陈旧度 | 超过 24h |
| --- | --- | ---: | ---: | ---: |
| #3 | Euro | 18 分钟 | 1311 分钟 | 0 |
| #3 | O/U | 99.383 分钟 | 5867.233 分钟 | 1 |
| #4 | Euro | 115 分钟 | 5404 分钟 | 3 |
| #4 | O/U | 81.583 分钟 | 2754.2 分钟 | 3 |

因此“零缺失”不代表数据同样成熟。后续模型实验必须报告陈旧度分桶，不能静默把四天前
的最后完整报价与冻结前数分钟的报价等权处理。

## 6. 命令

```bash
.venv/bin/python scripts/manage_nowscore_score_model_history.py capture \
  --issue 26074 --segment-idx 3 4

.venv/bin/python scripts/manage_nowscore_score_model_history.py replay \
  --issue 26074 --segment-idx 3 --capture-bundle CAPTURE_DIR

.venv/bin/python scripts/manage_nowscore_score_model_history.py verify BUNDLE_DIR
```

## 7. 前向采集运行方式

生产侧只负责发布研究资产，不把 Euro/O/U 写入正式决策、票据或发布物。独立进程
`live_score_model_odds_refresh_loop.py` 每分钟检查当前期的 segment 窗口，但只在两个
checkpoint 发起网络抓取：

- `prefreeze`：`freeze_at - 10 分钟`至冻结前；
- `freeze`：冻结时点起，并允许在错过窗口后执行一次 `late_recovery`。

checkpoint ID 由期次、segment、phase 和资产版本稳定组成。完整包永久幂等跳过；部分包
或失败请求默认退避 15 分钟再重试，避免上游异常时不断生成部分资产。每次尝试追加到
`collector_runs.jsonl`，不会覆盖已有 raw、manifest 或哈希。

有效响应明确证明指定 provider 没有该场市场时，页面记为 `unavailable`，原始响应及摘要
仍须保存。若其余页面均成功，采集 checkpoint 以 `complete_with_exclusions` 收口；排除场
不会计入市场覆盖率，严格回放仍输出对应 missing leg。WAF、HTTP 错误、解析异常和响应
缺失不能降级成排除项，只能保持 `partial` 并按退避策略重试。

运行状态中的 Euro/O/U 覆盖率仅统计已经落盘、页面抓取成功且至少存在一条完整赛前
记录的场次。网页当前能打开、接口当前有数据或 500 结算已回补，都不能替代该口径。

systemd 用户服务：

```text
beidanlot-score-model-odds-refresh.service
```

手动单轮审计：

```bash
.venv/bin/python scripts/live_score_model_odds_refresh_loop.py --issue current --once
```
