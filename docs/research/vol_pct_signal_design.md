# Pool-Volume Confidence Signal Design

**Status**: Track A backtested (redundant with niche rules). Track B closed — see §11.  
**Date**: 2026-05-31  
**Data window**: 2026-05-02 to 2026-05-30 (1,579 settled matches, 698,838 snapshots)

---

## 1. Problem Statement

The niche system qualifies legs using a static `p_hat_train` (trained hit probability) vs SP-implied probability.
It does not currently account for *how confident the market is* in those SP values.

A leg sitting at SP 4.0 because the pool is thin (few bettors) is structurally weaker than one at SP 4.0 on a deep pool.
In a thin pool, late money can swing SP by ±20%; in a deep pool the same amount moves it <1%.

**Hypothesis**: legs where the sharp-money signal (EU implied probability) diverges from the crowd signal (pool-implied probability from SP) in the *same direction as our p_hat* should have higher realised hit rates after filtering.

---

## 2. Data Reality

| Field | Availability | Notes |
|---|---|---|
| `eu_h / eu_d / eu_a` | 99% of snapshots | European pre-match odds from scraper |
| `sp_3 / sp_1 / sp_0` | 68–98% of snapshots | Parimutuel SP (best at close) |
| `vol_pct_3/1/0` | **0%** — always NULL | Schema exists; scraper cannot populate (see §11) |
| `pool_total` | **0%** — always NULL | No accessible free source (see §11) |

This means:
- **Track A (EU-vs-SP divergence)**: implementable immediately — backtested 2026-05-31, found redundant
- **Track B (raw vol_pct / pool_total)**: **closed** — see §11 for root-cause analysis

Both tracks are designed below. See §11 for the definitive conclusion.

---

## 3. Track A: EU-vs-SP Divergence Signal

### 3.1 Signal Construction

For each match option (home=3, draw=1, away=0) and the last snapshot before kickoff:

```python
# De-vigged EU probability (Shin / margin-removed)
eu_raw  = [1/eu_h, 1/eu_d, 1/eu_a]   # raw implied probs
overround = sum(../../doc/eu_raw)
eu_p3 = eu_raw[0] / overround          # normalised: home
eu_p1 = eu_raw[1] / overround          # draw
eu_p0 = eu_raw[2] / overround          # away

# Pool-implied probability from SP (parimutuel model: SP = 0.65 / vol_pct)
# → vol_pct = 0.65 / SP
pool_p3 = 0.65 / sp_3                  # home pool fraction
pool_p1 = 0.65 / sp_1                  # draw
pool_p0 = 0.65 / sp_0                  # away

# Divergence: positive means sharps favour outcome more than crowd does
div3 = eu_p3 - pool_p3
div1 = eu_p1 - pool_p1
div0 = eu_p0 - pool_p0
```

The `div` fields are the signal. From preliminary analysis on 2026-05 data:
- `div3` mean ≈ +0.20, std ≈ 0.19 — EU systematically prices home lower than crowd (expected: crowd overweights home)
- Raw correlation with home win outcome: −0.04 (weak, reflects measurement noise + needs niche filter)

### 3.2 Temporal Snapshot Selection

Use the **last snapshot ≤ 2h before kickoff** for each match. Rationale:
- SP stabilises after the 2h mark (median drift <2% per SP drift analysis)
- EU odds often locked by bookmakers ~2h before kickoff
- Beyond 2h: SP still moving, divergence signal noisy

```python
def last_snapshot_before(match_id, kickoff_ts, conn, window_hours=2.0):
    cutoff = kickoff_ts - timedelta(../../doc/hours=window_hours)
    # SELECT * FROM snapshots WHERE match_id=? AND snapshot_ts <= cutoff
    # ORDER BY snapshot_ts DESC LIMIT 1
```

### 3.3 Signal Variants

| Variant | Formula | Interpretation |
|---|---|---|
| `div_raw` | `eu_p − pool_p` | Raw divergence |
| `div_z` | `(div_raw − μ) / σ` per outcome code | Z-score (normalised across all matches that week) |
| `eu_edge` | `eu_p − p_hat_train` | EU price vs our model (independent of crowd) |
| `pool_edge` | `p_hat_train − pool_p` | Our model vs crowd (= classic niche edge) |

Priority for backtest: `div_raw` first (most interpretable), then `div_z` if variance is too high.

---

## 4. Track B: Direct vol_pct Signal

**Prerequisite**: fix the live collector to populate `vol_pct_3/1/0` and `pool_total`.

### 4.1 Scraper Fix Required

The `snapshots` table columns exist but the scraper (`src/live_collector/` — exact module TBD) never writes to them. The fix should:

1. Parse the pool distribution page from the 彩票中心 data source
2. Write `vol_pct_3 / vol_pct_1 / vol_pct_0` (each = fraction of pool on that outcome, summing to ~1)
3. Write `pool_total` (total yuan in pool at snapshot time)

Once populated, the signal is simpler than Track A:

```python
# Direct pool confidence signal
pool_p3 = vol_pct_3  # = 0.65 / sp_3 (equivalent but more direct)
pool_total_signal = pool_total  # deeper pool = more stable SP
```

### 4.2 Additional Signal: Pool Depth

```python
# Normalised pool depth (relative to trailing 8-week median)
pool_depth_z = (pool_total - rolling_median) / rolling_std
```

High `pool_depth_z` → SP is more price-discovered → signal is more reliable.

This cannot be derived from EU odds alone — requires actual pool_total data.

---

## 5. Stacking with N=4 / N=5 Strategies

Two integration modes:

### 5.1 Hard Filter (Additional Niche Gate)

Add `div_threshold` as a new niche parameter. A candidate passes only if:

```python
div = eu_p_for_selection - pool_p_for_selection
leg_passes = div >= div_threshold   # e.g., div_threshold = 0.02
```

**Pros**: clean, interpretable, no Kelly modification  
**Cons**: may filter too aggressively if div signal is noisy; reduces N-leg candidate count

Implementation: add `div_threshold: float = 0.0` to `NicheConfig` and evaluate in `qualify_candidates()`.

### 5.2 Soft Score (Kelly Modifier)

Scale Kelly fraction up/down based on signal strength:

```python
kelly_effective = kelly_base * (1 + alpha * div_z)  # alpha = 0.2–0.5
kelly_effective = min(kelly_effective, kelly_base * 1.5)  # cap at 1.5×
```

**Pros**: continuous, doesn't hard-filter legs, allows "confidence weighting"  
**Cons**: more complexity, harder to backtest cleanly, multiplies implementation risk

**Recommendation**: start with Hard Filter (../../doc/5.1) — cleaner signal, testable with existing backtest infrastructure.

### 5.3 N-Leg Interaction

For N=4/5, the signal compounds:
- If `div > 0` for all N legs → joint expectation is reinforced
- Require minimum `div_raw > 0` for all N legs (equivalent to: sharps all agree with crowd on direction at minimum)
- Bonus: require `sum(../../doc/div) > N × div_threshold` for the full combo to pass

---

## 6. Backtest Parameters

| Parameter | Value | Rationale |
|---|---|---|
| Data window | All settled issues 2024–2026 (CSV source) | Matches `n_sweep_backtest.py` methodology |
| Snapshot timing | Last snapshot ≤ 2h before kickoff | SP stability window; EU odds availability |
| Signal | `div_raw = eu_p − 0.65/sp` for selected outcome | Track A; no scraper change needed |
| Filter threshold sweep | div_threshold ∈ {−0.05, 0, 0.02, 0.05, 0.10} | Negative = no filter; positive = sharps agree |
| Strategy base | S4 (N=4, Kelly=1/8) and S11 (N=4+5 blend) | Current production strategies |
| Metric priority | Calmar → Sharpe → ROI (consistent with strategy selection) | Per S5 "Calmar 王" philosophy |
| Control | Run without signal filter; compare hit rate per threshold | δ(../../doc/hit_rate) is the cleanest outcome measure |

---

## 7. Expected Outcome

If the signal has real predictive power:
- `div_raw > 0.02` subgroup should show higher realised hit rate vs `div_raw ≤ 0` subgroup
- Win rate should improve even if N-filtered candidate count drops
- Sharpe and Calmar should improve (fewer low-confidence combos = lower stake variance)

If signal has no power:
- Hit rate will be flat across div_threshold values
- Total ROI may degrade (fewer combos = less stake deployed = same EV but smaller absolute profit)
- Conclusion: drop the signal, rely on niche rules alone

---

## 8. Implementation Roadmap

**Phase 1 — Track A validation (1–2 hours)**
1. Write `scripts/div_signal_backtest.py`: load CSV + EU from `beidan_live.db`, compute `div_raw` at 2h-before-kickoff snapshot, sweep `div_threshold`, report metrics
2. Compare vs baseline (no filter) on Calmar / win rate / n_combos

**Phase 2 — Integration if Phase 1 positive**
1. Add `div_threshold: float = 0.0` to `NicheConfig`
2. Pass EU odds into `LiveSnapshot` (check if already present in `load_open_matches()`)
3. Compute `div_raw` in `qualify_candidates()` and apply gate
4. Add `div_threshold` to webui strategy_params form

**Phase 3 — Track B (scraper fix)**
1. Identify pool distribution endpoint in live_collector scraper
2. Populate `vol_pct_3/1/0` and `pool_total` fields
3. Re-run backtest using `pool_total` as pool-depth weight

---

## 9. Open Questions

1. **EU odds timing**: are `eu_h/eu_d/eu_a` in the DB the pre-match closing line, or scraped at variable intervals? (Need to verify `snapshot_ts` distribution for eu-populated rows)
2. **EU coverage**: 99% overall, but does it drop for specific leagues or small matches? Low-coverage legs would need fallback (skip signal gate or use pool_p directly)
3. **Signal stationarity**: does the EU-vs-SP divergence structure change across seasons? (Early 2024 vs 2026 data might have different crowd behavior)
4. **vol_pct scraper source**: which endpoint/page does the live_collector use? The pool distribution might already be available if we scrape a different URL
5. **Hard filter vs soft score interaction with diversity_lambda**: filtering reduces candidate count, which may cause diversity_lambda to pick sub-optimal combos (fewer choices = less diversity room)

---

## 10. Appendix: Preliminary Signal Statistics (2026-05 data only)

From 692k snapshots with EU odds populated:

| Metric | home (../../doc/div3) | draw (../../doc/div1) | away (../../doc/div0) |
|---|---|---|---|
| Mean | +0.200 | — | — |
| Std | 0.188 | — | — |
| Raw corr w/ outcome | −0.039 | — | — |

Note: raw correlation is expected to be weak because it pools all matches, not just niche-qualified legs. The signal's predictive power must be evaluated *conditional on a leg being in a niche rule's SP range*, which is the Phase 1 backtest's job.

---

## 11. Post-Investigation Conclusions (../../doc/2026-05-31)

### Track A: EU-vs-SP divergence — CLOSED (../../doc/redundant)

Phase 1 backtest run on 9 issues (../../doc/2026-05). Key finding:

- 69% of niche-qualified candidates already have `div_raw > 0.10` — niche rules implicitly select high-divergence legs (p_hat > 0.65/SP is a div threshold by another name)
- Adding a hard filter at any threshold showed inconsistent per-issue effects (some issues improve, others degrade)
- With only 9 data points, no statistically meaningful conclusion possible
- **Decision**: Do not ship the div_raw hard filter. Signal is circular given niche rule construction.

### Track B: vol_pct / pool_total — CLOSED (data not obtainable)

Root cause investigation of the NULL fields:

**vol_pct_3/1/0 is mathematically redundant with SP:**

The parimutuel formula is exact: `SP = RETURN_RATE / vol_pct`, therefore `vol_pct = 0.65 / SP`. These fields would contain no independent information beyond what `sp_3/sp_1/sp_0` already holds. Populating them would just store derived values.

**The scraper is correct — 500.com requires authentication:**

The `trade.500.com/bjdc/` page serves `--` for all `<span class="tzbl">` fields to unauthenticated users, even during the active betting window. The JS handler for the "投注比例" dropdown only toggles CSS visibility (no AJAX call) — but the server-side HTML itself is "--" without a session cookie. Confirmed by fetching the live page (issue 26061, 132 active rows, all tzbl = "--").

**pool_total has no accessible free source:**

| Source tried | Result |
|---|---|
| `trade.500.com/bjdc/` | vol_pct "--" without auth; no pool_total field |
| `www.500.com/static/public/bjdc/xml/sp/just_{issue}_{play_id}.xml` | 404 |
| `zx.500.com/zqdc/kaijiang.php` (already scraped) | No pool total |
| `cp.zgzcw.com/lottery/bdplayvsforJsp.action` | No pool data |
| `lottery.gov.cn` | 403 |
| `jss.lottery.gov.cn` | DNS resolution failure |

**To obtain pool_total in future:** Would require either (../../doc/a) authenticated 500.com session scraped at betting time, or (../../doc/b) reverse-engineering the mobile app API. Neither is attempted here.

### What This Means for Strategy

The pool depth signal as originally conceived is not buildable without authentication or a new data source. The current niche+EU pipeline uses all available free data efficiently. No further action on this track unless a new data source is identified.
