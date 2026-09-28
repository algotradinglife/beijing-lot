# 盘口数据服务契约(草案)

> **状态:`DRAFT` / 未生效。**
> 按 `AGENTS.md`,契约归 PI 所有。本草案待 PI 审阅并经 Issue Graph 立项后生效;
> 在生效前,任何实现不得以本文件作为验收依据。
>
> 依据来源(均为实测,非推断):
> `src/titan_clean/store.py` 的权威 DDL、`src/titan_clean/snapshots.py` 的切面语义、
> `r/n7_market_projection.R` 的消费入参契约、
> `docs/research/titan_clean_database_contract.md` 的源角色与物理隔离要求。

---

## 1. 范围

本契约定义一个**面向算法调用的盘口服务库**,内容为 Titan 盘口:

| 市场 | 内容 | 覆盖 |
|---|---|---|
| `euro` | 欧赔 1x2(W/D/L) | 250,166 场次(已采) |
| `total` | 大小球(盘口线 + 大球/小球赔率) | 79,404 场次(已采,占欧赔场次的 31.7%) |

**非目标**:不采集、不扩覆盖、不合并结算标签、不作历史学习拟合/校准/下注。
结算线(`trusted_500_settlement`)与身份发现线保持独立,不在本契约内。

---

## 2. 已定决策(前置)

| # | 决策 | 取值 |
|---|---|---|
| D1 | 数据内容 | Titan 欧赔 + 大小球(不含北单玩法 SP、不含基本面) |
| D2 | 覆盖 | 只做已采到的 250,166 场次;扩覆盖另行立项 |
| D3 | 原始字节 | 归档为 `.tar.zst` + 写退役台账,**不删除** |
| D4 | 报价粒度 | 明细保留时序;**服务库内**只物化 cutoff 快照切面 |

---

## 3. 物理布局与隔离

契约要求 Titan / settlement / external-ID discovery **物理隔离**
(`titan_clean_database_contract.md`)。

```
$BEIJING_LOT_DATA_ROOT/clean_v1/
├── control/titan/control.sqlite          # 明细权威源(本契约的输入,非输出)
├── raw/titan/                            # 原始字节(归档后改为 *.tar.zst)
├── control/id_discovery_*/               # 身份发现,独立
└── control/settlement_500/               # 结算,独立
```

服务库(`market_odds_v1.sqlite`)**不得**与 settlement 或 discovery 库同文件,
并且**不得**包含任何结算标签列。建议置于
`clean_v1/control/titan/market_odds_v1.sqlite`,与明细同域但独立文件。

**消费者隔离要求**:仅需盘口特征的读取器必须能在**不挂载 settlement 库、
不持有 500/Nowscore 凭据**的条件下运行。

---

## 4. 表定义

所有时间列均为 **UTC 的 ISO-8601 文本**(带 `Z`),不用本地时间;
所有标识符列为 **TEXT**(保留前导零,不做数值转换);
所有比率列为 **REAL**;`NULL` 与空字符串的语义见第 5 节。

### T1 `market_fixture` — 场次身份(一次一行)

| 列 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `fixture_id` | TEXT | 否 | Titan 场次标识(= 明细库 `source_fixture_id`,URL 中的数字)。**主键** |
| `capture_batch_id` | TEXT | 否 | 指向明细库 `historical_fixture_capture.batch_id`,唯一键,用于回连可用性 |
| `kickoff_source_raw` | TEXT | 是 | 源站原始开赛时间串(**不解析、不改写**),诊断用 |
| `kickoff_at_utc` | TEXT | 是 | 由 `kickoff_source_raw` 依 `snapshots.py` 规则解析所得;**`HISTORICAL_PROXY`** |
| `home_team_source_id` | TEXT | 是 | 源站主队标识 |
| `away_team_source_id` | TEXT | 是 | 源站客队标识 |
| `competition_source_id` | TEXT | 是 | 源站赛事标识 |
| `euro_available` | INTEGER | 否 | `1/0`,是否存在可用欧赔切面 |
| `total_available` | INTEGER | 否 | `1/0`,是否存在被采到的大小球 |

**关系基数**:`market_fixture` 1 : 0..4 `euro_consensus_snapshot`;
1 : 0..`total_quote_snapshot`(大小球按公司 × 切面)。
`fixture_id` 唯一;`capture_batch_id` 唯一且非空。

> **注**:实测明细库中 `historical_fixture_capture` 的 `batch_id` 与场次 **1:1**
> (250,166 行 / 250,166 个 distinct `batch_id`)。本表沿用该基数,
> 并在校验中断言 `count(*) = count(distinct capture_batch_id)`。

### T1.1 键设计 —— 服务库**禁止**沿用明细库的字符串复合键

实测明细库 `historical_euro_1x2_quote` 的 `batch_id` 形如

```
historical:2026-08-29T11:55:35Z:1784028     # 39 字符
```

它同时是**唯一索引的首列**(`PRIMARY KEY(batch_id, record_source_id, ordinal)`)。
在 530,036,350 行上,这个字符串在每个行版本里被重复存了两次
(b-tree 表体 + 索引),按实测的 ~200 B/行 计算,它单独占据约 **40 GiB**,
即该表体积的 **40% 以上** —— 而它承载的信息(场次身份)只有 250,166 个取值。

因此契约要求:

- **K-1** 服务库所有事实表使用 **INTEGER 代理键**指向 `market_fixture`。
  任何事实行**不得**存储 `batch_id` 字符串。
- **K-2** `market_fixture.batch_id` 字符串只在本表存一次(250,166 行),
  作为回连明细库的外键,并附唯一索引。
- **K-3** `bookmaker_source_name` 同理由 `euro_consensus_snapshot` 移出;
  需要公司名时经公司维表解析。
- **K-4** `home_kelly` / `draw_kelly` / `away_kelly` 三列在服务库中**不保留**
  (3 × REAL = 24 B/行)。若日后需要,由**明细库**重新投影,不进服务库。

> 说明:K-4 是可逆的,因为明细库在归档后仍可还原(见 D3)。
> K-1 的关键性远高于 K-4 —— 前者省的是 40 GiB 量级,后者是 12 GiB 量级。

### T1.2 量级预算(供落盘方案参考)

| 表 | 行数量级 | 估计体积 |
|---|---:|---:|
| `market_fixture` | 250,166 | ~30 MB |
| `euro_consensus_snapshot` | ~1.0 M(250,166 × 4 切面) | ~110 MB |
| `total_quote_snapshot` | 3–11 M(79,404 × 4 切面 × 每场有效公司数) | **0.25–1.0 GiB** |
| `snapshot_receipt` / `source_retirement` | 十位量级 | 忽略 |
| **服务库合计** | | **约 0.4–1.2 GiB** |

`total_quote_snapshot` 是服务库的**主导项**,取决于每场有报价的公司数。
该值已按跨 root 分层抽样定标(见下),不再是无依据的区间。

**U-8 定标结果(已测)**:6 个 root、12 页分层抽样,每页有效报价公司数
**min 9 / 中位 11 / 均值 18.6 / max 35**。对应的 `total_quote_snapshot`
体积区间为 0.24–0.93 GiB。

> **定标方法警告**:首次抽样取自 `market-sqlite-batch-0001-v8`,该 root 实测
> 是最富的一档(样本 35、35),其单页值(37)高于全体中位数(11)三倍以上。
> 任何基于单一 root 的产出率都会**系统性高估**。定标必须跨 root、
> 且报告样本量与分布而非单点值。

对照明细库:`historical_euro_1x2_quote` 实测 **~98.6 GiB / 530,036,350 行 /
~200 B/行**(含唯一索引);全库 100.0 GiB。



### T2 `euro_consensus_snapshot` — 欧赔共识四切面

行含义:**某一 场次 × 切面 的跨公司共识欧赔**。与 `r/n7_market_projection.R`
的 `fixtures` 入参对齐(该入参的键为 `issue/slot/provider_id`,**不含公司**,
注释明写 `odds_W/D/L mean decimal odds`)。

| 列 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `fixture_id` | TEXT | 否 | 外键 → `market_fixture.fixture_id` |
| `snapshot_kind` | TEXT | 否 | 枚举,取 `initial` / `final` / `10h` / `1h` |
| `odds_w` | REAL | 是 | 主胜赔率(十进制) |
| `odds_d` | REAL | 是 | 平局赔率(十进制) |
| `odds_l` | REAL | 是 | 客胜赔率(十进制) |
| `company_count` | INTEGER | 否 | **参与共识的公司数**(必须 > 0;见第 6 节) |
| `availability_boundary_at_utc` | TEXT | 否 | 参与共识的公司报价中 **`trusted_received_at_utc` 的最大值** |
| `policy` | TEXT | 否 | 共识政策标识,见下 |
| `status` | TEXT | 否 | `OK` / `ABSENT`(见第 5 节) |

主键:`(fixture_id, snapshot_kind)`。

`policy` 的取值必须显式登记,至少区分:
`MEAN_ALL`(全体算术平均)、`MEAN_TRIMMED`(去极值)、`SINGLE_BOOK`(指定公司)。
**禁止**在未登记 policy 的情况下写入。首版建议只实现 `MEAN_ALL`,
并把「保留最大值(=公司间离散度)」作为后续独立列或独立表,不要塞进共识平均值。

**切面定义**(复用 `snapshots.py`,不另发明):

| kind | 定义 |
|---|---|
| `initial` | 每家公司在开赛前的**第一条**带时间报价 |
| `final` | 每家公司在开赛前的**最后一条**带时间报价 |
| `10h` / `1h` | 开赛前 10 小时 / 1 小时的 as-of 截面,取各公司在该时刻**之前**最新可见报价 |

谓词统一为 `market_time_source_raw < 目标时刻`,与明细库一致。

> **实现注记(必须处理)**:`snapshots.py` 对「整场无带时间赛前报价」会
> `raise TitanSnapshotError`(fail-closed),但对「该公司在 `10h`/`1h` 无可用报价」
> 是 **静默跳过**(`if eligible: append`)。契约要求这两者可区分,因此
> 本表以 `status='ABSENT'` 行显式表达「该切面未产出」,
> 并要求生成器登记每场每切面的缺席计数(见第 8 节 V-07)。

### T3 `total_quote_snapshot` — 大小球 as-of 截面(**按公司**)

行含义:**某一 场次 × 切面 × 公司** 的大小球报价。

保留公司维度是硬要求:`r/n7_market_projection.R` 的 `total_quotes` 入参校验包含
`anyDuplicated(total_quotes[c('issue','slot','provider_id','company')])`,
即**公司参与主键**。对大小球做跨公司平均会直接破坏该接口。

| 列 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `fixture_id` | TEXT | 否 | 外键 → `market_fixture.fixture_id` |
| `snapshot_kind` | TEXT | 否 | 同 T2 枚举 |
| `company_source_id` | TEXT | 是 | **首版预期为 `NULL`** —— 见第 7 节 |
| `company_label_source_raw` | TEXT | 是 | 源站公司标签原文(**已损坏**,见第 7 节)。仅作留痕,**不得**用于关联 |
| `line_value` | REAL | 是 | 盘口线数值(**已由既有解析器产出**):分档线取各档均值,如 `2/2.5` → `2.25` |
| `line_text` | TEXT | 是 | 盘口线原文,如 `2/2.5`、`2.5`(保留原串) |
| `over_odds` | REAL | 是 | 大球赔率 |
| `under_odds` | REAL | 是 | 小球赔率 |
| `availability_boundary_at_utc` | TEXT | 否 | 该行所属采集 receipt 的 `trusted_received_at_utc` |
| `market_time_source_raw` | TEXT | 是 | 源站时间原文,诊断用 |
| `status` | TEXT | 否 | `OK` / `ABSENT` |

主键:`(fixture_id, snapshot_kind, company_source_id, line_text)`。
**首版不允许**把 `company_label_source_raw` 放进主键或任何唯一约束。

> 两列 `line_*` 共存是刻意的,且**不增加工程**:既有解析器
> `src/fundamentals_titan_total.py::total_triplet()` 已同时产出
> `line`(数值)与 `line_text`(原串)。保留原串用于可追溯,数值列供直接消费;
> 消费方不需要自己写解析。

### T4 `snapshot_receipt` — 生成与复放收据

一次生成一行,机器可读。

| 列 | 类型 | 可空 | 说明 |
|---|---|---|---|
| `receipt_id` | TEXT | 否 | 主键 |
| `generated_at_utc` | TEXT | 否 | |
| `input_database_sha256` | TEXT | 否 | 明细库文件的 sha256 |
| `input_row_counts_json` | TEXT | 否 | 各输入表行数的 JSON |
| `implementation_sha256_json` | TEXT | 否 | 生成器及其导入 helper 的哈希 |
| `snapshot_kinds_json` | TEXT | 否 | 实际产出的切面枚举 |
| `absent_counts_json` | TEXT | 否 | 各切面的缺席计数(见 V-07) |
| `availability_policy` | TEXT | 否 | 与 `snapshots.py` 的 `receipt()` 对齐 |
| `prospective_use` | INTEGER | 否 | 首版为 `0` |
| `total_archived_sha256` | TEXT | 是 | 若有大小球来源,记录其归档哈希 |

### T5 `source_retirement` — 归档台账

**不新建 schema**,直接对齐仓库既有先例 `registry/source-retirement.json`:
`archive` / `archive_sha256` / `state` / `removed_at_utc` / `member_count`。
本表仅作为该台账在服务库内的只读投影,便于调用方自查数据来源是否已归档。

---

## 5. 缺失语义(四态,必须区分)

`AGENTS.md` 要求区分 missing / zero / empty string / empty result,
且不得把解析失败静默转为缺失。本契约定义四态,任何列不得混用:

| 状态 | 表达方式 | 含义 |
|---|---|---|
| **源未采** | 该 `(fixture, market)` 不产生任何行,且 `market_fixture.*_available = 0` | 我们从未抓取。**不是缺失** |
| **源站无值** | `status='ABSENT'` + `odds_*`/`over_odds`/`under_odds` 为 `NULL` | 抓到了,但源站在该切面无报价 |
| **解析失败** | **不得写入本库**;进 `historical_fixture_failure` 对应项,并在 receipt 的失败计数中登记 | 抓到了但解析不了 |
| **不适用** | 列为 `NULL` 且 `status='OK'`(例如 `initial` 切面的 `line` 允许为空) | 该列在此行按定义无值 |

**禁止**:用 `0` 表示缺失;用空字符串 `''` 表示缺失;用平均/中位数填补缺失。

---

## 6. 时间语义与可用性规则

三类时间必须分离(明细库已如此,本契约沿用):

| 类别 | 列 | 用途 |
|---|---|---|
| 事件时间 | `kickoff_source_raw`, `market_time_source_raw` | **仅诊断**。不得作为可用性依据 |
| 采集时间 | `requested_at_utc` | 诊断 |
| 可用性时间 | `trusted_received_at_utc` | **唯一可用性边界** |

规则:

- **A-1** `availability_boundary_at_utc` = 参与该行的所有公司报价中
  `trusted_received_at_utc` 的 **最大值**。不得取平均、不得取第一条。
- **A-2** 共识行的 `company_count` 必须 > 0 且等于实际参与条数;
  `company_count = 1` 的行必须可被消费方识别(它是单家报价,不是共识)。
- **A-3** 任何前瞻性使用必须满足
  `availability_boundary_at_utc < decision_at_utc`;不满足即 fail closed。
- **A-4** 首版全部产出标记为 `HISTORICAL_PROXY` 且 `prospective_use = 0`。
  这与 `snapshots.py` 的现状一致:它明文声明
  `prospective use is prohibited`。**把诊断层提升为前瞻可用层是独立的、
  未完成的治理动作**,不得由本契约默认授予。
- **A-5** 时区:源站时间按 naive `Asia/Shanghai` 解析(与 `snapshots.py` 一致);
  入库一律转 UTC 并带 `Z`。年份推断规则沿用 `snapshots.py`
  (仅跨 12/1 月翻转;其他未来日期留在开赛年并排除,不得回推)。

---

## 7. 大小球退化声明(必须显式)

已采到的 79,404 场次大小球,其字节经 `r.jina.ai` 读取器代理获取,实测:

- **数字载荷完好**:盘口线、大球/小球赔率可正常解析。
- **公司标签不可恢复**:原始字节按声明字符集 `errors='strict'` 解码即失败;
  按 UTF-8 `replace` 解出 186 个 `U+FFFD`;回转后仍残留 99 个 `U+FFFD`
  加私用区字符。属**不可逆**损坏。

因此:

- **D-1** 大小球行的 `company_source_id` 首版为 `NULL`,并配
  `company_label_source_raw` 留痕;**不得**用损坏标签做关联、分组或去重键。
- **D-2** 本库的欧赔共识与大小球**不可按公司对齐**(欧赔有干净的
  `company_source_id` / `bookmaker_source_name`,大小球没有)。
  需要跨市场同公司比较的场景,必须等大小球重采。
- **D-3** 任何消费方使用大小球时,必须能读到 `DEGRADED_SOURCE` 标注。
  建议在 `total_quote_snapshot` 上加 `source_quality TEXT NOT NULL`
  CHECK IN (`FULL`, `DEGRADED_SOURCE`),首版全部为 `DEGRADED_SOURCE`。
- **D-4** 大小球重采**不**属于本契约范围;其前置条件是会话式抓取可行性验证
  (直连 `vip.titan007.com/OverDown_n.aspx` 当前不可用,详见爬虫台账 C-001)。

---

## 8. 可执行校验(每条一个断言)

契约以断言实现,任一失败即停止,不得产出降级产物。

| ID | 断言 |
|---|---|
| V-01 | `market_fixture` 中 `fixture_id` 唯一;`capture_batch_id` 唯一且非空 |
| V-02 | `count(market_fixture) = count(distinct fixture_id)` 且 = 明细库 `historical_fixture_capture` 行数 |
| V-03 | `euro_consensus_snapshot.snapshot_kind ∈ {initial,final,10h,1h}` |
| V-04 | 对 `status='OK'` 的欧赔行,`odds_w/d/l` 均 > 0 且有限 |
| V-05 | 对 `status='OK'` 的欧赔行,`company_count >= 1` |
| V-06 | `availability_boundary_at_utc` 必须能在明细库找到对应的 `trusted_received_at_utc`,且为其参与者中的最大值 |
| V-07 | 每场每切面的 `ABSENT` 行数 + `OK` 行数 = 该场该切面应产出的公司数;缺席计数写入 receipt |
| V-08 | `total_quote_snapshot` 上 `(fixture_id, snapshot_kind, company_source_id, line)` 无重复 |
| V-09 | 标识符列均为 TEXT 且前导零保留(以 `0` 开头的 `source_fixture_id` 样本比对) |
| V-10 | 空输入产出**带类型的空表**而非空文件;空表 schema 与有数据时一致 |
| V-11 | 独立复放:同输入 + 同实现跑两次,产物逐字节一致(排序不稳定时按主键排序后比对) |
| V-12 | `source_quality` 对全部大小球行为 `DEGRADED_SOURCE` |
| V-13 | 库内**不存在**任何结算标签列(名称扫描 + 白名单列枚举双重检查) |
| V-14 | `snapshot_receipt` 的 `input_database_sha256` 与实际输入文件 sha256 一致 |

按 `AGENTS.md`,V-09/V-10 需覆盖 nulls、整数精度、标识符与前置零、时间戳、列类型、
空表 schema;相关测试放 `tests/`,R 侧转换测试用 `testthat`。

---

## 9. 生成与独立复放

- 入口为**薄命令**:`scripts/build_market_odds_serving.py`(提案名),
  显式接收 `--data-root`、`--output`、`--snapshot-kinds`,不含任何 `__file__`
  或 CWD 推导路径,无隐藏会话状态。
- 复算函数置于 `src/`,`snapshots.py` 的切面语义**直接复用**,不复制。
- 交付 `quarto/market_odds_serving.qmd` 作为验收入口:声明输入快照与哈希、
  渲染校验结果表、记录 review 命令与结论。
- 生成器**只读**打开明细库(`?mode=ro`),不写 `control.sqlite`。

---

## 10. 已知限制与未决事项

| # | 事项 | **决议** | 依据(时间效率) |
|---|---|---|---|
| U-1 | 共识 policy | **只 `MEAN_ALL`** | 消费者契约要的就是 mean(`odds_W/D/L mean decimal odds`);`policy` 列已留 hook,后续加取值不破坏 schema,不需要为它多跑一轮 |
| U-2 | 离散度 | **做,并入同表**:`w_min/w_max/d_min/d_max/l_min/l_max` 六列 | min/max 与 mean **同一趟聚合**,零额外扫描。约 +48 MB。**我此前"另开表"的建议按时间效率撤回** —— 另表要多一次 join、多一份 receipt,纯增成本 |
| U-3 | 诊断层 → 前瞻层治理 | **不独立立项、不阻塞交付**;首版照写 `HISTORICAL_PROXY` + `prospective_use=0` | 契约已有 **operator waiver:模型/策略优化阶段可作训练与优化数据**。"尽快给算法用"不需要等治理动作;前瞻生产再单独立项 |
| U-4 | 大小球重采 | **本次不立项** | 前置未解(会话式抓取 + 网络),170,762 场次从未采过,收益远滞后于交付。已采 79,404 足以先跑算法 |
| U-5 | 服务库落盘位置 | `clean_v1/control/titan/market_odds_v1.sqlite` | 同域同挂载,读盘口**不需额外挂载**;与 settlement/discovery 分文件即满足物理隔离 |
| U-6 | 归档回退演练 | **只做单分片完整闭环**:归档 → 解压 → 逐文件 sha256 比对 | 正确性可由单分片 + 抽样证明;全量演练是小时级且无额外信息 |
| U-7 | `line` 规范化 | **不做新字段** —— 解析器已同时产出 `line_value`(数值)与 `line_text`(原串),两者都入表 | 零新增工程;已测解析器 `total_triplet()` 就是这么产出的 |
| U-8 | 每场有效报价公司数 | **已定标**:min 9 / 中位 11 / max 35 | 已解决 |
| **U-9** | Step 0 代码合并范围 | **只带 3–6 个文件**,**不合并 146 个** | 需要的是 `src/fundamentals_titan_total.py`、`src/fundamentals_titan_euro.py`、`src/temporal_learning/partial_clock.py` 及其传递 import;其余依赖(`fundamentals_census`、`temporal_learning` 主体)**main 已有**。精确闭包用 Python 实际 import 计算,不靠目测 |

**已明确的边界**:本契约不覆盖扩覆盖采集;不含结算标签;不做拟合与下注。

---

## 11. 复用关系(不重造)

| 需要的能力 | 复用对象 | 不做什么 |
|---|---|---|
| 切面语义与时间解析 | `src/titan_clean/snapshots.py` | 不另写一套 cutoff 逻辑 |
| 源绑定哈希 | `snapshots.py::_fixture_source_binding` | 不发明新哈希口径 |
| 明细库结构 | `src/titan_clean/store.py` | 不改明细 schema |
| 归档台账 schema | `registry/source-retirement.json` | 不发明新台账格式 |
| 消费入参形状 | `r/n7_market_projection.R` | 不改变消费者契约 |
| 时间/权重机制 | `src/temporal_learning` | 不复制 temporal helper |

---

## 12. 决议记录(指导原则:时间与效率优先)

**owner 原则**:尽快拿到完备数据以供算法使用;时间与效率优先。

### 12.1 由此产生的排序

**唯一关键路径**(每步都直接推进"算法可用"):

1. 带 **3–6 个文件**过 main(复用既有解析器,**不重写**)
2. 契约随立项 issue 一并提交批准
3. 生成器 + V-01…V-14(复用 `snapshots.py` 的切面语义与
   `fundamentals_titan_total.py` 的解析)
4. 调用接口 + 测试
5. QMD 验收 + `codex review`
6. 归档明细(**验收通过后**才动)

**按同一原则明确推迟**(不在本次路径上):

| 推迟项 | 理由 |
|---|---|
| 扩覆盖采集(#483 的 612 期) | 已采部分足以先用;新采收益滞后于交付 |
| 大小球重采 170,762 场次 | 前置(会话式抓取 + 网络)未解;U-4 |
| 前瞻层治理立项 | 训练阶段已有 operator waiver;U-3 |
| 146 文件全量合并 | 只需 3–6 个;U-9 |
| `audits/` 留存与其余目录议题 | 与"让算法拿到数据"无关 |
| 明细库在库保留 | 归档即可;服务库不含明细 |

### 12.2 被该原则改变的两处既有建议(留痕)

1. **U-2**:先前建议离散度"另开表",按效率改为**并入同表六列** —— 同一趟聚合即可产出,另表纯增 join 与 receipt。
2. **U-7**:先前把 `line` 定义为"仅保留原串、不做数值化",按效率改为**两列共存** ——
   解析器本来就同时产出 `line` 与 `line_text`,禁用其一半产出是纯损失。

### 12.3 效率不得越过的最低线

原则是"快",但下列三条**不因快而降级** —— 它们的失效代价高于返工代价:

| 线 | 内容 | 依据 |
|---|---|---|
| **L-1** | 可用性边界必须回连 `trusted_received_at_utc` | A-1;否则数据在 cutoff 上不可判定,算法无法合法使用 |
| **L-2** | 缺失四态必须区分(第 5 节) | 否则"源未采"会被下游误读为"无信号" |
| **L-3** | 大小球必须标注 `DEGRADED_SOURCE`(第 7 节) | 否则损坏的公司维度会被静默使用,污染任何按公司的分析 |

违反任一条,交付的数据在其**用途上不可用** —— 那比一次做对更慢。

---

## 附录 A. 盘口线现状占用与目标占用(实测)

### A.1 现状

| 项 | 体积 | 性质 |
|---|---:|---|
| `clean_v1/control/titan/control.sqlite` | **100 GiB** | 明细权威源(530,036,350 行报价) |
| `clean_v1/raw/titan` | **183 G** | Titan 原始字节 + 67 个 `.tar.zst` 分片 |
| `markets/raw` | **70.5 GiB** | A 线采集,518,465 个文件 |
| `markets/releases` | 20 G | 18 个清洗批次 JSON + 9.0 G `market-history-v1.sqlite` |
| `markets/manifests` | 1.6 G | 计划与索引 |
| **盘口线合计** | **约 375 GB** | |

`markets/raw` 明细(前五项占 62.5 GiB):

| root | 体积 |
|---|---:|
| `market-forward-rolling-v1` | 19.78 GiB |
| `market-forward-auto-recovery-v1` | 14.47 GiB |
| `market-forward-persistent-v1` | 11.62 GiB |
| `verified-responses`(内容寻址) | 8.55 GiB |
| `market-roster-corrected-v1` | 8.11 GiB |
| `roster-supply-v1` | 3.11 GiB |
| `market-sqlite-batch-0001-v8` | 2.70 GiB |
| `market-forward-five-workers-v1` | 1.72 GiB |

> 同源其它线(不在本契约范围,列出以供对比):
> `settlement` 47 G、`audits` 20 G、`reports` 6.7 G、`fundamentals` 6.2 G、
> `shared/fixtures` 3.9 G、`runtime` 1.0 G。Sandisk 当前余量 **317 GB**。

### A.2 目标

| 项 | 体积 | 说明 |
|---|---:|---|
| 服务库 `market_odds_v1.sqlite` | **~0.45–1.25 GiB** | 见 T1.2 |
| 归档:`clean_v1/raw/titan` | **~4 GiB** | 按已实测 46:1 |
| 归档:`markets/raw` | **~1.6 GiB** | **按同源比率外推,非实测** |
| 归档:`markets/releases` | **~0.5 GiB** | 同上,外推 |
| **合计** | **约 6–7 GiB** | |

**净省约 368 GB。**

> **外推声明**:只有 `clean_v1/raw/titan` 的 46:1 比率是实测的(67 个分片,
> 68.4 GB → 1.48 GB)。`markets/raw` 与 `markets/releases` 的归档比率是**同源外推**,
> 实施时必须在**单个分片**上先测出实际比率再批量,不得直接按 2.2% 下结论。
> 该外推只影响"能省多少",不影响"服务库本体 ~0.45–1.25 GiB"这一实测结论。
