# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier

Terminal status: awaiting EV review at HEAD (see PR). Contract
BJ-UNIFIED-DYNAMIC-N-001 / v3. Research and paper settlement only. No betting,
release, or frontend authority follows from this result.

## Boundary and lanes

The frozen upstream #207 (merged `90869a959dc1b972cd872ffe465d1009e29df75e`,
manifest `48c11d97…`) is bound before execution. The incumbent is the fixed
N7/K8/native-¥2 path from #207 CONTROLLING K8 identities; CV_2022/CV_2023 come
from the #207 capital ledger and CV_2021 is reconstructed from the frozen
ticket identities with the identical native ¥2 rule.

The primary candidate is a per-issue learned action-value policy `Q_theta(x,a)`
fitted with `sklearn.neural_network.MLPRegressor` on the residual target
"matched pre-tax capital lift vs frozen N7/K8 incumbent". Controls are Ridge
(regularized linear) and best-fixed-action. 16 preregistered hash-derived seeds
are aggregated for stochastic lanes; seed identity is never a feature and never
selects.

## Chronology and learned-choice freeze

- CV_2021 is the initial fit block; Fold 1 = train CV_2021 → test CV_2022;
  Fold 2 = train CV_2021+CV_2022 → test CV_2023 (protocol delta #208-1:
  no 2020 ticket surface exists in the frozen upstream).
- Safety gate: execute the learned action only when conservative predicted lift
  (prediction − 1× train-fold residual RMSE) is positive AND coverage/OOD/
  fundability checks pass; otherwise fall back to the frozen incumbent or
  explicit NO_BET.
- 2024 calendar year and 2025/2026 LOCKED_TEST outcomes are embargoed; a
  verifier mutates 2024 labels and asserts zero fitted-parameter change.

## Terminal decisions

- `ELIGIBLE_CANDIDATE=false`: the safety-gated learned policy passes the
  preregistered gate on only 3 of 113 test issues (all three realized zero
  payout), so the gated path equals the frozen incumbent path on both folds.
  Median matched lift = 0.0; positive folds = 0.
- Selection rule step 5 therefore freezes the **frozen N7/K8/MARKET_WOR/
  native-¥2 incumbent** as the #209 candidate and publishes the full frontier
  and failure regimes.
- Key learned-policy diagnostics: calibration is monotone (predicted best lift
  bins 7.9 → 80.7 realized 63.6 → 827.3), so the Q model has signal; the
  ungated policy prefers short parlays (N=4/5) and the LEARNED_MLP lane, but
  the conservative gate vetoes nearly all executions — consistent with #207's
  finding that learned allocation does not automatically establish Edge.
- The frozen incumbent arm is bound exactly to the #207 CONTROLLING K8 path:
  CV_2023 ending ¥99,312.89, CV_2022 ending ¥99,072.00 (FROZEN_INCUMBENT_207).

## Controls / attribution matrix (CV_2023 test split, ¥100,000 start)

| Control | Ending capital ¥ | Turnover ¥ |
|---|---|---|
| capital_change_identical (SIMPLE_ACTIVE) | 101,424.58 | 880 |
| cash_no_bet (safety reference) | 100,000.00 | 0 |
| dynamic_nk_fixed_generator | 99,818.56 | 880 |
| static_n4k8 | 99,818.56 | 880 |
| static_n6k8 | 100,020.03 | 880 |
| static_n5k8 | 99,496.82 | 880 |
| static_n8k8 / n9k8 / n10k8 | 99,120.00 | 880 |
| n7k16_sensitivity | 98,240.00 | 1,760 |
| incumbent_n7k8 (frozen binding) | 99,312.89 | 880 |
| learned_policy (gated) | 99,312.89 | 880 |

Absolute performance is not lift: `selection.json` compares the learned path to
the frozen incumbent on identical issue support. Cash/NO_BET is reported
outside active-Edge attribution.

## What the frontier says

- N×K surface on CV_2021 shows mostly negative median matched lift; the best
  cells are single-issue LEARNED_MLP big-payout hits (e.g. N7/K8/LEARNED_MLP
  +¥2,210 on issue 21115), not a stable policy advantage.
- The frozen incumbent is a strong matched comparator: no bounded dynamic
  policy can clear the preregistered conservative safety gate on development
  folds.
- K16 native sensitivity underperforms K8 native on both folds (¥98,144 /
  ¥98,240 vs ¥99,072 / ¥99,312.89), consistent with #207's sensitivity rows.

## #209 handoff

`results/issue-208/handoff_209.json` is the single frozen handoff: model class
(MLPRegressor + StandardScaler), feature schema (STATE_FEATURE_NAMES), fitted
weights config, preprocessing, safety threshold (1× residual RMSE + OOD 0.99
quantile), inference code, candidate and fallback identities. 2024 was not
opened; fit boundary = train through 2022 / test 2023.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| REQ-208-01 upstream binding | provenance.json + incumbent_paths.parquet (FROZEN_INCUMBENT_207) | PASS |
| REQ-208-02 N/K semantics | verify_nk_semantics + tests | PASS |
| REQ-208-03 outcome isolation | verifier 2024-mutation + no 24xxxx rows | PASS |
| REQ-208-04 bounded frontier | protocol_log.json action grid + 16 seeds | PASS |
| REQ-208-05 matched attribution | 10-arm control matrix | PASS |
| REQ-208-06 capital accounting | verify_capital_accounting + continuity + tamper | PASS |
| REQ-208-07 decision evidence | full frontier + selection.json + controls | PASS |
| REQ-208-08 terminal freeze | handoff_209.json byte-identifiable | PASS |
| REQ-208-09 neural policy learning | MLPRegressor + Ridge + fixed-action, chronological, safety gate, weights serialized | PASS |

Decision input: the learned dynamic policy does not clear the preregistered
safety gate; freeze the frozen N7 incumbent for #209. Known risks: high payout
variance, bounded candidate recall, overlap, predicted-SP error, retrospective
risk calibration. Explicit review request: independently recompute N×K surface,
safety-gate census, incumbent path binding, capital conservation, chronological
splits, notebook clean-run and immutable replay before PI Review.
