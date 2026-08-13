# Issue #208 — Method Design & PROTOCOL-LOG (BJ-UNIFIED-DYNAMIC-N-001 v3)

Status: frozen before execution. Appended-only. Any change records a supersede row.

## 1. Contract binding (REQ-208-01)

- Upstream issue #207 merged at `90869a959dc1b972cd872ffe465d1009e29df75e` (PR #226).
  Terminal disposition: `ENGINE_VALID=true`, `ACTIVE_OVERLAY_EVIDENCE=false`,
  `DEPLOYABLE_POLICY=false`, frozen learned controller = `BOUNDED_NEURAL`,
  negative freeze = `NATIVE_2_YUAN`, controlling k = 8.
- Frozen upstream artifact package: `results/issue-207/`
  manifest SHA256 = `48c11d971c20cb2239cd342ade4084bea484686bd106253c77a320ba7ae78ab6`.
- Ticket surface: `results/issue-205/value_matrix.parquet` (the M×3 causal pre-event
  cell surface with control_probability, predicted_final_sp, sp_seed_std,
  official_final_sp_label, realized_outcome) — the same surface #206/#207 consumed.
- Causal tensor: `results/bj203_causal_tensor_v2/` (feature_values + labels,
  including 2024/2025/2026 identity — 2024+ must NEVER enter #208 features or fit).

## 2. Frozen incumbent identity

- Incumbent = **fixed N7/K8/native-¥2** path from #207 CONTROLLING panel.
  Generator lane: #207's own strongest absolute K8 row was `MARKET_WOR/NATIVE_2_YUAN`
  (ending capital ¥99,312.89 on CV_2023); #207's matched reference lane used in
  its own comparisons was `MARKET_WR/K8` (explicitly "not an accepted baseline").
  Decision: bind incumbent ticket identities EXACTLY from
  `results/issue-207/active_research_ticket_requests.parquet`
  (panel_role=CONTROLLING, k=8) — this is the frozen N7/K8 identity bundle.
  For the matched-lift reference the incumbent is evaluated with NATIVE_2_YUAN
  capital lane and its exact #207 ledger path
  (`issue_capital_ledger.parquet` controller=NATIVE_2_YUAN, k=8, policy=MARKET_WOR).
  The five #207 policies at K8 are all available as CONTROLLING identities; the
  incumbent comparison arm is MARKET_WOR/K8 (strongest absolute) and MARKET_WR/K8
  is reported as sensitivity reference (consistent with #207's own matched view).

## 3. Chronology and folds

- Development folds available in the frozen surface: CV_2021 (58 issues, 2021),
  CV_2022 (58 issues, 2022), CV_2023 (55 issues, 2023).
- **PROTOCOL-LOG DELTA #208-1 (folds)**: The contract text names
  "train through 2020/test 2021, train through 2021/test 2022, train through
  2022/test 2023". The frozen #205 value matrix / #204 predictions / #207 tickets
  begin at 2021 — there is no 2020 ticket surface in the frozen upstream
  (causal-tensor development coverage = 0.0 per #214 decision; #204 predictions
  start 21xxx). Therefore the constructible expanding folds are:
  - Fold 1: train {CV_2021} → test CV_2022   (i.e. train through 2021 / test 2022)
  - Fold 2: train {CV_2021, CV_2022} → test CV_2023 (train through 2022 / test 2023)
  - Fold 0 (train ≤2020 → test 2021) is NOT constructible from frozen upstream;
    CV_2021 is retained as the initial fit block and reported as first-year
    development evidence, matching #207's CV_2021-fit / CV_2022-freeze / CV_2023-terminal
    chronology. Primary terminal split = Fold 2 (train through 2022 / test 2023).
- 2024 labels/final SP/payouts: embargoed. 2025/2026 LOCKED_TEST: embargoed.
  A verifier test mutates 2024 labels and asserts zero fitted-parameter change.

## 4. Action space (frozen)

- N ∈ {4,5,6,7,8,9,10} (7 values)
- K ∈ {8,16,32} (3 values)
- Generator lane (4):
  1. `MARKET_WR` — market-weighted win-rate (from #206 CONTROL_POLICIES)
  2. `MARKET_WOR` — market-weighted win-odds-ratio (from #206)
  3. `VALUE_WOR` — simple residual/value-ranked WOR (experimental residual /
     expected pre-tax net ranking; #206 challenger family, deterministic)
  4. `LEARNED_MLP` — strongest non-promoted #207 research lane
     (#207 panel LEARNED_MLP; frozen #207/#206 learned ranker weights)
- Capital lane (2):
  1. `NATIVE_2_YUAN` — ¥2 per ticket, no top-up
  2. `SIMPLE_ACTIVE` — the single simplest accepted active controller from #207:
     #207's `EQUAL_1PCT` (equal-weight 1% risk fraction; the simplest accepted
     active control that #207 used as matched comparator). BOUNDED_NEURAL is the
     frozen learned controller but requires reopened Stage-4 learning; contract
     says "Do not reopen the full Stage-4 fraction/model grid" → EQUAL_1PCT is
     the simplest accepted active controller.
- NO_BET for infeasible / OOD / frozen safety cases.
- Action catalog total: 7×3×4×2 = 168 primary cells + NO_BET.
- 16 preregistered hash-derived seeds: derived from `sha256("bj208-seed-<i>")`
  for i in 1..16. All seeds aggregated (mean of matched lift over seeds) before
  forming action targets. Seed identity is never a feature and never selects.

## 5. State x (pre-event only)

Per issue, from causal M×3 tensor + issue market/SP summaries + frozen upstream
+ prior bankroll/path state:
- Issue-level distribution summaries of pre-event cells:
  - M (eligible match count), mean/max/std of max control probability per match,
    mean devig_euro_probability, mean euro_1h_odds, coverage of predicted SP,
    mean predicted_final_sp, mean sp_seed_std, HHI of market probability mass,
    match count, outcome HHI, mean probability residual z.
- Frozen upstream outputs: #207 incumbent issue-level summaries (mean
  log_joint_probability, mean expected_pre_tax_net, mean predicted_sp_product,
  ticket HHI, mean pairwise overlap) — pre-event only.
- Prior bankroll/path state: trailing 5/10-issue bankroll, running max drawdown,
  consecutive loss count, current bankroll (from incumbent path, prior to issue).
- FORBIDDEN: any result/score/settlement/winning_sp/official_sp/payout/tax/roi/
  profit/hit field may not enter x. Enforced by forbidden-name checker.

## 6. Counterfactual label surface (training targets)

- For every issue × action cell, replay ticket construction + settlement + capital
  from the frozen #205 cell surface (control_probability, predicted_final_sp,
  sp_seed_std, official_final_sp_label, realized_outcome) for development folds only.
- Ticket construction: generalized from #206's generator (top-mass systematic +
  weighted draws; MARKET_WR/MARKET_WOR stochastic with 16 seeds; VALUE_WOR and
  LEARNED_MLP deterministic scoring + top-K). Every ticket has exactly N distinct
  matches; cross-ticket overlap preserved and measured.
- Settlement: pre-tax gross multiple = product of official SP of chosen outcomes
  if all N hit else 0; tax-adjusted (×0.65) reference-only.
- Capital: start ¥100,000 per path; native ¥2 × K tickets per issue
  (post = pre − funded + payout); SIMPLE_ACTIVE lane uses EQUAL_1PCT risk
  fraction on identical tickets.
- Target y(x,a) = matched pre-tax ending-capital lift vs frozen N7/K8 incumbent
  on the same issue support and same ex-ante risk budget, seed-aggregated.

## 7. Models (REQ-208-09)

- Primary: `sklearn.neural_network.MLPRegressor` Q_theta(x,a), residual
  action-value (target = matched lift), StandardScaler pipeline.
  hyperparameters frozen (hidden (32,), alpha 1e-3, early_stopping, max_iter 500).
- Control 1: regularized linear — `sklearn.linear_model.Ridge` (alpha grid frozen).
- Control 2: best fixed action (single best (N,K,lane,capital) cell by
  development median lift — a fixed action, reported as control only).
- Chronological issue-block splits: fit Q on train folds only, evaluate on the
  test fold. 16 seeds aggregated in targets; model seed fixed 208001.
- At inference: argmax over actions of Q; safety gate: predicted conservative
  lift (predicted − 1× residual RMSE) > 0 AND coverage/OOD/fundability checks
  pass, else fallback to frozen incumbent or NO_BET.

## 8. Safety gate / fallback (preregistered)

- Conservative predicted lift = Q̂(x,a) − σ̂_residual (train-fold residual RMSE).
- Execute learned action only if conservative lift > 0 AND:
  - coverage: issue has ≥ N eligible matches with complete cells
  - OOD: state x within training distribution (max-abs standardized feature
    median ≤ frozen 0.99 quantile from fit folds)
  - fundability: bankroll ≥ K × ¥2 (or risk-fraction minimum for SIMPLE_ACTIVE)
- Else: frozen incumbent or NO_BET (explicit reason code).

## 9. Controls / attribution matrix (10 arms)

1. fixed N7/K8/native-¥2 incumbent (#207 frozen identity)
2. fixed N7/K16/native-¥2 sensitivity control
3. static per-N, K8, native-¥2 controls (7 rows)
4. dynamic N with fixed K8 and fixed generator
5. fixed N7 with dynamic K
6. dynamic N×K with fixed generator/capital
7. generator-only change at fixed N7/K8
8. capital-only change on identical tickets + funding support
9. full bounded dynamic policy (learned)
10. cash/NO_BET safety references (outside active-Edge attribution)

Comparison semantics: N/K/generator comparisons = same issue eligibility + same
ex-ante risk budget, lawful geometry preserved. Allocation comparisons = identical
ticket identities + identical executable yuan schedule. Impossible → NOT_IDENTIFIABLE.

## 10. Development selection rule (preregistered lexicographic)

1. valid replay, causal trace, no ruin, complete fold support
2. positive median matched ending-capital lift vs N7/K8 incumbent
3. positive matched lift in ≥2 of 3 development folds (constructible: fold1, fold2)
4. highest median matched lift → highest worst-fold lift → smaller issue-level
   max drawdown → lower complexity
5. else freeze N7 incumbent and publish full frontier + failure regimes

## 11. Resources

- Staged run: census → core controls → full policy. Target 6h, hard stop 12h,
  32 aggregate CPU-h, 16 GiB peak RSS, 20 GiB temp. Cache issue tensors and
  candidate tickets. If exceeded → publish completed coverage + Blocked.

## 12. Deliverables

- `notebooks/research/issue-208/bj208_dynamic_nk_policy.ipynb` (executed)
- `src/parlay_policy/` reusable package + tests (incl. tamper tests REQ-E06)
- `results/issue-208/` immutable package (manifest SHA256, schema, provenance,
  replay commands, #209 handoff)
- `docs/research/issue_208_dynamic_nk_policy.md` decision report + wiki update
