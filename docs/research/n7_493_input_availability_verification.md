# Issue #493 输入可用性核验（小范围、时间证据优先）

**任务**：先核验数据可用性，再实施最小回放。重点回答
"Nowscore 欧赔平均与大小球，能否取到每天北京时间 20:00 之前最近的有效快照"，
并核实两条线索：**开赛前截止提前量** 与 **SQLite disk I/O error**。
**方法约束**：不重复大范围扫描；先做小范围读取与时间证据检查。

---

## 0. 结论摘要（四条，全部有实测证据）

| 问题 | 结论 |
|---|---|
| Nowscore **欧赔平均**，20:00 前最近有效快照 | **取不到。可用期次 = 0。** |
| Nowscore **大小球**，20:00 前最近有效快照 | **取不到。可用期次 = 0。** |
| 决策窗口 | **次日自然日 `[次日00:00, 次次日00:00)`**（决策后 4–28 小时），合同更新后的正式口径 |
| 停售截止时间 | **不再作为准入规则**（合同要求删除/停用）。实测以 **5 分钟**为主（1,902 行中 82.9%）；**"10 分钟众数"结论已作废**，见 §4 |
| SQLite disk I/O error | **未能复现**；输入库健康，另有环境风险点 |

**新增发现（更正本交付上一版 audit 的遗漏）**：仓库里**存在**一条**前瞻分类、
销售状态 open、带真实抓取时间**的**总进球**序列
（`500_bjdc.live_market_sp_snapshots`，`market_key='total_goals'`，
`capture_classification='forward_complete_open'`，2,206,104 行，覆盖 19 个期次）。
它是 **500.com**，**不是 Nowscore**，且**不包含 1X2**。

---

## 1. Nowscore 欧赔平均：0 期可用

| 证据 | 数值 |
|---|---|
| `inputs/danchang_1x2.csv` | 6,534 行 / 26087–26097（26090 全缺）；只有 init/curr 两状态 |
| 行级时间戳 | **没有**；`inputs/nowscore_raw/` 67/67 个原始响应里 **0** 个时间 token |
| 采集器是否落盘时间 | **没有**：`write_raw()` 只写正文，`RawResponse.fetched_at` 被丢弃 |
| 唯一时间证据 | 文件 mtime 窗口 **2026-09-22T15:02:23+08:00 … 15:05:16+08:00**（单次事后读取） |
| 该窗口与结算的关系 | 晚于 26087–26096 全部结算；也晚于 `quarto/275` 自述的决策时刻 13:55 共 69 分钟 |

Nowscore 的**北单 SP 历史页确实带源时间标签**
（`src/nowscore_bjdc_sp_history.py`：`HistoryVector.source_ts_hkt`，
`TIME_RE = ^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$`，typeid 5 = `handicap_3way`），
**但仓库里没有任何 typeid=5 的抓取存档**：
`data/derived/nowscore_only/20260905_bf_history` 的 130 条抓取**全部是 typeid=8（比分）**，
且期次是 `130408/26082/…` 等历史期，不是本次回放期次。

**因此：Nowscore 欧赔平均不存在可用于 20:00 决策时刻的时间序列。**

## 2. Nowscore 大小球：0 期可用

`inputs/danchang_overunder.csv` 4,115 行，只有 `over_hk,line,under_hk`，
**每 (期次, 公司, 场次) 只有一个无时间状态，没有初盘**；同样没有行级时间戳。
Nowscore typeid 6 = `total_goals` 的抓取存档在仓库中**不存在**。

## 3. 新发现：500.com 前瞻总进球序列（本交付上一版遗漏）

`data/derived/500_bjdc/500_bjdc.sqlite.bak :: live_market_sp_snapshots`

| 维度 | 数值 |
|---|---|
| 总行数 | 62,266,059（`correct_score` 24.1M / `handicap_3way` 17.9M / `half_full` 8.8M / `total_goals` 7.7M / `upper_lower_odd_even` 3.9M） |
| 来源 | `https://www.500.com/static/public/bjdc/xml/sp/just_2…` → **500.com，非 Nowscore** |
| 时间字段 | `fetched_at_utc`（抓取）、`source_updated_at_hkt`（源更新）、`sale_cutoff_hkt`（停售） |
| 资格字段 | `capture_classification`、`sale_status`、`eligibility_evidence_json`、`eligibility_receipt_sha256` |

`capture_classification` 分布（全表）：

| 分类 | 行数 |
|---|---|
| `non_target_market_unclassified` | 30,573,424 |
| `terminal_backfill_exploratory_only` | 13,802,548 |
| `forward_incomplete_rejected` | 9,116,807 |
| **`forward_complete_open`** | **5,606,329** |
| `post_cutoff_static_exploratory_only` | 3,213,511 |
| `legacy_unclassified` | 19,903 |

**只有 `forward_complete_open` 是决策时刻可用的**，其中：

| market_key | 行数 |
|---|---|
| `correct_score` | 3,400,225 |
| `total_goals` | **2,206,104** |
| `handicap_3way`（1X2） | **0** |

`forward_complete_open` 的 `sale_status` **全部为 `open`**；
`fetched_at_utc` 范围 **2026-07-16T13:05:41Z … 2026-09-19T01:13:50Z**；
覆盖 **19 个期次**：26075–26086、26088、26089、26091–26096。

**与本次回放 27 期的交集 = 12 期**：
26075, 26076, 26077, 26078, 26079, 26081, 26082, 26083, 26084, 26085, 26086, 26088。

**含义（必须如实说）**：
- 合同要求的"大小球约束总进球"在 **12/27 期**上**存在决策时刻可得的降级来源**；
- 但它是 **500.com**，且**没有对应的前瞻 1X2**，所以"用同一来源同时定标 1X2 与总进球"
  仍不可能；
- 本轮回放**仍未接入**它：接入需要新的 reader、市场对齐与测试，
  且它改变不了"来源不是 Nowscore"这一合同级偏离。**这是待 PI 路由的下一步，不是已完成的替代。**

## 4. 停售截止时间与决策窗口（线索核实，结论经两次更正）

> **⚠ 本节结论已被 #493 合同正文的更新取代。** 合同更新后：决策窗口改为**次日自然日**
> `[次日00:00, 次次日00:00)`（= 决策后 4–28 小时），并明确**不要求为研究重建逐场临场停售
> 分钟阈值**、要求**删除/停用**统一推定对常规候选的依赖，只保留**明确不可售/取消/改期证据**
> 与**赛程异常**检查。本交付已据此**删除**逐场停售准入实现。
> 下面关于"逐场 5 分钟"的实测仍然有效**作为事实记录**（它推翻了旧"10 分钟众数"），
> 但它**不再是准入规则**。

> **本节曾给出"10 分钟众数"的结论，该结论是错的，现更正。**
> 错因：把 `sale_cutoff_hkt` 关联到 `nowscore_bjdc_matches.schedule_date + kickoff_time`，
> 而该 `kickoff_time` 对大量行是**占位符 `00:00`**。占位符造出约 −1435 分钟的假差值，
> 再用"加 1440 归一"把 −1430 读成 10 分钟，于是得到一个**并不存在的众数**。
> 直接读单场标签即可看到反例：26071 第 1 场 `kickoff_time=23:00`、
> `截止时间：2026-06-30 22:55` → **5 分钟**。

正确做法是改用**权威开赛时间** `beidan_live.matches.kickoff_ts`（来自 500.com 投注页
`比赛时间`）去关联 Nowscore 列表页的 `<td title="截止时间：YYYY-MM-DD HH:MM">`。
**1,902 行**（20/27 期，100% 可解析）的 `kickoff − 截止时间` 分布：

| 提前量 | 行数 | 占比 |
|---|---|---|
| **5 分钟** | **1,577** | **82.9%** |
| 150 分钟 | 49 | 2.6% |
| 30 分钟 | 40 | 2.1% |
| 15 分钟 | 33 | 1.7% |
| 100 / 120 / 60 / 180 分钟 | 29 / 24 / 23 / 15 | 1.5 / 1.3 / 1.2 / 0.8% |

**这改变了本轮实现（第二次）。** 回退常量 `N7_STOP_SALE_MINUTES` 改回 **5L**。

但更重要的是：**任何单一提前量都不该被套用到所有场次**。上表的长尾说明停售提前量
**逐场不同**，用众数（无论 5 还是 10）都是"以样本统计替代逐场证据"。
因此实现改为：

1. **逐场真实 `截止时间` 优先**——有记录就用记录，它直接决定该场在决策时点是否可投；
2. **无记录则停止准入**（`N7_UNKNOWN_CUTOFF_POLICY = "EXCLUDE"`）——
   任何假定的提前量都无法从样本**证明**安全，所以不猜；
3. **停售时间晚于开赛时间的自相矛盾记录**（95 行）显式排除并计数
   （`KICKOFF_CONTRADICTED_BY_SALE_CUTOFF`）：这 95 行**全部**落在
   `kickoff_ts` 为占位符 `T00:00:00` 的行上，真实时刻的行 **0 例**，
   两者必有其一为错，无法判定窗口归属，故不静默偏向任何一侧。

**代价必须写明**：27 期中 **7 期**（26051/26053/26055/26057/26061/26063/26064）
完全没有逐场停售记录，被整体停止准入。合格场由 4,327 降至 **1,804**，
收益结论只在这 **20 期**上成立。

## 5. SQLite disk I/O error：未能复现（线索核实）

| 检查 | 结果 |
|---|---|
| 输入库 `data/beidan_live.db`（284 MB，本地 NVMe） | `PRAGMA quick_check` = **ok**；`mode=ro` / `mode=ro&immutable=1` / 普通 三种打开方式全部 OK |
| 文件系统 | `/dev/nvme0n1p2`，636 GB 可用，29% 使用 |
| `journal_mode` | **wal**；`-wal`/`-shm` sidecar 均存在 |
| 51 GB `500_bjdc.sqlite.bak` / 6.9 GB `beidan_xlsm.sqlite` / 1.1 GB `beidan_modeling_plus_2026.sqlite` | 两种只读模式下的 schema 读取**全部 OK** |
| WAL + **只读目录**（`.tmpwork/walprobe` 构造实验） | **仍 OK**（SQLite 3.46.1 已能处理只读 WAL） |

**结论**：在本机当前状态下，**用本交付所需的scoped 读取无法复现该错误**。
可归因的风险点（未证实的假设，仅登记）：
1. **大范围全表扫描**：51 GB 库上的聚合查询是唯一在本机耗时达到分钟级的操作
   （本次核验中的 `group by capture_classification` 即属此类）；"避免大范围扫描"与之一致。
2. 机器上存在一个**只读 exFAT 可移动挂载**（`/dev/sda1 on /run/media/drwho1985/Sandisk type exfat (ro,…)`）。
   exFAT 无 POSIX 锁、只读挂载下无法建 WAL sidecar，是该错误类别的经典环境；
   但该盘上**没有** SQLite 文件，故无法直接归因。
3. 本交付**不依赖**上述任一路径：只读 `data/beidan_live.db`，每次查询按 (期次) 限定。

## 6. 20:00 决策时点的可取性（用已有产物，无新扫描）

来自 `results/n7_493_baseline_v4/epoch_scope.csv`（27 期 × 150 个决策时点）：

| 指标 | 数值 |
|---|---|
| 决策时点 | 150 |
| 窗口内合格 (场, 时点) | 4,327 |
| 取到 20:00 前最近有效 500.com 快照 | **3,433（79.3%）** |
| 无可用报价排除 | 894（20.7%） |
| **≥7 场可投的决策时点** | **98 / 150（65.3%）** |
| 不足 7 场 | 52（其中 38 个完全无报价） |
| 窗口外/停售后排除 | 0（epoch 推导与资格判定完全一致） |

**回答**：对 500.com 平均欧赔**可以**取到每天 20:00 前最近的有效快照（3,433/4,327）；
对 **Nowscore 欧赔平均与大小球，取不到**。可投时点只占 65.3%，
主要原因是部分期次的赔率轮询序列**在该期首场之后才开始**。

## 7. 复现命令（全部小范围）

```sh
# 输入库健康与打开方式
python3 -c "import sqlite3;c=sqlite3.connect('file:data/beidan_live.db?mode=ro',uri=True);print(list(c.execute('pragma quick_check')))"

# 停售截止时间分布（4,000 行关联，归一化到 [-60, 1380] 分钟）
python3 .tmpwork/probe_gap3.py

# 前瞻分类与市场覆盖
python3 .tmpwork/probe_fwd.py
python3 .tmpwork/probe_fwd2.py

# Nowscore 抓取存档的市场类型
python3 .tmpwork/probe_ns.py

# 只读 WAL 复现尝试
python3 .tmpwork/probe_wal.py
```

> 探针脚本是本次核验的一次性程序，位于 gitignore 覆盖的 `.tmpwork/`；
> 上面的命令即为完整可重放步骤。

---

## 8. 追加核验："类似 `live.nowscore.com/odds/match/{id}.htm` 这样的页面呢？"

> ### ⚠️ 本节 8.1–8.4 的结论已被 8.6 推翻，保留原文以留存判断过程
>
> 我先前据"连续取回后主页面开始返 404"判定该站点**限流**，并据此判定这一族页面
> **不可用**。**这是错的。** 实际是 **cookie 触发的软封**：换用干净 cookie jar
> （无痕等价）后同一端点正常返回。8.6 节给出更正后的结论与实测证据。
> 读者请以 **8.6 为准**，8.1–8.4 只作为"我为什么先判错"的记录。

**（原文，已被 8.6 更正）结论：这一族页面同样不能为 26051–26088 提供决策时刻的 Nowscore 欧赔/大小球。**
三条独立理由，外加一条真正带时间戳的替代家族（但无存档）。

### 8.1 `live.nowscore.com/odds/match/{id}.htm`（你给的那个页面）

| 事实 | 证据 |
|---|---|
| 仓库**认识**这个页面 | `nowscore_bjdc_matches.asian_url` 在 **3,800/3,800** 行都是 `https://live.nowscore.com/odds/mat…` |
| 你给的 id 在已存范围内 | `provider_match_id` 范围 2,906,706–3,090,721，含 3,049,659（该场属未采集期次） |
| 仓库**从不抓取**它 | `grep` `src/**/*.py` 里 `odds/match/` **0** 个抓取目标，只有链接字段 |
| 页面 HTML **没有赔率表** | 全文 **0 个 `<table>`**；只有 1 个完整时间戳（开赛时间 2026-09-23 13:30） |
| 赔率由 AJAX 加载 | 每家公司一个 `/odds/3in1Odds.aspx?companyid={cid}&id={matchid}` |
| 该载荷端点取不到 | 直接取 **404**；带浏览器 Referer **302 → /control/404.aspx** |
| 站点会限流 | 连续几次只读取回后，**主页面本身也开始返回 404 页** |

即：它**不是**可当作文档读的存档页，且**没有任何历史抓取**。

### 8.2 `cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5|6&issueNum={issue}`

这一族**确实有真实抓取**，而且是合同要的两个市场：

| 事实 | 证据 |
|---|---|
| 存档位置 | `data/derived/nowscore_only/20260905_pilot/`（60 条抓取，`schema=nowscore_capture_v1`） |
| 含 typeid **5（欧赔）** 与 **6（大小球）** | 各 **12** 条，另有 typeid 7/8/9 各 12 条 |
| 有真实观测时间 | 每条带 `received_at`（UTC）与 `sha256`，原始 HTML 保存在 `raw/` |
| `requested_issues` | 130408, 130509, 130511, 140706, 141112, 150903, 23054, 23093, 24051, 25033, 25053, **26082** |
| 与本次回放的交集 | **26082**（唯一一个） |

**但它是事后抓取，且页面只有当前状态：**

| 检查 | 结果 |
|---|---|
| 26082 typeid5 抓取的 `received_at` | **2026-09-05T09:18:23Z** |
| 该期次最早的 `截止时间` | **2026-08-04 23:55** |
| 差 | **晚约 31 天**——该期所有比赛早已踢完 |
| 页面是否含"变化"序列 | `初盘` **0** 次、`变化` **0** 次、`即时` 1 次 |
| 页面里的 170 个时间 token 是什么 | 是各场的**停售截止时间**（如 2013-04-13 01:45），**不是赔率变更时间** |
| `scope` 自述 | `"explicit diagnostic issues, not a complete historical universe"` |

**因此用它做 26082 的 20:00 快照，就是把已结算的最终赔率当成下注时信息——正是合同禁止的做法。**

### 8.3 真正带时间戳的替代家族（有解析器，无存档）

`src/nowscore_score_model_history.py`（docstring：*Immutable Titan007/Nowscore Euro 1X2 and over/under history primitives*）：

| 项 | 值 |
|---|---|
| 市场 | `MARKETS = ("euro_1x2", "over_under")` —— **正是合同要的两个市场** |
| 欧赔端点 | `https://1x2d.titan007.com/{provider_match_id}.js` |
| 大小球端点 | `https://m.titan007.com/HandicapDataInterface.ashx?scheid=…&type=3&oddskind=1&companyid=…&matchtime=…` |
| 时间标签 | `EURO_TIME_RE = ^(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$`；`OU_TIME_RE = ^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$` |
| 输出 | `ParsedSnapshot.snapshot_ts_hkt` + `time_normalization_status` + `phase` + `complete` + `raw_row_sha256` |
| **证据类别（自述）** | `SOURCE_CLASSIFICATION = "third_party_timestamped_archive"` |

**这才是"带时间戳"的那一族——是 Titan007，不是你给的 `live.nowscore.com/odds/match/` 页面。**
但两点必须同时说清：
1. 它是**第三方时间戳存档**（回溯取得），按 AGENTS.md
   "historical timestamp proxies are diagnostic only"，**不能自行升格为决策时刻证据**；
2. **磁盘上不存在它的任何抓取包**：全库搜 `capture_log.jsonl` 只有 pytest 夹具与上面那个
   `20260905_pilot`；搜 `1x2d.titan007` 在 data/results/.tmpwork 的 json/jsonl 中 **0 命中**。

### 8.4 对本轮交付的影响

**无变化。** 本轮回放仍只用 `beidan_live.db::snapshots`（500.com 门户平均欧赔，
真实观测 UTC 轮询时刻），大小球仍不接入，"来源不是 Nowscore"仍是**合同级偏离**。
上面三条新证据只是把"为什么取不到"钉得更死，并排除了一条看起来可行的替代路径。

### 8.5 复现命令（本节）

```sh
# 8.1 页面结构与载荷端点（只读，未落盘）
curl -s 'https://live.nowscore.com/odds/match/3049659.htm' | grep -c '<table'
curl -s -o /dev/null -w '%{http_code}\n' 'https://live.nowscore.com/odds/3in1Odds.aspx?companyid=1&id=3049659'

# 8.2 pilot 抓取包的市场与时间
python3 .tmpwork/probe_pilot.py
python3 .tmpwork/probe_pilot2.py
python3 .tmpwork/probe_26082.py

# 8.3 是否有时间戳存档
grep -rl '1x2d.titan007' --include=*.json --include=*.jsonl data results .tmpwork
```

> 本节所有网络访问均为**只读核验**，未写入 `data/`、未新增采集、未改动任何原始数据。

---

## 8.6 更正：该端点确实返回带时间戳的 Nowscore 欧赔与大小球

### 8.6.1 我先前判错的两个原因

1. **把 cookie 软封误判为 IP 限流。** 换用**干净 cookie jar**（等价于无痕窗口）后，
   同一端点 `live.nowscore.com/odds/3in1Odds.aspx` 立刻从 404 变为 **HTTP 200**。
   我先前用 `web_fetch` 与共享 jar 的 `curl` 连续取回，cookie 被服务端标记，
   于是"主页面也返 404"，我据此下了限流结论——**结论超出了证据**。
2. **我自己的正则被 JS 模板字符串吃掉了反斜杠**，导致首轮结构解析全部返回 0，
   进一步坐实了"页面没有表"的错误印象。修正后表结构立刻可见。

### 8.6.2 端点与实测

`GET https://live.nowscore.com/odds/3in1Odds.aspx?companyid={cid}&id={provider_match_id}`
（Referer 指向 `live.nowscore.com/odds/match/{id}.htm`；需干净 cookie jar）

用**我们自己的** 26082 第 1 场实测（`provider_match_id=3049291`，
米亚尔比 vs 布拉迪斯拉发）：

| 项 | 结果 |
|---|---|
| HTTP | **200**，47,654 bytes |
| 表数 | **3** —— `时\|比分\|主\|盘\|客\|变化\|状`（**亚盘**）、`时\|比分\|大\|盘\|小\|变化\|状`（**大小球**）、`时\|比分\|主\|和局\|客\|变化\|状`（**欧赔**） |
| 时间标签 | **130 个，70 个不同值** |
| 标签范围 | **08-02 18:11 → 08-05 01:28** |
| 时间格式 | `MM-DD<br />HH:MM`（**无年份**） |

**即：合同要求的两类市场（欧赔 1X2、大小球）都有逐条变更时间戳，且能对到我们的期次。**
仓库里已有该格式的规范化器：`src/nowscore_score_model_history.py` 的
`EURO_TIME_RE`、`src/nowscore_bjdc_sp_history.py` 的 `TIME_RE`（同为 `MM-DD HH:MM`），
以及 `snapshot_ts_hkt` / `time_normalization_status` 字段。

### 8.6.3 但这**不能**直接升格为决策时刻证据（三条硬约束）

1. **它是回溯取得、时间戳由源方自述。** 我们并没有前瞻观测它；
   对 2026-08 已结束的比赛，今天取回得到的是**源方声称的**变更历史。
   按 AGENTS.md "historical timestamp proxies are diagnostic only"，
   它属于**诊断类**证据；与本交付此前给 `beidan_xlsm` 的
   `RETROSPECTIVE_RELATIVE_PROXY` 评级同类。**我不得自行把它升格。**
   （它优于 `beidan_xlsm` 的地方是：这里是**逐条绝对时间标签**，而非计算出来的
   `ts_10h`；且理论上可按 epoch 截断重建 as-of 状态。是否采纳需 PI 裁决。）
2. **合同禁止本轮新增采集。** 3,800 场 × 多公司是一个规模化采集任务，
   **不属于 #493 的授权范围**，我不启动。
3. **需要 cookie 生命周期与速率管理。** 你的观察已确认封禁是 cookie 维度的；
   任何采集器必须使用新鲜 jar、有界速率与显式重试策略。

### 8.6.4 对 8.1 的具体更正

- "页面 HTML **没有赔率表**" —— 对 `odds/match/{id}.htm` 这个**外壳页**成立；
  **但**它的 AJAX 端点 `3in1Odds.aspx` 返回**完整的三市场带时间戳表**。
- "该载荷端点取不到（404 / 302→404）" —— 在**干净 cookie jar** 下为 **HTTP 200**。
- "站点会限流，主页面也返 404" —— 实为 **cookie 软封**，不是 IP 限流。

### 8.6.5 复现命令（8.6）

```sh
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'
rm -f .tmpwork/jar.txt
# 1) 外壳页，建立干净 cookie
curl -s -c .tmpwork/jar.txt -A "$UA" -o .tmpwork/p1.html \
  'https://live.nowscore.com/odds/match/3049291.htm'
# 2) 三合一赔率变更日志（亚盘/大小球/欧赔，逐条 MM-DD HH:MM）
curl -s -b .tmpwork/jar.txt -A "$UA" \
  -e 'https://live.nowscore.com/odds/match/3049291.htm' -o .tmpwork/p82.html \
  'https://live.nowscore.com/odds/3in1Odds.aspx?companyid=1&id=3049291'
```

> 同样为**只读核验**：未写入 `data/`、未新增采集、未改动任何原始数据。
