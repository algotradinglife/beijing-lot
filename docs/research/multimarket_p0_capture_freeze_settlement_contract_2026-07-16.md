# 北单多玩法 P0 采集、冻结与结算契约

日期：2026-07-16
状态：`production_collection_ready_research_roi_blocked`

## 1. 范围

P0 目标玩法固定为：

- 总进球 `playid=40`：`0,1,2,3,4,5,6,7+` 八项；
- 比分 `playid=42`：25 项精确比分及胜/平/负其他。

P0 只完善数据事实、研究冻结输入和结算真值，不改变正式决策链、票据、预算、
API 策略选择或 release manifest。

## 2. 不可变采集批次

每次目标玩法 HTTP 抓取发布一个目录：

```text
results/data_collection/multimarket_sp_capture_v1/<issue>/<batch_id>/
  raw.xml
  manifest.json
  SHA256SUMS
```

`batch_id` 由 issue、playid、本地 UTC 抓取时间和原始 payload SHA-256 计算。
目录在同一父目录中构造、校验后原子 rename；发布后不覆盖、不删除、不重用。
批次表行和结果项明细在同一个 SQLite savepoint 中提交；任一明细写入失败时，数据库
批次和明细一起回滚，失败抓取只进入 `fetch_log`。schema migration 在发布事务之前完成，
避免 SQLite DDL 隐式提交破坏该边界。

数据库表：

- `market_sp_capture_batches`：批次、来源、双时钟、payload/hash、行数和分类摘要；
- `live_market_sp_snapshots`：每个结果项追加 batch_id、来源、双时钟、销售状态、
  可过关元数据和采集分类。

双时钟语义：

- `fetched_at_utc`：本地实际收到响应的 UTC 时间，带 `+00:00`；
- `source_updated_at_hkt`：上游 XML 声明的更新时间，带 `+08:00`。

历史旧行保持 `legacy_unclassified`，不能追认为 forward。新行分类：

| 分类 | 含义 | ROI 可用 |
| --- | --- | --- |
| `forward_complete_open` | 双时钟早于停售、全向量完整、同轮页面未禁售 | 否，仍缺过关/限额确认 |
| `forward_complete_sale_unknown` | 向量完整但销售状态不足 | 否 |
| `forward_incomplete_rejected` | 售前但缺选项或无效 SP | 否 |
| `terminal_backfill_exploratory_only` | 售后只有中奖项终值 | 否 |
| `post_cutoff_static_exploratory_only` | 售后静态页面仍有多个值 | 否 |

当前 `parlay_allowed`、`parlay_modes_json` 和 `stake_limit_json` 保持 unknown/空值，
禁止从“有赔率”推断为“可过关”。

## 3. as-of 冻结口径

`kickoff - 10h` 不是金标准，只是便于跨场、跨期横向比较的固定偏移研究切片。
每期实际下注采用分段决策，因此生产回放的首选口径是 `segment_freeze`：同一段使用
同一个人工或自动冻结时间，对段内每场分别计算 `minutes_to_kickoff`。开赛时间不同，
倒计时自然不同，但所有输入都必须在共同决策时点可见。

允许的冻结模式：

| 模式 | as-of 定义 | 用途 |
| --- | --- | --- |
| `segment_freeze` | `segment_decision_windows.manual_frozen_at`，否则 `freeze_at` | 业务决策回放，默认优先 |
| `explicit_asof` | 指定绝对北京时间 | 恢复有证据的历史决策时点 |
| `standardized_offset` | 每场 `kickoff_hkt - Nh` | 研究横向比较；10h 是可修改参数 |

每条选中记录必须同时保存 `asof_hkt`、`kickoff_hkt`、`minutes_to_kickoff`、
`source_ts_hkt`、`source_age_minutes` 和 `selection_mode`。原始全序列不可回写，禁止
使用 as-of 之后的记录。没有真实 segment 冻结记录时，不得为历史期次虚构冻结时点。
生成命令必须显式指定冻结模式，不提供隐式 10h 默认值。

### 3.1 原 P0 10h 冻结命令

命令：

```bash
.venv/bin/python scripts/manage_multimarket_p0.py freeze-10h \
  --issue ISSUE --output-dir OUTPUT_DIR
```

真实 kickoff 由停售时间和捷报 kickoff clock 组合，选择停售后 0–6 小时内最近的
时间，避免跨午夜日期错误。该命令的目标时点为 `kickoff_hkt - 10h`，只代表
`standardized_offset` 的一个固定参数，不代表实际分段下注时点。

单场单玩法只有同时满足以下条件才进入冻结：

1. `fetched_at_utc` 和 `source_updated_at_hkt` 都不晚于目标时点；
2. 结果项数量严格为 8 或 25，所有 SP 均大于 1；
3. `sale_status=open`；
4. 分类严格为 `forward_complete_open`；
5. `match_id` 与 issue/match_idx 一致，且停售时间不为空；
6. 原始批次 `SHA256SUMS` 与数据库摘要一致。

不满足条件的场次写入 `rejections.csv`，不会用更晚快照、终值或旧无时间戳记录
替代。冻结包包含 `frozen_outcomes.csv`、`rejections.csv`、`manifest.json` 和
`SHA256SUMS`。当前过关方式与限额未知，因此 manifest 固定
`roi_authorized=false`。

冻结后可独立复验哈希、manifest 行数和场次玩法计数：

```bash
.venv/bin/python scripts/manage_multimarket_p0.py verify-freeze \
  --output-dir OUTPUT_DIR
```

## 4. 结算真值

`multimarket_settlement_truth` 每场每玩法保存：

- `fthg/ftag`；
- 总进球桶或比分选项码；
- 该命中项最终 winning SP；
- `settled`、`pending_or_unknown`、`result_complete_sp_missing`、
  `cancelled`、`postponed`、`void_sp1`；
- score 来源、winning SP 来源和终值 batch_id。

比分映射覆盖 25 项之外的 `home_other/draw_other/away_other`。SP=1 单独标记为
`void_sp1`，取消和延期不会伪装成普通结算。

命令：

```bash
.venv/bin/python scripts/manage_multimarket_p0.py settle --issue ISSUE
```

结算表允许在官方状态变化时更新，但不能修改原始抓取批次或冻结快照。

## 5. 生产验收

截至 2026-07-16：

- `26071–26074`：总进球和比分终值批次共 8 包，全部是
  `terminal_backfill_exploratory_only`；结算真值分别覆盖 16、67、10、65 场；
- `26075`：每轮两个 P0 包均含 25 场，17 场完整 forward，8 场终值回补；
- 14 个原始批次包全部通过 SHA-256 复验，其中 8 个是历史终值回补，6 个是
  `26075` 的三轮前瞻抓取；
- `26075` canonical v2 10h 冻结只纳入 #19–#25，共 14 个场次玩法、231 个选项行；
- #1–#18 没有合规 10h 批次，全部 `no_asof_snapshot`，未做替代回填；
- `26075` 当前结算为 8 场 × 2 玩法 settled，17 场 × 2 玩法 pending。

canonical 冻结路径：

```text
results/research/multimarket_10h_freeze_v1/26075_p0_20260716_v2
```

该冻结的 `SHA256SUMS` 文件摘要为
`88bcdceaa3e711a3fad43daea0018002101d170dc198300f33db77f1b6650439`。
无审计字段强校验的 `26075_p0_20260716` 保留为不可变 smoke 产物，不是 canonical 输入。

## 6. Nowscore 历史页 segment 验证

Nowscore 历史 SP 页包含带源时间的完整变化序列。研究回填器原子保存原始 HTML、
`selected_asof.csv`、页面清单、拒绝清单、manifest 和 `SHA256SUMS`，固定
`execution_enabled=false`、`roi_authorized=false`。

```bash
# 实际 segment 决策回放
.venv/bin/python scripts/backfill_nowscore_bjdc_sp_history.py backfill \
  --issue 26074 --typeid 6 7 8 9 --segment-idx 3

# 可选的固定偏移研究切片，N 可自行设定
.venv/bin/python scripts/backfill_nowscore_bjdc_sp_history.py backfill \
  --issue 26074 --typeid 6 7 8 9 --hours-before 10
```

26074 已按真实 `segment_decision_windows` 验证：

| segment | 共同 as-of | 场次 | 页面成功 | 每场倒计时范围 | 源快照陈旧度 |
| --- | --- | ---: | ---: | ---: | ---: |
| #3 | 2026-07-12 17:55 HKT | 15 | 60/60 | 35–305 分钟 | 0–4 分钟 |
| #4 | 2026-07-13 00:40 HKT | 14 | 56/56 | 35–1850 分钟 | 0–5 分钟 |

这说明共同决策时点与逐场不同倒计时可以同时成立；不能用统一的“距开赛 10 小时”
代替实际 segment 回放。两包 `SHA256SUMS` 摘要分别为
`315bfd69c4d29faaf8cbdf7f6a77de93621f0a3a469c256b36fd1e5ebf419682` 和
`19036092cf99af1b6205ba76c7a79640f4220b12a61326abd9c3f3e850674012`。

## 7. 验收测试

```bash
.venv/bin/pytest -q \
  tests/scripts/test_multimarket_p0.py \
  tests/scripts/test_nowscore_bjdc_sp_history.py
```

测试覆盖：不可变包与幂等、数据库原子回滚、双时钟 10h 成功链、原文及冻结文件
篡改拒绝、终值/停售拒绝、比分其他项、SP=1 特殊结算。
