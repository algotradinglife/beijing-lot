# Experiment Registry

状态：`protocol_v1_initialized`

本登记册记录进入 Freeze Protocol v1 的研究实验，而不是策略发布目录。每个条目必须在赛前
冻结时建立；事后探索可以登记，但其状态必须明确为 exploratory，不能补写为前向验证。
“有正 ROI”不是证据等级。

| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |
| --- | --- | --- | --- | --- | --- | --- |
| `SP-EFF-001` | SP-EFF-001: Does Beijing Single Match SP contain calibrated predictive information about 90-minute handicap 3/1/0 outcomes? | `research/sp-eff-001` | `14993d22c46585a8ad7ce8067cd1a87758eb986ac0028256ef49b3415451658a` | `reviewed` | `directional_sp_information_no_holm_rejection` | `A` |
| `MM-DATA-AUDIT-001` | For each target market (Handicap 3/1/0, Correct Score, Total Goals, Half/Full Time), does the current forward data chain provide sufficient evidence to support strict as-of research under Freeze Protocol v1? | `research/mm-data-audit-001` | `e3fee9f2241b258eb6fa406b50e80d403193448d73a9ea070c0a1e386ee8c976` | `reviewed` | `no_market_end_to_end_ready` | `B` |
| `SP-CONSISTENCY-001A-G0-R4` | Is strict paired pre-match coverage sufficient to compare score-derived and p34 handicap probabilities without leakage or retrospective substitution? | `strategy/active` | `12db65db1b7e4e976336c75df424d3866a0066dec5bbd92bce39accfe4c8fd4e` | `reviewed` | `insufficient_strict_data_no_formal_comparison` | `C (coverage gate only)` |
| `SCORE-PRICE-HIST-AUDIT-001` | Does the XLSM-derived historical score-price vector exist, and can its provider, market identity, and time semantics support any historical research use? | `strategy/active` | R5 package manifest | `frozen_pending_review` | `price_vector_present_but_identity_and_time_unverified; replay_prohibited` | `D` |
| `HIST-DATA-CENSUS-001` | Which long-horizon historical assets may support strict replay, proxy analysis, labels, settlement, or no research input? | `research/hist-data-census-001` | immutable census package manifest | `frozen_pending_review` | `inventory_and_admissible_use_matrix_frozen; no model_or_roi_conclusion` | `data eligibility audit` |
| `SCORE-HCAP-HIST-001-B0-B1-R8` | Does frozen historical score history plus known integer handicap improve 3/1/0 Log Loss over a handicap-only historical prior under chronological whole-season holdouts? | `strategy/score-hcap-hist-001` | `2afdc5922011dd258db9ac5b1d88d2f6992f0e16fedadd613e4b36546f58a8d8` | `frozen` | `NO_REPRODUCIBLE_INCREMENTAL_SIGNAL; fresh independent EV and PI continuity pending` | `C (retrospective; source provenance capped)` |

### MM-DATA-AUDIT-001 verification snapshot

- Freeze status: `frozen`; audit report status: `reviewed`; PI result: `no_market_end_to_end_ready` (PR #13).
- Test command: `pytest -q tests/test_mm_data_audit.py` — 72 passed.

| Market | Pre-Event Input | Freeze Support | Settlement Support |
| --- | --- | --- | --- |
| Handicap 3/1/0 | `PARTIAL` | `PARTIAL` | `READY_STRICT` |
| Total Goals | `READY_STRICT` | `SETTLEMENT_ONLY` | `READY_STRICT` |
| Correct Score | `READY_STRICT` | `SETTLEMENT_ONLY` | `READY_STRICT` |
| Half/Full Time | `PARTIAL` | `UNAVAILABLE` | `UNAVAILABLE` |

## 字段约定

| 字段 | 记录要求 |
| --- | --- |
| Experiment ID | 唯一、不可复用的实验标识；应与 `results/freeze/<experiment_id>` 一致。 |
| Research Question | 赛前写明、可被数据否定的问题，不写盈利承诺。 |
| Branch | 产生冻结决策的 git branch。 |
| Freeze ID | 冻结 manifest 生成的 hash 身份；无有效 freeze 时留空。 |
| Status | `planned`、`frozen`、`settled`、`reviewed`、`rejected` 或 `exploratory_only`。 |
| Result | 仅在有完整、可核验结算和独立 review 后记录；否则写 `pending`。 |
| Evidence Level | `A` 严格样本外/前向，`B` 可复验回测但仍需验证，`C` 探索观察，`D` 被否定或明显过拟合。 |

登记册不替代 freeze manifest。来源时间、输入 hash、模型版本、配置和冻结选码以对应不可变
包为准。
