# Strategy Worktree Handoff: Website Model EV

Date: 2026-07-02

## Purpose

This note separates the current website's live model-EV display from the strategy backtest work. The frontend should remain a decision console. Strategy research, replay, and parameter changes should move to the strategy worktree and only flow back after out-of-sample validation.

## Worktree Boundary

Current ownership split after the 2026-07-04 main integration:

- `feature/beijing-lot-codex` should focus on database maintenance, data ingestion, dashboard/API reliability, frontend usability, settlement review, and integration of validated strategy outputs.
- `feature/beijing-lot-strategy` should own model optimization, decision-chain optimization, draw-protection research, N-string portfolio selection, and historical/out-of-sample replay.
- Strategy changes should not be promoted into the live decision dashboard until they produce reproducible artifacts and a concise handoff describing data boundaries, leakage controls, and expected live behavior.
- The dashboard may display shadow/paper variants for audit, but production-facing defaults should remain stable unless the strategy worktree has validated the change.

## Current Website Model EV Version

The live website uses the decision API in `src/decision_api/app.py`.

Version registry:

```text
config/decision_versions.json
schema_version: decision_versions_v1
probability_model: bd_prob_handicap_calibrated_v1
q_model: q_ev_sp_v1
decision_chain: llm_chain_bet_protect_stop_v3
prompt_version: fixed_decision_chain_v3_bet_protect_stop
decision_model_version: gpt_fixed_decision_chain_v3
decision_config_hash: a95fcd6bcd94b8cd
```

Important current setting:

```text
Q_STOP_THRESHOLD = 1.00
```

So the current website hard stop is only `q < 1.00`. More conservative lines such as `1.10` or `1.20` are research candidates, not yet the live API setting.

## What "Model EV" Means On The Website

For live/current matches, the single-match model EV is computed online from SQLite rows, not from a persisted model artifact.

Data sources:

- Live website DB: `data/derived/500_bjdc/500_bjdc.sqlite`
- Historical calibration DB: `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`

Probability path:

1. Start from average European odds in the match row.
2. Convert to de-vig 3-result market probabilities.
3. Apply handicap-aware historical smoothing with only prior issues: `issue < current_issue`.
4. Calibration buckets are applied from broad to narrow:
   - global
   - Beidan handicap bucket
   - handicap + market top result
   - handicap + market top result + top-probability bucket
   - league + handicap + market top result + top-probability bucket
5. The public version label is `bd_prob_handicap_calibrated_v1`.

q path:

1. Use the calibrated probability for each of `胜/平/负`.
2. Use pre-result SP with this priority:
   - complete 500 preclose SP
   - if no result yet, complete 500 live SP
   - if no result yet, complete 500 trade HTML SP
   - if match has already settled and no preclose SP exists, do not fabricate a pre-result SP
3. Compute:

```text
q = calibrated_probability * selected_SP
```

The current website q does not multiply by the Beidan payout haircut in the displayed single-match q. It is an EV proxy / ranking score. Ticket-level strategy ROI is evaluated separately in historical replay.

Selection path:

- The top model result is the result with highest `q`.
- It is a no-buy if top `q < 1.00`.
- A second result is added by the model when `second_q >= 1.00` and `second_q / top_q >= 0.80`.
- The LLM-style fixed decision chain can then change the displayed `押/保/停` recommendation.
- If an active decision snapshot exists, Issue Board uses the active snapshot, not the newly recomputed dynamic decision.

## LLM Decision Layer

The live `押/保/停` cell is not pure model EV.

Decision chain version:

```text
llm_chain_bet_protect_stop_v3
source: gpt_fixed_decision_chain_v3_bet_protect_stop
```

Semantics:

- `押`: fixed-chain comprehensive primary decision after model q, probability, line-gap, odds movement, data analysis, and intelligence.
- `保`: protective result when q/EV tendency differs from the primary decision or model double coverage is retained.
- `停`: max q below the stop threshold, currently `1.00`.

This means strategy backtests should not treat the Issue Board final recommendation as a clean q-only selector unless they explicitly replay the fixed decision chain and snapshot rules.

## Main Strategy EV Pool In The Website

The `/api/issues/:issue/main-strategy` panel is separate from the single-match live q display.

Current production-facing candidates:

- `b384_dd32_smooth100`: stable / drawdown-control candidate
- `b384_dd32_smooth80_convex19`: profit / convexity candidate

Main strategy sources:

- A/B portfolio metrics: `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/`
- Historical EV ticket pool: `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- q/conf/drift leg diagnostics: `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv`

Important boundary:

- Historical issues can show settled ticket PnL from replay CSVs.
- Current live issues usually do not have a generated production N=7 EV pool yet.
- Live proxy ticket drafts are marked as `live_market_proxy_not_main_ev_pool` and should not be cited as production strategy evidence.

## Strategy Worktree Should Own

Strategy worktree should take over the following research and replay tasks.

1. q stop threshold replay
   - Compare hard stops at `1.00`, `1.05`, `1.10`, `1.15`, `1.20`.
   - Evaluate both leg-level filtering and full N=7 ticket replay.
   - Report annual performance, especially 2023-2025 and 2026 holdout/proxy if available.
   - Do not change `Q_STOP_THRESHOLD` in the website until this is validated.

2. Probability-first vs q-first selector
   - User hypothesis: use win probability to drive primary bet, use high q to thicken upside/protection.
   - Existing useful entry points:
     - `scripts/evaluate_p_first_depth_allocator.py`
     - `scripts/evaluate_p_core_q_overlay_arm.py`
     - `scripts/build_main_strategy_leg_ev_features.py`
   - Output should compare ROI, profit, maxDD, full-loss rate, issue win rate, and ex-best-issue ROI.

3. Main N=7 fixed-384 improvements
   - Keep the baseline budget at 384 units unless explicitly testing capital scaling.
   - Avoid lower-N rescue unless requested; recent direction is high-N with protection/diversity.
   - Compare against:
     - `b384_dd32_smooth100`
     - `b384_dd32_smooth80_convex19`
   - Preserve a same-budget comparison.

4. q/probability timestamp discipline
   - Live q uses `q_input_sp_snapshot_ts`, `q_input_probability_snapshot_ts`, and `q_calculated_ts`.
   - Backtests must use only pre-result snapshots and prior-issue calibration counts.
   - No final score, result code, or winning SP may enter pre-match selection.

5. Diagnostics policy
   - `line-gap` is diagnostic only in the current website.
   - `SP drift` is diagnostic or tiny paper convex sleeve only.
   - Do not promote either to a hard gate without OOS replay showing stability.

## Suggested First Deliverable From Strategy Worktree

Produce a concise report:

```text
docs/strategy/q_threshold_and_p_first_replay_YYYY-MM-DD.md
```

Minimum tables:

- q hard-stop threshold sweep, same budget, annual rows
- recent 2023-2025 rows
- baseline vs p-first/q-overlay vs q-first
- issue-level drawdown windows and full-loss streaks
- recommendation: keep website threshold, raise threshold, or expose threshold as strategy config only

Minimum machine-readable outputs:

```text
results/strategy_q_threshold_replay_YYYYMMDD/threshold_summary.csv
results/strategy_q_threshold_replay_YYYYMMDD/annual_summary.csv
results/strategy_q_threshold_replay_YYYYMMDD/issue_profit.csv
```

## Commands To Reuse

Read current version bundle:

```bash
python3 - <<'PY'
from src.decision_api.app import _active_version_bundle
print(_active_version_bundle())
PY
```

Check API endpoints:

```bash
curl http://127.0.0.1:8790/healthz
curl http://127.0.0.1:8790/api/issues/current/dashboard
curl http://127.0.0.1:8790/api/issues/current/main-strategy
```

Relevant strategy scripts:

```bash
python3 scripts/evaluate_p_first_depth_allocator.py
python3 scripts/evaluate_p_core_q_overlay_arm.py
python3 scripts/build_main_strategy_leg_ev_features.py
```

## Open Questions

- Should the website q stop remain `1.00`, or should a validated strategy profile use `1.10+` as a separate strategy gate?
- Should Issue Board show both model-q recommendation and fixed-chain `押/保/停`, or only the final fixed-chain decision?
- Should active snapshots freeze the q/probability version bundle per match before ticket construction?
- Should current issue production EV pool be generated explicitly before the UI allows ticket export?
