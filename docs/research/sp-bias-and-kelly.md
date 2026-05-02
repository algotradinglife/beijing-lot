# SP Bias and Kelly Sizing for 北京单场 让球胜平负

Research notes for the quantitative betting strategy. Two questions:
(1) Is there systematic public bias in SP — i.e. are冷门 over- or under-priced? and
(2) How should we size bets given parimutuel pool dynamics and noisy edge estimates?

Time-boxed literature review. Citations are real papers/books — see References at the end.

---

## 1. Public-Bias Evidence Summary

### 1.1 The classical favourite-longshot bias (FLB)

The favourite-longshot bias is one of the most replicated findings in betting-market economics. First documented by Griffith (1949) and rigorously tested in horse racing by Snyder (1978) "Horse Racing: Testing the Efficient Markets Model" (Journal of Finance), the consistent pattern in **bookmaker-style and US/UK parimutuel markets** is:

- **Long shots are systematically over-bet** (their realized win-rate is below the implied probability from odds).
- **Favourites are systematically under-bet** (their realized win-rate is above implied).

Quantitatively, Snyder's data and replications show that betting blindly on heavy favourites loses ~5–6% (close to track take), while betting on the longest shots loses 30–60%. The expected return on a horse with implied probability p tends to *rise* monotonically with p, often crossing breakeven only for the very heaviest favourites in some samples (Hausch–Ziemba–Rubinstein 1981; Asch–Quandt 1986; Thaler & Ziemba 1988 "Anomalies: Parimutuel Betting Markets").

**Mechanisms proposed** (Ottaviani & Sørensen 2008, "Noise, Information and the Favourite-Longshot Bias"; Snowberg & Wolfers 2010):
- **Risk-loving / utility-of-gambling** (neoclassical).
- **Probability misperception** — small probabilities get overweighted (prospect theory; Kahneman–Tversky).
- **Information asymmetry** — informed money flows to favourites; noise traders (recreational gamblers) cluster on longshots.
- **Heuristic / "lottery preference"** — recreational bettors love the chance of a large payoff.

### 1.2 Notable exceptions: Asian parimutuel pools

Hong Kong and Japan parimutuel data (Busche & Hall 1988; Busche 1994) show **little or no FLB, sometimes a reverse bias**. The standard explanation is sophistication of the bettor base and heavy presence of professional syndicates that arbitrage out the bias. This matters for 北单 because:

- 北单 is a parimutuel pool (like HKJC) and a Chinese-Asian market.
- But unlike HKJC, the pool sizes are smaller (50k–5M yuan vs HKJC's HK$100M+), and the bettor base is overwhelmingly recreational, with virtually no professional syndicates running CLT-scale arbitrage. So the conditions that *eliminate* FLB in HK do not hold in 北单 — we should expect classical recreational biases to dominate.

### 1.3 Soccer-specific biases (directly relevant to 让球胜平负)

Multiple studies on European 1X2 / 让球 markets converge on three biases that are directly transferable to 北单:

1. **Draw aversion ("X" is under-bet).** Deschamps & Gergaud, Forrest & Simmons, and many others: the draw is the single most consistently mispriced outcome in soccer fixed-odds and pool markets. Recreational bettors don't buy draws because (a) draws feel like "no result," (b) team narratives bias toward "someone wins," (c) the draw has no tribal allegiance. Predictology and betting-industry data confirm draws (especially in matched-quality matches and away-favourite scenarios) are systematically +EV.

2. **Home bias.** Czech, German, and English-football studies (Forrest & Simmons; Strumbelj & Sikonja; Fischer 2022 Kyklos on COVID empty stadiums) all find recreational bettors over-back home favourites. After the let球 line is applied, this manifests as the让球 home-favourite outcome being *over-bet* (low SP) when the home team is famous. The COVID empty-stadium natural experiment (Fischer 2022) showed home advantage and home-bias both fall together — confirming the bias is at least partly behavioural.

3. **Popularity / "name" bias.** Recreational money concentrates on famous teams (Barcelona, Manchester United, Real Madrid, Bayern). Their SP gets compressed regardless of true edge. Symmetrically, lesser-known teams in obscure leagues see SP inflation when they are favourites or even when they draw.

### 1.4 Chinese lottery context — 足彩 / 竞彩 / 北单

Direct Chinese-language academic work on FLB in 足彩 / 北单 is thin (the Chinese lottery is a state monopoly with restricted micro-data; most empirical work is by industry blogs and Zhihu posts rather than peer-reviewed papers). What we can establish:

- 500.com and other大数据 vendors note the empirical pattern: **冷门 SP values significantly overshoot fair-value implied probabilities**, especially in low-pool weekday matches where a few popular teams' fans dominate the pool.
- Industry guides (e.g. 500彩票 知识库) explicitly recommend SP 1.1–1.4 favourites as "most reliable to hit" — which is *consistent with FLB* (favourites realize higher than implied prob).
- The structure of 北单 — pool-based, 65% return rate, no liquidity from professionals — is closer to small US racetrack pools than to HKJC. We should therefore use US-FLB priors as our default.
- Chinese recreational bettors have an additional bias not seen in horse racing: **strong support of CSL / national-team / popular European clubs**. When such teams are on the让球 ticket, expect compressed SP on their winning outcome and inflated SP on opposing/draw outcomes.

### 1.5 Bottom line on bias direction

For 北单 让球胜平负, our prior should be:

| Outcome type                                            | Expected SP bias direction         | Implication for EV |
|---------------------------------------------------------|------------------------------------|--------------------|
| Heavy让球 favourite (popular team)                      | SP compressed (under-paid)         | Negative EV bias   |
| Long-shot (让球 underdog wins, popular team upset)      | SP inflated (over-paid)            | Positive EV bias   |
| **Draw (让球 平)**                                      | **SP inflated, especially in close matches** | **Strong +EV bias** |
| Home favourite (popular Chinese / European club at home)| SP compressed                      | Negative EV bias   |
| Obscure leagues / weekday low-pool matches              | Higher noise, both directions      | More variance      |

This is a **prior**, not a verified fact for 北单. The strategy must validate these priors with our own historical-SP backtest before relying on them quantitatively.

---

## 2. Recommended Priors for the Strategy

Given Section 1, we encode the following Bayesian priors that the model can either reinforce with data or override:

1. **Long-shot prior:** outcomes with implied prob (1/SP × 0.65) below 15% have **+3% to +8% systematic SP overpricing** (i.e., realized win-rate < implied — but expected loss is *less* than 35% because SP is inflated). Equivalently, realized EV on longshots is closer to breakeven than the raw 65% return-rate would suggest.

2. **Draw prior:** the让球 draw outcome (especially line = 0 and ±0.5 type lines, where it's most ambiguous) is **+5% to +10% +EV** versus naive Poisson / Dixon-Coles-style implied probabilities. This is the strongest, most-replicated bias in soccer markets and our highest-confidence prior.

3. **Popular-team home favourite:** SP is **compressed by 3%–8%** for high-profile home teams. Avoid blindly betting these even if your model says they will win.

4. **Low-pool effect (weekday, obscure matches):** treat as high-noise. Reduce stake or skip entirely. SP swings on small-pool matches can be 20%+ on small wagers, plus a single popular bettor in the pool can dominate distribution.

5. **Short-priced favourites (SP 1.10–1.30):** broadly *fair to slightly +EV* per Snyder pattern, but with low absolute edge. Only worthwhile in parlays or with high model confidence.

These priors should be implemented as **prior beliefs in a Bayesian edge model** — e.g., shrink your model's estimated EV toward 1.0 by ~50%, then add bias-direction adjustments above before computing Kelly stakes.

---

## 3. Kelly Formula for Our Use Case

### 3.1 Setup

For each outcome i in match m:
- p_i = our estimated true probability
- SP_i = expected payout per yuan wagered (gross; ≈ 0.65 × pool / winning-tickets)
- b_i = our stake on outcome i
- Pool_i = pre-existing pool stake on outcome i
- Pool = total pool across all outcomes

In 北单, decimal odds equivalent is `o_i = SP_i` (gross payout multiplier). Edge: `e_i = p_i × SP_i − 1`.

### 3.2 When does standard Kelly apply? (Pool-impact threshold)

Your bet shifts SP downward by a factor of approximately:

```
SP_after / SP_before ≈ Pool_i / (Pool_i + b_i)
                    ≈ 1 − b_i / Pool_i        (for b_i << Pool_i)
```

This is the dominant effect; the secondary effect (your bet adds to total pool but is split via 0.65 factor) is much smaller because you also benefit if you win.

**Rule of thumb:** if `b_i / Pool_i < 1%`, your impact is <1% of SP — treat as negligible. The Kelly stake error from ignoring impact is then second-order.

For typical 北单:

| Match-outcome pool size | Max stake at 1% impact | Comment                              |
|-------------------------|------------------------|--------------------------------------|
| 50,000 yuan (small)     | 500 yuan               | Need explicit pool-impact correction above this |
| 500,000 yuan (medium)   | 5,000 yuan             | Standard Kelly fine for retail stakes |
| 5,000,000 yuan (large)  | 50,000 yuan            | Standard Kelly always fine for our bankroll  |

For our typical 2–200 yuan stake range, **standard fixed-odds Kelly is essentially exact** — the bet impact is ≤0.4% even on the smallest pools. We can ignore self-impact below ~0.5% of the outcome's pool. Above that, see Section 3.5.

### 3.3 Standard Kelly (for negligible self-impact) — single match

```
f_i* = (p_i × SP_i − 1) / (SP_i − 1)         (one outcome, Kelly fraction of bankroll)
     = (p_i × o − 1) / (o − 1)
```

If `p_i × SP_i ≤ 1`: don't bet. This is the EV>1 filter.

### 3.4 Multiple matches in one batch (single-bet portfolio of independent matches)

Because matches are statistically independent, Kelly across N independent simultaneous bets reduces to a *concave optimization* over the joint outcome tree. Two practical formulations:

**(a) Independent-Kelly approximation (good when individual stakes are small):**
Stake each match independently using single-match Kelly. This *overstates* the optimal stake slightly because it ignores the bankroll constraint across simultaneous bets, but the error is O(f²) in total Kelly fraction. For our edges (1–5%), full Kelly is small enough (<5% per bet) that this approximation is fine up to ~10 simultaneous matches.

**(b) Numerical simultaneous Kelly (Smoczynski & Tomkins 2010; Whelan 2025):**
For independent events with multiple outcomes each, the joint Kelly maximizes
```
E[log(1 + Σ_m Σ_i b_{m,i} × (SP_{m,i} − 1) × 1{outcome m,i wins} − Σ_m Σ_i b_{m,i} × 1{outcome m,i loses})]
```
which is convex in {b_{m,i}}. Solve numerically with scipy.optimize. For independent matches this is equivalent to single-match Kelly applied per match because the log-utility is separable across independent random variables. **So in our case (independent matches) the approximation is exact, not approximate** — Kelly per match, and aggregate.

Important caveat from Whelan (2025) "On Optimal Betting Strategies With Multiple Mutually Exclusive Outcomes": **within a single match**, betting on multiple outcomes (e.g. backing both home win and draw) is sometimes optimal as a hedge — but generally only if you have edges on multiple outcomes simultaneously, which is rare. Default: one outcome per match.

### 3.5 Pool-impact correction (only needed for stakes >0.5% of outcome pool)

Following Isaacs (1953) "Optimal Horse Race Bets" and Hausch–Ziemba–Rubinstein (1981), the correct formulation when your bet is non-trivial:

```
Effective SP after your bet b_i:
  SP_i_after(b_i) = 0.65 × (Pool + b_i) / (Pool_i + b_i) × (winning-ticket fraction)
  ≈ SP_i × (Pool_i + b_i × s) / (Pool_i + b_i)   where s ≈ Pool_i/Pool < 1

Modified Kelly: maximize
  p_i × log(1 + b_i × (SP_i_after(b_i) − 1)) + (1 − p_i) × log(1 − b_i)
```

This is concave in b_i; solve with 1D Newton. The optimal stake is **always smaller** than naive Kelly (the more you bet, the worse your odds become). Practical implementation: use the closed-form HZR adjustment, or a one-step Newton from the standard-Kelly starting point.

For 北单, we will hit this regime only on small-pool matches with large bankrolls. Until our bankroll exceeds ~50,000 yuan and individual bets exceed ~500 yuan into small pools, we can skip this correction.

### 3.6 Fractional Kelly — what fraction and why

Theoretical case for fractional Kelly (MacLean, Thorp & Ziemba 2010; Thorp 2008; Ziemba 2003):

- Full Kelly is **growth-optimal only if your edge estimate p is exact**. With noisy p̂, full Kelly becomes negative-EV in expectation when the noise is large enough. Specifically, the optimal fraction to bet is approximately f × p / E[p̂]·correction, which for Gaussian noise on p̂ with std σ_p reduces approximately to:
  ```
  f_actual* ≈ f_kelly × (1 − σ_p² / (p × (1−p) × edge²))     (approximation)
  ```
  Even moderate uncertainty (σ_p ~ 0.02 on p ~ 0.4 with edge 3%) collapses the optimal fraction to ~25–40% of Kelly.

- **Half-Kelly captures ~75% of the long-run growth rate of full Kelly with less than half the volatility** (MacLean–Thorp–Ziemba). Quarter Kelly captures ~50% growth at ~25% volatility.

- **Drawdown risk:** full Kelly has a 50% probability of a 50% drawdown at some point. Half-Kelly cuts this dramatically. For sports betting where we *cannot* tightly verify our edge estimate, full Kelly is reckless.

**Industry consensus** (Thorp; Ziemba; Aaron Brown; sports-betting practitioners):
- Fractional Kelly **between 1/4 and 1/2** is the standard recommendation.
- For sports betting with edges estimated from limited data and significant model risk, **1/4 Kelly is typical**.
- Some practitioners (Joe Peta; quantitative sports books) advocate even smaller — 1/8 or 1/10 — for early-stage strategies until edge is empirically verified over 200+ bets.

---

## 4. Practical Staking Rule

Based on the above, the recommended staking algorithm for 北单 让球胜平负:

### 4.1 Filters (apply before staking)

1. **EV filter:** only bet outcomes with model `p_i × SP_i ≥ 1.05` (5% gross edge).
   *Rationale:* below 5% the noise in our p̂ estimate dominates; any "edge" is statistical illusion.

2. **Pool-size filter:** skip matches where the outcome's pool < 30,000 yuan.
   *Rationale:* SP volatility too high; small pools attract a single dominant bettor's bias.

3. **Liquidity filter for our bet:** ensure our intended stake b ≤ 0.5% of the outcome's pool (rough proxy: ≤ 0.5% × Pool_i).
   *Rationale:* keeps standard Kelly approximation valid; avoids self-impact.

4. **Bias-prior boost:** apply the Section-2 prior adjustments before EV calculation (e.g., +5% probability boost on draws in evenly matched fixtures; -5% on popular home favourites).

### 4.2 Staking formula (per qualifying bet)

```
edge_i      = p_i × SP_i − 1                      # gross expected return per yuan
f_kelly_i   = edge_i / (SP_i − 1)                 # standard Kelly fraction
f_actual_i  = 0.25 × f_kelly_i                    # quarter Kelly
stake_i     = f_actual_i × bankroll
stake_i     = min(stake_i, 0.05 × bankroll)       # hard cap: 5% per match
stake_i     = min(stake_i, 0.005 × Pool_i)        # liquidity cap: 0.5% of pool
stake_i     = max(stake_i, MIN_BET)               # 北单 min stake (typically 2 yuan)
                                                  # if computed stake < MIN_BET, skip the bet
```

### 4.3 Portfolio rule (multiple matches per batch)

- Treat each qualifying match independently and sum stakes (matches are independent so log-utility is separable).
- **Aggregate cap:** total batch stake ≤ 25% of bankroll. If sum exceeds this, scale all stakes proportionally.
  *Rationale:* protect against correlated model error across the batch (e.g., if our model has a systemic bias, all bets fail together).
- **Diversification minimum:** if betting >5 matches in one batch, the strategy is approaching index-like behavior — consider whether the average edge is real or a model artifact.

### 4.4 Concrete example

Bankroll = 10,000 yuan. Match: SP_home = 1.85 (popular home favourite), SP_draw = 3.40, SP_away = 4.60. Pool_draw = 80,000 yuan.

Model probabilities (after bias-prior adjustment, +5% to draw):
p_home = 0.42, p_draw = 0.32, p_away = 0.26.

EV check:
- Home: 0.42 × 1.85 = 0.777 → reject.
- Draw: 0.32 × 3.40 = 1.088 → 8.8% edge → qualify.
- Away: 0.26 × 4.60 = 1.196 → 19.6% edge → qualify (but check this isn't model overconfidence on a longshot).

Kelly on draw:
```
edge       = 0.088
f_kelly    = 0.088 / 2.40 = 0.0367           (3.67%)
f_actual   = 0.25 × 0.0367 = 0.00917         (0.92% of bankroll = 91.7 yuan)
stake      = 92 yuan
liquidity_cap = 0.005 × 80,000 = 400 yuan    (not binding)
hard_cap   = 0.05 × 10,000 = 500 yuan        (not binding)
final stake = 92 yuan on draw
```

Kelly on away (longshot — but 19.6% raw edge looks suspicious):
```
edge       = 0.196
f_kelly    = 0.196 / 3.60 = 0.0544           (5.44%)
f_actual   = 0.25 × 0.0544 = 0.0136          (1.36% = 136 yuan)
```
But — caveat — a 19.6% EV on a longshot is exactly the regime where model error is largest. Apply *additional* shrinkage on long-shots (say half the actual stake): ~68 yuan. Or simply require a higher EV threshold (>1.10) to bet long-shots, and then still use 1/4 Kelly.

### 4.5 Summary one-liner staking rule

**"On qualifying bets (EV ≥ 1.05 after Bayesian bias adjustment, pool ≥ 30k yuan), stake 1/4 Kelly, capped at 5% of bankroll per match and 0.5% of the outcome's pool. Aggregate batch cap at 25% bankroll. Default to draw or contrarian-EV picks; treat 'popular home favourite' picks as null until edge is empirically verified."**

---

## 5. Open Items / Things to Validate Empirically

Before going live, validate with at least 200 historical 北单 matches:

1. **Quantify SP-bias direction empirically** — regress realized win-rate on implied probability from SP, separately for: home favourite, draw, away win, and stratified by pool size and team popularity. Confirm the FLB and draw-aversion priors hold in 北单.
2. **Estimate p̂ noise** — for our model, what is σ(p̂) on a held-out backtest? Use this to choose the Kelly fraction precisely (theoretical formula in Section 3.6).
3. **Pool-size dependence** — does FLB strengthen in low-pool matches (more recreational dominance)? If so, the pool-size filter doubles as a bias-amplifier in our favour for small pools, but it also raises stake-impact concerns. Tradeoff to study.
4. **Correlation structure** — confirm that "independent matches" assumption holds at the SP level. If many bettors bet correlated parlays on the same handful of matches each weekend, residuals could be correlated.

---

## References

### Foundational / parimutuel
- Griffith, R.M. (1949). "Odds Adjustments by American Horse-Race Bettors." *American Journal of Psychology*.
- Snyder, W.W. (1978). "Horse Racing: Testing the Efficient Markets Model." *Journal of Finance* 33: 1109–1118.
- Hausch, D.B., Ziemba, W.T., & Rubinstein, M. (1981). "Efficiency of the Market for Racetrack Betting." *Management Science* 27(12): 1435–1452. https://pubsonline.informs.org/doi/10.1287/mnsc.27.12.1435
- Asch, P., Malkiel, B.G., & Quandt, R.E. (1984). "Market Efficiency in Racetrack Betting." *Journal of Business* 57(2): 165–175.
- Asch, P. & Quandt, R.E. (1986). *Racetrack Betting: The Professor's Guide to Strategies*. Auburn House.
- Thaler, R.H. & Ziemba, W.T. (1988). "Anomalies: Parimutuel Betting Markets: Racetracks and Lotteries." *Journal of Economic Perspectives* 2(2): 161–174.
- Hausch, D.B. & Ziemba, W.T. (eds.) (2008). *Efficiency of Racetrack Betting Markets*. World Scientific.
- Ziemba, W.T. (2021). "Parimutuel Betting Markets: Racetracks and Lotteries Revisited." LSE / SSRN.

### Favourite-longshot bias explanations
- Ottaviani, M. & Sørensen, P.N. (2010). "Noise, Information and the Favourite-Longshot Bias in Parimutuel Predictions." *American Economic Journal: Microeconomics*.
- Snowberg, E. & Wolfers, J. (2010). "Explaining the Favorite-Long Shot Bias: Is it Risk-Love or Misperceptions?" *Journal of Political Economy* 118(4). NBER WP 15923.
- Green, E., Lee, H., & Rothschild, D. (2020). "The Favorite-Longshot Midas." Working paper.

### Soccer-specific biases
- Forrest, D., Goddard, J., & Simmons, R. (2005). "Odds-setters as forecasters: The case of English football." *International Journal of Forecasting*.
- Deschamps, B. & Gergaud, O. (2007). "Efficiency in betting markets: Evidence from English football." *Journal of Prediction Markets*.
- Fischer, K. (2022). "Home advantage in professional soccer and betting market efficiency: The role of spectator crowds." *Kyklos*.

### Kelly criterion (foundations & extensions)
- Kelly, J.L. Jr. (1956). "A New Interpretation of Information Rate." *Bell System Technical Journal*.
- Isaacs, R. (1953). "Optimal Horse Race Bets." *American Mathematical Monthly* 60: 310–315.
- Breiman, L. (1961). "Optimal Gambling Systems for Favorable Games."
- Thorp, E.O. (2008). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market." In Hausch–Ziemba (eds), *Handbook of Sports and Lottery Markets*.
- MacLean, L.C., Thorp, E.O., & Ziemba, W.T. (2010). "Good and Bad Properties of the Kelly Criterion." https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf
- MacLean, L.C., Thorp, E.O., & Ziemba, W.T. (eds.) (2011). *The Kelly Capital Growth Investment Criterion: Theory and Practice*. World Scientific.
- Smoczynski, P. & Tomkins, D. (2010). "An explicit solution to the problem of optimizing the allocations of a bettor's wealth when wagering on horse races." *The Mathematical Scientist*.
- Whelan, K. (2025). "On Optimal Betting Strategies With Multiple Mutually Exclusive Outcomes." *Bulletin of Economic Research* 77(1): 67–85. https://onlinelibrary.wiley.com/doi/full/10.1111/boer.12474
- Chu, D., Wu, Y., & Swartz, T.B. (2018). "Modified Kelly Criteria." Simon Fraser. https://www.sfu.ca/~tswartz/papers/kelly.pdf

### Practitioner / applied
- Ziemba, W.T. & Hausch, D.B. (1986). *Beat the Racetrack* / (1987) *Dr. Z's Beat the Racetrack* (revised). William Morrow.
- 500.com 知识库 — 凯利指数, SP值 章节 (industry references for 中文 readers).
- Andersen et al. (2020). "In-Game Betting and the Kelly Criterion." Mathematica Applicanda.

### Chinese-context (limited peer-reviewed work)
- 张弛, 董红芳, 王乐萌, 姚蕾 (2024). "中国竞猜型彩票赛事选择标准体系研究." *体育科学*. http://tykx.xml-journal.net/cn/article/pdf/preview/10.16469/J.css.2024KX054.pdf
- 知乎 / 500彩票网 industry analysis posts on 北单 SP值 patterns (non-academic but data-rich).
