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

---

## 13. REWORK v2 supersede rows (2026-08-14, EV REJECT 53f67ec, PR #228)

EV rejected the first delivery at SHA `53f67ec` with `REWORK_TYPE=method`.
The following rows supersede the earlier frozen text. Each defect category is
traced to its root cause; the same-category full sweep is documented in
`docs/research/issue_208_dynamic_nk_policy.md` §REWORK-E09.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-2 | supersede | protocol_version → bj208-protocol-v2, contract_version → bj208-dynamic-nk-policy-v2 | v1 texts | EV R1 rework; all artifacts now carry v2 |
| #208-3 | supersede | selection rule wording "positive in ≥2 of 3 folds / complete three-fold support" → "positive on ALL constructible development folds (2 of 2)" | §10 rule 3 | Fold 0 (train≤2020/test 2021) is NOT constructible from frozen upstream (DELTA #208-1). The old text claimed three folds while the implementation ran two — internal inconsistency (EV M04). |
| #208-4 | supersede | model training: `early_stopping=True, validation_fraction=0.1` → `early_stopping=False` + chronological issue-block validation holdout (last 15% of train issues by issue id) | §7 primary_params | sklearn row-level early stopping would split one issue's 168 action rows across train/validation — a chronological-issue-block violation (EV D3). |
| #208-5 | supersede | SIMPLE_ACTIVE capital semantics: old `bundle_capital_equal1pct` truncated budget to K ticket-count units (funded ¥16 at ¥100k/K8) → exact #207 EQUAL_1PCT: requested=pre*1%, budget=min(pre,requested), integer ¥2-unit projection over K tickets (funded ¥1,000 at ¥100k/K8) | §6 capital lane | EV D2: #207 EQUAL_1PCT first-issue funded ¥1,000; the old implementation funded ¥16, destroying capital attribution and training labels. |
| #208-6 | supersede | controls: Ridge and best-fixed-action evaluated per fold with full paths, lift and ablation; stochastic execution/controls on the 16 preregistered seeds only (seed=0 removed); capital-change-identical arm binds frozen CONTROLLING identities | §9 controls | EV D3/D4: controls were metadata-only; seed=0 is not a registered seed; capital control re-drew tickets. |

### REWORK v2 evidence chain (EV D1)

- `results/issue-208/**` is now tracked (`.gitignore` exceptions mirror
  issue-205/206). All immutable artifacts, manifest, receipt, schema,
  provenance, COMPLETED marker and model artifacts are committed in the PR —
  a fresh checkout can re-verify without worker-local files.
- method_preflight hard-gate and package verify run on the committed package.

### REWORK v2 verifier / tamper (EV D4)

- manifest full coverage: every packaged file must be listed; unlisted
  payloads fail.
- provenance validated against trusted upstream hashes (not a "FORGED" prefix).
- capital accounting verifies start ¥100,000, integer ¥2 units,
  funded ≤ requested/pre, no top-up, path continuity.
- N/K semantics verifier receives K and checks exactly K tickets per bundle.
- outcome-triple validation (exactly {3,1,0} per match, ≤1 realized True,
  official SP non-negative or NaN) added to the census loader.
- REAL 2024 label-mutation invariance check (development panel surface
  unchanged after 2024 label mutation) — not a constant test.

### REWORK v2 metrics / drawdown (EV D5)

- `summarize_path` max drawdown now uses the RUNNING peak per issue
  (path [100, 80, 200] → 0.2, not 0.6). Golden tests call the production
  function, not free-standing constant arithmetic.
- holding-feasibility metrics materialized: time under water, recovery
  issues, max consecutive losing issues, rolling 5/10/20-issue loss
  probability and worst windows, ex-largest issue.

### REWORK v2 atomicity / durability (EV D6)

- runner builds in `results/issue-208.staging/`, fsyncs files + directory,
  writes COMPLETED.json, then atomically renames over the final output.
- manifest written AFTER all artifacts (including tamper results and the
  receipt) so SHA256SUMS.json has full coverage.
- NO_BET explicit path for infeasible/OOD/incumbent-infeasible cases —
  empty action lists no longer crash argmax.

---

## 14. REWORK v3 supersede rows (2026-08-15, PI adversarial review 5e45132)

PI rejected the v2 delivery at SHA `5e4513297783f3dd98eca9a41cf932bdbfb6003e`
(PR #230) with a blocking scientific defect: the delivery used the superseded
interpretation that 0.65 is a tax adjustment removable from pre-tax economics.
The Issue contract now records the controlling formula:

    pre_tax_gross_multiple = hit * 0.65 * product(official_final_sp_i)

0.65 is the Beijing Single Match ticket payout coefficient, applied EXACTLY
ONCE per winning N-fold ticket. It is never divided out, never applied per
leg, and never compounded as 0.65^N.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-7 | supersede | payout semantics: pre-tax gross multiple = hit × 0.65 × prod(official SP); expected_pre_tax_net = 0.65 × prod(p·SP) − 1 | §6 settlement + all v2 artifacts | PI adversarial review 2026-08-15: v2 omitted the Beijing payout coefficient in `tickets.py` (multiple = prod(SP)), divided it out in `replay.py:145` (payout = realized_gross/0.65 × ¥2), and reconstructed the incumbent from the inflated #207 ledger. 0.65 is a payout coefficient, not a tax factor. |
| #208-8 | supersede | incumbent path: RECONSTRUCTED for ALL development splits from frozen #207 CONTROLLING ticket identities with corrected economics (payout = sum(realized_gross) × ¥2); the superseded #207 ledger `gross_payout_yuan` (pre-tax = realized_gross/0.65) is never read | §2 frozen incumbent binding + v2 incumbent_paths | PI 2026-08-15: #207 accepted ticket identities stay frozen, but their bankroll economics are not an admissible baseline. The v2 incumbent read the inflated #207 ledger (CV_2023 23084 gross_payout 192.89 vs corrected 125.38). |
| #208-9 | supersede | contract/protocol version → bj208-dynamic-nk-policy-v3 / bj208-protocol-v3; constant renamed TAX_FACTOR → PAYOUT_COEFFICIENT (0.65) with "never divide out / per leg / 0.65^N" semantics | v2 versions + TAX_FACTOR name | The name "tax factor" encoded the superseded interpretation; the constant now states the coefficient semantics. |
| #208-10 | add | production-entry payout-economics verifier: `verify_payout_economics` recomputes 0.65×prod(SP) from frozen value-matrix panels + upstream CONTROLLING realized_gross and compares against `ticket_economics.parquet` and `incumbent_paths.parquet`; tamper probes for omission, division-out and 0.65^N | — | PI REQUIRED: independent EV must attack omission, division-out and 0.65^N failure modes through production entry points. |

### REWORK v3 evidence chain

- `src/parlay_policy/tickets.py`: `_rows_to_frame` / `_ticket_row` now compute
  `pre_tax_gross_multiple = hit * 0.65 * prod(official_sp)` and
  `expected_pre_tax_net = 0.65 * prod(p*SP) - 1`; raw `official_sp_product` is
  retained as an explicitly named diagnostic only.
- `src/parlay_policy/replay.py:145` + `incumbent_issue_ledger`: payout =
  sum(realized_gross) × ¥2 (realized_gross already includes 0.65 exactly
  once) — the `/TAX_FACTOR` division-out is removed.
- `src/parlay_policy/incumbent.py`: `build_incumbent_paths` reconstructs ALL
  splits (CV_2021/22/23) from frozen CONTROLLING identities with corrected
  economics; source = `RECONSTRUCTED_CORRECTED_ECONOMICS`.
- `scripts/run_bj208_policy.py`: `_frozen_incumbent_tickets` remaps the
  multiple column to `realized_gross`; `ticket_economics.parquet` materialized
  for production-entry verification; `verify_package` runs
  `verify_payout_economics`; decision/handoff record the formula.
- Tests: `tests/test_bj208_payout_economics.py` (golden formula + omission /
  division-out / 0.65^N production-entry tamper detection).

---

## 15. REWORK v3.1 narrow durability supersede rows (2026-08-15, PI narrow durability REJECT 1380d42)

PI read-only adversarial review at SHA `1380d42dadc19bab1af7a405d96b2522040e1ee7`
(PR #230) accepted the payout-economics correction but rejected one narrow
#209 handoff durability defect. This is a durability/contract correction only;
model class, selection rule and scientific conclusion are unchanged.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-11 | supersede | handoff package_manifest path: canonical post-publication `results/issue-208/SHA256SUMS.json`; never the transient staging path | v3 handoff `package_manifest` field | PI 2026-08-15: v3 serialized `results/issue-208.staging/SHA256SUMS.json` because `_build_handoff` received the staging output path; after atomic rename no `.staging/**` exists. |
| #208-12 | add | production-entry `verify_handoff_paths` — every handoff artifact path must resolve after atomic rename and must reject `.staging`; wired into `verify_package` + tamper attack 8 (`handoff_staging_path`) | — | PI REQUIRED: package verifier/tests must validate handoff paths against the final published package, not just serialize a plausible string. |
| #208-13 | revise | method.yaml preprocessing constraint text: ALL CV_2021/22/23 incumbent paths reconstructed from frozen #207 CONTROLLING ticket identities; superseded #207 ledger `gross_payout_yuan` never read | v3 method.yaml wording that said CV_2022/23 come from the #207 ledger | Text alignment with #208-8 / `build_incumbent_paths` implementation (all splits reconstructed since REWORK v3). |

### REWORK v3.1 evidence chain

- `scripts/run_bj208_policy.py`: `_build_handoff(..., published_output=...)`
  serializes the canonical post-publication manifest path; `run()` passes the
  final output path while the package is still staged; after `_atomic_publish`
  the FINAL package is verified again (`verify_package(output)`).
- `src/parlay_policy/verify.py`: `verify_handoff_paths(package)` resolves every
  handoff path against the package root, fails on `.staging` references, and
  fails if any artifact path does not exist post-publication; tamper attack 8
  rewrites `handoff_209.json` `package_manifest` to a `.staging` path and must
  be detected by the production verifier.
- method.yaml preprocessing constraint now matches the v3 implementation.
- Tests: `tests/test_bj208_handoff_paths.py` (handoff path resolution +
  `.staging` rejection at the production entry).
