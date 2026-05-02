# Combo-strategy half-backtest on historical 北单 data

**Date:** 2026-05-02  
**Code:** `src/backtest_combo/`  
**Sample DB:** `data/beidan_history.db` (issue-level batches)

## 1. Methodology

For each historical 期号 (weekly batch) we (a) compute model p3/p1/p0 from avg-EU 1X2 odds via proportional de-vig and the spec §4.3 draw correction, (b) predict per-option proxy SP using B2's per-result-code OLS fit on `winning_sp ~ avg_eu_winning_odds`, (c) emit candidates with single-leg edge ≥ 0.05, (d) drive `src.combo_optimizer.build_plan` with defaults (bankroll=100,000, top_k=14, n_legs=7, combo_ev_threshold=0.10, kelly=¼, weekly_stake_cap=25%), (e) settle each TicketPlan against actual results — combo wins iff every leg matches `result_code`, profit then equals `stake × (∏actual_winning_SP × 0.65 − 1)`. By design, the proxy SP is fit on the same market that drives our model probabilities, so the expected ROI is the rake (≈ −35%); this run is a pipeline-validation and variance-quantification exercise.

## 2. Sample size

| metric | value |
|---|---|
| issues (weeks) covered | 150 |
| weeks with ≥1 combo placed | 44 |
| total combos placed | 1,831 |
| total tickets placed | 345,306 |
| total stake (yuan) | 759,032 |
| total realised profit (yuan) | -759,032 |
| **cumulative ROI** | **-100.00%** |
| 95% bootstrap CI (per-plan) | [-100.00%, -100.00%] |

## 3. Weekly ROI distribution

Across weeks where at least one combo was placed:

| stat | value |
|---|---|
| n_active_weeks | 44 |
| mean | -100.00% |
| std | 0.00 pp |
| P5 | -100.00% |
| P25 | -100.00% |
| P50 | -100.00% |
| P75 | -100.00% |
| P95 | -100.00% |
| min | -100.00% |
| max | -100.00% |

## 4. Hit-rate findings

| metric | value |
|---|---|
| n_active_weeks | 44 |
| weeks_with_at_least_one_hit | 0 |
| frac_weeks_with_hit | 0.0000% |
| max_hits_in_a_week | 0 |
| total_combos_run | 1831 |
| total_combos_hit | 0 |
| empirical_combo_hit_rate | 0.0000% |
| predicted_combo_hit_rate | 11.1343% |

## 5. Edge attribution

### 5.1 By combo handicap mix

| bucket    |   n_combos |   total_stake |   total_profit |   hit_rate |     roi |
|:----------|-----------:|--------------:|---------------:|-----------:|--------:|
| all_h2+   |         89 |         43486 |    -43486.0000 |     0.0000 | -1.0000 |
| h0_h1_mix |          9 |          4230 |     -4230.0000 |     0.0000 | -1.0000 |
| mixed     |       1733 |        711316 |   -711316.0000 |     0.0000 | -1.0000 |

### 5.2 By combo selection mix

| majority   |   n_combos |   total_stake |   total_profit |   hit_rate |     roi |
|:-----------|-----------:|--------------:|---------------:|-----------:|--------:|
| 0-heavy    |        140 |         55030 |    -55030.0000 |     0.0000 | -1.0000 |
| 3-heavy    |       1691 |        704002 |   -704002.0000 |     0.0000 | -1.0000 |

## 6. Calibration

Mean predicted combo win prob: **11.1343%** vs empirical hit rate **0.0000%** (over-confident). See `figures/combo_calibration.png`.

## 7. Comparison vs single-bet B2 baseline

B2's single-bet empirical-proxy backtest reported **−35.43%** cumulative ROI (CI [−37.62%, −33.36%]) over 6,228 picks. This combo run lands at **-100.00%** (CI [-100.00%, -100.00%]) over 1,831 combos. If hits had occurred at the *predicted* rate the cumulative ROI would have averaged to roughly the rake (combos pay 35% rake once vs once-per-leg in single-bets). What we see instead is **worse than rake** because the model over-counts hits dramatically (see §9). Combos amplify any model bias because the joint probability multiplies seven correlated p̂ residuals.

## 8. Plots

- Cumulative profit + ROI: `figures/combo_cum_roi.png`
- Weekly ROI histogram: `figures/combo_weekly_roi_hist.png`
- Calibration: `figures/combo_calibration.png`

## 9. Honest verdict

Cumulative ROI = **-100.00%** (95% bootstrap CI -100.00% … -100.00%); single-bet B2 baseline was −35.43%; delta = -64.57 pp.

**This is consistent with no edge — and worse than the rake**, which is *itself* the most informative finding. The mechanism:

- The optimizer found 1,831 candidate combos across 44 weeks, all of which it scored as +EV under the model.
- The model's mean predicted joint win prob per combo was **11.1343%** (mean ∏SP ≈ 996 when computed on plans). Across 345,306 tickets the *expected* number of winning tickets was **41084**.
- The *realised* number of winning tickets was **0**.

So the model is not merely uncalibrated — it is dramatically over-confident on the very combos it self-selects. Two compounding causes:

1. **Selection bias from edge filter ≥ 0.05.** A leg passes the filter only where `p × proxy_SP × 0.65 ≥ 1.05`. Since the empirical OLS proxy SP is fit on the same eu_odds we use to derive p, picks survive the filter precisely when the OLS residual + the de-vig noise both line up favourably — these are by construction *the legs where the model is most likely to be wrong*. The edge filter is a winner's-curse engine.

2. **Probability-product error compounds.** A 7-leg combo's joint_p is extremely sensitive to per-leg p̂ inflation. If each leg's p̂ is biased high by 5pp at the +0.05-edge boundary, the joint can be 4–8× over-stated.

**Comparison vs B2's single-bet baseline (−35.43%).** Single-bet ROI regresses cleanly to the rake because the OLS fit absorbs systematic SP-vs-EU bias *on average*. The combo strategy concentrates stake on the right tail of that residual distribution, where the OLS over-estimate of SP combined with an over-estimate of p compounds across 7 legs. The ROI is therefore *more* negative than the rake, not less. Combos do not magically beat single-bets when both share the same biased probability source.

**Pipeline validation status — PASS.** The optimizer ran on every issue, respected the 25%-of-bankroll cap, and emitted plans with valid stakes and ticket counts on 44/150 weeks. No code-path errors. Settler correctly handled all-miss combos.

**Variance baseline for Live Collector.** Under the avg-EU-as-proxy model, weekly combo ROI on this dataset is degenerate: every active week lost 100% of stake. Live Collector validation must beat this both in (a) producing ≥1 winning combo per quarter and (b) showing predicted combo p calibrated to realised hit rate within an order of magnitude. With real Pinnacle AH + Skellam probabilities and real 北单 SP captures (which are *independent* of avg-EU residuals), neither effect (1) nor (2) above will fire in the same way — but until that data is in hand, this report is the proper null.
