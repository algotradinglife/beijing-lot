# #493 离线核验:Titan 多公司均值能力与来源切换(只读)

**核验日期**:2026-09-23
**核验方式**:**只读**,未发起任何新采集请求,未写入 `data/`,未改动 GitHub 图状态。
**触发**:PI 评论 2026-09-23T07:38:43Z。

## 0. 方法与边界

本文只回答 PI 指定的五个问题,以及两处需要**分开处理**的事项。所有结论都标注了
**证据类型**:实测(`OBSERVED`)、代码/契约文本(`DECLARED`)、或未证实(`UNVERIFIED`)。

**不构成**:不构成来源切换决议,不构成合同变更,不解除 #493→#494 依赖。

## 1. 文档对应的原生 issue/PR 及当前状态

PI 提到的 `docs/operations/nowscore-retirement-titan-continuation.md`(位于
`beijing-lot-market-odds`)**在该工作区是未跟踪文件**:

| 项 | 状态(`OBSERVED`) |
|---|---|
| 该文档 `git ls-files` | **未跟踪**(untracked) |
| 该工作区当前分支 | `feat/market-odds-parser-closure`(**无 upstream**) |
| 与 `origin/main` 的关系 | **HEAD 不在 `origin/main` 上**(`git merge-base --is-ancestor` 为假) |
| 远端分支中承载 Titan 快照工作的分支 | **0 个**(`git branch -r --contains` 为空;两次观测远端分支数分别为 **172** 与 **176** —— 观测时刻不同,**均无命中**) |
| 从该分支发起的 PR | **0 个**(`gh pr list --head` 为空) |
| `src/market_odds_serving.py`、`registry/market-odds-snapshot-and-storage-v1.json` | 在工作区存在,**registry 未跟踪**;`market_odds_serving.py` 不在 `origin/main` |
| `src/titan_clean/snapshots.py` | **在 `origin/main` 上**,但 main 版本 `SNAPSHOT_KINDS = ("initial","final","10h","1h")` —— **不含 `prev_day_2000`**(main 中该串出现 **0** 次;工作区版本 **4** 次) |

**结论(有界表述)**:在**下述检索覆盖范围内**,**未找到**该文档所述能力的原生载体:

**检索覆盖范围(如实列出,不超出)**:

| 检索 | 命令/方法 | 覆盖 |
|---|---|---|
| 承载该分支的远端分支 | `git branch -r --contains <HEAD>` over **176** 个远端分支(另一时刻观测为 **172**) | 全部远端分支 |
| 该分支的 PR(任意状态) | `gh pr list --state all --head feat/market-odds-parser-closure` | 指定 head 分支 |
| 相关 issue | `gh issue list --state all --search "market odds serving" / "盘口 服务库" / "titan 欧赔"` | GitHub 搜索索引 |
| 该工作区 | `git ls-files` / `git merge-base --is-ancestor` | 本地工作区 |

**该检索不能证明**:不存在承载同类能力的**其它分支或已关闭 PR**;
不存在**表述不同因而未被上述关键词命中**的 issue。
因此这是一个**有界检索结果(`OBSERVED_BOUNDED`)**,**不是**"绝对不存在"的断言。

**仍然成立的结论**:该能力**尚未落到 `origin/main`**(`merge-base --is-ancestor` 为假),
且**该文档本身是未跟踪文件**。按 AGENTS.md「Bodies, comments, labels, chat, and local
files cannot override or reconstruct graph state」,**该文档不能替代原生图状态**,
**也不能自动变更 #493 合同**。

最接近的原生载体是 **#464**(Operations: 采集运行时栈入库)及其 PR **#475**
(`codex/464-runtime-stack` → `main`,OPEN),它确实包含 `src/titan_clean/*` 与
`tests/titan_clean/test_snapshots.py`;但 **#475 不包含 `src/market_odds_serving.py`**,
也不包含 `MEAN_ALL` 共识服务。**#464 的图边为空**(无 `blockedBy`/`blocking`/`subIssues`/`parent`)。

## 2. 权威服务库/版本与数据契约

| 项 | 值 | 证据 |
|---|---|---|
| 控制库 | `/run/media/drwho1985/Sandisk/data/beijing-lot/clean_v1/control/titan/control.sqlite`(**107,325,014,016 字节**) | `OBSERVED` |
| `schema_meta` | `titan_clean_control_v1` / `PRIMARY_FEATURE` / `titan` | `OBSERVED` |
| 欧赔长表 | `historical_euro_1x2_quote`,主键 `(batch_id, record_source_id, ordinal)` | `OBSERVED` |
| 共识服务 | `src/market_odds_serving.py`,`SERVING_SCHEMA = 'market_odds_serving_v1'`,`CONSENSUS_POLICY = 'MEAN_ALL'` | `DECLARED` |
| 服务契约 | `docs/research/market_odds_serving_contract.md`(589 行) | `DECLARED` |

**契约关键条款**(第 5、6 节):

- **四态缺失语义**:源未采 / 源站无值(`status='ABSENT'`)/ 解析失败(**不得写入本库**)/ 不适用。
  **禁止**用 `0` 或空串表示缺失,**禁止**用平均填补缺失。
- **A-1**:`availability_boundary_at_utc` = 参与公司 `trusted_received_at_utc` 的**最大值**。
- **A-3**:前瞻使用必须满足 `availability_boundary_at_utc < decision_at_utc`,否则 fail closed。
- **A-4**:首版全部产出标记 `HISTORICAL_PROXY` 且 `prospective_use = 0`。
- **A-5**:源站时间按 naive `Asia/Shanghai` 解析,入库转 UTC 带 `Z`。

## 3. #493 样本映射与 `prev_day_2000` 覆盖

### 3.1 样本映射:**零命中**

`#493` 探针样本(`results/n7_493_probe_sample_v1/`,50 行:`sample_primary24.csv` 24 行 +
`sample26.csv` 26 行)的 `provider_match_id` 在 Titan 观测表中**映射成功 0/50**。

原因(`OBSERVED`):

| 维度 | #493 样本 | Titan 欧赔库 |
|---|---|---|
| `provider_match_id` 范围 | 2,912,857 – 3,061,587 | **253,266 – 2,655,951** |
| 开赛年份 | 2026 | **2010–2024（全 15 年,逐年均有）**;2026 年 **0 场** |

`historical_fixture_observation` **全表 250,166 条**的开赛年份分布（`OBSERVED`,全量枚举）：

| 年 | 场次 | 年 | 场次 | 年 | 场次 |
|---|---|---|---|---|---|
| 2010 | 14,120 | 2015 | 18,368 | 2020 | 11,913 |
| 2011 | 16,356 | 2016 | 18,778 | 2021 | 18,840 |
| 2012 | 17,309 | 2017 | 19,450 | 2022 | 16,686 |
| 2013 | 18,597 | 2018 | 18,388 | 2023 | 15,716 |
| 2014 | 17,373 | 2019 | 18,062 | 2024 | 10,210 |

> **修正留痕**：本文初稿据 **前 3,000 行**抽样声称年份仅 2010/2011/2019/2020。
> 该抽样**恰好落在早期批次**，**不足以刻画全表**。经全量枚举更正为上表。
> 样本非重叠结论（2026 = 0 场）**不受影响**，但年份范围的表述已更正。

**结论**:Titan 欧赔库与 #493 样本所在赛季**id 区间不重叠、年份不重叠**。
**不能**把 Titan 欧赔库当作 #493 样本的直接替代输入。PI 所述"既有映射桥直接可用"
在**本样本上未被证实**。

### 3.2 `prev_day_2000` 覆盖:**能力已验证,但仅限欧赔**

代码路径 `src/titan_clean/snapshots.py::previous_day_slice` 语义为
**目标时刻之前的最新值(fail-closed)**,目标 = 开赛日**前一天**的 20:00(naive Shanghai,即 12:00Z)。

实测(`OBSERVED`,只读,无新采集):

| 检验 | 结果 |
|---|---|
| 3 场样本切片产出 | `initial`/`final`/`10h`/`1h`/`prev_day_2000` **五类均产出** |
| 40 场不变量校验 | `prev_day_2000` 行 **9,148** 条,**违反 0 条**(严格早于目标、且严格早于开赛) |
| 无 `prev_day_2000` 行的场次 | **0 / 40** |

**可复放证据**:上述测量由 `.tmpwork/titan_inv.py`(核验脚本,随本次交付保留)产出,
其**唯一输入**为只读控制库与兄弟工作区的
`src/titan_clean/snapshots.py`,**无网络**。复放方式:

```bash
.venv/bin/python .tmpwork/titan_inv.py     # 见下方"输入绑定"
```

**输入绑定**(核验时的取值):

| 项 | 值 |
|---|---|
| 控制库 | `/run/media/drwho1985/Sandisk/data/beijing-lot/clean_v1/control/titan/control.sqlite` |
| 库大小 | `107,325,014,016` 字节 |
| `snapshots.py` | 兄弟工作区 `beijing-lot-market-odds`,非 main 版本 |
| 抽取范围 | `limit=40`(按 `source_fixture_id` 升序的前 40 场) |
| 期望输出 | `fixtures 40 ... invariant violations 0`;切片计数 **9,148** |

**未绑定**:本文**未**记录那 40 个 `source_fixture_id` 的字面清单,也未把控制库
`sha256` 写入交付 —— 因此该测量**可复放但不可逐字节比对**。
若需独立复核,**请以 `limit=40` 重跑并比对上述三个数字**。

**`snapshots.py` 模块本身在 main 上存在**(`git cat-file -e origin/main:src/titan_clean/snapshots.py` 成立);
**不在 main 上的是 `prev_day_2000` 这一能力** —— main 版本的
`SNAPSHOT_KINDS = ("initial","final","10h","1h")`,该串在 main 中出现 **0** 次。
因此这是**工作区新增能力**,不是已合并能力。

### 3.3 ⚠️ 该模块内部存在**时区口径矛盾**(新发现,本次核验范围内未解决)

代码注释与 receipt 声称市场时间是 **naive `Asia/Shanghai`**,同时 `kickoff_at_utc()`
声称 **kickoff 字面量已是 UTC**。但 `previous_day_slice()` **直接取 kickoff 字面量的
日历日**,**未做 UTC→Shanghai 转换**:

```python
def previous_day_slice(kickoff: datetime) -> datetime:
    day = kickoff.date() - timedelta(days=1)   # 取的是字面量自己的日期
    return datetime(day.year, day.month, day.day, _PREV_DAY_SLICE_HOUR, 0)
```

**实测反例**(`OBSERVED`):

| 输入 kickoff 字面量 | 解析结果 | `kickoff_at_utc()` | `previous_day_slice()` |
|---|---|---|---|
| `2020,1-1,01,18,00,00` | `2020-01-01 18:00` | `2020-01-01T18:00:00Z` | **`2019-12-31 20:00`** |

若 kickoff 字面量确为 UTC(如 `kickoff_at_utc()` 所声明),则该场次在上海时区是
**2020-01-02 02:00**,其"前一天 20:00(北京)"应为 **2020-01-01 20:00**;
代码返回 **2019-12-31 20:00**,**差了整整一天**。

**因此**:该模块**不能同时**满足"kickoff 为 UTC"与"prev_day_2000 为北京前一天 20:00"
两种声明,必有其一错误。**本次核验不裁决哪一方错误**——这需要 Titan 源方证据;
但该矛盾**必须由该模块的持有者解决**,在此之前 `prev_day_2000` 的**语义不可依赖**。

> 受影响范围:凡 kickoff 落在 **16:00–24:00 UTC** 的场次(即北京次日 00:00–08:00),
> 其 `prev_day_2000` 切片日期可能整体偏移一天。§3.2 的"违反 0 条"检验**只验证了
> 切片早于目标**,**不验证目标日期本身是否正确**,故**不能**排除该缺陷。

## 4. 欧赔共识的固定成员及缺失规则

| 项 | 状态 |
|---|---|
| 政策标识 | `MEAN_ALL`(全体算术平均)—— **已在契约登记** |
| **固定成员集合** | **未固定**(`UNVERIFIED`) |
| 实际聚合范围 | 对**所有**参与公司取均值 |

**这是本文最重要的口径分歧。** 文档写"共识值取**权威公司集合**的均值,`src/market_odds_serving.py`
已实现";但**代码实现的是全体均值**:

```python
# src/market_odds_serving.py::euro_consensus_rows
for row in snapshot_set.rows:
    if row.home_odds is None or ...: continue
    by_kind[row.kind].append(row)      # 无成员过滤
ws = [r.home_odds for r in companies]
out.append(dict(..., odds_w=sum(ws) / len(ws), ..., company_count=len(companies)))
```

代码内搜索 `AUTHORITATIVE` / `member_set` / tier 常量:**0 处**。
`registry/market-odds-snapshot-and-storage-v1.json` 自己把这一点列为 **`open_item`**:

> "Tier is not yet fixed: 5 companies (\*\*\*\*\*) vs 9 companies..." —
> `required_before_use`: "Fix the member set, record which members contributed per
> snapshot, and never let a missing member silently change the basis."

**实测佐证规模**:单个场次内 `company_source_id` 去重为 **294** 个,文档所称"一个批次 179 家公司"
亦在另一场次复现。**294 家全量均值 ≠ 5/9 家权威均值**,两者是**不同的口径**,
必须**分开处理**。

**缺失规则**(契约 A-2 与代码一致):某切面**无任何参与公司**时写 `status='ABSENT'`,
`odds_*` 为 `NULL`,`company_count=1`;有参与公司时 `company_count` = 实际参与数。
**缺失成员会静默改变均值基准**——这正是 registry `required_before_use` 禁止的。

**另需注意**:文档称 Titan 的 `companyid` 体系与 Nowscore **完全相同**
(`47`=平* 等)。实测**不支持**该等价:Titan 库内 `47` 在该场次**无任何行**,
而 Pinnacle 实为 `177`(**Pinnacle Sports**)。**两个 id 空间存在分歧**,
不能把 Nowscore 的 id→公司映射直接套用到 Titan。

## 5. 大小球是否有 20:00 前带时间历史

**结论:在本核验所及的欧赔控制库中不存在大小球历史表(`OBSERVED`)。**

| 检验 | 结果 |
|---|---|
| 控制库全部表名 | 14 张,**无** over/under / total 表 |
| `historical_aux_capture.endpoint_kind` CHECK 约束 | 仅允许 `'analysis'`、`'handicap'` —— **无 over/under 取值** |
| 该表行数 | `analysis` 171 + `handicap` 170 = **341 行**(相对欧赔 250,166 场) |
| 任何表结构含 over/under/total 关键字 | **无** |

因此,**大小球是否存在 20:00 前带时间历史,在本核验范围内无法证实**,
且**初值/终值不能替代**——它们不带 as-of 语义,取"最接近 20:00 的一侧"
会用到 20:00 时尚不存在的报价(前视泄漏)。

服务层 `TOTAL_SNAPSHOT_KINDS = ('initial','final')`,即大小球**只发初/终两切面**,
**不发** `10h`/`1h`/`prev_day_2000`——与上述一致。

## 6. 对文档两处规模声明的独立核验

| 声明 | 核验结果 |
|---|---|
| **250,166 场次** | **证实**:控制库捕获表实测 **250,166** 行(`OBSERVED`) |
| **5.3 亿行** | **部分印证,未逐行证实**:对前 200 场次实测均值 **1,817.3** 行/场 × 250,166 ≈ **4.55 亿**。量级一致,但**未做全表 count**(库 107 GB,`dbstat` 不可用,全扫超出本次只读核验预算)。**不作为已验证事实** |
| **179 家公司** | **证实**:单场次实测去重公司数达 294,文档所称一个批次 179 家在另一场次复现(`OBSERVED`) |
| **Titan `companyid` 与 Nowscore 相同** | **不支持**:见 §4 末尾(`47`≠平*) |

## 7. 原始字节保留:治理差异,不由本地文档覆盖

文档第 81 行提出"**原始字节不保留**",并以 `registry/market-odds-snapshot-and-storage-v1.json`
的 `raw-retention` 决策为依据。核验如下(**分开陈述,不合并判断**):

| 项 | 事实 |
|---|---|
| 该 registry 的**授权依据** | `"basis": "owner standing instruction for this project: one serving SQLite per line, modelled on the settlement reference database"` |
| 该 registry **自身状态** | **未跟踪文件**(`git ls-files` 为空),**不在 `origin/main`** |
| Titan 控制库**元数据** | `historical_fixture_capture.raw_path` + `raw_sha256` 均为 `NOT NULL`,且 `clean_v1/raw/` 目录确实存在 |
| 本任务(beijing-lot)`AGENTS.md` 条款 | 「**Preserve original bytes**, encoding, source identity, and collection timestamps separately from cleaned data」「**Preserve raw responses for offline parsing replay**」 |

**处置**:
1. 该决策声称的依据是**"owner standing instruction"**——但**本次核验未找到指向该指令的
   原生 issue/PR/comment 记录**(见 §1:该分支无 PR,远端分支检索无命中;**该检索为有界结果**)。
2. `raw-retention` 决策的 `open_item` 自己写明:"**The capture table must be populated
   from the capture the build already reads, and its presence in the released database
   verified BEFORE any raw deletion.**" 该前置条件**未见核验记录**。
3. 该 registry 是**未跟踪的本地文件**,按 AGENTS.md **不能覆盖**已发布的治理条款。

**关于"实际保留"的证据强度(自我更正)**:本节初稿把
"`raw_path`/`raw_sha256` 非空 + 目录存在"当作"**保留原始字节**"的证明。
这**不充分** —— 二者只证明**元数据与目录**存在,**不证明被引用的文件仍在**、
也不证明其**内容与记录的 `sha256` 相符**。本次核验**未**逐条抽取 `raw_path` 并校验哈希,
因此准确的表述是:**控制库保留了指向原始字节的元数据,字节本身的存在性与一致性未核验**。

**因此**:不依据该本地文档改写 #493 的原始数据保留要求。**来源切换 ≠ 保留条款变更**,
两者必须分开裁决。**请 PI 出具对应的已授权决策及其适用范围**,否则应保持现有条款。

## 8. 时区线索清单(选项 C,只读盘点)

PI 要求:"列出既有页面/代码中的时区线索;诊断性的年份/时区假设须单独标注;
不得因 PI 点名某个时区就升级证据等级。"

### 8.1 市场线(beijing-lot-market-odds)已有明确时区主张

| 位置 | 线索 | 类型 |
|---|---|---|
| `src/titan_clean/snapshots.py:128` | 注释:kickoff 字面量**已是 UTC**;market 时间是 naive `Asia/Shanghai` | `DECLARED` |
| `src/titan_clean/snapshots.py:129` | **独立交叉验证**:场次 `356276/356278/357841` 的字面量字段与欧赔页自身 `kickoff_utc` **完全相等**;若对 kickoff 施加上海偏移,会把每个已发布开赛时间**提前 8 小时** | `DECLARED`(有具名场次) |
| `src/titan_clean/snapshots.py:235` | receipt `source_timezone = "Asia/Shanghai"` | `DECLARED` |
| `tests/titan_clean/test_snapshots.py:322` | 同一 356276/356278/357841 验证在测试中复述 | `DECLARED` |
| `docs/research/market_odds_serving_contract.md:277` | **A-5**:源站时间按 naive `Asia/Shanghai` 解析 | `DECLARED` |

**强度评估**:这是**具名场次的对照校验**(三个场次、两个独立解析路径),强于纯假设,
但仍属 `DECLARED`——**未**在本次核验中重新独立复核那三个场次。
**不应据此把 #493 的 `TZ_UNDECIDED` 直接改写为已决**。

### 8.2 #493 探针自身的时区状态(**保持独立标注**)

| 项 | 状态 |
|---|---|
| `TZ_UNDECIDED` | **维持**。Nowscore 外壳页**无任何时区声明** |
| `YEAR_ASSUMED = 2026` | **维持为假设**。页面时间戳无年份 |
| `TZ_ASSUMED = "UTC+8"` | **维持为诊断假设**,字段名已含 `ASSUMED` |
| 两市场回溯时间戳差异(欧赔 19:02 / 大小球 18:30) | **维持为回溯记录差异**,不据此断言当时可得性 |

**关键区分**:市场线的 `Asia/Shanghai` 主张**针对 Titan 源**,
#493 探针的 `UTC+8` 是**针对 Nowscore 源**。**两者是不同来源的证据**,
**不能互相移植**。PI 点名某时区**不构成**证据升级。

## 9. 三件事的分开处理(按 PI 要求)

| # | 事项 | 当前状态 | 未决之处 |
|---|---|---|---|
| 1 | **来源切换**(Nowscore → Titan) | 已有本地文档与实现;**已列明检索范围内未找到原生图载体**(有界结论,见 §1) | **未找到** issue/PR;**不能**由本地文档自动变更 #493 合同 |
| 2 | **固定多公司聚合口径** | `MEAN_ALL` 已登记;但**成员集合未固定** | 代码实为**全体 179/294 家均值**,非"权威集合";5 家 vs 9 家**未决**;缺失成员会静默改变基准 |
| 3 | **历史可用性证据** | `prev_day_2000` 能力**已在本工作区验证**(40 场 / 9,148 行 / 0 违反);**仅限欧赔** | 大小球**无带时间历史表**;源报价时间**仍不等于当时观测可用时间**;`HISTORICAL_PROXY`、`prospective_use = 0` |

## 10. 未决项(供 PI 裁决,不自行决定)

1. **原生载体**:是否为该 Titan 共识/快照能力建立原生 issue,并把 `registry/market-odds-snapshot-and-storage-v1.json`
   纳入版本控制?当前它**未跟踪**。
2. **成员集合**:5 家还是 9 家?**定下来之前,"平均"一词在本仓不可用于指代该服务输出**
   ——它当前是全体均值。文档样本仅 2 个场次,不足以定论。
3. **#493 映射**:Titan 欧赔库与 #493 样本**零重叠**;"既有映射桥直接可用"**未证实**。
   若要对接,**需要另一批覆盖 2026 赛季的 Titan 捕获**——本次不请求。
4. **保留条款**:请出具 `raw-retention` 决策所依据的**已授权决策及其适用范围**。
5. **大小球历史**:本核验范围内**无**带时间历史表;不能以初/终值替代。

## 11. 边界声明

- 本文**只读**:**未发起任何源站采集请求**;**未写入 `data/`**;**未修改 GitHub 图状态**(仅读);
- 核验原生载体时使用了**只读的 GitHub API 与 `git` 查询** —— 这些**是网络请求**,
  故**不**笼统声称"无网络"。声明本身**不能回溯证明**未发生写入或图变更;
  未启动 #494;未关闭或合并任何 issue/PR。
- `UNVERIFIED` / `DECLARED` 项**不因本文出现而升级为已证实**。
- **源报价时间不自动等于当时观测可用时间**——该原则在本文所有可用性表述中维持。
