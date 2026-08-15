# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier

REWORK v3 at HEAD (PI adversarial review of SHA `5e45132` fixed; supersedes
EV REJECT of `53f67ec` and the v2 delivery). Contract BJ-UNIFIED-DYNAMIC-N-001
/ v3. Research and paper settlement only. No betting, release, or frontend
authority follows from this result.

## Payout economics (PI correction 2026-08-15)

The controlling pre-tax convention includes the Beijing Single Match payout
coefficient exactly once per winning N-fold ticket:

    pre_tax_gross_multiple = hit * 0.65 * product(official_final_sp_i)

0.65 is a ticket payout coefficient, NOT a tax factor. It is never divided
out, never applied per leg, and never compounded as 0.65^N. Expected ticket
economics use the same boundary: `expected_pre_tax_net = 0.65 * prod(p·SP) − 1`.

The v2 delivery at `5e45132` used the superseded interpretation:
`src/parlay_policy/tickets.py` set the winning multiple to `prod(SP)` (omission),
`src/parlay_policy/replay.py:145` reconstructed payout as
`sum(realized_gross)/0.65 × ¥2` (division-out; upstream #206 `realized_gross`
already equals `0.65 × prod(SP)`), and the incumbent path was bound to the
inflated #207 ledger `gross_payout_yuan` (192.89 vs corrected 125.38 on
CV_2023/23084). All of those call sites are corrected; upstream frozen #207
ticket identities are inherited but their bankroll economics are reconstructed
under the corrected formula (`RECONSTRUCTED_CORRECTED_ECONOMICS`).

## Boundary and lanes

The frozen upstream #207 (merged `90869a959dc1b972cd872ffe465d1009e29df75e`,
manifest `48c11d97…`) is bound before execution. The incumbent is the fixed
N7/K8/native-¥2 path from #207 CONTROLLING K8 identities; ALL development
splits (CV_2021/CV_2022/CV_2023) are reconstructed from the frozen CONTROLLING
ticket identities under the corrected economics: payout per ticket =
`realized_gross × ¥2`, funded = K × ¥2, post = pre − funded + payout.

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

## Terminal decisions (REWORK v3)

- `ELIGIBLE_CANDIDATE=false`: the safety-gated learned policy passes the
  preregistered gate on 0 of 113 test issues, so the gated path equals the
  corrected frozen incumbent path on both folds (Fold 1 = ¥99,072.00, Fold 2 =
  ¥99,245.38). Median matched lift = 0.0; positive folds = 0 of 2.
- Selection rule step 5 therefore freezes the **frozen N7/K8/MARKET_WOR/
  native-¥2 incumbent** as the #209 candidate and publishes the full frontier
  and failure regimes.
- The corrected incumbent ending capital is LOWER than the v2 reported value
  (CV_2023 ¥99,245.38 vs ¥99,312.89) because the single CV_2023 winning ticket
  (23084) now pays ¥125.38 instead of the inflated ¥192.89. The terminal
  conclusion (no eligible learned row) is unchanged, but every matched lift,
  control path, safety gate and risk metric was regenerated under the corrected
  economics.
- The Q model has signal: calibration is monotone (predicted best-lift bins
  −6.6 → 260.9 realized 2,215 → 17,333), the chronological validation RMSE is
  lower than fit RMSE, and changing only pre-event state changes the selected
  action. The ungated model prefers short parlays (N=4) and the LEARNED_MLP
  lane, but the conservative gate vetoes every execution — consistent with
  #207's finding that learned allocation does not automatically establish Edge.

## Controls / attribution matrix (CV_2023 test split, ¥100,000 start, REWORK v3)

| Control | Ending capital ¥ | Note |
|---|---|---|
| static_n8k8 | 100,218.21 | static N=8 K8 native ¥2 |
| cash_no_bet | 100,000.00 | safety reference (funded=0) |
| fixed_n7_dynamic_k | 99,798.87 | K16 best by train-fold median |
| static_n5k8 | 99,710.20 | |
| dynamic_nk_fixed_generator | 99,609.10 | = static_n4k8 (N4 wins train median) |
| static_n4k8 | 99,609.10 | |
| dynamic_n_fixed_k8_lane | 99,609.10 | |
| static_n9k8 | 99,403.42 | |
| static_n6k8 | 99,387.50 | |
| generator_change_n7k8 | 99,338.59 | MARKET_WR lane at N7/K8 |
| incumbent_n7k8 | 99,245.38 | corrected frozen incumbent path |
| ridge_policy | 99,245.38 | safety-gated = incumbent |
| learned_policy | 99,245.38 | safety-gated = incumbent |
| static_n10k8 | 99,120.00 | |
| n7k16_sensitivity | 99,106.12 | K16 native ¥2 |
| best_fixed_policy | 76,292.89 | N4/K32/LEARNED_MLP/native |
| capital_change_identical | 62,178.64 | EQUAL_1PCT on identical tickets, corrected multiples |

Key attribution findings (REQ-208-05):

- **N**: the frontier is not monotone; N=8 static (¥100,218) edges the frozen
  N7 incumbent (¥99,245), but this is development-fold evidence only and is NOT
  promoted (selection rule freezes the incumbent; the per-issue learned policy
  is the only candidate class per REQ-208-09).
- **K**: K16 (n7k16_sensitivity ¥99,106) is below K8 native — consistent with
  #207's K sensitivity rows.
- **Generator**: generator_change_n7k8 (MARKET_WR ¥99,339) is slightly above
  the MARKET_WOR incumbent (¥99,245); lane differences are second-order.
- **Capital**: capital_change_identical on identical tickets with EQUAL_1PCT
  ends ¥62,179 — a ~38% drawdown from betting 1% of bankroll per issue on
  parlays. Under the corrected economics this is LOWER than the v2 value
  (¥64,659) because the single winning ticket's EQUAL_1PCT-funded payout drops
  by the 0.65 factor. The identical-ticket binding is unchanged (frozen #207
  CONTROLLING identities).
- **Exposure**: cash/NO_BET reference is flat ¥100,000; lower exposure is the
  only arm that never loses capital, reported outside active-Edge attribution.

## Required issue-level outputs (REQ-208-07)

All materialized in `results/issue-208/`: `issue_capital_ledger.parquet`,
`decision_rows_all.parquet`, per-fold learned and control paths,
`action_frequency.csv`, `action_variation_demo.csv`, `calibration_curve.csv`,
`chronological_train_val_loss.csv`, `ood_fallback_census.csv`,
`permutation_importance.csv`, `decision_ticket_identities.parquet` (per-seed
ticket identities for stochastic lanes), `ticket_economics.parquet`
(REWORK v3: per-ticket pre-tax multiples for the production payout-economics
verifier), `selection.json`, `handoff_209.json`.

## REWORK-E09 same-category sweep evidence (REWORK v3 payout-economics)

For the PI payout-economics defect class, the FULL payout/expected-value call
surface was swept (not just the four reported instances):

1. **`src/parlay_policy/tickets.py` `_rows_to_frame`** (omission): winning
   multiple was `prod(official_sp)` — now `hit × 0.65 × prod(official_sp)`;
   `expected_pre_tax_net` was `prod(p·SP) − 1` — now `0.65 × prod(p·SP) − 1`.
   `_ticket_row` carries the same correction; raw `official_sp_product` is
   retained as an explicitly named diagnostic only.
2. **`src/parlay_policy/replay.py:145`** (division-out): incumbent CV_2021
   reconstruction divided `realized_gross` by 0.65 — now `realized_gross × ¥2`
   (realized_gross already includes the coefficient exactly once).
   `incumbent_issue_ledger` no longer reads the inflated #207 ledger.
3. **`src/parlay_policy/incumbent.py`** (inflated baseline): the #207 ledger
   `gross_payout_yuan` (pre-tax = realized_gross/0.65) is never read; all
   splits are reconstructed from frozen CONTROLLING identities with corrected
   economics.
4. **`scripts/run_bj208_policy.py` `_frozen_incumbent_tickets`**
   (division-out in the identical-ticket capital arm): the upstream inflated
   `pre_tax_gross_multiple` column is remapped to `realized_gross` before
   `bundle_capital_equal1pct` settlement.
5. **`src/parlay_policy/verify.py`** (REQ-E06 / PI REQUIRED #3): new
   `verify_payout_economics` recomputes `0.65 × prod(SP)` from frozen
   value-matrix panels and compares against `ticket_economics.parquet` and
   `incumbent_paths.parquet`; three new tamper probes attack omission,
   division-out and 0.65^N through the production verifier — 7/7 detected.
6. **State features / diagnostics**: `features.py` consumes the upstream
   `expected_pre_tax_net` which upstream already computes as
   `0.65 × cj × sp_product − 1` (correct); no change needed. `diagnostics.py`
   has no payout arithmetic.
7. **Upstream root** (`src/bankroll_policy/fixed_n7.py:413-414`): the frozen
   #207 code labels the correct 0.65-adjusted gross as "tax-adjusted" and
   derives an inflated "pre-tax" by division. #207's accepted artifacts stay
   frozen (manifest `48c11d97…`); the supersession is recorded in
   PROTOCOL-LOG #208-7/#208-8 and #208 never consumes that field.

## REQ coverage

| Requirement | Evidence at reviewed SHA |
|---|---|
| REQ-208-01 upstream binding | `results/issue-208/provenance.json` + loaders fail-closed on manifest hashes |
| REQ-208-02 N/K semantics | `verify_nk_semantics(tickets, k)` + census triple validation |
| REQ-208-03 outcome isolation | REAL 2024-mutation invariance test `test_2024_mutation_invariance_real` |
| REQ-208-04 bounded frontier | 16 seeds only; `decision_ticket_identities.parquet`; no seed=0 |
| REQ-208-05 matched attribution | control matrix above + identical-ticket capital arm (corrected multiples) |
| REQ-208-06 capital accounting | `verify_capital_accounting` (start ¥100,000, ¥2 units, continuity) |
| REQ-208-07 decision evidence | full frontier, equity paths, holding metrics, adversarial arms |
| REQ-208-08 terminal freeze | `handoff_209.json` v3 (byte-identifiable candidate/fallback + payout semantics) |
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
- The corrected payout coefficient lowers every winning payout by 0.65 vs the
  superseded interpretation; the frozen #207 CONTROLLING ticket identities are
  unchanged, but the #207 ledger's own economics are superseded for #208.

## Replay

```
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bj208_metrics.py tests/test_bj208_tamper.py tests/test_bj208_payout_economics.py
```
