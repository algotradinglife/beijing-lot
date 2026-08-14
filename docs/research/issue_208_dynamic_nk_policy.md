# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier

REWORK v2 at HEAD (see PR; EV REJECT of SHA `53f67ec` fixed). Contract
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
selects. SIMPLE_ACTIVE capital replicates the frozen #207 EQUAL_1PCT exactly
(requested = pre×1%, integer ¥2-unit projection over K tickets).

## Chronology and learned-choice freeze

- CV_2021 is the initial fit block; Fold 1 = train CV_2021 → test CV_2022;
  Fold 2 = train CV_2021+CV_2022 → test CV_2023 (protocol delta #208-1:
  no 2020 ticket surface exists in the frozen upstream). Selection rule
  wording superseded (#208-3) to "positive on ALL constructible folds (2 of 2)".
- Model training uses chronological issue-block validation (last 15% of train
  issues by issue id); sklearn row-level early stopping is disabled (#208-4).
- Safety gate: execute the learned action only when conservative predicted lift
  (prediction − 1× train-fold residual RMSE) is positive AND coverage/OOD/
  fundability checks pass; otherwise fall back to the frozen incumbent or
  explicit NO_BET.
- 2024 calendar year and 2025/2026 LOCKED_TEST outcomes are embargoed; a REAL
  verifier mutates 2024 labels and asserts zero fitted-parameter change.

## Terminal decisions

- `ELIGIBLE_CANDIDATE=false`: the safety-gated learned policy passes the
  preregistered gate on 0 of 113 test issues, so the gated path equals the
  frozen incumbent path on both folds (Fold 1 = ¥99,072.00, Fold 2 =
  ¥99,312.89). Median matched lift = 0.0; positive folds = 0 of 2.
- Selection rule step 5 therefore freezes the **frozen N7/K8/MARKET_WOR/
  native-¥2 incumbent** as the #209 candidate and publishes the full frontier
  and failure regimes.
- The Q model has signal: calibration is monotone (predicted best-lift bins
  ¥0.4 → ¥444 realized ¥2,415 → ¥27,105), the chronological validation RMSE is
  lower than fit RMSE (1,555 vs 1,976), and changing only pre-event state
  changes the selected action (N4/K32/LEARNED_MLP ↔ N5/K8/MARKET_WR ↔
  N6/K32/LEARNED_MLP …). The ungated model prefers short parlays (N=4) and the
  LEARNED_MLP lane, but the conservative gate vetoes every execution —
  consistent with #207's finding that learned allocation does not automatically
  establish Edge.
- The frozen incumbent arm is bound exactly to the #207 CONTROLLING K8 path:
  CV_2023 ending ¥99,312.89, CV_2022 ending ¥99,072.00 (FROZEN_INCUMBENT_207).

## Controls / attribution matrix (CV_2023 test split, ¥100,000 start)

| Control | Ending capital ¥ | Note |
|---|---|---|
| static_n8k8 | 100,809.55 | static N=8 K8 native ¥2 |
| fixed_n7_dynamic_k | 100,164.42 | K16 best by train-fold median |
| static_n5k8 | 100,028.00 | static N=5 K8 native ¥2 |
| cash_no_bet | 100,000.00 | safety reference (funded=0) |
| dynamic_nk_fixed_generator | 99,872.46 | = static_n4k8 (N4 wins train median) |
| n7k16_sensitivity | 99,572.50 | K16 native ¥2 |
| static_n9k8 | 99,556.04 | |
| static_n6k8 | 99,531.54 | |
| generator_change_n7k8 | 99,456.30 | MARKET_WR lane at N7/K8 |
| ridge_policy | 99,312.89 | safety-gated = incumbent |
| incumbent_n7k8 | 99,312.89 | frozen #207 path |
| learned_policy | 99,312.89 | safety-gated = incumbent |
| static_n10k8 | 99,120.00 | |
| best_fixed_policy | 88,603.98 | N4/K32/LEARNED_MLP/native |
| capital_change_identical | 64,659.14 | EQUAL_1PCT on identical tickets |

Key attribution findings (REQ-208-05):

- **N**: the frontier is not monotone; N=8 static (¥100,810) edges the frozen
  N7 incumbent (¥99,313), but this is development-fold evidence only and is NOT
  promoted (selection rule freezes the incumbent; the per-issue learned policy
  is the only candidate class per REQ-208-09).
- **K**: K16 (n7k16_sensitivity ¥99,573) is not systematically better than K8
  native — consistent with #207's K sensitivity rows.
- **Generator**: generator_change_n7k8 (MARKET_WR ¥99,456) is below the
  MARKET_WOR incumbent (¥99,313 × close); lane differences are second-order.
- **Capital**: capital_change_identical on identical tickets with EQUAL_1PCT
  ends ¥64,659 — a 35% drawdown from betting 1% of bankroll per issue on
  parlays. This is the corrected D2 result: the R1 delivery reported ¥101,425
  because its SIMPLE_ACTIVE arm funded only ¥16/issue (K8 × ¥2) instead of the
  frozen EQUAL_1PCT rule. The correction makes the active-capital arm bind the
  exact #207 EQUAL_1PCT/MARKET_WOR/K8 ledger (ending ¥64,659.136… matches #207
  to 7 decimals), so the attribution is now causal and identical-ticket.
- **Exposure**: cash/NO_BET reference is flat ¥100,000; lower exposure is the
  only arm that never loses capital, reported outside active-Edge attribution.

## Required issue-level outputs (REQ-208-07)

All materialized in `results/issue-208/`: `issue_capital_ledger.parquet`
(1,921 rows × 17 policy arms), `decision_rows_all.parquet`, per-fold learned
and control paths, `action_frequency.csv`, `action_variation_demo.csv`,
`calibration_curve.csv`, `chronological_train_val_loss.csv`,
`ood_fallback_census.csv`, `permutation_importance.csv`,
`decision_ticket_identities.parquet` (per-seed ticket identities for stochastic
lanes), `selection.json`, `handoff_209.json`.

## REWORK-E09 same-category sweep evidence

For each EV defect class, the full call surface was swept (not just the
reported instance):

1. **Evidence chain / schema**: all required artifacts (decision.json,
   SHA256SUMS.json, handoff_209.json, selection.json, issue_capital_ledger,
   schema.json, provenance.json, receipt.sha256, COMPLETED.json, model
   artifacts) are committed under `results/issue-208/` and `.gitignore` now
   allows issue-208 (D1). Manifest keys are relative paths so nested
   `models/*.joblib` are covered; verify_manifest enforces full coverage
   (unlisted payloads fail).
2. **Capital / attribution / metrics**: `bundle_capital_equal1pct`,
   `issue_action_lift`, `full_path_replay`, all 17 control arms, selection and
   handoff now use the corrected EQUAL_1PCT semantics; `capital_change_identical`
   binds frozen CONTROLLING identities; matched lift, running-peak drawdown,
   time-under-water, recovery, max consecutive losses, rolling 5/10/20 loss and
   worst windows are computed in `summarize_path` (D2/D5).
3. **Leakage / chronology**: `fit_mlp` and `fit_learned_ranker` disable sklearn
   early stopping; validation is a chronological issue-block holdout; Ridge and
   best-fixed controls are evaluated per fold with full paths + ablation
   (`path_control_ridge_policy_*`, `path_control_best_fixed_policy_*`); model
   weights + scaler are serialized (`models/fold1_mlp.joblib`,
   `models/fold2_mlp.joblib`) so handoff_209 is label-blind replayable (D3).
4. **Verification / tamper**: every tamper test attacks the production
   `verify_package` entry on a full copy of the package; manifest full-coverage,
   provenance identity (trusted hashes), capital start/¥2-units/requested/K,
   N/K semantics with K, outcome-triple validation, and a REAL 2024-mutation
   invariance check (D4).
5. **Atomicity / durability**: runner builds in `.staging`, fsyncs files +
   dir, writes COMPLETED.json before the final manifest, atomically renames
   over the output; manifest is written after all artifacts including tamper
   results and COMPLETED (D6).
6. **Boundaries**: empty actions → explicit NO_BET; M<N and pool<K handled;
   NaN/Inf, duplicate/missing outcome codes, multiple/no realized outcomes,
   non-negative official SP, missing upstream rows, fundability and incumbent
   fail-closed paths are covered by loaders + tests (D4/D6).

## REQ coverage

| Requirement | Evidence at reviewed SHA |
|---|---|
| REQ-208-01 upstream binding | `results/issue-208/provenance.json` + loaders fail-closed on manifest hashes |
| REQ-208-02 N/K semantics | `verify_nk_semantics(tickets, k)` + census triple validation |
| REQ-208-03 outcome isolation | REAL 2024-mutation invariance test `test_2024_mutation_invariance_real` |
| REQ-208-04 bounded frontier | 16 seeds only; `decision_ticket_identities.parquet`; no seed=0 |
| REQ-208-05 matched attribution | control matrix above + identical-ticket capital arm |
| REQ-208-06 capital accounting | `verify_capital_accounting` (start ¥100,000, ¥2 units, continuity) |
| REQ-208-07 decision evidence | full frontier, equity paths, holding metrics, adversarial arms |
| REQ-208-08 terminal freeze | `handoff_209.json` (byte-identifiable candidate/fallback) |
| REQ-208-09 neural policy | MLPRegressor Q with Ridge + best-fixed controls, joblib weights, label-blind replay |

## Known risks

- The learned policy never executes under the conservative gate on development
  folds; this is a null result for learned dynamic choice in-sample, not proof
  of absence of edge in terminal 2024 (only #209 may test that).
- Static N=8's positive development lift is not promoted; it is a single-fold
  observation and the selection rule's only candidate class is the learned
  policy.
- EQUAL_1PCT's deep capital drawdown reflects parlay risk at 1%-per-issue
  funding, consistent with #207's Stage-4 finding; it is reported as a
  risk-conditioned reference, not a recommendation.

## Replay

```
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bj208_metrics.py tests/test_bj208_tamper.py
```
