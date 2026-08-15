# Issue #208 — dynamic N×K and risk-conditioned parlay policy frontier

REWORK v4 (EV REJECT `ea1fc51` fixed), generated from producer-code commit
`REWORKV4_COMMIT_PLACEHOLDER`. Contract BJ-UNIFIED-DYNAMIC-N-001 / v6.
Research and paper settlement only. No betting, release, or frontend authority
follows from this result.

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
  issues by issue id). The split is resolved before every fit: fold 1 has
  49 FIT / 9 VALIDATION issues and fold 2 has 98 FIT / 18 VALIDATION issues,
  with zero overlap. MLP, Ridge, ranker, fixed-action and OOD fitting all use
  FIT only; sklearn row-level early stopping is disabled (#208-4).
- Safety gate: execute the learned action only when conservative predicted lift
  (prediction − 1× train-fold residual RMSE) is positive AND coverage/OOD/
  fundability checks pass; otherwise fall back to the frozen incumbent or
  explicit NO_BET.
- 2024 calendar year and 2025/2026 LOCKED_TEST outcomes are embargoed. The
  frozen value matrix contains no calendar-2024 rows, so the executable probe
  mutates all 50,970 available `LOCKED_TEST` rows and performs two actual
  terminal-fold refits. MLP/ranker weights, scalers, fixed action, OOD
  threshold and earlier live-path decisions remain byte-signature identical.

## Path-state causality (REWORK v4, EV D1)

Every selection path (primary MLP, Ridge, best-fixed, dynamic N / dynamic K /
dynamic N×K restricted controls, actual-refit probe, fallback continuation and
NO_BET subsequent issues) now scores each issue from ITS OWN strictly-prior
live history. `live_prior_state_from_rows` rebuilds
`prior_bankroll_yuan`, `prior_trail5_bankroll_yuan`,
`prior_trail10_bankroll_yuan`, `prior_running_drawdown_pct` and
`prior_consecutive_losses` from the lane's actual settlements; the running
drawdown peak anchors at the time-zero ¥100,000 initial bankroll. Once a
learned/control action diverges from the incumbent, the next issue's state
follows that lane, never the frozen incumbent counterfactual path. This is the
thin first neural layer described in the contract; a later permutation-invariant
M×3 encoder is deferred until #209 establishes learned dynamic choice adds
signal.

## Recovery / holding semantics (REWORK v4, EV D2)

`max_recovery_issues` now counts the longest COMPLETED underwater episode only;
a right-censored terminal episode that never recovers is reported separately as
`open_underwater_issues`. `recovery_issues` counts completed recovery events.
The verifier recomputes episodes with an independent primitive implementation,
so the producer and the auditor cannot share the same semantic error. The
CV_2022 incumbent path, for example, ends underwater and now reports
`max_recovery_issues=0 / open_underwater_issues=58` (previously the open
episode was mislabeled as a completed 58-issue recovery).

## Terminal decisions (REWORK v4 / v6)

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
- The Q model shows a coarse ranking tendency, not calibrated actionable
  signal. Predicted best-lift bins rise from −6.6 to 260.9 while realized bin
  means are 2,608 / 6,608 / 1,197 / 4,019 / 12,148: the highest bin is strongest,
  but adjacent bins are not monotone and the scales are badly mismatched.
  Chronological validation RMSE (1,012) is below fit RMSE (1,290), yet the
  conservative gate vetoes all 113 executions. This is model diagnostic
  information, not evidence of Edge.

## Controls / attribution matrix (CV_2023 test split, ¥100,000 start, v6)

| Control | Ending capital ¥ | Note |
|---|---|---|
| static_n8k8 | 100,218.21 | static N=8 K8 native ¥2 |
| cash_no_bet | 100,000.00 | safety reference (funded=0) |
| fixed_n7_dynamic_k | 99,798.87 | per-issue scorer selects K8 on all 55 issues |
| static_n5k8 | 99,710.20 | |
| static_n4k8 | 99,609.10 | |
| dynamic_n_fixed_k8_lane | 99,609.10 | scorer varies, selected action collapses to N4 |
| best_fixed_policy | 99,569.54 | best train-fold fixed cell: N4/K8/MARKET_WR/native |
| dynamic_nk_fixed_generator | 99,487.45 | state-conditioned; N varies, K remains 8 (live-path scoring, v6) |
| static_n9k8 | 99,403.42 | |
| static_n6k8 | 99,387.50 | |
| generator_change_n7k8 | 99,338.59 | MARKET_WR lane at N7/K8 |
| incumbent_n7k8 | 99,245.38 | corrected frozen incumbent path |
| ridge_policy | 99,245.38 | safety-gated = incumbent |
| learned_policy | 99,245.38 | safety-gated = incumbent |
| static_n10k8 | 99,120.00 | |
| n7k16_sensitivity | 99,106.12 | K16 native ¥2 |
| capital_change_identical | 62,178.64 | EQUAL_1PCT on identical tickets, corrected multiples |

Note: the v6 dynamic N×K restricted control (¥99,487.45 CV_2023) is lower than
the v5 value (¥99,632.80) because the control now scores from its own live
prior path instead of the frozen incumbent counterfactual history (EV D1). The
terminal conclusion is unchanged.

Key attribution findings (REQ-208-05):

- **N**: the frontier is not monotone or stable. Static N=8 reaches ¥100,218
  on CV_2023 but ends ¥99,072 on CV_2022. The state-conditioned N-only scorer
  chooses N4 on 111 issues and N9 on 2 CV_2023 issues; joint N×K varies N across
  3 values on CV_2022 and 6 values on CV_2023, but ends ¥99,483 / ¥99,633 and does not beat the
  strongest fixed control. The one-fold N8 gain is therefore a diagnostic
  sweet spot, not a promotion.
- **K**: the state-conditioned K-only scorer chooses K8 in every issue, and
  joint N×K also keeps K8 throughout. N7/K16 ends ¥98,317 / ¥99,106 versus
  K8's ¥99,072 / ¥99,245, but it also funds twice as much (¥32 vs ¥16 per
  issue). It is an exposure sensitivity, not a pure ticket-count comparison.
  Under the frozen native-¥2 minimum, a pure same-yuan K8-vs-K16 attribution is
  `NOT_IDENTIFIABLE`; no claim that K16 construction itself is worse follows.
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
- **Learning**: all 113 primary-policy decisions fall back to the incumbent.
  This proves the safety layer works, but the observed zero matched lift is a
  fallback identity, not evidence that the neural head improved the baseline.

## Required issue-level outputs (REQ-208-07)

All materialized in `results/issue-208/`: `issue_capital_ledger.parquet`,
`decision_rows_all.parquet`, per-fold learned and control paths,
`action_frequency.csv`, `action_variation_demo.csv`, `calibration_curve.csv`,
`chronological_train_val_loss.csv`, `ood_fallback_census.csv`,
`permutation_importance.csv`, `decision_ticket_identities.parquet` (per-seed
ticket identities for stochastic lanes), `ticket_economics.parquet`
(REWORK v3: per-ticket pre-tax multiples for the production payout-economics
verifier), `dynamic_control_decisions.parquet` (per-issue scores/actions),
`path_holding_metrics.parquet`, `chronology_blocks.parquet`,
`training_frame_all.parquet`, `validation_frame_all.parquet`,
`holdout_refit_baseline.json`, `holdout_refit_mutated.json`, `holdout_mutation_receipt.json`,
`selection.json`, `handoff_209.json`.

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
   division-out and 0.65^N through the production verifier.
6. **State features / diagnostics**: `features.py` consumes the upstream
   `expected_pre_tax_net` which upstream already computes as
   `0.65 × cj × sp_product − 1` (correct); no change needed. `diagnostics.py`
   has no payout arithmetic.
7. **Upstream root** (`src/bankroll_policy/fixed_n7.py:413-414`): the frozen
   #207 code labels the correct 0.65-adjusted gross as "tax-adjusted" and
   derives an inflated "pre-tax" by division. #207's accepted artifacts stay
   frozen (manifest `48c11d97…`); the supersession is recorded in
   PROTOCOL-LOG #208-7/#208-8 and #208 never consumes that field.

## REWORK v4 closure evidence (EV REJECT ea1fc51)

The v6 rework preserves all accepted payout, chronology, holdout-refit,
manifest/receipt and transactional-publication corrections, and closes the
three method-level blockers from the independent EV REJECT at `ea1fc51`:

1. **Path-state causality (D1):** every executed-policy call site now scores
   from its own live prior history. `live_prior_state_from_rows` derives all
   five path-dependent state features from the lane's own rows; the running
   drawdown peak includes the time-zero ¥100,000 anchor; the incumbent prior
   loss streak uses net P&L < 0 (payout < funded). Golden tests cover lane-own
   history and the anchor. Training/OOD/diagnostics intentionally retain the
   fit-time incumbent reference distribution (the label-surface target is
   matched lift vs the incumbent) and this choice is recorded in PROTOCOL-LOG
   #208-27.
2. **Recovery/holding semantics (D2):** `max_recovery_issues` covers completed
   episodes only; `open_underwater_issues` reports right-censored terminal
   episodes; `verify_path_metrics` recomputes episodes with an independent
   primitive implementation. Golden tests cover never-recovered and
   completed-then-open paths.
3. **Semantic evidence binding (D3):** `verify_state_semantics` recomputes the
   five path-dependent state features from `incumbent_paths.parquet` per
   (split, issue) and compares against training/validation frames, then binds
   the fold2 MLP scaler drawdown mean to the FIT training mean. A legal
   re-manifest of `training_frame_all.parquet` (shift drawdown +0.5) fails
   closed. The production tamper suite now detects 23/23 attacks.

The v5 closure evidence below remains valid and is retained for reference.

## PI takeover v5 closure evidence

The v5 rework preserves all accepted payout and handoff corrections, and closes
the exact remaining categories from the two EV REJECTs at `42b6e386`:

1. **Dynamic attribution:** global median cell lookup is removed. Three
   restricted MLP controls score lawful actions separately per issue using the
   causal state and the live path bankroll. The committed decision table has
   113 distinct score signatures per control across the two folds. N-only now
   chooses N9 on two CV_2023 issues while K-only remains K8 throughout.
2. **Capital/fallback:** frozen tickets contribute only funded stake and payout
   to the actual current bankroll. Native and SIMPLE_ACTIVE fundability are
   lane-specific; the latter has the exact ¥200 minimum. All 1,921 ledger rows
   have zero conservation error.
3. **Chronology and holding metrics:** fit/validation sets are materialized in
   `chronology_blocks.parquet` before every fit, with zero issue overlap.
   Time-zero drawdown, net-P&L loss streaks, rolling
   5/10/20 net-P&L windows, recovery, retained cash, active-support ROI,
   HHI/overlap/repeat and ex-largest issue are calculated by production code
   and published in `path_holding_metrics.parquet`.
4. **Holdout isolation:** `holdout_mutation_receipt.json` records two actual
   terminal-fold refits around a 50,970-row domain-preserving LOCKED_TEST
   mutation; signatures are identical (`d7862638…`).
5. **Verifier/evidence:** every one of 55 delivered CSV/Parquet frames and every
   JSON/model artifact is inventoried; receipt, chronology, path metrics,
   dynamic argmax, code bindings and actual-refit payloads are independently
   recomputed. All 22 semantic/remanifest attacks are detected. The manifest
   binds all 70 delivered files other than itself.
6. **Transactional publication:** last-good output is retained until final
   post-rename verification. Focused tests cover second-rename restoration,
   post-publish rollback, successful commit, immediate retry and
   `KeyboardInterrupt` cleanup.

## REQ coverage

| Requirement | Evidence at reviewed SHA |
|---|---|
| REQ-208-01 upstream binding | `results/issue-208/provenance.json` + loaders fail-closed on manifest hashes |
| REQ-208-02 N/K semantics | `verify_nk_semantics(tickets, k)` + census triple validation |
| REQ-208-03 outcome isolation | two content-bound actual-refit payloads plus `holdout_mutation_receipt.json` over 50,970 LOCKED_TEST rows; FIT/VALIDATION issue sets are disjoint |
| REQ-208-04 bounded frontier | 16 seeds only; `decision_ticket_identities.parquet`; no seed=0 |
| REQ-208-05 matched attribution | per-issue restricted controls + identical-ticket capital arm; pure same-yuan K8/K16 marked NOT_IDENTIFIABLE |
| REQ-208-06 capital accounting | `verify_capital_accounting` (start ¥100,000, ¥2 units, continuity) |
| REQ-208-07 decision evidence | full frontier, equity paths, holding metrics, adversarial arms |
| REQ-208-08 terminal freeze | `handoff_209.json` v6 (byte-identifiable candidate/fallback + payout semantics; canonical post-publication manifest path) |
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
- The corrected payout coefficient sets every winning payout to 65% of the
  superseded interpretation; the frozen #207 CONTROLLING ticket identities are
  unchanged, but the #207 ledger's own economics are superseded for #208.
- Dynamic score variation does not guarantee useful decision variation: N-only
  changes on only two issues and K-only remains fixed. Any next model must improve the
  state representation/target, not merely rerun a denser fixed grid.

## Replay

```
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py run --output results/issue-208
PYTHONPATH=src .venv/bin/python scripts/run_bj208_policy.py verify --output results/issue-208
PYTHONPATH=src .venv/bin/python -m pytest tests/test_bj208_*.py
```
