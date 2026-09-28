# Issue #493 交付物 1：实际可用历史输入 / 发布快照 核验

**范围**：核验 N7 决策口径（契约节奏 20:00 Asia/Shanghai = 12:00Z，选未来 24h 内开赛且仍可投注的场次）所需的
**Nowscore 欧赔 1X2 快照**与 **Nowscore 大小球快照**，以及仓库与数据根目录中一切可能替代它们的历史赔率材料。

**结论一句话（直说不足）**：**不存在任何能够证明在 20:00 决策时刻之前已可得的 Nowscore 欧赔或大小球快照。**
仓库里全部 Nowscore 北单盘口材料（期次 26087–26097）是 **2026-09-22 15:02–15:05 (+08:00) 一次性读取的、无时间戳的
(初盘, 即时) 二元状态**；该时刻晚于 275 号交付自述的决策时刻 13:55，也晚于 26087–26096 全部期次的结算。
数据缺口**未解决**，且**不能靠文档声明解决**。

---

## 1. 真正在决策时刻可得的（(a)）

只有一类：**带观测 UTC 采集时间的第三方平均欧赔轮询序列**，但它**不是 Nowscore**。

| evidence | 存储 | 市场 | 采集时间证据 | 覆盖 | 代理等级 |
|---|---|---|---|---|---|
| EV-11 | `data/beidan_live.db::snapshots` | 500.com `pjoz` / cp.zgzcw.com `#esp_N` 平均欧赔 | `snapshot_ts` ISO-8601 **带 Z**（观测轮询时刻） | 1,623,942 行 / 5,578 场 / 33 期（26051–26088） | **OBSERVED_AVAILABILITY**（但来源身份不满足契约） |
| EV-14 | `data/derived/500_bjdc/…::live_sp_snapshots` | 北单 SP | `fetched_at`（同一列混用 naive 与 +00:00） | 6,365,726 行 / 32 期 | **OBSERVED_AVAILABILITY**（非欧赔、非大小球） |
| EV-16 | `data/derived/500_bjdc/…::market_sp_capture_batches` | 比分 / 总进球 SP | `fetched_at_utc` + `source_updated_at_hkt` | 10,373 批 / 23 期 | **OBSERVED_AVAILABILITY**（无 1X2、无大小球） |

**EV-11 的 20:00 (12:00Z) 决策时刻覆盖（按 (期次, 决策时刻) 逐格计算）**

- 候选 fixture-epoch 共 **5,562**，其中 **3,861（69.4%）** 至少有一条 `snapshot_ts ≤ epoch` 且 `eu_h` 非空的快照；
  **1,701 个候选 fixture-epoch 完全没有盘前快照**。
- 按期次汇总的覆盖率从 **13.8%（26052）** 到 **100%（26065/26067/26075）**；最差五个：
  26052 13.8%、26084 15.5%、26058 20.6%、26071 23.9%、26086 24.3%。
- 轮询间隔（同一场次相邻快照）：n=1,618,364，min 0.02 / p25 6.37 / **p50 9.87** / p75 13.57 / p90 18.02 / max 4,353 分钟。
  批次式轮询使同一 epoch 内各场的 lag 相同（例如 26051@2026-05-02T12:00Z 全部 164 场 lag=657.3 分钟，即采集器首个批次）。
- **5,578 场中 1,552 场（27.8%）的首条快照晚于开赛**；另有 **12 行 `eu_h` 为 NULL**。
- 逐格明细在 `coverage.csv`（`market=euro_1x2_500com_epoch`，182 行）。

**EV-11 为什么仍不满足契约（来源身份）**

- `snapshots.source` 在 **1,623,942/1,623,942** 行都是字面量 `"merged"`，**逐行上游身份不可恢复**。
- `src/live_collector/parser.py`：`parse_bet_page_500` 用 `class="pjoz"` span 写 `eu_h/eu_d/eu_a`（约 198–202 行）；
  `parse_bet_page_zgzcw` 用 `id="esp_\d+"` 的 `value` 写同一三列（约 306–308 行）。两者都是**门户站的平均欧赔**。
- `src/live_collector/scraper.py` 的 URL 只有 `trade.500.com` / `zx.500.com` / `cp.zgzcw.com` / `live.500.com`；
  **`grep -rn -i nowscore src/live_collector/` 返回 0 行**。

---

## 2. 明确不可得的（(b)）

### 2.1 Nowscore 欧赔 / 大小球：单快照，且读取发生在事后

| 事实 | 数值 |
|---|---|
| `inputs/danchang_1x2.csv` 行数 / 期次 | **6,534** 行；26087,26088,26089,**26091**,26092,26093,26094,26095,26096,26097（**26090 全缺**） |
| 公司（`COMPANY_NAMES`） | c0 平均欧*、c1 澳M、c3 皇G 覆盖全部期次；**c4 立B / c8 36* / c9 WL / c14 伟D 仅存在于 26097**（各 23 或 17 行） |
| init vs curr | 6,296/6,534（**96.4%**）不同，最大绝对变动 23.5 → 确为两个状态，**但两者都没有任何时间** |
| `inputs/danchang_overunder.csv` | **4,115** 行，公司仅 c1/c3；schema 是 `over_hk,line,under_hk` → **每 (期次,公司,场次) 只有一个无时间状态，没有初盘** |
| `danchang_payout.csv` / `danchang_winrate.csv` | 各 **2,335** 行，公司 id −2 / −1，同样单状态无时间 |
| `inputs/nowscore_raw/` | **67** 个原始响应；**67/67 的文件里没有任何日期/时间 token**（只含 `<odds issueNum="…">`） |
| 原始响应 vs CSV 记录数 | **0 处不一致**（逐文件重数 `<i>`；两个 `_call` 整期文件 149 / 40 条与其期次 CSV 合计完全相等）→ CSV 是原始 XML 的忠实投影，缺的不是解析 |
| 唯一时间证据 | 文件 mtime：**2026-09-22T15:02:23+08:00 … 15:05:16+08:00**（单一采集窗口） |
| 采集器是否落盘时间 | **没有**。`RawResponse.fetched_at` 在内存里存在，但 `write_raw()` 只写 `raw.text`，**该字段被丢弃** |

**这是本交付最关键的判定**：26087–26096 在 2026-09-22 15:04 之前**早已结算**（500 数据中 26096 最后停售 2026-09-20 11:05）。
因此这些期次的 `curr_*`（"即时"）只可能是**事后读取到的终态/归档值**；文件内没有任何证据能把它与收盘值区分开。
**不得把终态伪装成当时信息。** 期次 26097 的采集时刻 15:04 也**晚于 275 号交付自述的决策时刻 13:55** 69 分钟，
且 `inputs/26097_eu_odds.json` 中 slot 1/2 的状态已是 `中场`。

### 2.2 `inputs/eu_odds_26087_26095.csv` 的口径

| 列 | 含义（实测） | 决策时刻可用性 |
|---|---|---|
| `issue,slot,kick` | kickoff，**Asia/Shanghai 本地、无时区标记**（与 live DB `kickoff_ts` 在 26088 的 81/82 场完全一致） | 事件时间，非报价时间 |
| `eu_w/eu_d/eu_l` | 1634/1634 非空、0 解析失败，**但没有任何时间戳、没有原始响应** | **不可用**：无法证明任何 cutoff 之前存在 |
| `sp_at_2h_w/d/l` | "开赛前 2h"的 SP；**没有保留该行的时间戳**；8 行（全在 26087）为空串（缺失，非 0、非解析失败）；与 `sp_close` 不同的行有 1,547/1,626，故确为另一个状态 | **不可用**（除非能证明 cutoff < kick−2h；2h 是由 kick 推出的，不是观测到的） |
| `sp_close_w/d/l` | 收盘 SP；**`sp_ts_raw` 就是它的行时间** | **不可用**：收盘值 |
| `sp_ts_raw` | `MM-DD HH:MM`（11 字符），**无年份、无时区**，501 个不同值 | 诊断用 |
| `rows_after_kick` | 开赛后的变盘行数 | 诊断用 |

**`sp_close_*` 存在前视，实测确凿**：以 kick 的年份补全 `sp_ts_raw` 后，**602/1634 = 36.84%** 的收盘行时间 **晚于开赛**，
且 `rows_after_kick>0` 恰好也是 **602** 行（两者 0 矛盾）。按期次：26089 189/356、26094 159/383、26092 157/371、
26087 48/134、26093 19/94、26095 12/85、26091 10/129、26088 8/82。

**覆盖洞**：这 8 个期次的北单欧赔 fixture 共 **1,910** 场，`eu_odds` 只覆盖 **1,634** 场，**缺 276 场（14.4%）**，
其中 26087 只覆盖 134/340（缺 206）。

**provenance 洞（blocker）**：仓库内**没有任何代码**读写 `sp_at_2h_*` / `sp_close_*` / `rows_after_kick`
（`grep -rl "sp_at_2h" .` 只命中 `quarto/275_bj_decision_epoch_odds.qmd`）。275 号文档称来源是
nowscore `1x2/{matchid}.js`，但**仓库里不存在 `1x2.nowscore` 这个 endpoint**（`grep` 0 命中）。
该文件**无法重建、无法离线重放**。

### 2.3 唯一的多时点欧赔/大小球序列：不是 Nowscore，且只有相对时间

`data/derived/beidan_xlsm/beidan_xlsm.sqlite::market_snapshots`

| 事实 | 数值 |
|---|---|
| 市场 | `euro_1x2` **11,716,140** 行；`over_under` **14,059,368** 行；另有 asian_handicap / kelly_1x2 |
| 时点 | 仅 4 个**名义**标签 `{initial, 10h, 1h, final}`，每个 12,887,754 行 |
| 时间戳 | `market_snapshots` **没有任何时间列**。唯一时间样列 `matches.ts_10h` = **kickoff − 600 分钟，50000/50000 抽样完全精确** → **是算出来的网格标签，不是观测采集时刻**。`initial/1h/final` 连算出来的时间都没有 |
| 公司 | euro_1x2 15 家、over_under 18 家：香港马会/威廉/立博/皇冠/澳门/Bet365/Bwin/Pinnacle/竞彩足球… **没有一个是 Nowscore 公司代号** |
| 缺失 | over_under **3,869,072 行（27.5%）** 的 v1/v2/v3 至少一个为空；euro_1x2 **2,081,419 行（17.8%）** 不完整。列语义（v1/v2/v3）在库内无文档 |
| 覆盖 | 195,269 场 / 701 期（140101–25042，2013-12 … 2025-07） |
| 来源 | `source_meta.source_path` = `/mnt/c/Users/hhusl/Downloads/soccer lot/北单采集器/北单采集器/beidan.xlsm`（Windows 第三方采集器），`converted_at` 2026-06-25T02:22:22Z |
| 项目自身评级 | `results/bj236_eu_odds_timeseries_v1/COVERAGE_REPORT.json` 自述 `causal_grade = "RETROSPECTIVE_RELATIVE_PROXY"`、`strict_forward_rows = 0` |

→ 评级 **HISTORICAL_TIMESTAMP_PROXY_DIAGNOSTIC_ONLY**（诊断专用）。另注：`src/eu_odds_timeseries/source.py` 的
docstring 称该库是"declared Nowscore/Titan historical workbook"，**与库自身的 source_meta 不符**。

### 2.4 其它被核查并判为不足的材料

| evidence | 材料 | 为什么不足 |
|---|---|---|
| EV-15 | `500_bjdc::matches.avg_odds_*`（78,292 场） | 每场**一个**平均欧赔，无初盘、无序列 |
| EV-17 | `beidan_history.db::historical_matches.avg_eu_*`（38,422 行） | 同上；`scrape_log` 的 150 条 `fetched_at` **全部落在 2026-05-02 00:54:48–00:58:42**，只标定回填动作 |
| EV-18 | `beidan_features.db::matches.p_open_*/p_close_*`（190,511 行有开/收） | 两个**无时间**状态，且已转成概率 |
| EV-19 | `src/forward_snapshot/` | 一个**看起来正确**的 Nowscore 前瞻采集器（HKT/UTC、append-only、内容寻址原始体），但**磁盘上不存在任何 store 根**、`BEIJING_LOT_DATA_ROOT` 未设置 → **落盘 0 条** |
| EV-09 | `inputs/26097_results.csv` | 只有表头，**0 数据行**（空结果，不是解析失败） |
| EV-21 | `bj396_2025_settlement_backfill_v2/nowscore_probe_ledger.csv` | 真实的 Nowscore 抓取（`nowscore_captured_at_utc` = 2026-08-25T12:54:16+00:00、payload sha256），但内容是 2025 结算回填的身份/状态/SP，**不是欧赔或大小球** |

**明确回答"仓库或数据根里到底有没有 Nowscore 欧赔/大小球时间序列"：没有。**
已核查 `data/derived/`（`nowscore_only/`、`500_bjdc/`、`beidan_xlsm/`）、`data/cache/`、`results/`、
`src/titan_clean/`、`src/eu_odds_timeseries/`、`src/eu_proxy_backfill/`、`beidan_live.db`、`beidan_history.db`、
`beidan_features.db`、`500_bjdc.sqlite.bak`。`data/derived/nowscore_only/` 存的是**比分/其它玩法 SP 历史页**，
不含 1X2 欧赔或大小球盘口时间序列。

---

## 3. 代理等级（逐证据类）

| 等级 | 证据 |
|---|---|
| **OBSERVED_AVAILABILITY**（观测到采集时刻，可用于前瞻） | EV-11（500/zgzcw 平均欧赔轮询；**来源身份不满足 Nowscore 契约**）、EV-14（北单 SP）、EV-16（比分/总进球 SP） |
| **DOCUMENTED_CONSERVATIVE_BOUNDARY** | EV-10（采集器代码层面的保守边界：1x2 取 c0/c1/c3、大小球取 c1/c3；HK 盘 → 十进制 = hk+1） |
| **HISTORICAL_TIMESTAMP_PROXY_DIAGNOSTIC_ONLY** | EV-12 / EV-13（beidan_xlsm 4 名义时点，ts_10h 为计算值）、EV-20（项目自述 RETROSPECTIVE_RELATIVE_PROXY）、EV-21（真实 Nowscore 抓取但市场不对） |
| **INSUFFICIENT** | EV-01…EV-09、EV-15、EV-17、EV-18、EV-19 |

**保守性声明**：凡不能证明在决策 cutoff 之前已存在的，一律 **INSUFFICIENT** 或 **PROXY_DIAGNOSTIC_ONLY**，
**没有任何一项 Nowscore 证据被评为 OBSERVED_AVAILABILITY**。

---

## 4. 前 5 大证据缺口（精确数字）

1. **Nowscore 全类材料零时间戳** — 4 个解析 CSV + **67/67** 原始响应均无任何时间 token；`write_raw()` 丢弃 `fetched_at`。
   唯一时间是 mtime 窗口 **2026-09-22T15:02:23+08:00 … 15:05:16+08:00**（单一事后窗口）。
2. **`eu_odds` 收盘列前视** — **602/1634 = 36.84%** 的 `sp_close_*` 行时间晚于开赛（与 `rows_after_kick>0` 的 602 行零矛盾）；
   且 `eu_w/d/l` **1,634/1,634 行无时间戳**、文件**无生成器**。
3. **`beidan_live.db` 的 20:00 决策时刻覆盖不足** — **1,701/5,562（30.6%）** 候选 fixture-epoch 无盘前快照；
   按期次 **13.8%（26052）…100%**；**1,552/5,578（27.8%）** 场次首条快照晚于开赛；且 `source` 100% 为 `"merged"`。
4. **唯一多时点序列没有时间** — `market_snapshots` 无时间列，`ts_10h` = kickoff−600min **50000/50000** 精确 →
   计算值；`initial` 12,887,754 行无任何时间证据；`final` 12,887,754 行为收盘。
5. **Nowscore 期次与可核验期次几乎不重叠** — `beidan_live.matches` 覆盖 26051–26088（33 期），
   与 Nowscore 期次 26087–26097 只重叠 **26088** 一期（该期 81/82 场 kickoff 完全一致）。
   跨源核验只能做一期；26087、26089、26090–26097 在 live 库中**完全不存在**。

补充（非前五但需登记）：`eu_odds` 缺 **276/1,910（14.4%）** 场；期次 **26090 全缺**；
26097 的 c1/c14 只覆盖 **17/23** 场；`forward_snapshot` 落盘 **0** 条。

---

## 5. 与 275 号交付的差异（独立复核，未采信其叙述）

| 275 号原文 | 复核结果 |
|---|---|
| 第 25 行 "47 个原始响应" | **错**：`inputs/nowscore_raw/` 实为 **67** 个文件 |
| 第 729 行 "36.8% 的 SP 记录晚于开球" | **复现**：602/1634 = **36.84%** |
| 第 740 行 "33.5%（548/1634）的场次…开球后的变盘行" | **不能复现**：实测 **602/1634 = 36.84%**；548 与 `rows_after_kick>0`（602）及其它任何列都不吻合 |
| 第 745 行 欧赔来源 "nowscore 平均欧*" | 仓库内**不存在** `1x2.nowscore` 抓取代码；该 CSV 无生成器，来源**不可核验** |
| 第 30 行 决策时刻 2026-09-22 13:55 HKT | 26097 的 danchang 采集发生在 **15:04 +08:00**（mtime），**晚 69 分钟** |

另：275 号文档第 6 条评审发现（"决策面向机制没有 cutoff 强制"）为 **NOT FIXED**，本审计独立证实该缺口成立且更严重
——不仅缺 cutoff 强制，**连 cutoff 所需的可得性证据本身都不存在**。

---

## 6. 复现命令

工具链：`.venv/bin/python`（Python 3.14.4）、`Rscript`（R 4.6.1）。**未联网、未运行采集器、未安装任何包、未改动任何既有文件。**
所有表由两个 stdin heredoc 程序生成（按任务限制，未在仓库落任何脚本文件；生成逻辑即下表命令）。

**表 → 命令对照**

| 表 | 命令 |
|---|---|
| `coverage.csv`（EV-01…EV-21 逐来源/逐期次 + EV-11 逐 epoch 182 行） | 程序 (1) + 程序 (3)；核心查询：`select issue,count(*),count(distinct slot) from danchang_1x2` 等价于 python `csv.DictReader` 聚合；epoch 行由 `select issue,match_id,match_idx,kickoff_ts from matches` 与 `select match_id,snapshot_ts,eu_h from snapshots order by match_id,snapshot_ts` 逐场计算 |
| `companies.csv` | 程序 (1)：`Counter(company)` over 4 个 CSV；`select market,bookmaker,count(*) from market_snapshots group by 1,2` |
| `timestamps.csv` | 程序 (1)：CSV 表头检查 + `grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}:[0-9]{2}:[0-9]{2}|timestamp|date=' inputs/nowscore_raw/*.xml`（0 命中）+ `stat -c '%y %n'` |
| `gaps.csv` | 程序 (2) |
| `exclusions.csv` | 程序 (2) |
| `source_hashes.csv`（97 项） | 程序 (2) 对小文件用 `hashlib.sha256`；7 个 GB 级库用 `sha256sum` |
| `MANIFEST.json` / `SHA256SUMS.json` | 程序 (2) + 程序 (3) |

**逐条可复制的命令**

```bash
# 1. 原始响应里到底有没有时间戳（0 命中 = 没有）
grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}:[0-9]{2}:[0-9]{2}|timestamp|date=' inputs/nowscore_raw/*.xml

# 2. 每个原始响应的记录数（与解析 CSV 逐文件比对；0 处不一致）
for f in inputs/nowscore_raw/*.xml; do printf '%s %s\n' "$(basename $f)" "$(grep -o '<i>' $f | wc -l | tr -d ' ')"; done

# 3. 唯一的时间证据：文件 mtime（单一采集窗口）
stat -c '%y %n' inputs/nowscore_raw/*.xml inputs/*.csv inputs/*.json inputs/*.rds

# 4. 采集器是否落盘 fetched_at
grep -n 'fetched_at' src/nowscore_danchang_odds.py            # 只在内存 dataclass 上
grep -n 'def write_raw' -A 8 src/nowscore_danchang_odds.py    # 只写 raw.text

# 5. live DB 的 eu_* 来自哪里（确认非 Nowscore）
grep -rn -i nowscore src/live_collector/                      # 0 行
grep -n 'http' src/live_collector/scraper.py                  # trade.500.com / zx.500.com / cp.zgzcw.com / live.500.com
sed -n '195,205p;300,312p' src/live_collector/parser.py        # .pjoz 与 #esp_N 写 eu_h/d/a

# 6. eu_odds 没有生成器
grep -rl 'sp_at_2h' . --exclude-dir=.git --exclude-dir=r_lib   # 只有 quarto/275_bj_decision_epoch_odds.qmd
grep -rn '1x2.nowscore' --include=*.py --include=*.R .          # 0 命中

# 7. forward_snapshot 有没有落盘
grep -n 'BEIJING_LOT_DATA_ROOT' -r src/forward_snapshot/       # 环境变量，本机未设置
find /home/drwho1985/beidan-lot-runtime -iname '*forward*'      # 0 命中（等价：find $DATA_ROOT）

# 8. 大文件哈希
sha256sum data/derived/500_bjdc/500_bjdc.sqlite.bak data/derived/beidan_xlsm/beidan_xlsm.sqlite \
          data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite data/beidan_live.db \
          data/beidan_history.db data/beidan_features.db data/raw/beidan.xlsm

# 9. R 侧（读取派生 rds 的列与维度）
Rscript --vanilla -e 'x<-readRDS("inputs/26097_open_legs.rds"); print(dim(x)); print(names(x))'
```

**程序 (1) / (2) / (3) 的关键内核（全部经 `.venv/bin/python` 以 stdin heredoc 执行，只读 `file:…?mode=ro` 打开 SQLite）**

```python
# (a) eu_odds 前视判定：rows_after_kick 与 sp_ts_raw>kick 是否一致
def pt(s, ref):                      # "MM-DD HH:MM" -> datetime，年份由 kick 推断
    mm, dd = s.split(' '); mo, da = map(int, mm.split('-')); h, mi = map(int, dd.split(':'))
    for y in (ref.year, ref.year-1, ref.year+1):
        try: return dt.datetime(y, mo, da, h, mi)
        except ValueError: pass
after = sum(1 for r in eu if pt(r['sp_ts_raw'], pk(r['kick'])) > pk(r['kick']))   # -> 602
crosstab = collections.Counter((int(r['rows_after_kick']) > 0, pt(r['sp_ts_raw'], pk(r['kick'])) > pk(r['kick'])) for r in eu)
# -> {(False, False): 1032, (True, True): 602}   零矛盾

# (b) 20:00 Asia/Shanghai (=12:00Z) 决策时刻覆盖
kick_utc = dt.datetime.fromisoformat(kickoff_ts).replace(tzinfo=HKT)   # kickoff_ts 是北京本地 naive
E = dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC)
candidates = [m for m in issue_matches if E <= m.kick_utc < E + dt.timedelta(hours=24)]
pre = [t for t, eu_h in snapshots_of(match) if t <= E and eu_h is not None]
lag_min = (E - max(pre)).total_seconds() / 60.0
# -> candidates 5562, with-pre 3861 (69.4%), without-pre 1701

# (c) xlsm 的 ts_10h 是计算值还是观测值
round((dt.datetime.fromisoformat(kickoff_ts) - dt.datetime.fromisoformat(ts_10h)).total_seconds()/60.0)
# -> Counter({600: 50000})   50000/50000 精确等于 kickoff-10h
```

**已知不可判定项（unknown，不猜）**

- 期次 26090 是"从未开出"还是"请求失败"——无文件、无失败日志。
- 各期次 `init_*` / `curr_*` 的绝对报价时刻——只剩 mtime，而 mtime 是文件系统产物。
- 26087–26096 的 `curr_*` 是否等于收盘值——离线无法检验，文件内也无证据。
- `beidan_live.db` 每行快照的上游身份（`source` 恒为 `"merged"`）。
- `inputs/eu_odds_26087_26095.csv` 的真实来源（仓库内无生成器）。
- beidan.xlsm 除 10h 网格点以外的快照实际时刻。

---

## 7. 对 N7 的直接含义（路由建议，不改变 Issue Graph）

1. **N7 的"决策时刻 Nowscore 欧赔 + 大小球"输入目前不存在**。任何依赖它的回溯标定都只能拿到**单点事后状态**，
   必须显式登记为回顾性诊断证据，不得用于 26098+ 的实际选场。
2. 若必须推进，**唯一可用的决策时刻可得序列是 EV-11（500.com/zgzcw 平均欧赔）**，但它**不满足"Nowscore"这一来源契约**，
   且 20:00 epoch 覆盖只有 69.4%（期次最低 13.8%）。用它就要**改契约**（明确写"允许 500.com 平均欧赔"），
   不能靠文档把 Nowscore 的缺口说成已解决。
3. **`src/forward_snapshot/` 是唯一现成的 Nowscore 前瞻采集机制**，已具备 HKT/UTC 时间与 append-only 存储；
   它只能产生**未来**的证据，**无法补历史**。要恢复"决策时刻可得性"，必须现在就让它跑起来并落盘 receipt。
4. `inputs/eu_odds_26087_26095.csv` 在补上生成器、原始响应与带年份/时区的行时间之前，**不应作为证据进入任何 cutoff 收据**。
