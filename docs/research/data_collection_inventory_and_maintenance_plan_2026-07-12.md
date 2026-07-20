# 北单项目数据采集清单与维护计划

日期：2026-07-12
状态：生产维护基线 v1
主决策库：`data/derived/500_bjdc/500_bjdc.sqlite`
赛前时序库：`data/beidan_live.db`
机器可读计划：`config/data_collection_plan.json`

> 合并边界（2026-07-20）：本文件与采集、不可变快照和 systemd 单元一并进入研究基础基线。
> “运行状态”页面和 `audit_data_collection_status.py` 的逐采集器展示依赖独立的看板 API 发布，
> 不随本次研究资产合并而启用；因此本文件中相应条目是已定义的运维契约，不是当前 `main` 的运行保证。

## 1. 目标与边界

本清单解决四个问题：

1. 明确每项生产数据由哪个采集器负责，避免无人维护或重复抓取。
2. 明确刷新周期、覆盖率、时效阈值和不可回补数据的冻结要求。
3. 将采集器进程、最近尝试、最近成功、覆盖率、下次计划和错误统一展示在“运行状态”。
4. 将采集失败变成显式预警，并为每类失败规定补采和降级动作。

决策 artifact、下注计划和赛后复盘属于数据消费/产物链，不归类为原始数据采集器；它们继续保留在信息更新矩阵中。

## 2. 生产采集器清单

### 2.1 主决策库

| ID | 数据内容 | 代码入口 | 调度进程 | 当前计划 | 落库表 | 重要性 |
|---|---|---|---|---|---|---|
| `issue_list_500` | 期次列表、当前期识别 | `scripts/scrape_500_bjdc.py:fetch_issue_list` | `live_sp_refresh_loop.py` | 每 15 分钟 | `issues`, `fetch_log(kind=issue_list)` | critical |
| `issue_html_500` | 场次、开赛时间、让球、可见 SP、赛果、结算 SP | `scripts/scrape_500_bjdc.py:scrape_issue` | `live_sp_refresh_loop.py` | 每 15 分钟；当前/最近/未结算期 | `matches`, `fetch_log(kind=issue_html)` | critical |
| `live_sp_500` | 三项北单 SP 时间序列 | `scripts/scrape_500_bjdc.py:scrape_live_sp` | `live_sp_refresh_loop.py` | 每 15 分钟 | `live_sp_snapshots`, `fetch_log(kind=live_sp_xml)` | critical |
| `market_sp_total_goals_500` | 总进球 0 至 7+ SP 时间序列 | `scripts/scrape_500_bjdc.py:scrape_live_sp` | `live_sp_refresh_loop.py` | 每 15 分钟 | `live_market_sp_snapshots(playid=40)`, `market_sp_capture_batches` | important |
| `market_sp_upper_lower_odd_even_500` | 上下单双四项 SP 时间序列 | `scripts/scrape_500_bjdc.py:scrape_live_sp` | `live_sp_refresh_loop.py` | 每 15 分钟 | `live_market_sp_snapshots(playid=41)` | important |
| `market_sp_correct_score_500` | 25 项比分 SP 时间序列 | `scripts/scrape_500_bjdc.py:scrape_live_sp` | `live_sp_refresh_loop.py` | 每 15 分钟 | `live_market_sp_snapshots(playid=42)`, `market_sp_capture_batches` | important |
| `market_sp_half_full_500` | 九项半全场 SP 时间序列 | `scripts/scrape_500_bjdc.py:scrape_live_sp` | `live_sp_refresh_loop.py` | 每 15 分钟 | `live_market_sp_snapshots(playid=51)` | important |
| `score_nowscore` | 捷报映射、实时比分、半场比分、状态 | `scripts/scrape_nowscore_bjdc.py` | `live_score_refresh_loop.py` | 每 2 分钟 | `nowscore_bjdc_matches`, `fetch_log(kind=nowscore_bjdc)` | critical |
| `detail_nowscore` | 近期状态、交锋、排名、盘路、欧赔共识 | `scripts/scrape_nowscore_match_details.py` | `live_artifact_refresh_loop.py` | 每 5 分钟扫描；单场 TTL 2 小时 | `nowscore_match_details` | critical |
| `intel_digest` | 赛制、排名和专家标题摘要 | `scripts/collect_match_intel.py` | `live_artifact_refresh_loop.py` | 每 5 分钟扫描；单场 TTL 2 小时 | `match_intel_sources`, `match_intel_digest` | important |

### 2.2 赛前时序与结算旁路

| ID | 数据内容 | 代码入口 | 调度 | 落库表 | 重要性 |
|---|---|---|---|---|---|
| `legacy_prekick_snapshot` | 500 + zgzcw 合并的赛前 3-SP、欧赔、销量比占位及独立结算 | `python -m live_collector` | 5–15 分钟随机间隔 | `data/beidan_live.db`: `matches`, `snapshots`, `settlements` | critical |

这一路是 append-only forward 数据。历史网页无法可靠恢复完整赛前 3-SP 和销量比例，因此进程退出超过一个刷新窗口即为严重故障。

### 2.3 备用与人工任务

| ID | 用途 | 代码入口 | 默认状态 | 启用条件 |
|---|---|---|---|---|
| `detail_500_fallback` | 500 单场分析详情，作为捷报详情故障时的备用源 | `scripts/scrape_500_match_details.py` | standby | 捷报详情持续失败或需要交叉验证时人工运行 |
| 历史期导入 | 一次性导入或回填历史 500 数据 | `scripts/import_500_bjdc_to_sqlite.py`, `scripts/scrape_500_bjdc.py --all` | manual | 研究数据扩容，不参与实时 SLA |
| Cookie 维护 | 恢复 500 受限字段 | `scripts/refresh_500_cookies.py` | manual | 抓取出现受限页或字段系统性为空 |

备用采集器不运行不应触发生产红色预警，但必须在运行页显示为“待命”，避免被误认为遗漏。

## 3. 数据时间计划

### 3.1 期次生命周期

| 阶段 | 必须执行 | 验收条件 |
|---|---|---|
| 新期发现 | 刷新期次、场次、捷报映射 | `issues` 能识别 current；`matches` 与捷报映射覆盖全部场次 |
| 分段前两段 | 刷新 SP、详情、情报；重走决策输入 | 当前段和下一段开赛前均有带时间戳的输入快照 |
| 临场窗口 | 保持 SP 与比分循环；不得用开赛后信息覆盖冻结建议 | 正式 artifact 的输入时间早于对应场次开赛 |
| 比赛进行中 | 高频刷新比分；继续保存 SP 变化 | 比分源不超过 5 分钟；采集失败显式告警 |
| 完赛后 | 继续刷新赛果和结算 SP，触发复盘 | 已完赛场次均有 result、winning SP 或明确的待结算状态 |
| 整期结束 | 冻结采集审计和复盘结果 | 采集覆盖、延迟、失败次数可追溯 |

### 3.2 SLA 与告警

| 采集器 | 计划间隔 | stale 阈值 | 覆盖要求 | 故障等级 |
|---|---:|---:|---:|---|
| 期次/500 场次/500 SP | 900 秒 | 1,200 秒 | current 100% | bad |
| 捷报比分 | 120 秒 | 300 秒 | current 100% | bad |
| 捷报详情 | 扫描 300 秒；行 TTL 7,200 秒 | 9,000 秒 | current 100% | bad |
| 情报摘要 | 扫描 300 秒；行 TTL 7,200 秒 | 9,000 秒 | 尽力 100%；无有效来源必须显示 missing | warn/bad |
| 赛前时序旁路 | 300–900 秒 | 1,200 秒 | 每轮 current 全场 | bad |

状态判定顺序：进程未运行 > 最近尝试失败 > 必需覆盖不完整 > 数据过期 > 正常。页面不得仅凭进程存活判断正常。

## 4. 调度职责与去重

目标职责如下：

- `live_sp_refresh_loop.py`：唯一负责 500 期次、场次 HTML，以及让球胜平负、总进球、上下单双、比分和半全场 SP XML。多结果玩法按 `(issue, playid, fetched_at, row_idx, outcome_code)` 展开保存，不复用胜平负三列。
- 高维玩法只对 current 期持续留存；近期已完结期仅做一次性终值回补。上游在停售后只保留中奖项终值，无法还原此前未采集的完整赛前赔率向量，禁止把终值回补标记成历史赛前快照。
- `live_score_refresh_loop.py`：唯一负责捷报比分与映射。
- `live_artifact_refresh_loop.py`：只负责按 TTL 扫描捷报详情、情报摘要，以及后续决策产物维护；不再重复刷新 500/SP/比分。
- `python -m live_collector`：独立维护不可回补的赛前时序库和结算旁路。

所有循环的计划间隔按“本轮开始到下一轮开始”计算；网络和结算耗时必须从睡眠时间中扣除。否则进程虽然存活，实际采集间隔仍会超过 SLA。

人工“完整刷新工作流”仍可串行调用全链路，用于故障恢复，但常驻调度不得重复所有源。

## 5. 运行状态契约

“运行状态”必须为每个注册采集器展示：

- 采集器名称、重要性、启用/待命状态；
- 所属进程及进程是否存活；
- 计划间隔、最近尝试、最近成功、下次计划；
- 当前期覆盖数量与缺失场次；
- 最新错误和建议维护动作；
- 数据源、代码入口和落库表。

后端从 `config/data_collection_plan.json` 读取静态计划，从 SQLite、`fetch_log`、运行时进程状态和赛前时序库计算动态状态。配置缺失或 schema 无效必须返回告警，不得静默回退为“正常”。

命令行使用相同状态口径：

```bash
.venv/bin/python scripts/audit_data_collection_status.py --issue current
.venv/bin/python scripts/audit_data_collection_status.py --issue current --json
.venv/bin/python scripts/audit_data_collection_status.py --issue current --fail-on-warn
```

默认在采集计划无效或存在 `bad` 时退出码为 2；`--fail-on-warn` 会在仅有提醒时返回 1。

## 6. 故障恢复手册

### 6.1 进程退出

1. 在运行页确认具体 owner process。
2. 使用 `scripts/manage_decision_dashboard.py restart` 恢复主决策库三个进程。
3. `legacy_prekick_snapshot` 独立恢复：`PYTHONPATH=src .venv/bin/python -m live_collector`。
4. 确认进程恢复后仍需检查最近成功和覆盖率，不能只看 PID。

### 6.2 覆盖缺失

1. 先确认上游映射是否完整：`matches` → `nowscore_bjdc_matches`。
2. 详情缺失时运行 `scrape_nowscore_match_details.py --issue ISSUE --limit 96 --stale-hours 0`。
3. 情报缺失时运行 `collect_match_intel.py --issue ISSUE --limit 96 --stale-hours 0`。
4. 无有效来源的情报保持 `missing`，不可用空摘要伪装 `ok`。
5. 补采后重走 decision input，只生成 draft/research 快照；不得覆盖已冻结赛前建议。

### 6.3 数据过期但进程存活

检查日志中是否存在解析为 0 行、上游页面改版、数据库锁、网络超时或反爬页面。每次成功必须同时满足 HTTP 成功和有效行数大于零。

## 7. 维护节奏

### 每日

- 查看运行页所有 critical 采集器是否正常。
- 检查 current 覆盖率和缺失场次。
- 检查不可回补的赛前时序最近成功是否在 20 分钟内。

### 每期

- 新期发现后确认比赛数量在各表一致。
- 每个分段开赛前保存采集审计时间和决策输入时间。
- 整期结束后记录缺失率、最大延迟、失败/恢复次数。

### 每月或上游改版后

- 运行 parser fixture 和 data-chain smoke tests。
- 抽检字段语义、比分主客顺序、让球赛果映射和 SP 完整性。
- 更新本文件和机器可读计划；代码、计划、运行页三者必须同步。

## 8. 验收标准

1. 文档与 `config/data_collection_plan.json` 中的生产采集器一一对应。
2. Operations API 返回逐采集器状态，而不仅是三个父进程状态。
3. 前端能显示每个采集器的进程、覆盖率、最近成功、下次计划和错误。
4. 停掉任一 critical owner process 后，对应采集器在运行页变红。
5. 构造缺行、过期和失败日志时，状态分别产生明确预警。
6. artifact 循环不再重复抓取已由 SP/比分循环负责的数据。
7. `py_compile`、后端测试、前端测试和生产构建通过。

## 9. 后续优化队列

1. 将 current 的 500/SP 调度从固定周期升级为分段感知：临场缩短、无近期比赛时放宽。
2. 为详情和情报增加逐场“首次赛前采集时间”，直接验证是否在 kickoff 前完成。
3. 将采集审计固化为每期 artifact，支持统计长期缺失率和延迟分布。
4. 为 `live_collector` 纳入统一进程管理，替代当前独立守护方式。
5. 解决 `tzbl` 长期为空和旧采集器跨期归属风险；在修复前不得作为模型强特征。

## 10. 2026-07-16 多玩法扩展验收

- 已确认玩法映射：总进球 `playid=40`、上下单双 `41`、比分 `42`、半全场 `51`。
- `26075` 四玩法均覆盖 `25/25` 场；其中 17 场尚未停售时取得完整赔率向量，8 场已结束只能取得中奖项终值。
- `26072`、`26073`、`26074` 分别完成 `67/67`、`10/10`、`65/65` 场终值回补。该回补不是赛前快照。
- systemd `beidanlot-sp-refresh.service` 已验证可运行五玩法循环；目标主机仍须显式加载单元，并由后续看板 API 发布逐采集器 `ok / healthy` 状态。
- 四种新玩法只写 `live_market_sp_snapshots`。原 `live_sp_snapshots` 继续只保存 `playid=34`，正式决策读取路径不变。
- 总进球和比分 P0 的不可变批次、10h as-of 冻结与结算真值契约见 `docs/research/multimarket_p0_capture_freeze_settlement_contract_2026-07-16.md`。
- 赛前 SP 冻结采用双口径：实际下注回放优先使用 segment 的共同冻结时间，并为每场
  保存不同的开赛倒计时；`kickoff-Nh` 只用于标准化研究切片，10h 不是固定业务标准。
- Nowscore 时间戳历史页保留原始全序列，并可按 `segment_freeze`、`explicit_asof`、
  `standardized_offset` 三种模式生成带 SHA-256 的不可变研究包；任何模式均不进入正式执行。
- 比分模型 Euro/O/U 使用 Excel VBA 同源的 Titan007/Nowscore 接口生成独立不可变资产：
  Euro 为 `1x2d.titan007.com` JS，O/U 为 `HandicapDataInterface` 的 `oddskind=1`。
  严格 segment 回放及 26074 #3/#4 验收见
  `docs/research/nowscore_score_model_strict_segment_snapshot_asset_2026-07-16.md`。
- 外部公司正确比分价格使用独立不可变链路，详见
  `docs/research/correct_score_price_strict_asof_asset_2026-07-17.md`。该链路保存
  William Hill 正确比分历史、双 provider ID、raw/hash，只按
  `snapshot_ts <= segment.freeze_at` 选最后完整向量。500 `playid=42` 停售后终值
  只作结算/覆盖审计；26076 起前瞻运行，源 405 显式标为 `source_blocked`。
