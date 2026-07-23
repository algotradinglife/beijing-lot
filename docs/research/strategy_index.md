# Beijing-lot Strategy Archaeology Index

> 盘点日期：2026-07-21（Asia/Shanghai）
>
> 目的：记录已出现过的策略、模型和组合实验的证据边界，而不是筛选新的盈利方案。
> 本索引中的历史 ROI、收益或命中率都是报告中的观察值，不构成可复制优势或执行建议。

## 1. 范围与编目方法

本次扫描覆盖 `docs/strategy/`（29 个文件）、`docs/research/`（371 个文件）、`results/`
（3,967 个文件）和 `scripts/`（208 个文件），并以文件名和正文中的
`strategy`、`model`、`backtest`、`evaluate`、`walkforward`、`decision`、`portfolio`、
`q`、`odds`、`SP`、`Kelly`、`N=3`、`N=7` 等关键词筛选。

结果目录中大量条目是同一输入、同一结算方式下的阈值、种子、预算或组合权重扫描，不是独立研究。
为避免把一次数据窥探拆成许多“成功策略”，本索引以**策略/证据单元**编号：同一假设的参数网格、
图表和中间 CSV 在一条记录中列为 aliases，而不会重复计数。

### 1.1 证据等级

| Level | 定义 | 本次盘点结论 |
| --- | --- | --- |
| A | 规则事先冻结；严格赛前输入；独立样本外验证；收益口径含可执行成本/可售性。 | **无。** |
| B | 有滚动或时间序列样本外结果，但赛前时点、价格或可执行性仍需补强。 | 仅若干预测模型与历史 walk-forward。 |
| C | 探索性回测、同样本敏感性、短期 shadow 或数据工程试验。 | 本仓库大多数策略报告。 |
| D | 官方结算为负、明显集中/过拟合，或资料明确否定该假设。 | 若干 Kelly、单场高 SP、2026 proxy、泛化 league 与 draw 删除方向。 |

`Data grade` 沿用 [research_status.md](research_status.md) 的 A/B/C/D 数据分级：严格 as-of、
可检查时间戳、代理/探索、结算/赛后。策略的 Evidence Level 不等于数据等级。

### 1.2 强制审计项

- **未来信息：** 除非资料明确说明 snapshot/freeze 在开赛前，否则历史 XLSM 的 `final`、终值和
  赛后报告一律不得当作赛前特征。
- **SP：** `winning_sp`、终值回补及停售后多玩法报价仅可结算或核验；不得作为训练/筛选输入。
- **样本内选择：** 同一数据集上筛过多个阈值、N、预算、种子或 sleeve 的最高 ROI 只记为探索性。
- **成本与可执行性：** 单腿 profit proxy、组合模拟和真实可买票不是同一口径；返奖率、限额、
  串关许可、停售和人工执行成本缺失时，ROI 不得升级为策略证据。

## 2. 策略总表

| ID | Strategy Name | Experiment Type | Data / as-of status | Evidence | Research Value |
| --- | --- | --- | --- | --- | --- |
| S001 | 历史 3-way 市场基线与组合回测 | backtest | 2014-2025 XLSM/3-SP proxy | C | 仅作对照 |
| S002 | 让球三结果概率模型 | walk-forward | XLSM historical proxy | B | 保留预测评估 |
| S003 | Rich 特征与 q-veto N=7 | walk-forward + backtest | XLSM historical proxy | C | 不可视为收益策略 |
| S004 | 平局二元 Logistic / Forest | walk-forward | XLSM historical proxy | D | 停止删除平局规则 |
| S005 | 联赛/标签历史 walk-forward | walk-forward | 2016-2025 historical proxy | B | 负向控制，保留审计 |
| S006 | Snapshot-pure 三结果模型 | backtest | 10h/1h snapshot proxy | B | 保留概率研究 |
| S007 | Asian-line / handicap 特征重建 | exploratory analysis | historical proxy + backfill | C | 数据质量研究 |
| S008 | 单场 EV 与 Kelly 资金分配 | walk-forward + backtest | XLSM + official settlement | D | 停止作为收益路线 |
| S009 | 早期组合优化与 N sweep | exploratory analysis | mixed historical proxy | C | 仅作组合机制参考 |
| S010 | N=3 选择器与覆盖组合族 | backtest | 2023-2025 / proxy | C | 归档，不扩参 |
| S011 | N=7 cold-tail / 高 SP 尾部 | backtest + validation | 3-SP / proxy | D | 不再追逐冷门尾部 |
| S012 | N=7 q-pocket / gate / risk | exploratory + walk-forward | historical proxy | C | 保留为失败模式审计 |
| S013 | N=7 保护、sleeve、drawdown 组合族 | backtest | historical proxy, many grids | C | 不得按最高 ROI 选型 |
| S014 | 固定 256/384 主组合与保护腿 | backtest + paper watchlist | historical proxy | C | 仅作为历史基准 |
| S015 | 2026 live holdout proxy | forward-like replay | 2026 1h live proxy | D | 关键反证，保留 |
| S016 | SP drift 时间窗与 haircut | exploratory replay | pre-kick panel; timing partly observed | C | 仅做数据质量/时点假设 |
| S017 | 欧赔均值替代 / SP disagreement | shadow backtest | 26071-26072 snapshots | C | 诊断用途，不替代价格 |
| S018 | q 与 final-SP / SP-native 诊断 | exploratory analysis | mixed final and snapshot prices | C | 只保留校准审计 |
| S019 | v3 LLM 决策链 vs previous q | live observation | issue 26071, 15 settled legs | C | 历史对照，不推广 |
| S020 | v3.3.3 标准化决策链 | artifact audit + observation | 26071-26076 artifacts | C | 保留工程基线 |
| S021 | v4.2 layered merge 决策链 | replay | 26071-26072, late/augmented inputs | C | 观察，不执行 |
| S022 | v4.3 probability-first 决策链 | shadow backtest | 26071-26072, 81 legs | C | 不进入 release |
| S023 | v3.3.3 主押/保护裁剪实验 | counterfactual | 26071-26074 legacy artifacts | C | 仅前向 paper 资格 |
| S024 | shadow N=4 probability-weighted 512 | paper portfolio | 26072-26074, ten seeds | C | continue paper-only |
| S025 | Segment N/票组构造与预算缩放 | operational simulation | live artifacts, seed samples | C | 可用性研究，不是 alpha |
| S026 | 正确比分 Poisson / EV-q 研究包 | data readiness | forward price assets incomplete | C | 暂停收益评估 |
| S027 | 比分投影与让球平局适配器 | approximate replay | 26071-26074 proxy/research artefacts | C | 只保留校准试验 |
| S028 | 多玩法 / A9 保护腿比较 | data-contract / dry-run | immutable event inputs | C | 先补证据资产 |

## 3. 逐项证据档案

### S001 - Historical 3-way market baseline and combo backtests
- **Research Question:** 历史三项 SP、市场共识和不同 N 串能否形成正收益基线？
- **Core Hypothesis:** 以历史赔率/概率代理筛腿并组合可超过随机或全包基线。
- **Data Used:** `beidan_xlsm`、`beidan_full_3sp.csv` 与早期特征库；主要跨 2014-2025，赛前字段多为 XLSM 命名快照，属 C 级代理。
- **Method / Experiment Type:** 市场概率、组合优化、N sweep 与模拟结算；exploratory backtest。
- **Metrics:** ROI、profit、hit rate、issue win rate、ticket count、drawdown。
- **Result Summary:** 建立了后续模型/组合的比较基线，但不同报告的收益对价格口径和筛选规则高度敏感。
- **Current Evidence Level:** C。
- **Limitations:** 历史 SP 时点并非完整可审计赛前序列；可能混入终值；无统一冻结规则、可售性或成本审计。
- **Research Value:** 保留为对照和数据迁移测试；停止把正 ROI 行当作策略候选。
- **Sources / aliases:** `combo_backtest_report.md`、`combo_optimizer_v1.md`、`limited_backtest_report.md`、`n_walkforward.md`、`scripts/n_sweep_backtest.py`、`scripts/backtest_combo_*.py`。

### S002 - Handicap-adjusted three-result probability model
- **Research Question:** 让球、市场与历史特征能否改善 3-way 概率预测？
- **Core Hypothesis:** 多项 Logistic/校准模型在未来期次的 log loss 和 Top-k 上优于市场基线。
- **Data Used:** XLSM modelling SQLite；62 个滚动窗口、17,685 测试场次（报告）；2014-2025 proxy snapshot，非严格逐场赛前证明。
- **Method / Experiment Type:** 多分类概率模型、12 期训练滚动 walk-forward。
- **Metrics:** log loss、accuracy、Top-1/Top-2、校准；部分报告附 N=7 ticket ROI。
- **Result Summary:** 标准结果模型报告 model log loss 1.0682 对市场 1.1577、accuracy 43.29% 对 39.15%；预测改善没有稳定转化为组合收益。
- **Current Evidence Level:** B（预测指标时间外，但输入时点仍为代理）。
- **Limitations:** 训练窗口和特征选择已探索过；票据结算与模型指标目标不一致；赛前价格来源未完全冻结。
- **Research Value:** 值得保留为可复现实验锚点，不可据此声称存在投注优势。
- **Sources / aliases:** `results/beidan_result_model_n7/`、`results/beidan_result_model_n7_l2_grid/`、`scripts/walkforward_beidan_result_model_eval.py`。

### S003 - Rich-feature q-veto N=7 model
- **Research Question:** 丰富特征和 model/market 比值 veto 能否使 N=7 组合通过收益门槛？
- **Core Hypothesis:** q 或 model/market 分歧可排除低质量腿。
- **Data Used:** 与 S002 同一 XLSM 代理；62 窗口、1,238 张票。
- **Method / Experiment Type:** rich 特征、多参数 L2/min-p/ratio 网格、walk-forward ticket backtest。
- **Metrics:** log loss、ROI、issue win rate、best issue profit share、drawdown、loss streak。
- **Result Summary:** `q_baseline_model_veto` 报告 ROI 85.47%，但 53.4% 净利润来自最佳期；同报告的 `result_model_high_sp` ROI -34.94%。
- **Current Evidence Level:** C。
- **Limitations:** 同数据集网格扫描；赔率代理；高集中度；收益并非独立复验。
- **Research Value:** 保留集中度门槛这一否定性经验；停止将 q-veto 作为收益候选。
- **Sources / aliases:** `results/beidan_result_model_rich_n7/`、`results/beidan_result_model_rich_n7_veto_grid/`、`scripts/walkforward_beidan_result_model_eval.py`。

### S004 - Draw binary Logistic and Random Forest
- **Research Question:** 是否能可靠识别可删除或需保护的平局选项？
- **Core Hypothesis:** 平局二元分类可安全降低覆盖深度。
- **Data Used:** XLSM historical proxy，17,685 测试场次、draw rate 27.57%。
- **Method / Experiment Type:** Logistic、balanced Logistic、Random Forest，滚动/样本外评估与阈值扫描。
- **Metrics:** log loss、Brier、ROC-AUC、AP、precision/recall、错误删除率。
- **Result Summary:** 最佳 forest ROC-AUC 0.526、AP 0.295；较高阈值会删除大量真实平局，未显示可安全的平局删除能力。
- **Current Evidence Level:** D。
- **Limitations:** 代理时点、阈值扫描、多重比较；即使分类略优也未验证票据收益。
- **Research Value:** 停止“模型删除平局”路线；可作保护规则的风险基线。
- **Sources / aliases:** `results/beidan_draw_binary_*`、`scripts/evaluate_beidan_draw_binary.py`。

### S005 - League and historical match-tag walk-forward
- **Research Question:** 联赛、排名和 Asian-line 标签能否在市场+让球之上增加泛化预测力？
- **Core Hypothesis:** 某些联赛或标签提供稳定残差。
- **Data Used:** 190,511 可用历史行；2016-2025 按赛季的 OOS，历史赛前/closing 代理字段。
- **Method / Experiment Type:** earlier-season-only multinomial Logistic 的特征消融；walk-forward。
- **Metrics:** OOS log loss、按联赛 improvement count。
- **Result Summary:** league 加入 market+handicap 的 OOS log loss 变化 +0.000747（更差），10 个赛季中 9 个更差；近期正向联赛切片也未跨季确认。
- **Current Evidence Level:** B（严格时间顺序的预测反证，但非当前 freeze 数据）。
- **Limitations:** 不能回答组合 ROI；标签选择可能受最近样本影响；历史赔率时点仍为代理。
- **Research Value:** 作为反例和负向控制保留；停止硬编码联赛加成。
- **Sources / aliases:** `historical_match_tag_walkforward_2026-07-11.md`、`historical_positive_league_tag_effect_2026-07-11.md`、`scripts/backtest_historical_match_tags_walkforward.py`。

### S006 - Snapshot-pure result model
- **Research Question:** 只用决策时点的快照输入能否改善概率质量并提升 N=7？
- **Core Hypothesis:** 去除 final-odds 泄漏后，模型仍优于 snapshot-market 基线。
- **Data Used:** 历史模型表的 10h/1h 命名快照；时间字段为 C 级代理，报告含 10h/1h 比较。
- **Method / Experiment Type:** snapshot-market 对比 snapshot-pure 概率模型，随后 N=7 模拟回测。
- **Metrics:** log loss、Top-1、Top-2、模拟 ROI/集中度。
- **Result Summary:** 10h log loss 1.1601 -> 1.1005、Top-2 68.6% -> 72.1%；N=7 收益未稳定改善。
- **Current Evidence Level:** B（概率质量），组合收益为 C。
- **Limitations:** 快照来源需要再冻结；下游票据方差和集中度；预测指标并不等于可交易 edge。
- **Research Value:** 值得作为严格 as-of 复现的锚点，不可推广其票据结果。
- **Sources / aliases:** `snapshot_pure_result_model_audit_2026-06-26.md`、`scripts/snapshot_pure_result_model.py`、`scripts/evaluate_snapshot_pure_result_model.py`。

### S007 - Asian-line / handicap feature rebuild
- **Research Question:** 让球线回填、清洗和建模是否改变历史结果模型结论？
- **Core Hypothesis:** 更完整的 Asian-line 特征能改善决策输入。
- **Data Used:** XLSM/backfill 历史表；赛前时点仍为代理。
- **Method / Experiment Type:** schema/feature rebuilding 与 rerun；exploratory analysis。
- **Metrics:** 覆盖、字段完整性、模型/策略重跑差异。
- **Result Summary:** 主要产出是字段和输入链路修复，没有独立、稳定的收益验证。
- **Current Evidence Level:** C。
- **Limitations:** 数据工程与策略效果混在一起；回填可能使用赛后可见信息；没有预注册比较。
- **Research Value:** 保留为数据质量工作，不作为策略。
- **Sources / aliases:** `asian_line_modeling_rebuild_2026-06-30.md`、`asian_line_backfill_strategy_rerun_2026-06-30.md`。

### S008 - Single-match EV and fractional Kelly allocation
- **Research Question:** q/EV 筛选后，用 Kelly 或按 EV 配资能否提高单场官方结算收益？
- **Core Hypothesis:** 概率 edge 存在时，分数 Kelly 能改善增长和回撤。
- **Data Used:** XLSM 17,685 场、12 期训练窗口；官方 winning SP 结算，特征价格为历史代理。
- **Method / Experiment Type:** EV proportional、top-EV、quarter-Kelly 与基准仓位的 walk-forward backtest。
- **Metrics:** ROI、profit/match、coverage、hit rate、profitable issues、max drawdown。
- **Result Summary:** 官方结算下 `ev_prop_budget` ROI -29.14%、`kelly_fractional` -29.10%；正收益仅出现在 proxy-odds settlement。
- **Current Evidence Level:** D。
- **Limitations:** proxy 与官方结算分歧揭示价格泄漏/错配风险；未捕获资金池冲击、限额与税费。
- **Research Value:** 停止以 Kelly 修复负 edge 的路线；保留为结算口径一致性测试。
- **Sources / aliases:** `sp-bias-and-kelly.md`、`results/beidan_stake_allocation_kelly_l2_003/`、`scripts/evaluate_beidan_stake_allocation.py`。

### S009 - Early combo optimizer and N sweep
- **Research Question:** N 的选择、赔率带和组合采样是否能产生更好的历史组合分布？
- **Core Hypothesis:** 存在可由优化器挑出的 N/赔率/覆盖结构。
- **Data Used:** 历史 3-SP/特征代理，多个年份和预算切片。
- **Method / Experiment Type:** 组合优化、N=2..N=8 网格、seed/票数扫描；exploratory analysis。
- **Metrics:** ROI、hit rate、ticket count、权益曲线、集中度。
- **Result Summary:** 形成大量候选池与图表，但没有单一预先冻结的胜出规则。
- **Current Evidence Level:** C。
- **Limitations:** 参数和目标函数多重比较；高 N 收益对个别中奖票敏感；可执行成本不完整。
- **Research Value:** 只用于理解组合算术和后续实验的对照。
- **Sources / aliases:** `combo_optimizer_v1.md`、`n_dynamic_issue_depth_2026-06-27.md`、`scripts/n_sweep_backtest.py`、`scripts/evaluate_combo_*.py`。

### S010 - N=3 selector and coverage-combo family
- **Research Question:** N=3 的独立、disjoint、coverage-round、SP-balanced 或 calibrated selector 能否稳定收益？
- **Core Hypothesis:** 低 N 分散与选码深度能改善资金利用率。
- **Data Used:** 2023-2025/历史代理，不同组合报告共用相近输入。
- **Method / Experiment Type:** 多个 selector/coverage/backtest 变体。
- **Metrics:** ROI、profit、命中、权益曲线、组合重叠。
- **Result Summary:** 文档记录多个正负结果，但它们是同一研究簇的筛选输出，不能作为独立复现。
- **Current Evidence Level:** C。
- **Limitations:** selector、预算、SP 折扣和 N 同时扫描；无严格赛前 SP；缺少留出期统一结算。
- **Research Value:** 归档为“低 N 分散”假设，停止继续参数搜索。
- **Sources / aliases:** `n3_*.md`（13 份）、`recent_2023_2025_n3_n4_combo_anatomy_2026-06-28.md`、`scripts/evaluate_n3_*.py`。

### S011 - N=7 cold-tail / high-SP tail
- **Research Question:** 冷门高 SP 尾部是否能提供 N=7 的凸性收益？
- **Core Hypothesis:** 少数高赔率命中足以补偿大量损失。
- **Data Used:** 历史 3-SP 与 10h/1h/final proxy 的多个阈值切片。
- **Method / Experiment Type:** cold-tail、高 SP anchor、high-N backtests 与 validation。
- **Metrics:** ROI、命中、full loss、profit concentration、drawdown。
- **Result Summary:** 尾部报告和后续模型报告显示极端集中；高 SP `result_model_high_sp` 在同一滚动报告中为负 ROI。
- **Current Evidence Level:** D。
- **Limitations:** final/10h/1h 代理混用；阈值后选；极端稀有事件导致高方差。
- **Research Value:** 停止作为候选策略；保留为集中度和尾部风险反例。
- **Sources / aliases:** `n7_combo_cold_tail_*.md`、`high_n_*`、`results/cold_high_odds_tail_*`。

### S012 - N=7 q-pocket / gate / dynamic risk family
- **Research Question:** q 区间、置信度、SP 稳定性和 issue gate 能否识别更安全的 N=7 期次？
- **Core Hypothesis:** 高 q 或特定 q pocket 是可分离的风险/收益状态。
- **Data Used:** 历史 proxy；部分报告使用 2014 trusted 子集和滚动窗口。
- **Method / Experiment Type:** bucket analysis、gate selector、dynamic risk 与 walk-forward。
- **Metrics:** ROI、hit rate、issue risk、period robustness、drawdown。
- **Result Summary:** 产生多个互相依赖的 pocket/gate 候选；没有在独立严格赛前数据中固定并复验。
- **Current Evidence Level:** C。
- **Limitations:** 同一 q 定义与价格代理；大量 gate/whitelist/period 扫描；收益选择偏差。
- **Research Value:** 保留 q 的稳定性审计，不保留任何 pocket 为执行规则。
- **Sources / aliases:** `n7_q_pocket_*.md`（14 份）、`n7_q_bucket_stability_audit_2026-06-26.md`、`scripts/evaluate_q_pocket_*.py`。

### S013 - N=7 protection, sleeve and drawdown portfolio family
- **Research Question:** 保护腿、sleeve、cooldown、issue smoothing 与资本缩放能否降低 N=7 回撤？
- **Core Hypothesis:** 在保留高 N 核心的同时，用小型保护组合改善 full-loss 与 drawdown。
- **Data Used:** 历史 proxy 与同源 ticket 账本；大量 256/384 权重网格。
- **Method / Experiment Type:** portfolio backtest、seed/权重/风险门控扫描。
- **Metrics:** ROI、issue win rate、full-loss rate、max drawdown、loss/dead streak、tickets/issue。
- **Result Summary:** 有些组合改善某一回撤指标，但最佳收益组合常提高 full-loss 或 max drawdown；没有独立留出验证。
- **Current Evidence Level:** C。
- **Limitations:** 多目标挑选、重叠票组、代理 SP、历史最优权重不可直接执行。
- **Research Value:** 保留“收益与防御不能从同一最高 ROI 行推断”的审计结论。
- **Sources / aliases:** `n7_*protection*`、`n7_*sleeve*`、`n7_*cooldown*`、`n7_*drawdown*`、`n7_*capital*`（约 40 份）及对应 `scripts/evaluate_n7_*.py`。

### S014 - Current 256/384 main portfolio and leg-tag protection
- **Research Question:** 固定 256 主仓和 384 保护 sleeve 是否能在历史账本上提供更稳健组合？
- **Core Hypothesis:** 小额 tag protection 能降低连败/满损，而不是只提高历史 profit。
- **Data Used:** historical enriched source tickets 与 p-first decision table，非严格当前赛前回放。
- **Method / Experiment Type:** fixed-budget portfolio backtest 与 watchlist 比较。
- **Metrics:** profit、ROI、full-loss、maxDD、loss streak、recent ROI。
- **Result Summary:** 稳定 baseline `b384_dd32_smooth100` ROI 0.959、maxDD -13,690；更高 profit tag 组合 ROI 2.082 但 maxDD -23,402，报告明确不建议替换 baseline。
- **Current Evidence Level:** C。
- **Limitations:** 大量 tag/权重选择；数据来源位于历史 worktree；收益与实际可买票/时点未闭环。
- **Research Value:** 作为防御性组合的历史案例，不作为可执行主策略。
- **Sources / aliases:** `current_n7_operating_profile_384.md`、`main_strategy_*`、`main_strategy_leg_tag_protection_384_2026-07-01.md`。

### S015 - 2026 live holdout proxy
- **Research Question:** 历史高 N/EV 路线能否在 2026 逐轮 1h 数据上存活？
- **Core Hypothesis:** 若历史 edge 真实，应在新的 2026 期次保留收益。
- **Data Used:** 完全结算的 2026 live 1h snapshots；报告列 9 期、其中 8 期产出票据；仍为 proxy replay。
- **Method / Experiment Type:** pre-2026 训练、2026 forward-like holdout、排除部分结算。
- **Metrics:** ticket issue win/loss、ROI、ex-best sensitivity、concentration。
- **Result Summary:** 默认 proxy 在所有测试票据期亏损；全历史敏感性仅靠一大赢家，移除后为负。
- **Current Evidence Level:** D。
- **Limitations:** 不是精确 production 384 链；覆盖不完整；但方向性反证强于历史最优扫描。
- **Research Value:** 必须保留为反证；停止以历史高 N ROI 支持发布。
- **Sources / aliases:** `2026_current_data_holdout_summary_2026-06-29.md`、`scripts/evaluate_2026_live_holdout_proxy.py`。

### S016 - SP drift timing window and band haircut
- **Research Question:** 早决策的 SP 漂移是否可由更近开赛时点或按档 haircut 减轻？
- **Core Hypothesis:** 低/高 SP 有系统漂移，临场输入可降低错误 q。
- **Data Used:** pre-kick panel 974,423 行、1,757 matches；决策腿 3,959；部分为 forward snapshot，部分为复放代理。
- **Method / Experiment Type:** drift quantile、timing curve、N=4 反事实 replay。
- **Metrics:** drift bias、residual drift、ROI、hit、maxDD。
- **Result Summary:** 报告显示 residual drift 从约 18h 的 46% 降至 30min 的 2%；1h replay ROI 很高但只有 12 次命中，保守 haircut 行 ROI +11.6%，均被报告标为样本薄和同样本。
- **Current Evidence Level:** C。
- **Limitations:** final/winning SP 是结算锚而非可交易价格；haircut 同期估计；N=4 少量命中主导。
- **Research Value:** 值得保留为采集时点和数据质量假设；不作为收益规则。
- **Sources / aliases:** `sp_drift_phase0.md`、`sp_drift_phase1.md`、`sp_drift_phase4.md`、`sp_drift_forward.md`、`scripts/run_sp_drift_*.py`。

### S017 - Euro-average-SP replacement and SP disagreement
- **Research Question:** 欧赔均值是否能稳定北单异常 SP 所导致的 q 选择？
- **Core Hypothesis:** 外部欧赔可作为北单早盘异常的锚，而不是直接交易价格替代。
- **Data Used:** 26071-26072 active snapshots，81 settled legs、76 有 SP 结算；赛前 payload，但样本很小。
- **Method / Experiment Type:** 固定概率/情报/赛果，只替换价格的 shadow backtest。
- **Metrics:** q tails、coverage、primary hit、cost、profit/ROI proxy。
- **Result Summary:** 保护命中 79.0% -> 74.1%，成本 160 -> 148，ROI proxy 6.9% -> 7.8%；没有清晰优胜者。
- **Current Evidence Level:** C。
- **Limitations:** 两期、共享决策、单腿 proxy、欧赔均值不是北单可得执行价格。
- **Research Value:** 保留为 price-sanity 诊断；停止“欧赔替代北单 SP”表述。
- **Sources / aliases:** `euro_avg_sp_shadow_backtest.md`、`v3_3_3_sp_disagreement_guard_backtest_2026-07-11.md`、`scripts/analyze_euro_avg_sp_shadow_backtest.py`。

### S018 - q / final-SP and SP-native diagnostics
- **Research Question:** q 是否稳定、是否与最终 SP 或市场变化一致？
- **Core Hypothesis:** 若 q 是有效 edge proxy，其排序和收益关系应跨时间稳定。
- **Data Used:** historical 3-SP、final/settlement 对照和 live snapshots；混合数据等级。
- **Method / Experiment Type:** q persistence、bucket audit、SP-native calibration、draw-odds sensitivity。
- **Metrics:** q 分位、校准、ROI proxy、SP drift、selection changes。
- **Result Summary:** 发现 q 对价格时点敏感；现有资料没有证明 q 是独立的期望值估计。
- **Current Evidence Level:** C。
- **Limitations:** final SP 与赛前 SP 容易混淆；同一价格可同时参与筛选和结算；多重切片。
- **Research Value:** 只保留作为变量审计和泄漏检查。
- **Sources / aliases:** `q_persistence_analysis.md`、`draw_odds_sensitivity_2026-06-27.md`、`p_*_q_overlay_384_2026-07-01.md`、`scripts/run_sp_native_analysis.py`。

### S019 - v3 LLM decision chain versus previous model-q
- **Research Question:** LLM/结构化信息层是否优于原 model-q 选码？
- **Core Hypothesis:** 信息面可把错误主押转为保护并提高覆盖。
- **Data Used:** 26071，15 settled legs（另 1 未结算）；同一 active snapshot。
- **Method / Experiment Type:** live observation / single-issue leg proxy comparison。
- **Metrics:** coverage、primary hit、cost、profit/ROI proxy、single/double mix。
- **Result Summary:** v3 coverage 53.3% -> 80.0%，ROI proxy 23.3% -> 32.2%，但成本 20 -> 25。
- **Current Evidence Level:** C。
- **Limitations:** 单期、同一结算、非 ticket replay、后验规则解释风险。
- **Research Value:** 保留为决策链考古起点，不支持泛化。
- **Sources / aliases:** `decision_chain_v3_vs_previous_26071_2026-07-03.md`、`structured_decision_chain_26071_shadow_2026-07-03.md`。

### S020 - v3.3.3 standardized decision chain
- **Research Question:** 能否使 API/artifact 决策一致、锁定赛前版本并正确区分结算字段？
- **Core Hypothesis:** 工程可重复性是任何 v3.3.3 比较的前提。
- **Data Used:** 26073 artifact audit 和 26071-26076 structured snapshots；赛前有效性逐 artifact 检查。
- **Method / Experiment Type:** baseline audit、shadow/live observation、artifact parity。
- **Metrics:** parity、pre-kick validity、primary hit、coverage、保护深度、stop state。
- **Result Summary:** Phase 1 通过工程边界验证；不是模型收益验证。后续期的表现仍是少数期观察。
- **Current Evidence Level:** C。
- **Limitations:** 旧运行链与标准化链不可混计；情报时效不齐；没有独立收益评估。
- **Research Value:** 值得保留为当前研究测量基线。
- **Sources / aliases:** `v3_3_3_phase1_baseline_audit_2026-07-11.md`、`active_v3_3_3_contract_handoff_2026-07-07.md`、`structured_decision_chain_*v3.3.3*`。

### S021 - v4.2 layered merge decision chain
- **Research Question:** 结构化 team-strength merge 能否修复 v3.3.3 的方向/平局冲突？
- **Core Hypothesis:** 多层合并提高覆盖，full-cover/skip 处理不确定性。
- **Data Used:** 26071 与 26072（含 augmented NowScore 结算）；部分为 late-proxy/非正式 500 结算。
- **Method / Experiment Type:** chain replay、rolling N-ticket seed simulation。
- **Metrics:** coverage、primary hit、ROI seed quantiles、full-cover 数。
- **Result Summary:** 报告的覆盖提高，rolling N replay 也显著更高；但 v4.2 使用 augmented/late inputs，buy-only 与 full-budget 不可比。
- **Current Evidence Level:** C。
- **Limitations:** 两期、输入时点不一致、seed simulation、组合成本可能爆炸、非正式结算。
- **Research Value:** 仅作为观察和冲突处理实现记录。
- **Sources / aliases:** `structured_decision_chain_v4_2_0000_backtest_summary_2026-07-05.md`、`v4_2_0000_execution_dashboard_handoff_2026-07-05.md`、`scripts/evaluate_structured_decision_chain_v4_2.py`。

### S022 - v4.3 probability-first chain
- **Research Question:** 固定概率主押、将 q 限于保护位是否更节省覆盖且提高主押？
- **Core Hypothesis:** q 不应推翻概率 top，SP sanity 可抑制异常价格。
- **Data Used:** 26071-26072，81 settled legs；v4.2 比较臂为 late proxy artifact。
- **Method / Experiment Type:** shadow backtest；不写 release。
- **Metrics:** coverage、primary hit、cost、mean depth、profit/ROI proxy。
- **Result Summary:** v4.3 primary hit 49.4% 高于 v3.3.3 42.0%，但 coverage 71.6% 低于 79.0%；ROI proxy 15.2%，无独立验证。
- **Current Evidence Level:** C。
- **Limitations:** 两期、同一规则后验设计、price substitution、单腿 proxy；与 v4.2 非同样本时点。
- **Research Value:** 不进入 release；保留作为“主押/覆盖是不同目标”的例子。
- **Sources / aliases:** `probability_first_decision_chain_v4_3_backtest_2026-07-07.md`。

### S023 - v3.3.3 primary optimization and protection trimming
- **Research Question:** 在不改变覆盖集或固定预算下，主押排序、双选和保护裁剪能否改善效率？
- **Core Hypothesis:** 概率优先或删除特定保护码可降低成本而不伤害覆盖。
- **Data Used:** 26071-26074、118 settled/104 executable（Phase 3）；含 legacy/non-standard artifacts。
- **Method / Experiment Type:** counterfactual ablation、fixed-budget replay、leave-one-issue-out。
- **Metrics:** primary hit、coverage、protection depth、ROI、LOIO sensitivity。
- **Result Summary:** 个别 in-sample 变体改善，但移除任一期会翻转 ROI；报告明确为 paper-forward hypotheses。
- **Current Evidence Level:** C。
- **Limitations:** 小样本、旧 artifact、候选多、同样本选择、非严格同一时间输入。
- **Research Value:** 仅能在后续预注册前向观察中验证；不优化参数。
- **Sources / aliases:** `v3_3_3_phase2_primary_optimization_2026-07-11.md`、`v3_3_3_phase3_protection_trimming_2026-07-12.md`、forward protocols、对应 `evaluate_*` scripts。

### S024 - shadow_n4_probability_weighted_512
- **Research Question:** 固定整期 N=4、512 元、概率优先抽样是否比现有票组更稳健？
- **Core Hypothesis:** 较低 N 与概率加权可改善三期组合诊断。
- **Data Used:** 26072-26074；shadow v3.3.3 选码；3,000 候选构造、10 seeds。
- **Method / Experiment Type:** paper portfolio / seed sensitivity。
- **Metrics:** merged diagnostic ROI、seed sensitivity、预算与执行开关。
- **Result Summary:** 三期合并诊断 ROI +27.82%，但文档明确十个 seed 不是独立验证，状态 `continue_paper_non_selectable`。
- **Current Evidence Level:** C。
- **Limitations:** 仅三期、抽样随机性、共用输入、无冻结运营随机策略、无前向执行复核。
- **Research Value:** 只保持前瞻纸面观察；不得加入 release 或前端可选项。
- **Sources / aliases:** `shadow_n4_probability_weighted_512_*_2026-07-14.md`。

### S025 - Segment N / ticket construction and budget scaling
- **Research Question:** 分段、N 上限、票组数上限和 scale-to-budget 如何影响人工执行与集中度？
- **Core Hypothesis:** 票组结构和预算是风险分配问题，不能从单场推荐直接推出。
- **Data Used:** 26072-26076 live artifacts、seed sample 和 operational windows；不少文件是运行时设计输出。
- **Method / Experiment Type:** operational simulation / portfolio construction。
- **Metrics:** selected bundles、cost、overlap、concentration、N、seed dispersion、settlement status。
- **Result Summary:** 产出大量分段票组文档，主要解决可解释性与成本；没有独立长期表现结论。
- **Current Evidence Level:** C。
- **Limitations:** 同一决策链上 seed 生成，票组可售性和实际下注并非完整记录；历史 ticket ROI 不能证明构造规则。
- **Research Value:** 保留为执行/风险审计；不计入 alpha 策略。
- **Sources / aliases:** `segment_betting_plan_*.md`、`segment_decision_refresh_protocol_2026-07-12.md`、`scripts/estimate_segment_betting_plan.py`、`scripts/replay_rolling_segment_n_tickets.py`。

### S026 - Correct-score Poisson / EV-q research package
- **Research Question:** 正确比分市场是否可用 1X2+O/U 推导分布并做 Top-k、EV/q 选择？
- **Core Hypothesis:** 有完整外部正确比分赛前价格时，可校准 Poisson 基线并评估深度。
- **Data Used:** 26076 起 forward external price captures；Nowscore/Crown 常缺尾部，Okooo/Williams 受登录/405 限制。
- **Method / Experiment Type:** data readiness + paper-only model design。
- **Metrics:** snapshot completeness、staleness、as-of validity、Top-k/EV-q（尚未可算）。
- **Result Summary:** 没有完整带时间戳赛前价格向量，严格 EV/q、ROI 和收益回放均未开始。
- **Current Evidence Level:** C（无策略收益证据）。
- **Limitations:** 缺尾部类别、部分/终值禁止输入、可售性未知；不能拿 500 中奖终值回填。
- **Research Value:** 先维护不可变价格资产；停止任何正确比分盈利主张。
- **Sources / aliases:** `correct_score_price_strict_asof_asset_2026-07-17.md`、`correct_score_research_results_2026-07-18.md`、`research/correct_score/`。

### S027 - Score projection and handicap-draw adapter
- **Research Question:** 由赛前 1X2/O-U 生成比分分布，再以让球/平局校准是否改善诊断？
- **Core Hypothesis:** 严格冻结的概率投影可用于比分选择或平局修正。
- **Data Used:** 26071-26074 proxy/research artifacts；部分为 approximate replay，不是完整正确比分价格回测。
- **Method / Experiment Type:** calibration lock、approximate replay、paper model。
- **Metrics:** proper-score metrics、diagnostic predictions、calibration、hit diagnostics。
- **Result Summary:** 已有首轮实现和研究报告，但明示只能 paper-only；没有合格 EV/q 或 ROI 结果。
- **Current Evidence Level:** C。
- **Limitations:** 价格输入不完整、calibration 与 outcome 同期、正确比分 tail 缺失、不可执行。
- **Research Value:** 保留为数据齐备后的模型候选，不推进策略。
- **Sources / aliases:** `score_projection_handicap_draw_*.md`、`2026-07-18-*-score-projection-*.md`、`scripts/run_approximate_score_projection_replay.py`。

### S028 - Multi-market and A9 protection-leg comparison
- **Research Question:** 总进球/比分等玩法的冻结输入，能否安全支持保护腿比较？
- **Core Hypothesis:** 只有事件包、overlap 哈希、停售前校验与研究回执都完整时，比较才可解释。
- **Data Used:** P0 immutable capture/freeze bundles、A9 event/receipt 路径；不写生产数据库。
- **Method / Experiment Type:** contract validation、dry-run、research snapshot production。
- **Metrics:** hash、coverage、earliest cutoff、partial-settlement rejection、idempotency。
- **Result Summary:** 研究侧消费链和生产侧事件契约已定义；这不是收益或预测策略实验。
- **Current Evidence Level:** C（数据工程证据）。
- **Limitations:** 玩法可售性、限额和完整赛前价格仍不足；不能由 dry-run 推出 ROI。
- **Research Value:** 值得继续作为严格回放基础；禁止接入正式策略或票据。
- **Sources / aliases:** `multimarket_p0_capture_freeze_settlement_contract_2026-07-16.md`、`strategy_parallel_a9_automation_coordination_contract_2026-07-16.md`。

## 4. 已否定与仍可保留的结论

### 已有明确反证或应停止的方向

1. **以 Kelly 或仓位公式修复负单场 edge：** 官方结算为负（S008）。
2. **泛化 league one-hot / 近期联赛加成：** 历史 OOS 没有支持（S005）。
3. **通过平局二元模型大量删平：** AUC 接近随机，阈值删去真实平局（S004）。
4. **高 SP/cold-tail 的历史凸性叙事：** 结果集中且严格报告可为负（S011）。
5. **将历史高 N ROI 外推到 2026：** 2026 proxy 提供负向压力测试（S015）。

### 值得保留，但只能作为研究基础的方向

1. **概率模型的时间外评分：** S002/S006 只在严格输入资产冻结后重现。
2. **价格时点与 SP drift：** S016/S017 用于采集和 as-of 质量审计，而非现在下注。
3. **v3.3.3 artifact 边界：** S020 是测量一致性前提，不是收益证据。
4. **多玩法与正确比分资产：** S026/S028 的价值是避免终值泄漏，尚未证明预测优势。

## 5. Research PI 的当前答案

1. **过去研究过什么？** 历史概率模型、SP/q/漂移、N=3/N=7 组合与资金分配、决策链、分段票组、
   多玩法与比分数据资产均已有探索；完整映射见 S001-S028。
2. **哪些方向已经失败？** Kelly-on-proxy、泛化联赛标签、平局删除、高 SP 冷门尾部，以及以历史收益外推 2026。
3. **哪些发现值得继续？** 严格赛前数据、预测评分、SP 时点审计与不可变冻结链路；它们都不是盈利结论。
4. **当前最有价值的下一步是什么？** 建立跨研究的输入 hash、规则版本、时间等级、结算口径和留出期的实验注册表；
   然后只复现少量锚点（S002、S005、S006、S008、S015），不再搜索新参数。

## 6. 维护规则

- 新报告先链接至既有 Strategy ID；只有改变研究问题、数据时点或规则族时才新增 ID。
- 参数、seed、预算和图表必须列为同一条目的 alias，不能以最大 ROI 新建策略。
- 每条新收益记录必须同时写入：输入 hash、赛前时间等级、是否使用 final/winning SP、训练/测试边界、
  所有扫描参数、实际成本/可售性和 concentration diagnostics。
- 未满足这些条件的结果默认 C；明确的负向复验默认 D。
