# Issue #208 REWORK v4 — same-category sweep evidence (EV §4 mandatory)

Contract BJ-UNIFIED-DYNAMIC-N-001 / v6. This document answers the EV REJECT
`ea1fc51` requirement: "返工必须提交'同类问题完整排查'声明与证据". Each defect is
classified, every category is swept across ALL known call sites, and the actual
checked paths are listed. EV may re-probe any listed call site.

---

## Category 1 — path-state causality (EV D1)

**Defect**: `_state_with_bankroll(ctx, bankroll)` replaced only
`prior_bankroll_yuan`; the other four path-dependent state features
(`prior_trail5_bankroll_yuan`, `prior_trail10_bankroll_yuan`,
`prior_running_drawdown_pct`, `prior_consecutive_losses`) stayed frozen at the
incumbent's counterfactual history. Once a learned/control action diverged from
the incumbent, the next issue's state was wrong.

**Root-cause class**: path-state causality / state-feature construction.

**Fix**: `live_prior_state_from_rows(rows)` (src/parlay_policy/features.py)
rebuilds all five path-dependent features from the lane's own accumulated
settlement rows; `_state_with_prior(ctx, prior)` (scripts/run_bj208_policy.py)
replaces all five in the design vector. `incumbent_prior_state`
(src/parlay_policy/incumbent.py) now anchors the running drawdown peak at the
time-zero ¥100,000 initial bankroll and defines losses by net P&L < 0.

**Sweep — every selection path that consumes state x** (checked and fixed):

| Call site | File:line | Path | Fixed |
|---|---|---|---|
| `_learned_action_fn` | scripts/run_bj208_policy.py:418-435 | primary MLP learned policy | YES — `_state_with_prior(ctx, prior)` |
| `_refit_action_fn` | scripts/run_bj208_policy.py:885-908 | holdout actual-refit probe | YES — `_state_with_prior(ctx, prior)` |
| `_run_controls` restricted branch | scripts/run_bj208_policy.py:1818-1854 | dynamic N / dynamic K / dynamic N×K restricted controls | YES — `live_prior_state_from_rows(rows)` per arm |
| `_ridge_action_fn` | scripts/run_bj208_policy.py:2143-2160 | Ridge control | YES — `_state_with_prior(ctx, prior)` |
| `_fixed_action_fn` | scripts/run_bj208_policy.py:2160-2177 | best-fixed-action control | YES — `_state_with_prior(ctx, prior)` |
| `full_path_replay` loop | src/parlay_policy/replay.py:483-496 | computes `prior` from the lane's own rows before EVERY action_fn call | YES |
| fallback→incumbent continuation | src/parlay_policy/replay.py:516-576 | next issue after a fallback reads the lane's actual (rebased) history | YES — rows include the rebased frozen-incumbent settlement |
| NO_BET subsequent issues | src/parlay_policy/replay.py:498-515 | NO_BET rows append actual bankroll; next issue's prior comes from them | YES |

**Training/OOD/diagnostics intentionally NOT live-path**: `ctx.state`
(build_issue_contexts) is the fit-time reference distribution: the label
surface target is "matched lift vs frozen incumbent", so the covariate x at fit
time is the incumbent prior state; the OOD scaler (`fit_states`,
run_bj208_policy.py:397/866) is fitted on the FIT-fold incumbent states and
applied to live states at inference as a preregistered safety boundary.
These are fit-time distributions, not executed-policy states; the EV defect was
about the executed decision path, which is fully covered above. This choice is
recorded in the protocol log (#208-27) and is not a silent deviation.

**Independent adversarial probe (EV-style)**: the old behavior — change live
bankroll to 50 while trail/drawdown/loss stay `90, 80, 0.2, 3` — is now
impossible: `live_prior_state_from_rows` derives every feature from the rows
passed in. Golden tests: `test_live_prior_state_uses_lane_own_history`,
`test_live_prior_state_time_zero_anchor`.

---

## Category 2 — metric semantics (EV D2)

**Defect**: `max_recovery_issues` incremented on every underwater issue,
including right-censored terminal episodes that never recovered
(replay.py:712-732 old). 25/34 paths had `recovery_issues == 0` while
`max_recovery_issues > 0`.

**Root-cause class**: metric definition / right-censoring / verifier blind spot.

**Fix**: `summarize_path` now distinguishes:
- `recovery_issues` = count of COMPLETED recovery events (episode reached a new
  running peak),
- `max_recovery_issues` = longest COMPLETED underwater episode duration,
- `open_underwater_issues` = length of the right-censored (open) episode at
  path end (0 if the path ends at/above peak),
- `time_under_water_issues` unchanged (total underwater issues).

`verify_path_metrics` now uses the INDEPENDENT `_independent_recovery_episodes`
primitive implementation (src/parlay_policy/verify.py), not production
`summarize_path`, so a producer semantic error cannot be rubber-stamped.

**Sweep — every window/aggregation definition checked**:

| Metric | Where | Semantics checked |
|---|---|---|
| max_drawdown_pct | replay.py `_running_peak_drawdown` / `materialize_issue_path_metrics` | running peak includes time-zero anchor (already correct; verified) |
| prior_running_drawdown_pct (state) | incumbent.py `incumbent_prior_state` | **fixed** — anchor added |
| prior_running_drawdown_pct (live state) | features.py `live_prior_state_from_rows` | **fixed** — anchor added |
| prior_trail5/trail10 (state) | incumbent.py / features.py | aligned to `tail(5).iloc[0]` / `tail(10).iloc[0]` = post N issues back |
| max_consecutive_losing_issues | replay.py `summarize_path` / features.py | net P&L < 0 (payout < funded) — incumbent loss streak **fixed** from gross==0 to net<0 |
| time_under_water_issues | replay.py `summarize_path` | total underwater issues (unchanged) |
| recovery_issues | replay.py `summarize_path` | completed recovery event count |
| max_recovery_issues | replay.py `summarize_path` | longest completed episode only (**fixed**) |
| open_underwater_issues | replay.py `summarize_path` | right-censored open episode length (**new**) |
| rolling 5/10/20 loss prob/worst | replay.py `summarize_path` | net-P&L windows, right-censoring at path end (verified) |
| ex-largest issue | replay.py `path_holding_metrics` | ex-largest = sum minus largest abs P&L issue (verified) |
| minimum retained cash | replay.py `summarize_path` | min(pre - funded) (verified) |
| near_ruin / ruin | replay.py `summarize_path` | ≤10% / ≤0 of initial capital (verified) |

Golden tests: `test_recovery_terminal_censored_never_recovers`,
`test_recovery_completed_then_open`, `test_time_under_water`,
`test_max_consecutive_losses`, `test_drawdown_includes_time_zero`,
`test_live_prior_state_time_zero_anchor`.

---

## Category 3 — verifier/schema semantic binding (EV D3)

**Defect**: a legal re-manifest attack — copy the package, shift
`prior_running_drawdown_pct` in `training_frame_all.parquet` by +0.5, regenerate
SHA256SUMS.json — passed `verify_package` (failure_count=0). The manifest only
proved intra-package hash self-consistency, not that training evidence matches
the source-derived causal recomputation or the fitted model.

**Root-cause class**: evidence chain / schema-semantic verifier / verification
blind spot.

**Fix**: `verify_state_semantics(package)` (src/parlay_policy/verify.py):
1. recomputes the five path-dependent state features per (split, issue) from
   `incumbent_paths.parquet` (itself bound to frozen #207 CONTROLLING
   identities + payout economics) and compares against
   `training_frame_all.parquet` / `validation_frame_all.parquet`;
2. binds the fold2 MLP scaler mean for `prior_running_drawdown_pct` to the
   recomputed fold2 FIT training-frame mean;
3. fails closed on any divergence. Wired into `verify_package` (runner) and the
   production tamper suite adds `training_state_drawdown_shift` (attack 23).

**Sweep — decision-critical evidence binding** (what is bound and how):

| Evidence | Binding | Verifier |
|---|---|---|
| training_frame_all / validation_frame_all state columns | source-derived recomputation from incumbent_paths + model scaler mean | `verify_state_semantics` |
| fold2 MLP weights/scaler | manifest + scaler-vs-frame binding + holdout refit signature | `verify_state_semantics`, `verify_holdout_mutation_receipt` |
| incumbent_paths.parquet | frozen CONTROLLING identities + payout economics recomputation | `verify_payout_economics`, `verify_provenance` |
| issue_capital_ledger.parquet | start ¥100k, ¥2 units, conservation, continuity, no top-up | `verify_capital_accounting` |
| decision_rows_all / dynamic controls | embargo, argmax, per-issue causal-state scoring | `verify_no_embargoed_split`, `verify_dynamic_control_decisions` |
| path_holding_metrics.parquet | independent episode + issue-metric recomputation | `verify_path_metrics` |
| manifest + receipt | every delivered byte hashed (except manifest itself), receipt content-bound | `verify_manifest`, `verify_receipt` |
| code/config/env | producer commit, method.yaml, requirements, runner + package modules | `verify_code_bindings` |
| chronology | FIT/VAL issue blocks disjoint + chronological + fit-use flags | `verify_chronology` |

**Adversarial probes included** (production entry, re-manifest allowed):
`training_state_drawdown_shift` (new), plus existing 22 attacks (settlement
mutation, self-consistent ledger, manifest forgery, source-trace forgery,
payout omission/division/0.65^N, handoff staging, completion, schema, bundle
drop, REQ evidence, dynamic globalized/non-argmax, zero drawdown, holding
forgery, code-binding omission, receipt append/rewrite/duplicate/delete,
forged holdout attestation). Test: `test_tamper_training_state_shift_detected`.

---

## Declared checked scope

I checked, for every category, the files and call sites listed above plus:

- `src/parlay_policy/replay.py` — full read; action_fn contract, settlement,
  NO_BET, frozen-incumbent rebase, materialize, summarize, holding metrics;
- `src/parlay_policy/incumbent.py` — full read; prior-state construction,
  loss-streak definition, anchor;
- `src/parlay_policy/features.py` — full read; state vector layout, both prior
  state constructors;
- `scripts/run_bj208_policy.py` — full read; all 5 state-consuming action fns,
  controls matrix, holdout refit, metadata, schema, manifest, handoff;
- `src/parlay_policy/verify.py` — full read; all verifier functions + tamper
  suite; added independent episode recomputation + state semantics.

No same-category defect remains at any listed call site. EV may re-probe any of
them with the same or new attacks.
