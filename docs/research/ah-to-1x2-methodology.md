# AH-to-1X2 conversion: methodology research and design

Project: 北京单场 让球胜平负 quant strategy
Author / date: built for beijing-lot, 2026-05-02
Code: `/Volumes/Data Drive/workspace/trading/beijing-lot/notebooks/ah_to_1x2.py`

## 1. Problem statement

北单 让球胜平负 prices three outcomes (3 / 1 / 0) at a fixed **integer** handicap
(e.g. -1, +1, 0). Sharp international books (Pinnacle being the gold standard)
quote the AH market at half- or quarter-ball lines (e.g. -1.25, -0.75) and the
draw is removed from the book. We need a principled way to:

1. Take Pinnacle's AH + O/U quotes,
2. Recover a true probability distribution over the goal difference D = H - A,
3. Integrate that over the 北单 integer line to produce P(3), P(1), P(0).

## 2. Methods surveyed

### 2.1 Buchdahl / football-data.co.uk

Joseph Buchdahl (the maintainer of football-data.co.uk and author of *Squares
& Sharps* and *Monte Carlo or Bust*) does not publish a single closed-form
"AH → 1X2" formula. His public writing focuses on:
- the **wisdom-of-the-crowd** approach to de-vigging (proportional / equal
  margin / power);
- empirical evidence (his X / Twitter discussion of equal-margin de-vig vs
  power) showing **power method** dominates equal-margin and beats proportional
  on most large-margin books, while on Pinnacle (≤ 2-3% overround) all three
  methods give nearly identical de-vigged probabilities.

His closest direct contribution: in selecting "the" handicap line for his CSV
files he picks the line *closest to 50/50* with the most contributing
bookmakers — implicitly treating the AH line as a quote of *supremacy* (the
median of the goal-difference distribution). This is the conceptual foundation
for the Skellam approach below.

### 2.2 Pinnacle "1X2 to Handicap odds conversion"

Pinnacle's published page on this conversion describes a Poisson-based
work-flow:

1. De-vig the 1X2 odds.
2. Solve for `(λ_home, λ_away)` such that an independent Poisson model
   reproduces P(home), P(draw), P(away).
3. Re-integrate the bivariate Poisson grid over any handicap to produce
   handicap-market quotes.

This is the inverse of what we need (1X2 → AH), but the **same Poisson grid
trick** works in reverse. We follow exactly that family of approach.

### 2.3 Academic references

- **Karlis & Ntzoufras (2008/2009)** — "Bayesian modelling of football outcomes
  using the Skellam distribution for the goal difference." This paper is the
  cleanest theoretical home for an AH-style market: the goal difference D is
  Skellam-distributed, P(D = k) has a closed form using modified Bessel
  functions, and the AH market is *literally* a quoted CDF/PMF of D shifted by
  the line. Critically, modelling D directly avoids needing to assume the per-
  team scores are independent Poissons and absorbs (much of) the Dixon-Coles
  low-score correction into the Skellam structure.
- **Dixon & Coles (1997)** — adds dependence at low scores via the τ
  correction. We do *not* implement this here because:
  (a) it requires fitting on historical scorelines, not just market quotes;
  (b) Karlis-Ntzoufras show Skellam fits the goal-difference marginal nearly
  as well; (c) we only need three integrated probabilities (3/1/0), and the
  τ correction only redistributes mass at D ∈ {-1,0,1}, which integer-line 北单
  *already* groups together as the draw outcome.
- **Kuypers (2000)** — efficient-market analysis of football odds, uses
  λ-pair calibration but on 1X2 rather than AH.
- **Štrumbelj (2014)** — a key methodological reference on de-vigging: the
  power method (also called "Shin" in some papers) emerges as the empirical
  best for high-margin books.
- **Whelan (2024)** — *Returns on Complex Bets* — empirical study on 84k
  matches confirming Pinnacle AH is the sharpest single market, supporting
  using PAHH/PAHA as the primary input.

### 2.4 Python libraries

- `oddslib` / `mlfoot` / `soccerstan` — none provide a turnkey AH-line → 1X2
  function. `soccerstan` fits Bayesian Dixon-Coles on score data; `mlfoot` is
  match-feature based; `oddslib` is small and odds-format only. We therefore
  roll our own thin Skellam-based module.

## 3. Chosen methodology

### 3.1 Probability model

```
HomeGoals ~ Poisson(λ_h)
AwayGoals ~ Poisson(λ_a)            (independent)
D = HomeGoals - AwayGoals  ~  Skellam(λ_h, λ_a)
```

Two free parameters → **two market constraints**:

1. **Total goals constraint** (from O/U 2.5):
   `λ_h + λ_a = λ_total` chosen so that
   `P(H + A > 2.5)` under Poisson(λ_total) equals the de-vigged "over"
   probability. (The sum of two independent Poissons is Poisson regardless of
   the split, so totals only fix the sum.)

2. **Supremacy constraint** (from AH market):
   Solve for `μ = λ_h - λ_a` such that the model's AH-home win probability at
   the quoted AH line `ah_line` equals the de-vigged AH-home implied
   probability. AH rules implemented for integer / half / quarter lines:
   - integer: win if D + line > 0, push if D + line == 0, lose if < 0.
     Expected recovery = P(D > -line) + 0.5 · P(D == -line).
   - half: pure win/lose, win if D + line > 0.
   - quarter: split 50/50 between two adjacent integer/half legs.

Once `(λ_h, λ_a) = ((λ_total + μ)/2, (λ_total - μ)/2)`, the 北单 integer
handicap probabilities for line `h` are read directly off the Skellam:

```
p3 = P(D > -h) = 1 - SkellamCDF(-h)
p1 = P(D = -h) = SkellamPMF(-h)
p0 = P(D < -h) = SkellamCDF(-h - 1)
```

### 3.2 De-vigging

We expose two methods:

- **Proportional** (default) — `p_i = (1/o_i) / Σ(1/o_j)`. Exact when the
  margin is applied equally on both sides, which is the empirical case for
  Pinnacle two-way markets. Closed form, no fit.
- **Power** (Shin/Buchdahl) — find `k ≥ 1` with `Σ (1/o_i)^k = 1`. Better on
  high-margin books, marginal on Pinnacle.

On the calibration test below the two methods produce nearly identical
results, confirming Pinnacle two-way overrounds are well-balanced and either
method is fine for this data source. We default to `proportional`.

### 3.3 Why Skellam (D directly) and not bivariate Poisson on a 2-D grid?

Both produce the same answer when:
- scores are independent Poisson (the AH market and the totals market alone
  cannot identify a Dixon-Coles τ correction);
- our targets are functions of D only (true for all 北单 outcomes).

Skellam is simply the marginal of the bivariate-Poisson grid and is
computationally cheaper / closed-form via `scipy.stats.skellam`. If we later
want to incorporate a 1X2 quote *as well* (giving us a third constraint), the
2-D grid plus a Dixon-Coles τ becomes natural — see "next steps" below.

## 4. Sanity checks (unit tests, all green)

| # | Check | Result |
|---|---|---|
| 1 | AH=0 with symmetric odds → μ=0, p3 = p0 | passes (p3=p0=0.3702, p1=0.2596) |
| 2 | Probabilities sum to 1 at any target line | passes (sum = 1.0 to 1e-12) |
| 3 | Monotonicity: p3 increases as the home handicap improves (-2 → +2) | passes ([0.11, 0.26, 0.50, 0.75, 0.91]) |
| 4 | Fair AH=-1 odds (1.95/1.95) round-trip to AH-home prob 0.5 | passes (μ=1.07, prob=0.5000) |
| 5 | Skellam mass sums to 1 internally; asymmetry P(D=1)>P(D=-1) when home favoured | passes |
| 6 | Power vs proportional de-vig agree to <5e-3 on a balanced two-way book | passes |

## 5. Calibration test on real Pinnacle data (Premier League 2024-25)

For each of the 377 PL matches with full Pinnacle quotes, we:

1. Take Pinnacle's quoted AH line + AH home/away odds and O/U 2.5 odds;
2. Calibrate (λ_h, λ_a) by the method above;
3. Predict 1X2 probabilities at `target_handicap = 0`;
4. Compare against Pinnacle's *own* 1X2 odds (de-vigged the same way).

This is a self-consistency / round-trip test of the conversion. If the model
can reconstruct Pinnacle's 1X2 quotes from their own AH + O/U quotes, the
conversion logic is sound.

Results:

| metric | proportional | power |
|---|---|---|
| n matches | 377 | 377 |
| mean abs deviation vs book (avg of 3 outcomes) | **0.01117** | 0.01277 |
| abs dev home | 0.00887 | 0.01227 |
| abs dev draw | 0.01596 | 0.01452 |
| abs dev away | 0.00868 | 0.01150 |
| RMSE vs book | 0.01386 | 0.01527 |
| Brier (model vs outcome) | 0.58303 | 0.58309 |
| Brier (book vs outcome) | 0.58318 | 0.58390 |
| log-loss (model) | 0.97722 | 0.97744 |
| log-loss (book) | 0.97696 | 0.97778 |

Interpretation:
- Mean per-outcome deviation between our reconstructed 1X2 and Pinnacle's
  actual 1X2 is **~1.1 percentage points**, with the largest gap on the draw
  (1.6pp). This is well within Pinnacle's two-way margin width (~2-3%) and
  reflects exactly the information loss expected from collapsing AH + total →
  Skellam (which loses any score correlation that 1X2 captures explicitly).
- The **Brier and log-loss are essentially equal** to Pinnacle's (model 0.583
  vs book 0.583). On predictive accuracy our derived 1X2 is statistically
  indistinguishable from the source 1X2 quote at this sample size. This is
  the cleanest possible validation that the conversion is sound.
- Power and proportional de-vig produce essentially the same result, as
  expected on Pinnacle's narrow two-way books.

## 6. Recommended next steps

1. **Use Pinnacle quotes from a live odds API** as the input. Make sure the AH
   line we pull is the *primary* (most-traded) Pinnacle AH line, since the
   model assumes a high-volume sharp quote.
2. **Add the 1X2 quote as a third constraint** when available. With three
   constraints (total + AH supremacy + draw probability) we have a degree of
   freedom for a Dixon-Coles τ correction; this would let us model the slight
   draw-mass excess that the Skellam under-predicts (visible above as the
   1.6pp draw gap).
3. **Margin diagnostics on 北单**. Apply the same converter to historical 北单
   results (where we observe FT score and the 北单 line). The Brier of the
   *model probabilities* vs the *actual 3/1/0 outcome at 北单's line* will
   tell us how good the AH market is for predicting 北单 outcomes — and hence
   the size of any pricing edge.
4. **EV strategy layer**. Once we trust p3/p1/p0 from this module, the betting
   layer compares them against 北单's published payouts (which include the
   ~18% house take on 让球胜平负 in the Chinese welfare-lottery format) to
   compute expected value per unit stake. Only positive-EV bets are taken,
   subject to Kelly sizing.
5. **Robustness against quarter-line ambiguity**. Some data feeds round
   quarter lines to halves and re-quote — verify on Pinnacle's raw API that
   `AHh` matches the actual line tradable.
6. **Optional fallback**. If at some point the AH market is unavailable, we
   can derive (λ_h, λ_a) from 1X2 + total alone (Pinnacle's own published
   trick); this requires a 2-D grid solver but is closed-loop on the same
   Skellam framework.

## 7. References

- Karlis, D. & Ntzoufras, I. (2009). *Bayesian modelling of football outcomes:
  using the Skellam's distribution for the goal difference.* IMA Journal of
  Management Mathematics.
- Dixon, M. & Coles, S. (1997). *Modelling association football scores and
  inefficiencies in the football betting market.* J. Royal Statist. Soc. C.
- Buchdahl, J. — football-data.co.uk; *Squares & Sharps*; X/@12Xpert post on
  equal-margin vs power de-vig (Dec 2023).
- Pinnacle Betting Resources — *1X2 to Handicap odds conversion*,
  *How good are Pinnacle's Asian Handicap markets*.
- Whelan, K. & Spillane, A. (2024). *Returns on Complex Bets: Evidence From
  Asian Handicap Betting on Soccer.* Review of Behavioral Finance.
- Kuypers, T. (2000). *Information and efficiency: an empirical study of a
  fixed-odds betting market.* Applied Economics.
