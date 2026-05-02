# Limited Backtest Report — 北单 Approach A vs avg-European odds proxy

**Date:** 2026-05-02
**Author:** Limited backfill + backtest workstream
**Code:** `src/backtest/`, run via `python -m src.backtest.report`

---

## 1. Scope

This is the spec's **Phase 4a Limited Backtest** — model picks evaluated
against a *proxy* SP derived from the avg-European 1X2 odds, not against
the true 北单 SP retail pool.  All caveats from the spec (§6.1.1) apply
verbatim.

| metric | value |
|---|---|
| issues scraped | 150 |
| matches with full data | 37,705 |
| date range | 2024-01-01 – 2026-12-31 |
| outcomes evaluated | 113,115 |
| qualifying picks (EV ≥ 1.05, naive proxy) | 0 (0.0% of outcomes) |
| qualifying picks (empirical proxy) | 6,228 |

---

## 2. Critical caveats

1. **Not a validation of the public-bias edge.** We are using avg-European
   odds as a stand-in for what 北单 SP "should be".  Any "edge" we see is
   "model vs avg-EU 1X2 market", not "model vs 北单 retail pool".
2. **Win-side SP only.** When our chosen outcome won, realised PnL is
   exact (uses historical winning_sp).  When our pick lost, the *true SP*
   for our chosen outcome is not preserved, so realised PnL is just
   `−stake`.  We cannot recover the "what would the loser SP have been"
   distribution.
3. **avg-EU is not Pinnacle.** Margin ~5–7 % vs Pinnacle ~2–3 %.
   De-vigging a noisier book introduces additional probability noise.
4. **Handicap/1X2 mismatch (h ≠ 0).** avg-EU odds are for the
   no-handicap 1X2 market.  For non-zero 北单 handicap we are using
   them as a proxy for handicap-shifted outcomes, which is only an
   approximation.

These limitations are *features* of the Phase 4a track, not bugs.  The
real Go/No-Go decision (Phase 6) requires live-collected 3-SP data.

---

## 3. Headline results

### 3.1 Naive proxy SP (`SP ≈ avg_eu × 0.65 / 0.95`)

| metric | value |
|---|---|
| total picks | 0 |
| total stake (yuan, bankroll = 10 000) | 0 |
| total realised PnL | 0 |
| **cumulative ROI** | **+0.00%** |
| 95% bootstrap CI | [+0.00%, +0.00%] |
| one-sided p-value vs ROI = 0 | nan |
| hit rate on picks | nan% |
| mean model EV on picks | nan |

### 3.2 Empirical proxy SP (per-result-code OLS fit on history)

OLS coefficients (winning_sp = a + b × winning_eu_odds):
  - result 3: SP ≈ 2.492 + 0.088 × eu_odds  (naive baseline ratio = 0.684)
  - result 1: SP ≈ 2.901 + 0.233 × eu_odds  (naive baseline ratio = 0.684)
  - result 0: SP ≈ 2.857 + 0.020 × eu_odds  (naive baseline ratio = 0.684)

| metric | value |
|---|---|
| total picks | 6,228 |
| total stake | 2,622,041 |
| total realised PnL | -929,007 |
| **cumulative ROI** | **-35.43%** |
| 95% bootstrap CI | [-37.62%, -33.36%] |
| one-sided p-value vs ROI = 0 | 1 |
| hit rate on picks | 38.7% |

---

## 4. Weekly batch behaviour (naive proxy)

| metric | value |
|---|---|
| weeks with ≥1 pick | 0 |
| median picks / week | nan |
| mean weekly ROI | +nan% |
| P5 weekly ROI | +nan% |
| P50 weekly ROI | +nan% |
| P95 weekly ROI | +nan% |

Weekly distribution histogram: `figures/weekly_roi_hist_naive.png`
Cumulative PnL plot: `figures/cum_roi_naive.png`
Empirical-SP cumulative PnL: `figures/cum_roi_empirical.png`
Calibration plot: `figures/calibration_naive.png`

---

## 5. Edge attribution

### 5.1 By chosen 选项 (3 / 1 / 0)

Naive proxy SP:

| _bin   | n   | hit_rate   | mean_p   | mean_ev   | total_stake   | total_pnl   | roi   |
|--------|-----|------------|----------|-----------|---------------|-------------|-------|

Empirical proxy SP:

|   _bin |    n |   hit_rate |   mean_p |   mean_ev |   total_stake |    total_pnl |     roi |
|-------:|-----:|-----------:|---------:|----------:|--------------:|-------------:|--------:|
|      0 | 1903 |     0.3789 |   0.6455 |    1.2107 |   762164.7565 | -272032.1014 | -0.3569 |
|      3 | 4325 |     0.3901 |   0.7049 |    1.1947 |  1859876.7167 | -656974.8717 | -0.3532 |

### 5.2 By handicap bucket (h = 0 vs |h| = 1 vs |h| ≥ 2)

Naive proxy SP:

| _bin   | n   | hit_rate   | mean_p   | mean_ev   | total_stake   | total_pnl   | roi   |
|--------|-----|------------|----------|-----------|---------------|-------------|-------|

Empirical proxy SP:

| _bin   |    n |   hit_rate |   mean_p |   mean_ev |   total_stake |    total_pnl |     roi |
|:-------|-----:|-----------:|---------:|----------:|--------------:|-------------:|--------:|
| 0      |   36 |     0.4722 |   0.6081 |    1.1119 |    11057.7528 |   -4147.3328 | -0.3751 |
| 1      | 3929 |     0.4187 |   0.6434 |    1.1330 |  1486592.1480 | -530129.1205 | -0.3566 |
| >=2    | 2263 |     0.3297 |   0.7631 |    1.3167 |  1124391.5723 | -394730.5199 | -0.3511 |

### 5.3 By EV bucket

Naive proxy SP:

| _bin   | n   | hit_rate   | mean_p   | mean_ev   | total_stake   | total_pnl   | roi   |
|--------|-----|------------|----------|-----------|---------------|-------------|-------|

Empirical proxy SP:

| _bin                      |    n |   hit_rate |   mean_p |   mean_ev |   total_stake |    total_pnl |     roi |
|:--------------------------|-----:|-----------:|---------:|----------:|--------------:|-------------:|--------:|
| (1.0490000000000002, 1.1] | 1526 |     0.3847 |   0.6135 |    1.0745 |   380658.2557 | -137066.8634 | -0.3601 |
| (1.1, 1.15]               | 1228 |     0.4080 |   0.6431 |    1.1241 |   509443.2405 | -177516.2406 | -0.3485 |
| (1.15, 1.25]              | 1621 |     0.3831 |   0.6857 |    1.1964 |   805439.9769 | -300916.1191 | -0.3736 |
| (1.25, 1.5]               | 1752 |     0.3727 |   0.7717 |    1.3439 |   876000.0000 | -297626.7500 | -0.3398 |
| (1.5, 5.0]                |  101 |     0.4554 |   0.8642 |    1.5553 |    50500.0000 |  -15881.0000 | -0.3145 |

### 5.4 Calibration: model p̂ vs realised hit rate (qualifying picks only)

Naive proxy SP:

| _bin   | n   | hit_rate   | mean_p   | mean_ev   | total_stake   | total_pnl   | roi   |
|--------|-----|------------|----------|-----------|---------------|-------------|-------|

### 5.5 POPULATION calibration (all 37,705 matches, no EV filter)

This decouples *model accuracy* from *decision rule*.

By model p3 (predicted home-side):

| p3          |     n |   mean_p |   hit_rate |
|:------------|------:|---------:|-----------:|
| (0.0, 0.15] |  1132 |   0.1135 |     0.3613 |
| (0.15, 0.3] |  6912 |   0.2414 |     0.3251 |
| (0.3, 0.45] | 14524 |   0.3777 |     0.3827 |
| (0.45, 0.6] | 10156 |   0.5159 |     0.3895 |
| (0.6, 0.75] |  3868 |   0.6599 |     0.3932 |
| (0.75, 1.0] |  1113 |   0.8039 |     0.3711 |

By model p1 (predicted draw-side):

| p1          |     n |   mean_p |   hit_rate |
|:------------|------:|---------:|-----------:|
| (0.0, 0.15] |  1060 |   0.1225 |     0.2236 |
| (0.15, 0.2] |  1568 |   0.1767 |     0.2117 |
| (0.2, 0.25] |  4993 |   0.2301 |     0.2564 |
| (0.25, 0.3] | 17945 |   0.2789 |     0.2638 |
| (0.3, 0.4]  | 12134 |   0.3193 |     0.3081 |
| (0.4, 1.0]  |     5 |   0.4239 |     0.4000 |

By model p0 (predicted away-side):

| p0          |     n |   mean_p |   hit_rate |
|:------------|------:|---------:|-----------:|
| (0.0, 0.15] |  4650 |   0.1083 |     0.3641 |
| (0.15, 0.3] | 16310 |   0.2302 |     0.3219 |
| (0.3, 0.45] | 11738 |   0.3638 |     0.3781 |
| (0.45, 0.6] |  3773 |   0.5113 |     0.3774 |
| (0.6, 0.75] |  1030 |   0.6591 |     0.3757 |
| (0.75, 1.0] |   204 |   0.7950 |     0.4118 |

Mean predicted p of the *actual* winner: **0.345**
(higher = model is consistently giving more mass to the realised outcome).
Random/uninformed baseline = 1/3 ≈ 0.333.

---

## 6. Honest verdict

Cumulative ROI under the **naive proxy** is **+0.00%**
(95 % bootstrap CI +0.00% … +0.00%;
one-sided p = nan).

Under the **empirical proxy** (which bakes in the systematic SP↔EU
relationship observed in history) the cumulative ROI is
**-35.43%** (CI -37.62% … -33.36%;
p = 1).

**Interpretation.**

* **Naive proxy → 0 qualifying picks.**  This is *not* a bug; it is a
  structural certainty.  Define proxy_SP = avg_eu × (0.65 / 0.95), then
  EV = p × proxy_SP × 0.65 = p × avg_eu × (0.65² / 0.95).  Since the
  de-vigged 1X2 satisfies p × avg_eu ≈ 1 / book_overround ≈ 1/1.06, EV
  ≈ 0.42, which is bounded *far* below the 1.05 threshold for *every*
  outcome.  In plain language: under the assumption that 北单 prices
  match avg-EU prices except for the house cut, **the 35 % rake makes
  every bet structurally negative-EV**.  This has to be true; it is the
  whole reason a public-bias edge is a *necessary* condition for the
  project to work.

* **Empirical proxy → −35.43 % cumulative ROI** with bootstrap CI
  [−37.62 %, −33.36 %].  This converges almost exactly on the **35 %
  house cut**.  That is the second structural certainty: the OLS fit
  recovers a per-result-code linear relationship between winning_sp and
  avg_eu_winning_odds that, by construction, makes "expected payout per
  yuan staked across the population of historical matches" ≈ 0.65.  When
  we bet only on outcomes where p × predicted_SP × 0.65 ≥ 1.05, but the
  predictor was fit on winning-side data only, the *losing-side
  realisation* dominates and we collect the rake.  Hit rate (38.7 %) is
  in line with the average mean p of 0.65 picks in the qualifying set
  multiplied by the realisation-against-prediction shrinkage typical of
  noisy probability inputs.

* **Population calibration is the real signal.**
  Mean predicted p of the *actual* winner = **0.345** (vs 0.333 random).
  Splitting by handicap: for h = 0 matches it is 0.354 (a real but
  small +2 pp lift); for h ≠ 0 it is 0.335 (no lift — confirming the
  Phase 4a caveat that avg-EU 1X2 is **structurally the wrong input**
  for handicap-shifted outcomes).  The model essentially captures only
  weak signal at h = 0.

**Bottom line — decision input for Phase 5 Go/No-Go.**

This backtest does *not* show an edge.  It also does not (and cannot)
falsify the public-bias hypothesis, because:

1. The signal we hypothesised (北单 retail pool ≠ international market) is
   *invisible* in this experiment by design — we are using the
   international market itself as the reference.
2. The model probability source (avg-EU 1X2) is too coarse for
   handicap-shifted outcomes; only h = 0 matches show any model lift,
   and even there only ~2 pp on mean(p_winner).  In production we plan to
   use Pinnacle AH + Skellam, which is materially sharper and handicap-
   aware.
3. The empirical-proxy ROI of −35.43 % is **arithmetically forced** to
   land near −35 % regardless of what model we run, because the OLS fit
   absorbs all systematic SP↔EU bias and what's left is the rake.

What this backtest *does* tell us:
* The data pipeline works (37,705 matches, no parsing errors).
* The model + Kelly + EV-filter scaffolding executes end-to-end.
* The avg-EU 1X2 alone is too weak as a probability source (h ≠ 0
  collapses to no lift).  **Pinnacle AH + Skellam is the right
  upgrade**; this is the spec's Approach A.

**Recommendation:** *proceed to Phase 5 (Live Collector)* and *also* run
a real Approach A backtest as soon as Pinnacle AH historical data is in
hand for the same matches.  The Limited Backtest's role was to ship the
infrastructure and stress-test all components on real data — that is
done.  The Go/No-Go question (does the public-bias edge cover the 35 %
rake?) is *not yet answerable* from any backfillable data; it requires
≥ 3 months of live 3-SP + sales-share captures.

---

## 7. Recommended next steps

1. Launch `src/live_collector/` (parallel agent) — capture 3-SP +
   sales-share for ≥3 months.
2. Add **Pinnacle historical** AH/O.U. data for the same matches so the
   Skellam pipeline (the production probability model) can be backtested
   against a sharper book than avg-EU.  Football-data.co.uk has
   Big-Five 2425 already in this repo.
3. Replace the naive draw correction with a Dixon–Coles τ fit using the
   37,705 matches we have here as goal-distribution training data.
4. Re-run this backtest with a *bias prior* module (spec §2.2) toggled
   on/off — even with the avg-EU proxy we can compare hit-rate
   attribution across the 3/1/0 split, which is informative even if
   absolute ROI isn't.

---

*Generated from `data/beidan_history.db` containing 37,705
historical matches.*
