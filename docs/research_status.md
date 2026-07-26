# Beijing-lot Research Status

> 盘点日期：2026-07-20（Asia/Shanghai）
>
> 范围：本文件描述工作树中实际存在的数据、代码、文档和实验产物。它不是策略建议、
> 发布说明或盈利主张。动态数据库会继续更新，文中行数和最新时间戳均为盘点时观察值。

## 1. Project Overview

Beijing-lot 是一个以北单足球让球胜平负为主的研究与决策辅助仓库。项目同时保存：

- 长历史的赛果、赔率和特征代理数据；
- 2026 年起逐轮采集的赛前 SP、比分和外部赔率时间序列；
- 分段决策、票组和赛后复盘产物；
- 多个历史探索实验及一个本地决策看板。

当前应把它理解为一个正在建设数据证据链的研究项目，而不是已经获得可复现盈利结论的
系统。正式决策配置中存在概率模型、q 值和 v3.3.3 决策链，但这些是工程配置，不能替代
独立的样本外有效性证明。

### 1.1 Top-level directory tree

```text
beijing-lot/
├── apps/                 # Decision dashboard frontend
├── config/               # Version, release and collector plans
├── data/                 # Raw exports, SQLite stores, logs and profiles
├── docs/                 # Research, strategy and operations documents
├── notebooks/            # Python exploratory scripts, not Jupyter notebooks
├── ops/                  # systemd and Windows/WSL operational configuration
├── results/              # Experiment outputs and immutable capture/replay assets
├── scripts/              # Collectors, transforms, analyses and CLIs
├── src/                  # Reusable Python application and research modules
├── tests/                # Automated tests
└── .worktrees/           # Parallel worktrees; not a research data source
```

### 1.2 目录与模块

| 路径 | 类别 | 当前作用 |
| --- | --- | --- |
| `data/raw/` | 原始数据 | 历史北单 3-SP/结算 CSV、用户导出历史、football-data 五大联赛 CSV，以及早期回测输入。 |
| `data/derived/` | 派生数据 | `500_bjdc` 主决策库、`beidan_xlsm` 工作簿转换/建模库、SP drift 面板。 |
| `data/beidan_live.db` | 赛前时序数据 | append-only 的逐轮比赛、3-SP、可选投注比例/池规模、欧赔和结算旁路。 |
| `data/beidan_history.db`、`data/beidan_features.db` | 历史/特征旁库 | 早期历史赛果与特征实验输入；不是当前严格实时回放的唯一事实源。 |
| `scripts/scrape_*.py`、`scripts/live_*_loop.py` | 数据采集与调度 | 500、Nowscore/Jiebao、赛前快照、比分、详情、情报和多玩法捕获。 |
| `scripts/import_*`、`convert_*`、`normalize_*`、`build_*` | 清洗与建模表构造 | 导入 CSV/XLSM、标准化让球/队名、构建 `match_features`、`outcome_features` 和动作候选。 |
| `scripts/analyze_*`、`evaluate_*`、`backtest_*`、`walkforward_*` | 分析与实验 | 单场概率、q/赔率、N=3/N=7 组合、决策链、资金与敏感性研究。 |
| `src/` | 可复用实现 | 数据库访问、live collector、回测器、概率/策略模块、决策 API、WebUI 服务。 |
| `apps/decision-dashboard/` | 前端 | 本地决策看板和运行状态展示。 |
| `notebooks/` | 探索脚本 | 没有 Jupyter `.ipynb`；该目录实际是 Python 探索脚本，不是版本化 notebook 实验记录。 |
| `results/` | 实验结果 | 约 33GB 的 CSV、manifest、图、票组、冻结包和回测目录。许多目录名表示实验意图，但没有统一实验注册表。 |
| `results/data_collection/` | 原始捕获资产 | 新链路的原始响应、manifest、SHA-256 摘要和捕获批次。 |
| `results/research/` | 冻结研究输入 | 按 as-of 规则挑选的多玩法、Euro/O/U、正确比分等研究快照。 |
| `docs/research/` | 研究文档 | 数据契约、实验报告、决策链审计和前向观察记录。 |
| `docs/strategy/` | 策略设计资料 | 历史假设、路线图和执行约束。应与已验证的研究结论分开阅读。 |
| `tests/` | 验证 | 解析器、采集、决策 API、策略与前端测试；不等同于统计学验证。 |

### 1.3 数据流概览

```text
500.com HTML / XML --------------------> 500_bjdc.sqlite
       |                                     |- issues, matches, settlement/SP
       |                                     |- live_sp_snapshots
       |                                     `- live_market_sp_snapshots
       |
Nowscore/Jiebao ------------------------> 500_bjdc.sqlite
       |                                     |- match mapping and live score
       |                                     `- details and intelligence digest
       |
500.com + zgzcw live collector --------> beidan_live.db
                                             |- append-only 3-SP/volume/euro snapshots
                                             `- settlement side table

XLSM vendor workbook + 2026 update ----> beidan_modeling_plus_2026.sqlite
                                             |- match/outcome/action features
                                             `- 10h, 1h, final, initial odds proxies

immutable capture bundles -------------> results/data_collection/
as-of freeze/replay bundles -----------> results/research/
analysis scripts ----------------------> results/ and docs/research/
```

## 2. Data Assets

### 2.1 Data dictionary: Beijing single-game core

| Asset | Source and acquisition | Update and observed scope | Main fields | Meaning and research status | Quality / limitations |
| --- | --- | --- | --- | --- | --- |
| `data/derived/500_bjdc/500_bjdc.sqlite:issues` | 500.com 北单期次 HTML, `scripts/scrape_500_bjdc.py` | Collector plan: 15 minutes. At audit: 2,134 issue identifiers, `070502`–`26076`. | `issue`, `ordinal`, `label`, `is_selected`, `is_current`, `year`, `first_seen_at`, `last_seen_at` | Issue discovery and lifecycle anchor. | Issue number alone is not a decision-time timestamp; current issue state can change during polling. |
| `...:matches` | 500.com trade page, same scraper | Collector plan: current/recent/unsettled issues every 15 minutes. At audit: 74,814 rows, 219 league labels. | `issue`, `match_idx`, `fid`, `league`, `home`, `away`, `end_time`, `handicap_line`, ranks, `score`, `result_*`, `winning_sp`, `sp_home/draw/away`, average Euro odds, `raw_row_hash`, `fetched_at` | Main match and 3-way settlement inventory. `result_code` is the handicapped 3/1/0 result. | Table upserts `(issue, match_idx)`: it is not a full historical version of every page. `fetched_at` is a local timestamp without an explicit timezone. |
| `...:live_sp_snapshots` | 500 XML `just_{issue}_34.xml`, `scrape_live_sp` | Plan: 15 minutes. At audit: 481,909 rows, issues `26065`–`26076`. | `issue`, `playid`, `fetched_at`, `source_updatetime`, teams, league, handicap, `sp_home/draw/away`, `raw_node` | Time series for handicap 3-way SP. | Earlier history is absent; source update time and capture time have mixed timestamp conventions. Do not infer a particular pre-kick snapshot when no contemporaneous row exists. |
| `data/beidan_live.db` | `python -m live_collector`: 500.com + zgzcw, with 500 result fallback | Plan: randomized 5–15 minute polling. At audit: 3,444 matches (`26051`–`26076`), 934,080 snapshots, 2,247 settlements. | `matches`: issue/match/kickoff/teams/handicap; `snapshots`: `sp_3/1/0`, `vol_pct_3/1/0`, `pool_total`, `eu_h/d/a`, `snapshot_ts`, `source`; `settlements`: score, result, winning SP, average Euro odds | The principal append-only forward 3-way time series. It is suitable for strict as-of work only after per-match pre-kick coverage and settlement completeness are verified. | `vol_pct_*` and `pool_total` require authenticated 500 cookies and can be null. There is no historical reconstruction for missing polls. Snapshot `source` is currently `merged`, which weakens source-level provenance unless raw logs are inspected. |
| `data/raw/beidan_full_3sp.csv` | Historical 3-SP/settlement export, imported by `import_beidan_full_3sp_to_sqlite.py` | 135,556 data rows observed; header example begins `180201`. | `expect`, `match_no`, kickoff, league, teams, score, handicap, half-time score, `result_code`, `winning_sp`, `last_update_ts`, `sp_3/1/0` | Broad historical 3-way settlement inventory. | `last_update_ts`/SP semantics are not a verified decision-time series for every match. Treat as settlement or proxy input unless a source-time contract is separately established. |
| `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite` | Vendor XLSM parsed without executing macros by `convert_beidan_xlsm_to_sqlite.py`; 2026 update joins added by build scripts | At audit: 201,270 `matches`, `outcome_features` 603,810, `action_candidates` 1,610,160. Covers issues `140101`–`26051`; build metadata `2026-06-30`. | `matches`, `market_consensus`, `match_features`, `outcome_features`, `action_candidates`; 1X2 Euro odds/probabilities at `initial`, `10h`, `1h`, `final`, Kelly and line features | Historical modelling table for 3-way probabilities and action-level backtests. | Coverage ends at `26051`, while the operational database continues to `26076`. Excel serial conversion includes a sentinel date `1899-12-30`; all analyses must filter invalid kickoff values. Snapshot fields are source-workbook proxies and require their own as-of validation. |
| `data/derived/500_bjdc/500_bjdc.sqlite:nowscore_*` | `cp.nowscore.com` BJDC page and detail pages; `scrape_nowscore_bjdc.py`, `scrape_nowscore_match_details.py` | Score mapping plan: 2 minutes; details: 5-minute scan and 2-hour TTL. At audit: 519 match rows (`26065`–`26076`), 264 detail rows (`26071`–`26076`). | stable `provider_match_id`, schedule/kickoff, league, teams, score/half-time/status, sale flag, URLs; detail summaries, raw hash and payload | Cross-source match identity, real-time score, context, and source URLs. | Detail content is a mutable scraped summary. Match mapping and name/handicap alignment must be checked before joins; text is not a validated predictive feature. |
| `match_intel_sources`, `match_intel_digest`, `match_details_500` | Nowscore/500 details and `collect_match_intel.py` | Best effort; detail TTL 2 hours. | source tier, title/URL/text, payload hash, digest, status/error | Auditable research context and missingness diagnostics. | No long, homogeneous historical text corpus; post-hoc text must not leak into pre-match studies. |

### 2.2 Data dictionary: non-3-way markets and external prices

| Asset | Source and acquisition | Update and observed scope | Fields / coverage | Research eligibility and caveats |
| --- | --- | --- | --- | --- |
| `live_market_sp_snapshots` | 500 XML, playids 40/41/42/51 via `scrape_live_sp` | Plan: 15 minutes. At audit: 1,403,836 rows, issues `26071`–`26076`. 40 total-goals: 180,992 rows; 41 upper/lower odd/even: 116,800; 42 correct-score: 640,675; 51 half/full: 261,981. | `issue`, `playid`, `market_key`, outcome code/label/SP, dual source/capture times, sale status, parlay fields, raw node/hash linkage. Playid mapping: 40 total goals, 41 upper/lower odd/even, 42 correct score, 51 half/full. | A raw time series exists. However, sale and parlay metadata are mostly incomplete: 595,732 rows have `sale_status=unknown`; `parlay_allowed` is `unknown` for all rows at audit. “Quoted” is not evidence that the outcome was purchasable in a particular parlay. |
| `market_sp_capture_batches` and `results/data_collection/multimarket_sp_capture_v1/` | Immutable P0 capture publisher with raw XML, manifest and `SHA256SUMS` | At audit: 613 batches, `26071`–`26076`; target 40/42 has forward-complete-open classifications. | batch IDs, payload and bundle hashes, row counts, source and capture clocks, sale classification. | Required audit layer for strict total-goals/correct-score research. Historical terminal-backfill rows are explicitly exploratory/settlement-only, not pre-match price inputs. |
| `multimarket_settlement_truth` | Settlement builder, based on final score and winning SP | At audit: 548 `(issue, match, market)` rows: 528 settled, 18 pending/unknown, 2 cancelled. | `fthg`, `ftag`, outcome code, winning SP, status, special flags, source provenance. | Good for truth labels after checking flags. A final winning SP is not a pre-match SP. |
| `results/data_collection/nowscore_score_model_history_v1/` and `results/research/nowscore_score_model_segment_replay_v1/` | Titan007/Nowscore Euro 1X2 and O/U endpoint capture, triggered around segment freezes | Forward immutable asset; exact usable coverage must be read from each manifest. | provider match ID, Euro/O/U price vectors, source and fetch times, line, raw hash, completeness, as-of age. | Intended strict model input, paper-only. Do not replace it with currently displayed pages or terminal values. |
| `results/data_collection/correct_score_price_history_v1/` and corresponding replay root | Nowscore Crown correct-score observations, optional Okooo/William Hill route, immutable capture loop | Forward collection starts with issue `26076`; automated rolling observations are configured. | provider and match IDs, 25 exact score prices, page/source time, raw files/hash, completeness and missing reason. | Current Nowscore/Crown pages commonly lack the three tail outcomes; these are explicitly `partial` and cannot support strict Top-k, EV/q or ROI. Okooo history may require login or return 405. |
| `data/derived/beidan_xlsm/beidan_xlsm.sqlite:exotic_odds` (`market="score"`) | Historical vendor XLSM tail, converted read-only by `convert_beidan_xlsm_to_sqlite.py` | `SCORE-PRICE-HIST-AUDIT-001` found 5,076,994 price rows across 195,269 matches; 157,405 valid complete 26-way vectors. | 26 score labels, one value per `(match_id, outcome)`; joins to converted kickoff/`ts_10h` fields are possible. | **Present but unqualified.** The audit did not establish provider identity, Beijing p42 identity, a source observation clock, or that `ts_10h` applies to the score vector. Classification: `UNRESOLVED`/`UNVERIFIED`, `PROHIBITED` for replay. Do not call it historical pre-match p42 SP. |
| `data/raw/football-data/` | Imported external football-data CSVs | Five leagues across multiple seasons; `SUMMARY.md` reports 9,498 matches and 100+ columns for the listed source set. | Match identity, results and bookmaker columns, depending on file. | External modelling/control data, not an auditable North Beijing single-game price history. League and team matching need normalization. |

### 2.3 Specific answers to the Beijing single-game data questions

| Question | Evidence-backed answer |
| --- | --- |
| Match information, league, teams and time? | Yes. `matches`, `nowscore_bjdc_matches`, `beidan_live.matches` and XLSM-derived `matches` contain them, but their update and timestamp semantics differ. |
| Bet types? | Yes. Handicap 3-way (`playid=34`), total goals (40), upper/lower odd/even (41), correct score (42), half/full (51) are explicitly mapped in the 500 XML collector. |
| SP data? | Yes, with different grades: final/current 3-way SP in `matches`; append-only live 3-way snapshots in `beidan_live` and `live_sp_snapshots`; multi-market outcome SP in `live_market_sp_snapshots`; workbook 1X2 snapshots in the modelling DB. |
| Final results? | Yes. Main table, live collector settlements, Nowscore score fields, raw 3-SP export and multi-market truth all contain results, with source-specific completeness and correction behavior. |
| Parlay information? | Incomplete. Multi-market schema has `parlay_allowed`, `parlay_modes_json`, `stake_limit_json`, but at audit `parlay_allowed` is all `unknown`. Ticket-generation outputs exist, but they are not a source-of-truth record of market availability or limits. |
| Historical SP changes? | Partly. `beidan_live.db` provides actual forward sequences from `26051`; 500 main live snapshots begin at `26065`; multi-market snapshots begin at `26071`. Older XLSM 1X2 fields provide named snapshots (`initial`, `10h`, `1h`, `final`), not a verified continuous historical sequence. Its separate 26-column score tail is now presence-verified but has unresolved provider/market/time semantics, so it is prohibited for historical as-of replay. |
| Betting volume or market information? | Partly and not reliably complete. `beidan_live.snapshots` has `vol_pct_*` and `pool_total`; these depend on authenticated 500 cookies and have no audited long historical coverage. External Euro prices/consensus are available in several assets. No verified full historical turnover, liquidity or parlay-limit series exists. |

### 2.4 Data quality grading

Use these labels when selecting a research dataset:

| Grade | Definition | Examples |
| --- | --- | --- |
| A: strict as-of eligible | Append-only or immutable record with source/capture time, known pre-decision relation, completeness checks and no post-cutoff substitution. | Verified `beidan_live` rows with pre-kick coverage; validated Nowscore/Titan replay bundles; valid P0 freeze bundles. |
| B: time-stamped but must be checked per use | Has capture time but may have mutable/upserted rows, incomplete options or source-time ambiguity. | `live_sp_snapshots`, `nowscore_*`, `live_market_sp_snapshots` before manifest-level qualification. |
| C: proxy / exploratory | Historical or snapshot-like values without sufficient proof that they were observable at the claimed decision point. | XLSM 10h/1h fields, `beidan_history.db` average Euro odds, historical 3-SP export. |
| D: settlement or post-sale only | Correct for outcome verification, prohibited as a pre-match feature or ROI input. | Winning SP backfills, terminal 500 multi-market rows, post-match reviews. |

## 3. Existing Analysis

The repository contains a large number of strategy and sensitivity scripts. They fall into the
following research families; file counts and directory names are not evidence of independent
replications.

| Family | Representative implementation / report | Dataset and method | Status |
| --- | --- | --- | --- |
| Historical 3-way probability modelling | `walkforward_beidan_result_model_eval.py`, `snapshot_pure_result_model.py`, `historical_match_tag_walkforward_2026-07-11.md` | Multinomial/logistic-style probability evaluation on historical outcome features, with walk-forward or rolling windows. | Model metrics are available; no profitability claim follows. |
| q and price diagnostics | `run_sp_native_analysis.py`, `run_sp_drift_*`, `analyze_euro_avg_sp_shadow_backtest.py` | Compare SP-derived q, Euro price proxies, movements and decision-chain sensitivity. | Mainly diagnostic, often small live samples. |
| N=3/N=7 combination backtests | `evaluate_n*_*.py`, `backtest_combo/`, `results/*n7*` | Generate legs and ticket portfolios, then compute simulated stake/return/ROI/drawdown. | Large exploratory family with high multiple-comparison risk. |
| Decision-chain v3.3.3 / v4.2 comparison | `evaluate_structured_decision_chain_shadow.py`, `evaluate_structured_decision_chain_v4_2.py` | Frozen artifact or shadow CSV replay with primary, protection and stop states. | v3.3.3 engineering baseline was normalized; comparative performance remains a paper/observational question. |
| 2026 live holdout proxy | `evaluate_2026_live_holdout_proxy.py`, `2026_current_data_holdout_summary_2026-06-29.md` | Historical training plus 2026 live 1h snapshots and settled tickets. | Negative / highly concentrated results are documented; proxy is not exact production replay. |
| Multi-market data readiness | `manage_multimarket_p0.py`, Nowscore/correct-score capture managers | Immutable capture, as-of freeze, settlement truth and hash verification. | Data engineering validation, not a completed return study. |
| Data-source and collection audits | collector runbook, P0 contract, `audit_data_collection_status.py` | Coverage, freshness, parser and manifest verification. | Necessary operational evidence, not predictive evidence. |

### 3.1 Existing model artefacts

Configuration identifies the following currently implemented components:

| Component | Declared version / role | Inputs | Current evaluation measures |
| --- | --- | --- | --- |
| Handicap-adjusted 3-result probability | `bd_prob_handicap_calibrated_v1` | 500/live-market proxy, integer handicap and calibrated outcome probabilities. | Log loss, Brier score, Top-1 accuracy, Top-2 coverage and calibration-oriented diagnostics. |
| q expected-value proxy | `q_ev_sp_v1` | Probability estimate and a pre-result SP snapshot when available. | q distribution, selection changes, hit/coverage, simulated cost/return/ROI proxy. q is not independently proven expected value. |
| Fixed decision chain | `llm_chain_bet_protect_stop_v3.3.3` | Probability, q, SP, handicap, timestamped match-detail/intel inputs and guards. | Primary hit rate, protected coverage, protection depth, stop state, artifact parity and pre-kick validity. |
| Snapshot-pure result model | Research module, not declared production release | Snapshot odds/probability/rank, handicap, train-only priors, Kelly and permitted drift. | Log loss, Top-1, Top-2; downstream N=7 return is separately evaluated. |
| N=7 / ticket allocation families | Many research scripts; release registry names a fixed-384 main family | Selected legs, simulated ticket construction, budget/seed/protection settings. | Stake, payout, PnL, ROI, full-loss rounds, max drawdown, concentration and leave-one-issue sensitivity. |

No model in the repository has a documented, independently replicated proof of positive live
expectation after North Beijing single-game takeout, availability constraints and a prespecified
out-of-sample protocol.

### 3.2 Experiment record

The following is a compact registry for the principal identifiable experiments. It deliberately
does not relabel every parameter sweep as a separate scientific result.

#### EXP-001: Snapshot-pure result model audit

- **Research Question:** Does a result model using only decision-time snapshot inputs improve 3-way probability quality without final-odds leakage?
- **Dataset:** Historical model table; reported 10h/1h evaluation in `snapshot_pure_result_model_audit_2026-06-26.md`.
- **Method:** Snapshot-market baseline versus snapshot-pure model; log loss, Top-1 and Top-2, followed by N=7 simulated-ticket comparisons.
- **Result:** Reported 10h log loss improved from 1.1601 to 1.1005 and Top-2 coverage from 68.6% to 72.1%; 1h values show a similar model-metric improvement.
- **Conclusion:** Better single-match predictive scores did not reliably improve N=7 simulated return.
- **Limitations:** Historical snapshot provenance and tail-return concentration; ticket outcome is a separate objective.
- **Next Step:** Reproduce under a frozen, time-grade-labelled dataset before interpreting downstream return.

#### EXP-002: 2026 current-data live holdout proxy

- **Research Question:** Does the historical high-N / EV route survive on 2026 forward 1h data?
- **Dataset:** Fully settled 2026 issues with local `beidan_live` 1h snapshots; default report lists nine issues and eight ticket-producing issues.
- **Method:** Train on pre-2026 history, generate a proxy replay, exclude partially settled issues.
- **Result:** The reported last-24-window baseline, EV and topology proxies all lost every tested ticket issue; all-history sensitivity had one large winning issue and negative ROI after removing it.
- **Conclusion:** This is a negative stress signal, not evidence for the historical route.
- **Limitations:** It is explicitly not the exact production 384 chain and 2026 coverage was incomplete at the report date.
- **Next Step:** Use the now-extended data only after an exact, preregistered replay input set is frozen.

#### EXP-003: Historical league/tag walk-forward ablation

- **Research Question:** Do league labels, ranks and Asian-line fields add 3-way predictive value beyond market plus handicap?
- **Dataset:** 190,511 usable historical rows; 2016–2025 season-wise out-of-sample tests.
- **Method:** Earlier-season-only training, same multinomial logistic form and test rows; compare feature sets.
- **Result:** Adding league to market+handicap changed OOS log loss by +0.000747 (worse); all-with-league was worse in 9 of 10 reported seasons.
- **Conclusion:** No support for a generic league one-hot improvement.
- **Limitations:** Uses closing/pre-match available fields, not the current segment freeze input; does not assess ticket ROI.
- **Next Step:** Retain as a negative control and avoid league-rule claims from recent small groups.

#### EXP-004: Recent positive-league follow-up

- **Research Question:** Are apparent short-window gains for selected leagues stable in older out-of-sample seasons?
- **Dataset:** Selected league slices from 2016–2025 OOS and recent 26071–26072 development observations.
- **Method:** Paired baseline versus league-tag model within each league.
- **Result:** All listed league log-loss deltas were non-improving or near zero; cross-season improvement counts were inconsistent.
- **Conclusion:** The recent signals are observations, not reusable league effects.
- **Limitations:** Selection was post-hoc and several leagues have small samples.
- **Next Step:** Do not hard-code a league adjustment without a new prespecified validation set.

#### EXP-005: Euro-average-SP substitution shadow

- **Research Question:** Does replacing 500 SP with contemporaneous Euro consensus make q decisions less unstable?
- **Dataset:** Active decision snapshots for issues 26071–26072, 81 settled legs and 76 legs with SP settlement in the report.
- **Method:** Hold model probability, intel, handicap and outcomes fixed; replace only the price input.
- **Result:** q tails contracted and average selection depth/cost fell; protected hit rate also fell (79.0% to 74.1%). ROI proxies were 6.9% versus 7.8%.
- **Conclusion:** Price disagreement is a useful diagnostic hypothesis, not a validated replacement rule.
- **Limitations:** Two issues, proxy settlement, and shared decisions make observations highly dependent.
- **Next Step:** Treat any disagreement guard as paper-only until prospectively frozen.

#### EXP-006: v3.3.3 Phase 1 baseline audit

- **Research Question:** Is the v3.3.3 engineering baseline internally consistent and protected from post-kickoff artifact substitution?
- **Dataset:** API/artifact parity tests and issue 26073 production artifacts.
- **Method:** Unify decision core, lock artifact before first kickoff, distinguish absent ticket financials from match settlement.
- **Result:** Parity/release/freeze tests passed; 26073 selected artifact was pre-kickoff valid. The report notes three unrelated legacy WebUI test failures.
- **Conclusion:** This validates an engineering/measurement boundary, not forecast skill.
- **Limitations:** It does not establish an out-of-sample return estimate.
- **Next Step:** Preserve the frozen artifact protocol in all future comparative experiments.

#### EXP-007: v3.3.3 primary-selection and protection counterfactuals

- **Research Question:** Can primary ranking or protection trimming improve efficiency while holding coverage/cost controls fixed?
- **Dataset:** Historical frozen/legacy decision artefacts; Phase 3 reports 118 settled matches, 104 executable, across 26071–26074.
- **Method:** Counterfactual primary/cover variants, fixed-budget ticket replay and leave-one-issue-out sensitivity.
- **Result:** Some variants improved particular in-sample proxy rows, but reported ROI flips across omitted issues; `model_ev_only` depends on 26073 and baseline ticket ROI was negative in the shown four-issue replay.
- **Conclusion:** Candidates remain paper-forward hypotheses only.
- **Limitations:** Legacy/non-standardized artefacts, few issues, shared tuning and multiple comparisons.
- **Next Step:** Prospective paired observation with a fixed rule and complete pre-kick inputs.

#### EXP-008: Multi-market P0 capture/freeze/settlement

- **Research Question:** Can total-goals and correct-score data be captured and replayed at a defensible as-of time?
- **Dataset:** 26071 onward batches; P0 contract documents 26075 validation and terminal backfill for earlier issues.
- **Method:** Immutable raw XML, manifest and SHA-256; freeze requires complete pre-cutoff vector, sale state and timestamp checks; settlement is separate.
- **Result:** The pipeline records both valid forward rows and explicit rejections. Historical terminal data are labeled exploratory-only.
- **Conclusion:** Data readiness has improved; ROI authorization remains false.
- **Limitations:** Parlay/limit metadata remain unknown and early historical pre-kick coverage is sparse.
- **Next Step:** Continue collection and publish coverage/missingness before any model experiment.

#### EXP-009: Correct-score external-price asset

- **Research Question:** Is there a complete, timestamped external correct-score price vector for strict EV/q replay?
- **Dataset:** 26076 forward captures from Nowscore/Crown and attempted Okooo/William Hill access.
- **Method:** Immutable raw pages and hashes; require exact-score and tail completeness before replay eligibility.
- **Result:** Nowscore observations retain exact-score prices but commonly miss tail outcomes; Okooo access can be blocked/login-required.
- **Conclusion:** No strict correct-score EV/q or ROI result exists yet.
- **Limitations:** Incomplete outcome vectors and blocked provider history.
- **Next Step:** Record missingness faithfully; never substitute terminal 500 values as pre-match prices.

## 4. Existing Findings

The following statements have direct supporting analyses, but their scope is intentionally narrow.

1. **Historical league labels did not add general OOS 3-way accuracy.** The 2016–2025 season walk-forward comparison found no generic improvement and mostly worse log loss after adding league one-hot fields.
2. **Snapshot-pure modelling improved reported single-match probability metrics.** It improved reported log loss and Top-2 coverage over the snapshot-market baseline, while failing to show a stable N=7 return improvement.
3. **2026 proxy replay is a warning, not validation.** The documented short-window holdout lost all test ticket issues; a favourable all-history sensitivity was concentrated in one issue.
4. **A pre-kick artifact boundary is now explicit for the v3.3.3 comparison path.** The baseline audit prevents using a post-settlement artifact as the observed pre-match recommendation.
5. **The project now distinguishes raw multi-market captures, as-of freezes and settlement truth.** This prevents terminal winning SP from being silently represented as a historical pre-match vector.
6. **Complete market availability is not established merely by a quoted SP.** Parlay permissions and limits are not populated, so return work for multi-market tickets is not authorized.

These are research and data-integrity findings. None says that a given selection, market, league, price rule or portfolio has positive expected return.

## 5. Unverified Observations

The following items are present in reports or result folders but do not meet a sufficient standard for a general claim:

| Observation | Why it remains unverified |
| --- | --- |
| A recent league category appears to improve hit rate. | Selected after inspecting small recent samples; historical season walk-forward did not confirm a stable generic league effect. |
| Extreme 500 SP versus Euro consensus identifies bad q decisions. | The direct shadow report uses two issues and a proxy return measure; no locked prospective rule is yet evaluated. |
| A primary/cover rule improves v3.3.3 efficiency. | Counterfactuals use few issues, legacy artefacts and many candidate comparisons; leave-one-issue-out results are unstable. |
| N=7 or high-SP configurations have attractive historical ROI. | Several reports show dependence on one or a few large winning tickets/periods. Ex-best and ex-top-K checks often change the conclusion. |
| Better probability accuracy should improve ticket profitability. | The snapshot-pure audit is a direct counterexample: probability metrics improved while simulated high-N economics did not reliably improve. |
| Multi-market/score EV can be estimated from historical winning SP. | This would use post-sale information unless a complete, timestamped pre-sale vector is verified; current contracts prohibit it. |

## 6. Known Limitations

### 6.1 Scientific limitations

- **Small samples:** Recent decision-chain and price-substitution reports cover only a few issues. Legs from the same issue are correlated and must not be treated as independent trials.
- **Multiple comparison:** The repository contains many parameter sweeps and experiment directories. A best row chosen after scanning them is an exploratory result, not a test result.
- **Data snooping and leakage:** Final prices, winning SP, post-match text and retroactive artifacts can be available in the same database as pre-match fields. Every study needs an explicit as-of cutoff and source-time rule.
- **Outcome mismatch:** Log loss, Top-1/Top-2, protected coverage, ticket hit rate, ROI, drawdown and manual betting burden answer different questions. Improvement in one does not imply improvement in another.
- **Return realism:** Multi-market purchase availability, permitted parlay modes, limits, cancellation and void handling are not yet fully captured. A simulated ticket is not automatically an executable ticket.

### 6.2 Data limitations

- Historical assets use mixed timestamp conventions. Older `fetched_at` strings may lack timezone; newer immutable bundles explicitly record UTC/HKT clocks.
- `matches` and Nowscore mapping tables are mutable upserts, whereas live snapshots and capture bundles are append-only. They require different audit treatment.
- Pre-26051 3-way work depends heavily on workbook/export snapshot proxies, not a locally observed continuous 500 SP history.
- The current modelling-plus database ends at issue 26051; it is not a complete mirror of the current live database through 26076.
- Correct-score external prices are currently incomplete or access-constrained, and cannot support strict EV/q or ROI study.
- The cookie-dependent volume fields may be missing and have no demonstrated long historical availability.
- Raw source, transformed database, frozen research input and reported result are not yet linked by one repository-wide dataset/experiment manifest.
- The worktree contains many uncommitted generated documents and code changes. Until committed hashes and manifests are recorded, reproducibility depends on the local state.

### 6.3 Engineering limitations relevant to research

- The test suite has documented legacy failures outside the v3.3.3 baseline scope; test pass status must be recorded with each research run.
- `results/` is large and heterogeneous. Directory names alone do not preserve command line, package version, input hash, random seed or exclusion rules.
- `notebooks/` contains Python files rather than notebook metadata, so hypotheses, execution order and output provenance are not automatically captured.

## 7. Recommended Next Research Tasks

These are research-foundation tasks only. They do not propose a new betting rule, model or
portfolio.

1. **Create a canonical research dataset manifest.** For each study, record input paths, SHA-256 hashes, row counts, schema version, issue range, time grade and code commit. Separate A/B/C/D data grades at the loader boundary.
2. **Publish a machine-readable data dictionary and schema checks.** Derive it from SQLite `PRAGMA table_info`, CSV headers and capture manifests; alert on renamed fields, duplicated keys, invalid handicaps, invalid scores and mixed timezone values.
3. **Establish an experiment registry.** Assign stable experiment IDs; record question, hypothesis status, data eligibility, train/test windows, command, seed, metrics, result path and whether the outcome is exploratory or confirmatory.
4. **Reproduce a small set of anchor analyses.** Re-run EXP-001 through EXP-005 from immutable inputs or explicitly label each unavailable dependency. This is a reproducibility audit, not a search for a better result.
5. **Finish the strict as-of coverage audit.** Report, by issue/segment/match/market, whether a complete pre-freeze vector exists, its source age and why a row was rejected. Do not impute missing pre-match values with terminal data.
6. **Audit settlement joins and source disagreement.** Produce one reconciled truth table for score, handicapped 3-way code, cancellation/postponement, winning SP and provenance; quantify conflicts before using a row in evaluation.
7. **Define a preregistered evaluation protocol.** Freeze the unit of analysis, embargo period, train/test chronology, primary and secondary metrics, concentration diagnostics, multiple-testing policy and stop criteria before any next model comparison.
8. **Separate operational artefacts from research data.** Keep decisions, ticket plans and dashboard state queryable, but require a read-only, hash-addressed export for any paper intended as evidence.

## Appendix A: Field semantics requiring care

| Field family | Interpretation |
| --- | --- |
| `result_code` / `result_label` | North Beijing single-game outcome after applying its handicap convention. It is not necessarily the raw 1X2 score result. |
| `winning_sp` | Winning option's settlement SP. It is a truth/settlement field, not automatically a pre-match feature. |
| `sp_3`, `sp_1`, `sp_0` | North Beijing 3-way prices for handicap win/draw/loss; order must not be silently mapped to raw home/draw/away without the handicap semantics. |
| `euro_*` / `avg_odds_*` | External or average Euro 1X2 prices. Provider, timestamp and whether the value is final/average/snapshot must be retained. |
| `fetched_at`, `snapshot_ts`, `source_updatetime` | Respectively local capture time, collector observation time and upstream-declared update time. They are not interchangeable. |
| `sale_status`, `parlay_allowed`, `stake_limit_json` | Availability metadata. Unknown must remain unknown; it must not be converted to allowed. |
| `capture_classification` | Distinguishes forward complete capture from post-sale/terminal backfill. It controls research eligibility. |
| `q_score` | Project expected-value proxy, not a calibrated proof of expected return. |
| `confidence` / `probability` | Model outputs whose version and input timestamp must accompany any evaluation. |

## Appendix B: Primary evidence files

- `docs/research/data_collection_inventory_and_maintenance_plan_2026-07-12.md`
- `docs/research/multimarket_p0_capture_freeze_settlement_contract_2026-07-16.md`
- `docs/research/nowscore_score_model_strict_segment_snapshot_asset_2026-07-16.md`
- `docs/research/correct_score_price_strict_asof_asset_2026-07-17.md`
- `docs/research/snapshot_pure_result_model_audit_2026-06-26.md`
- `docs/research/2026_current_data_holdout_summary_2026-06-29.md`
- `docs/research/historical_match_tag_walkforward_2026-07-11.md`
- `docs/research/historical_positive_league_tag_effect_2026-07-11.md`
- `docs/research/euro_avg_sp_shadow_backtest.md`
- `docs/research/v3_3_3_phase1_baseline_audit_2026-07-11.md`
- `docs/research/v3_3_3_phase3_protection_trimming_2026-07-12.md`
