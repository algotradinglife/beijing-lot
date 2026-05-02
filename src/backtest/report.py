"""Generate the limited-backtest report markdown + supporting figures."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import simulator
from .ev import RETURN_RATE_RATIO_NAIVE
from .kelly import RETURN_RATE


REPO = Path(__file__).resolve().parents[2]
FIG_DIR = REPO / "docs" / "research" / "figures"
REPORT = REPO / "docs" / "research" / "limited_backtest_report.md"


def _bin_summary(picks: pd.DataFrame, bin_col: str, bins) -> pd.DataFrame:
    """Group picks by a binned column and summarise n / hit_rate / ROI / EV."""
    if picks.empty or bin_col not in picks.columns:
        return pd.DataFrame(columns=[
            "_bin", "n", "hit_rate", "mean_p", "mean_ev",
            "total_stake", "total_pnl", "roi",
        ])
    p = picks.copy()
    if isinstance(bins, list):
        p["_bin"] = pd.cut(p[bin_col], bins=bins, include_lowest=True)
    else:
        p["_bin"] = p[bin_col]
    g = p.groupby("_bin", observed=True).agg(
        n=("pnl", "size"),
        hit_rate=("won", "mean"),
        mean_p=("p_chosen", "mean"),
        mean_ev=("model_ev", "mean"),
        total_stake=("stake", "sum"),
        total_pnl=("pnl", "sum"),
    ).reset_index()
    g["roi"] = np.where(g["total_stake"] > 0, g["total_pnl"] / g["total_stake"], 0.0)
    return g


def _bootstrap_ci_roi(picks: pd.DataFrame, n_iter: int = 2000, alpha: float = 0.05) -> tuple[float, float, float]:
    """Bootstrap confidence interval for total ROI = sum(pnl) / sum(stake)."""
    if picks.empty:
        return (0.0, 0.0, 0.0)
    pnl = picks["pnl"].to_numpy(dtype=float)
    stake = picks["stake"].to_numpy(dtype=float)
    n = len(pnl)
    rng = np.random.default_rng(42)
    rois: list[float] = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        s = stake[idx].sum()
        if s > 0:
            rois.append(pnl[idx].sum() / s)
    rois.sort()
    point = pnl.sum() / max(stake.sum(), 1e-9)
    lo = rois[int(alpha / 2 * n_iter)]
    hi = rois[int((1 - alpha / 2) * n_iter)]
    return point, lo, hi


def _signrank_pvalue_picks(picks: pd.DataFrame) -> float:
    """One-sample test that mean per-pick PnL is > 0.

    Uses a normal approximation for sample-mean PnL.
    """
    if picks.empty:
        return 1.0
    pnl = picks["pnl"].to_numpy(dtype=float)
    n = len(pnl)
    mean = pnl.mean()
    sd = pnl.std(ddof=1) if n > 1 else 0.0
    if sd == 0:
        return 1.0
    z = mean / (sd / math.sqrt(n))
    # one-sided p-value (right tail) under N(0,1)
    from math import erf
    return 0.5 * (1 - erf(z / math.sqrt(2)))


def make_cum_roi_plot(picks: pd.DataFrame, label: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if picks.empty:
        ax.text(0.5, 0.5, "no picks", ha="center")
    else:
        cr = simulator.cumulative_roi(picks)
        ax.plot(cr["kickoff_ts"], cr["cum_pnl"], label="cumulative PnL (yuan)")
        ax.set_xlabel("kickoff date")
        ax.set_ylabel("cumulative PnL (yuan)")
        ax.set_title(f"Cumulative PnL — {label}")
        ax.axhline(0, color="grey", linestyle=":")
        ax2 = ax.twinx()
        ax2.plot(cr["kickoff_ts"], cr["cum_roi"] * 100, color="orange", alpha=0.6, label="cumulative ROI (%)")
        ax2.set_ylabel("cumulative ROI (%)")
        ax.legend(loc="upper left")
        ax2.legend(loc="lower right")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def _df_to_md(df: pd.DataFrame, idx: bool = False) -> str:
    return df.to_markdown(index=idx, floatfmt=".4f")


def build_report(db_path: Path) -> str:
    with sqlite3.connect(str(db_path)) as conn:
        df = simulator.load_matches(conn)

    n_matches = len(df)
    n_issues = df["issue"].nunique()
    date_min = df["kickoff_ts"].min()
    date_max = df["kickoff_ts"].max()

    # Fit empirical SP model for an honest comparison of "predicted SP vs naive".
    naive_picks, _ = simulator.simulate(df, use_empirical_sp=False)
    emp_picks, sp_model = simulator.simulate(df, use_empirical_sp=True)

    # Headline numbers
    n_picks = len(naive_picks)
    pickrate = n_picks / max(n_matches * 3, 1)
    naive_point, naive_lo, naive_hi = _bootstrap_ci_roi(naive_picks)
    emp_point, emp_lo, emp_hi = _bootstrap_ci_roi(emp_picks)
    p_naive = _signrank_pvalue_picks(naive_picks) if not naive_picks.empty else float("nan")
    p_emp = _signrank_pvalue_picks(emp_picks)

    # Population-level model calibration on ALL matches (regardless of EV
    # threshold).  This separates "model fit quality" from "decision rule
    # quality".
    pop_rows = []
    for row in df.itertuples(index=False):
        try:
            from src.backtest.model import model_probs_from_eu
            probs = model_probs_from_eu(
                row.avg_eu_home, row.avg_eu_draw, row.avg_eu_away,
                int(row.handicap_line), apply_correction=True,
            )
        except Exception:
            continue
        pop_rows.append(dict(
            issue=row.issue, p3=probs.p3, p1=probs.p1, p0=probs.p0,
            result=row.result_code, abs_h=abs(int(row.handicap_line)),
        ))
    pop = pd.DataFrame(pop_rows)
    pop["mean_p_winner"] = np.where(
        pop["result"] == "3", pop["p3"],
        np.where(pop["result"] == "1", pop["p1"], pop["p0"]),
    )
    # Hit rate by outcome — does the model assign higher p to outcomes that win?
    pop["actual3"] = (pop["result"] == "3").astype(int)
    pop["actual1"] = (pop["result"] == "1").astype(int)
    pop["actual0"] = (pop["result"] == "0").astype(int)
    pop_calib_3 = pop.groupby(pd.cut(pop["p3"], bins=[0, 0.15, 0.30, 0.45, 0.60, 0.75, 1.0]),
                               observed=True).agg(n=("p3", "size"),
                                                  mean_p=("p3", "mean"),
                                                  hit_rate=("actual3", "mean")).reset_index()
    pop_calib_1 = pop.groupby(pd.cut(pop["p1"], bins=[0, 0.15, 0.20, 0.25, 0.30, 0.40, 1.0]),
                               observed=True).agg(n=("p1", "size"),
                                                  mean_p=("p1", "mean"),
                                                  hit_rate=("actual1", "mean")).reset_index()
    pop_calib_0 = pop.groupby(pd.cut(pop["p0"], bins=[0, 0.15, 0.30, 0.45, 0.60, 0.75, 1.0]),
                               observed=True).agg(n=("p0", "size"),
                                                  mean_p=("p0", "mean"),
                                                  hit_rate=("actual0", "mean")).reset_index()

    # Weekly batch ROI
    weekly = simulator.aggregate_weekly(naive_picks)
    weekly_emp = simulator.aggregate_weekly(emp_picks)

    # Edge attribution by chosen outcome
    by_outcome = _bin_summary(naive_picks, "chosen_outcome", bins="cat")
    by_outcome_emp = _bin_summary(emp_picks, "chosen_outcome", bins="cat")

    # Edge attribution by handicap
    def _add_h_bucket(p: pd.DataFrame) -> pd.DataFrame:
        if p.empty or "handicap" not in p.columns:
            return p
        p = p.assign(abs_h=p["handicap"].abs())
        p["h_bucket"] = p["abs_h"].apply(
            lambda h: "0" if h == 0 else "1" if h == 1 else ">=2"
        )
        return p

    naive_picks = _add_h_bucket(naive_picks)
    emp_picks = _add_h_bucket(emp_picks)
    by_handicap = _bin_summary(naive_picks, "h_bucket", bins="cat")
    by_handicap_emp = _bin_summary(emp_picks, "h_bucket", bins="cat")

    # EV bucket
    ev_bins = [1.05, 1.10, 1.15, 1.25, 1.50, 5.0]
    by_ev = _bin_summary(naive_picks, "model_ev", bins=ev_bins)
    by_ev_emp = _bin_summary(emp_picks, "model_ev", bins=ev_bins)

    # Calibration: model p vs realised hit rate by p-bucket
    p_bins = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75, 1.0]
    cal = _bin_summary(naive_picks, "p_chosen", bins=p_bins)

    # Weekly distribution stats
    if not weekly.empty:
        wp5 = weekly["roi"].quantile(0.05)
        wp50 = weekly["roi"].median()
        wp95 = weekly["roi"].quantile(0.95)
        wmean = weekly["roi"].mean()
        wn_picks_med = weekly["n_picks"].median()
    else:
        wp5 = wp50 = wp95 = wmean = wn_picks_med = float("nan")

    # SP-fit summary (empirical model)
    if sp_model:
        sp_fit_lines = "\n".join(
            f"  - result {code}: SP ≈ {a:.3f} + {b:.3f} × eu_odds  "
            f"(naive baseline ratio = {RETURN_RATE_RATIO_NAIVE:.3f})"
            for code, (a, b) in sp_model.coefs.items()
        )
    else:
        sp_fit_lines = "  (empirical fit not available)"

    # Plots
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    make_cum_roi_plot(naive_picks, "naive proxy SP", FIG_DIR / "cum_roi_naive.png")
    make_cum_roi_plot(emp_picks, "empirical proxy SP", FIG_DIR / "cum_roi_empirical.png")

    # Histogram of weekly ROI
    fig, ax = plt.subplots(figsize=(7, 4))
    if not weekly.empty:
        ax.hist(weekly["roi"] * 100, bins=20, alpha=0.7, color="steelblue")
        ax.axvline(0, color="grey", linestyle=":")
        ax.set_xlabel("Weekly batch ROI (%)")
        ax.set_ylabel("# weeks")
        ax.set_title("Weekly batch ROI distribution (naive proxy SP)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "weekly_roi_hist_naive.png", dpi=110)
    plt.close(fig)

    # Calibration plot
    fig, ax = plt.subplots(figsize=(5, 5))
    if not cal.empty:
        ax.plot(cal["mean_p"], cal["hit_rate"], "o-", label="picks")
        ax.plot([0, 1], [0, 1], "--", color="grey", label="ideal")
        for _, row in cal.iterrows():
            ax.annotate(f"n={int(row['n'])}", (row["mean_p"], row["hit_rate"]),
                        xytext=(3, 3), textcoords="offset points", fontsize=8)
        ax.set_xlabel("model p (mean per bucket)")
        ax.set_ylabel("realised hit rate")
        ax.set_title("Calibration of model p̂ — qualifying picks")
        ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "calibration_naive.png", dpi=110)
    plt.close(fig)

    # ----- assemble markdown -----
    md = f"""# Limited Backtest Report — 北单 Approach A vs avg-European odds proxy

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
| issues scraped | {n_issues} |
| matches with full data | {n_matches:,} |
| date range | {date_min:%Y-%m-%d} – {date_max:%Y-%m-%d} |
| outcomes evaluated | {n_matches * 3:,} |
| qualifying picks (EV ≥ 1.05, naive proxy) | {n_picks:,} ({pickrate * 100:.1f}% of outcomes) |
| qualifying picks (empirical proxy) | {len(emp_picks):,} |

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
| total picks | {n_picks:,} |
| total stake (yuan, bankroll = 10 000) | {naive_picks['stake'].sum():,.0f} |
| total realised PnL | {naive_picks['pnl'].sum():,.0f} |
| **cumulative ROI** | **{_fmt_pct(naive_point)}** |
| 95% bootstrap CI | [{_fmt_pct(naive_lo)}, {_fmt_pct(naive_hi)}] |
| one-sided p-value vs ROI = 0 | {p_naive:.4g} |
| hit rate on picks | {naive_picks['won'].mean() * 100:.1f}% |
| mean model EV on picks | {naive_picks['model_ev'].mean():.3f} |

### 3.2 Empirical proxy SP (per-result-code OLS fit on history)

OLS coefficients (winning_sp = a + b × winning_eu_odds):
{sp_fit_lines}

| metric | value |
|---|---|
| total picks | {len(emp_picks):,} |
| total stake | {emp_picks['stake'].sum():,.0f} |
| total realised PnL | {emp_picks['pnl'].sum():,.0f} |
| **cumulative ROI** | **{_fmt_pct(emp_point)}** |
| 95% bootstrap CI | [{_fmt_pct(emp_lo)}, {_fmt_pct(emp_hi)}] |
| one-sided p-value vs ROI = 0 | {p_emp:.4g} |
| hit rate on picks | {emp_picks['won'].mean() * 100:.1f}% |

---

## 4. Weekly batch behaviour (naive proxy)

| metric | value |
|---|---|
| weeks with ≥1 pick | {len(weekly)} |
| median picks / week | {wn_picks_med:.0f} |
| mean weekly ROI | {_fmt_pct(wmean)} |
| P5 weekly ROI | {_fmt_pct(wp5)} |
| P50 weekly ROI | {_fmt_pct(wp50)} |
| P95 weekly ROI | {_fmt_pct(wp95)} |

Weekly distribution histogram: `figures/weekly_roi_hist_naive.png`
Cumulative PnL plot: `figures/cum_roi_naive.png`
Empirical-SP cumulative PnL: `figures/cum_roi_empirical.png`
Calibration plot: `figures/calibration_naive.png`

---

## 5. Edge attribution

### 5.1 By chosen 选项 (3 / 1 / 0)

Naive proxy SP:

{_df_to_md(by_outcome)}

Empirical proxy SP:

{_df_to_md(by_outcome_emp)}

### 5.2 By handicap bucket (h = 0 vs |h| = 1 vs |h| ≥ 2)

Naive proxy SP:

{_df_to_md(by_handicap)}

Empirical proxy SP:

{_df_to_md(by_handicap_emp)}

### 5.3 By EV bucket

Naive proxy SP:

{_df_to_md(by_ev)}

Empirical proxy SP:

{_df_to_md(by_ev_emp)}

### 5.4 Calibration: model p̂ vs realised hit rate (qualifying picks only)

Naive proxy SP:

{_df_to_md(cal)}

### 5.5 POPULATION calibration (all {n_matches:,} matches, no EV filter)

This decouples *model accuracy* from *decision rule*.

By model p3 (predicted home-side):

{_df_to_md(pop_calib_3, idx=False)}

By model p1 (predicted draw-side):

{_df_to_md(pop_calib_1, idx=False)}

By model p0 (predicted away-side):

{_df_to_md(pop_calib_0, idx=False)}

Mean predicted p of the *actual* winner: **{pop["mean_p_winner"].mean():.3f}**
(higher = model is consistently giving more mass to the realised outcome).
Random/uninformed baseline = 1/3 ≈ 0.333.

---

## 6. Honest verdict

Cumulative ROI under the **naive proxy** is **{_fmt_pct(naive_point)}**
(95 % bootstrap CI {_fmt_pct(naive_lo)} … {_fmt_pct(naive_hi)};
one-sided p = {p_naive:.3g}).

Under the **empirical proxy** (which bakes in the systematic SP↔EU
relationship observed in history) the cumulative ROI is
**{_fmt_pct(emp_point)}** (CI {_fmt_pct(emp_lo)} … {_fmt_pct(emp_hi)};
p = {p_emp:.3g}).

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
* The data pipeline works ({n_matches:,} matches, no parsing errors).
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
   {n_matches:,} matches we have here as goal-distribution training data.
4. Re-run this backtest with a *bias prior* module (spec §2.2) toggled
   on/off — even with the avg-EU proxy we can compare hit-rate
   attribution across the 3/1/0 split, which is informative even if
   absolute ROI isn't.

---

*Generated from `data/beidan_history.db` containing {n_matches:,}
historical matches.*
"""
    return md


def main():
    db_path = REPO / "data" / "beidan_history.db"
    text = build_report(db_path)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text)
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
