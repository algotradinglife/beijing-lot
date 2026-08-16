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

---

## 16. PI takeover v4 supersede rows (2026-08-15, EV REJECT e5bb257)

The independent audit at exact PR #230 HEAD
`e5bb2578710d4f57031bd2180c6a691570524356` accepted the D1 pre-pool
exclusion, canonical handoff path and corrected 0.65 payout semantics. It
rejected the remaining executable-method defects D2–D6. At the user's direct
instruction, the PI took over this bounded rework without changing the model
family, action catalog or selection rule.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-14 | supersede | dynamic N, dynamic K and dynamic N×K attribution controls are separately fitted restricted MLP policies and score every lawful action per issue from causal pre-event state plus that policy path's live prior bankroll | v3.1 global train-fold median cells | EV D2: a repeated global winner is a fixed-action control and cannot identify dynamic policy value. |
| #208-15 | supersede | frozen incumbent fallback preserves ticket identities/economics but applies funded stake and payout to the actual current bankroll; it never copies an absolute frozen post-bankroll | v3.1 absolute post-bankroll fallback | EV D3: copying the frozen post value after a learned loss injected capital and violated path continuity. |
| #208-16 | supersede | lane-specific fundability: native requires `K × ¥2`; SIMPLE_ACTIVE requires at least one integer ¥2 unit from a 1% request, hence minimum current bankroll ¥200 | common `K × ¥2` test for both lanes | EV D3: SIMPLE_ACTIVE could be selected at bankroll ¥100 despite an unfundable ¥1 request. |
| #208-17 | supersede | max drawdown includes time-zero ¥100,000; loss means net P&L < 0; rolling 5/10/20 metrics use net-P&L windows; issue holding, recovery, concentration, overlap, repeat and ex-largest diagnostics are materialized in `path_holding_metrics.parquet` | v3.1 gross-payout loss/window semantics and report-only metrics | EV D4: a small gross return can still lose money, and the committed evidence must reflect investor holding feasibility. |
| #208-18 | supersede | holdout probe performs two real production-path terminal-fold refits after a domain-preserving `LOCKED_TEST` label/SP mutation and compares MLP/ranker weights, scalers, fixed action, OOD threshold and live-path earlier decisions | census-only mutation comparison | EV D5: split filtering alone did not demonstrate fitted-state invariance. |
| #208-19 | supersede | production verification invokes completion, rich decision/capital/#209 schema, REQ evidence paths, N/K bundle semantics, dynamic-control semantics, capital, payout and handoff checks; provenance binds producer code commit, method, requirements lock, runner and package modules | existence-only schema and partial verifier | EV D5: remanifested semantic corruption previously passed. Exact final PR HEAD remains necessarily external in the producer handoff and independent EV verdict. |
| #208-20 | supersede | unique staging package; last-good output retained until post-publication verification; failed second rename or final verification restores last-good; `BaseException` cleanup and immediate retry are tested | delete-backup-before-second-rename publisher | EV D6: a replacement fault could destroy the only complete package. |

### PI takeover v4 proportional boundary

- D1 remains closed: all 594 zero-realized development matches also have all
  control probabilities missing and are excluded before candidate pools and
  action targets; retained zero-realized matches remain zero.
- The model family, N/K/lane/capital catalog, 16-seed aggregation, selection
  rule, corrected 0.65 coefficient and terminal scientific question are
  unchanged. Output changes are attributable only to D2–D4 corrections.
- Decision-critical frames carry columns, types, non-null fields, keys,
  domains and units. Auxiliary diagnostic tables remain manifest-bound under
  the Issue's proportional schema allowance.
- Producer evidence records REQ-208-01..09 paths and the producer code commit.
  The exact final review HEAD is posted externally because a Git commit cannot
  contain its own hash; independent EV must bind that full 40-character HEAD.

---

## 17. PI takeover v5 closure rows (2026-08-15, concurrent EV REJECTs at 42b6e386)

Two independent fresh audits bound PR #230 exact HEAD
`42b6e386cf74bff5e0377314dd9a258712d48430`. They reproduced the scientific
result and accepted the v4 payout, dynamic-control, live-bankroll, fundability,
holdout-refit and transactional-publication corrections, but found remaining
method/evidence boundary failures. These rows do not change the action grid,
model family, seed aggregation, selection rule or scientific hypothesis.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-21 | supersede | resolve chronological fit/validation issue blocks before any ticket-ranker, Q-MLP, Ridge, fixed-action, restricted-control or OOD fit; validation issues enter scoring/diagnostics only | v4 fit-all + separately score validation | Concurrent EV A D1: declared validation issue rows still entered the actual fit APIs. |
| #208-22 | supersede | every replay path materializes issue-level running-peak drawdown and net-P&L loss streak from primitive bankroll rows; frozen incumbent identities provide overlap/HHI/repeat metrics | v4 placeholder issue metrics / null frozen exposure | Concurrent EV A D2: aggregate metrics were correct while 1,460 published issue rows carried zero drawdown and decisive fallback paths had null concentration evidence. |
| #208-23 | supersede | schema declares every CSV/Parquet column exactly; each auxiliary frame is explicitly diagnostic-only; every JSON/model payload is inventoried; production verification recomputes chronology, issue path metrics, dynamic argmax and the complete code-binding set | v4 nine-frame subset schema | Concurrent EV A D3: 44 data frames were undeclared and remanifested semantic corruption could pass. |
| #208-24 | supersede | SHA256SUMS covers every delivered byte except itself; `receipt.sha256` is a canonical one-line method binding and is manifest-bound; manifest identity is externally bound by exact Git HEAD + EV | v4 receipt excluded from manifest | Concurrent EV B D1: append/duplicate/rewrite of receipt bytes passed both manifest and receipt verification. |
| #208-25 | supersede | after safe-control exclusion, every retained development match must have exactly one realized outcome and a positive finite official-SP triple; embargoed rows remain label-blind | v4 accidental current-data safety | Concurrent EV B D2: a future retained zero-realized match would be silently settled as a loss. |
| #208-26 | supersede | arbitrary audit output directories are supported, but all serialized #209 references remain canonical `results/issue-208/**`; the boundary is resolved before scientific stages | v4 output-dependent handoff ref | Concurrent EV B D3: alternate-output replay failed only after the full expensive computation. |

### v5 executable evidence

- `chronology_blocks.parquet`, `training_frame_all.parquet` and
  `validation_frame_all.parquet` expose disjoint per-fold roles and fit-use
  flags; `verify_chronology` checks the issue sets and chronological order.
- `materialize_issue_path_metrics` is the single path finalizer;
  `verify_path_metrics` independently recomputes each issue row and every
  aggregate holding field from primitive funded/payout/bankroll values.
- `schema.json` carries the exact complete frame/JSON/model inventory;
  `verify_package_schema` rejects omissions, stale declarations, column drift
  and critical frames mislabeled diagnostic-only.
- Holdout refit baseline and mutated fitted payloads are materialized,
  manifest-bound and linked to the fold2 joblib numerical state plus terminal
  decisions.
- Production tamper suite adds receipt append/rewrite/duplicate/delete,
  non-argmax dynamic action, zeroed issue drawdown, omitted code binding and
  forged holdout attestation attacks.

---

## 18. REWORK v4 closure rows (2026-08-15, EV REJECT ea1fc51)

Independent fresh audit bound PR #230 exact HEAD `ea1fc51bc2e67407cfad59e4034e1e63e33a74f2`.
The audit reproduced all v5 scientific numbers and accepted payout, chronology,
holdout-refit, manifest/receipt and transactional-publication corrections, but
found three method-level blockers. These rows do not change the action grid,
model family, seed aggregation, selection rule, corrected 0.65 coefficient or
scientific hypothesis. Output changes are attributable only to D1–D3.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-27 | supersede | every selection path (primary MLP, Ridge, fixed action, N-only/K-only/N×K restricted controls, actual-refit probe, fallback continuation and NO_BET subsequent issues) scores each issue from ITS OWN strictly-prior live history: trail5/trail10 bankroll, running drawdown and economic loss streak all come from the lane's actual settlements, never from the frozen incumbent counterfactual path; the running drawdown peak includes the time-zero ¥100,000 anchor | v5 `_state_with_bankroll` replaced only `prior_bankroll_yuan`, leaving four path-dependent features from the incumbent path | EV D1: once a learned/control action diverges, the next issue's state was counterfactual; 114/116 states had an unanchored drawdown feature that also entered scaler, MLP and dynamic controls |
| #208-28 | supersede | recovery metrics distinguish COMPLETED recovery duration (`max_recovery_issues`), open/censored underwater duration (`open_underwater_issues`) and recovery event count (`recovery_issues`); a right-censored terminal underwater episode is never reported as a completed recovery; `verify_path_metrics` recomputes episodes with an independent primitive implementation, not production `summarize_path` | v5 `max_recovery_issues` incremented on every underwater issue including terminal-censored episodes; verifier reused the production summary | EV D2: 25/34 paths had `recovery_issues == 0` while `max_recovery_issues > 0`; CV_2022 learned_policy published 58 recovery issues that never recovered |
| #208-29 | supersede | production verification recomputes the five path-dependent state features from the frozen incumbent source and binds the fitted model's scaler drawdown mean to the fold2 FIT training mean; a legal re-manifest of `training_frame_all.parquet` (e.g. shifting drawdown +0.5) fails closed even with a fully valid SHA256SUMS.json; tamper suite adds `training_state_drawdown_shift` | v5 manifest-only intra-package hash binding | EV D3: remanifested critical training evidence passed `verify_package` because the manifest cannot prove that training state matches source-derived causal recomputation or the fitted model |

### v6 executable evidence

- `live_prior_state_from_rows` (features.py) rebuilds all five path-dependent
  state features from a lane's own accumulated rows; `_state_with_prior`
  (runner) replaces them in the design vector at every call site
  (learned/refit/restricted/ridge/fixed).
- `incumbent_prior_state` anchors the running peak at ¥100,000 and defines a
  loss by net P&L < 0 (payout < funded), consistent with
  `max_consecutive_losing_issues`.
- `summarize_path` publishes `open_underwater_issues` and restricts
  `max_recovery_issues` to completed episodes; golden tests cover
  never-recovered and completed-then-open paths.
- `verify_state_semantics` recomputes prior state per (split, issue) from
  `incumbent_paths.parquet` and compares against training/validation frames,
  then checks the fold2 scaler drawdown mean against the FIT training mean.
- Production tamper suite now includes 23 attacks; `training_state_drawdown_shift`
  is detected by the semantic verifier even after a legal manifest rewrite.

---

## 19. PI takeover v7 closure rows (2026-08-15, concurrent EV REJECTs at feed021a)

Two independent audits bound PR #230 exact HEAD
`feed021a0a20ea3e08c8c06a5c0a93bfe0e41f79`. Both reproduced the published
null result and all accepted payout/chronology/capital/recovery evidence, but
their union exposed five method/evidence boundaries. These rows preserve the
action catalog, model families, seeds, selection rule and 0.65 ticket payout
semantics; all scientific output changes are consequences of the causal
lag-state correction only.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-30 | supersede | trail5/trail10 use the exact N-issue lag only when N completed issues exist; otherwise they use time-zero ¥100,000 in training, validation, live inference, controls and actual refit; verifier rebuilds this independently | v6 FIT helper used first observed post during warm-up | R7 D1: 27 FIT issue states / 4,536 action rows had training/inference warm-up drift. |
| #208-31 | supersede | actual-refit payload and published inventory enumerate ranker, primary MLP, Ridge, best-fixed, three restricted MLPs, OOD scaler/threshold, diagnostic MLP and terminal decisions; every numerical fitted object has a separate joblib binding | v6 primary/ranker/fixed/OOD subset receipt | R7 D2: Ridge and three restricted MLPs were outside outcome-isolation evidence. |
| #208-32 | supersede | production verifier independently rebuilds fold ends/lifts, median, positive folds, rule1-3, eligibility, candidate and drawdown from decisive path primitives; selection, handoff candidate/fallback and fitted model are relation-bound | v6 minimal handoff shape/path verification | R7 D3: a legal re-manifest could forge a +¥999,999 promotion and learned handoff. |
| #208-33 | supersede | only exact package-relative root `SHA256SUMS.json` is excluded; nested same-name files, unsafe relative paths and symlinks fail closed in producer/verifier/tamper helpers | v6 basename exclusion | R7 D4: `models/SHA256SUMS.json` bypassed full-delivery binding. |
| #208-34 | supersede | output→backup rename, first fsync, staging→output rename, second fsync, post-verify rollback and backup cleanup are transaction boundaries; faults restore visible last-good and preserve retryable staging | v6 first-fsync outside rollback boundary | R7 D5: first parent-fsync failure hid last-good in an orphan backup. |

### v7 executable evidence contract

- `fitted_object_inventory.json` plus eight terminal model/scaler artifacts
  bind every fitted numerical object; baseline and mutated actual-refit payloads
  must be byte-semantic equals and equal the published inventory.
- `verify_selection_authority` recomputes terminal authority from learned and
  incumbent path primitives and binds selection to #209 handoff/model state.
- Tamper suite adds false terminal promotion and nested manifest-name escape.
- Golden tests span lag warm-up counts 1/4/5/9/10 and first/second parent-fsync
  failure plus transient backup-cleanup failure.

---

## 20. PI takeover v8 C1/E1 closure rows (2026-08-16, finalize REJECT d51bd3e)

The finalize audit at exact PR #230 HEAD
`d51bd3e07b84039cc7172c8d3fef776d99aca95d` reproduced the null result but
found one conclusion-input defect (C1) and one finalize evidence defect (E1).
These corrections preserve the frozen action catalog, model families, seeds,
selection rule, chronology and 0.65 ticket payout semantics.

| Row | Action | Scope | Supersedes | Rationale |
|---|---|---|---|---|
| #208-35 | supersede | ticket identity is the canonical unordered set of paired `(immutable match id, outcome code)` legs; paired arrays are sorted together before serialization/hash, candidate pools deduplicate that identity, every WOR/top-K selector rejects semantic aliases, and the production verifier independently reconstructs the canonical hash and bundle uniqueness | v7 separately sorted match key plus generation-order outcome/hash | Finalize C1: 1,738 non-WR semantic duplicate rows entered bundles; 36/9,744 action-label rows changed after correction, with maximum absolute matched-lift delta ¥54,170.80. |
| #208-36 | supersede | after final-package verification, ownership of the obsolete backup is removed from the outer rollback before cleanup; cleanup parent-fsync failure preserves the verified new package and immediate retry remains safe; every nested directory is fsynced bottom-up | v7 backup cleanup followed by parent fsync while outer rollback still held the backup path | Finalize E1: if backup deletion succeeded and parent fsync failed, generic rollback deleted the verified output and could not restore the missing backup. |
| #208-37 | add | exact before/after C1 evidence is reproduced from superseded commit `d51bd3e…` by `scripts/analyze_bj208_c1_correction.py` and committed under `docs/research/evidence/issue-208-r8/`; the production runner contains no compatibility layer for the superseded artifact | — | Preserve auditable correction attribution without imposing a backward-compatibility tax on the current model runtime. |

### v8 executable evidence

- Producer code commit:
  `d2e1f9c4f74c61b8e174a09f6d54c7dc79625be5`.
- `tests/test_bj208_canonical_identity.py` covers permutation invariance,
  semantic pool uniqueness, selector rejection and verifier rejection.
- `tests/test_bj208_publication.py` covers cleanup parent-fsync failure,
  verified-new visibility, immediate retry and nested-directory fsync order.
- Production tamper suite adds `semantic_ticket_order_alias`; 26/26 attacks
  are detected.
- Full replay: 1,154 seconds; 87 focused tests; package verifier PASS; all 78
  non-manifest payloads bound.
- Final disposition remains `eligible=false` with frozen
  N7/K8/MARKET_WOR/native-¥2 incumbent; the unchanged terminal decision does
  not erase the material intermediate action-surface corrections.
