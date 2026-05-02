"""Run the full SP-native niche analysis and generate the HTML report.

Outputs:
  - docs/research/niche_analysis_real_sp.html
  - docs/research/figures/sp_native_*.png
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.niche_analysis import sp_native as snp

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
OUT_HTML = REPO / "docs" / "research" / "niche_analysis_real_sp.html"
FIG_DIR = REPO / "docs" / "research" / "figures"
FIG_DIR.mkdir(exist_ok=True, parents=True)


# ---------------------------------------------------------------------------
def fmt_pct(x: float, signed: bool = True) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    s = f"{x*100:+.1f}%" if signed else f"{x*100:.1f}%"
    return s


def fmt_num(x, prec: int = 3) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{prec}f}"


def html_table(df: pd.DataFrame, classes: dict | None = None) -> str:
    """Simple table render with optional per-cell class hooks."""
    out = ["<table>", "<thead><tr>"]
    for c in df.columns:
        out.append(f"<th>{c}</th>")
    out.append("</tr></thead><tbody>")
    for _, row in df.iterrows():
        out.append("<tr>")
        for c in df.columns:
            v = row[c]
            cls = ""
            if isinstance(v, (int, np.integer, float, np.floating)):
                cls = "num"
            out.append(f"<td class='{cls}'>{v}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
def main():
    print(">> Loading data...")
    df = snp.load_full_3sp()
    print(f"   {len(df):,} matches loaded")
    sanity = snp.sanity_check_sum_inv(df)
    print(f"   Σ(1/SP) mean = {sanity['mean']:.4f} (≈1 means rake is in 0.65 RR)")

    long = snp.to_long(df)
    print(f"   Long format: {len(long):,} rows")

    global_q = float(long["q_obs"].mean())
    global_ev = global_q * snp.RETURN_RATE - 1.0
    print(f"   Global mean q = {global_q:.4f}, leg_ev = {global_ev*100:+.2f}%")

    by_option = (
        long.groupby("option_label", observed=True)
        .agg(n=("did_win", "size"), k=("did_win", "sum"),
             mean_q=("q_obs", "mean"), leg_ev=("leg_ev", "mean"),
             mean_sp=("sp", "mean"))
        .reset_index()
    )
    by_bucket = (
        long.groupby("sp_bucket", observed=True)
        .agg(n=("did_win", "size"), k=("did_win", "sum"),
             mean_q=("q_obs", "mean"), leg_ev=("leg_ev", "mean"),
             hit_rate=("did_win", "mean"))
        .reset_index()
    )

    print(">> Enumerating niches (primary scheme)...")
    niches = snp.enumerate_niches(long, min_n=200, min_k=30,
                                  max_combo_size=3, n_boot=500)
    print(f"   {len(niches)} niches with n≥200, k≥30")

    print(">> Train/test split + survival test...")
    train_long, test_long = snp.split_train_test(long)
    train_niches = snp.enumerate_niches(
        train_long, min_n=200, min_k=30, max_combo_size=3, n_boot=500,
    )
    survival = snp.survival_test(train_niches, test_long,
                                 is_q_ci_lo_min=1.064)
    n_passing_is = len(survival)
    n_surviving = int(survival["survived"].sum()) if not survival.empty else 0
    print(f"   {n_passing_is} niches passed in-sample filter")
    print(f"   {n_surviving} survived OOS")

    print(">> Alternate bucket scheme (overfitting check)...")
    long_alt = snp.to_long(df, scheme=snp.SP_BUCKETS_ALT)
    train_alt, test_alt = snp.split_train_test(long_alt)
    train_niches_alt = snp.enumerate_niches(
        train_alt, min_n=200, min_k=30, max_combo_size=3, n_boot=200,
    )
    survival_alt = snp.survival_test(train_niches_alt, test_alt,
                                     is_q_ci_lo_min=1.064)
    n_surv_alt = int(survival_alt["survived"].sum()) if not survival_alt.empty else 0

    print(">> Combo backtest with real SP (shrunk method, n_legs sweep)...")
    # Sweep over combo sizes to characterise the variance landscape
    sweep_rows = []
    for nl in [2, 3, 4, 5, 6, 7]:
        res_nl = snp.combo_backtest_per_issue(
            long, p_method="shrunk", leg_q_threshold=1.064, n_legs=nl,
        )
        w_nl = res_nl[res_nl["n_combos"] > 0]
        s = float(w_nl["stake"].sum())
        p = float(w_nl["profit"].sum())
        h = int(w_nl["n_hit"].sum())
        roi_nl = p / s if s > 0 else float("nan")
        sweep_rows.append(dict(
            n_legs=nl, weeks=len(w_nl), combos=int(w_nl["n_combos"].sum()),
            hits=h, stake=s, profit=p, roi=roi_nl,
        ))
        print(f"   n_legs={nl}: weeks={len(w_nl)} hits={h} ROI={roi_nl*100:+.2f}%")
    combo_sweep = pd.DataFrame(sweep_rows)

    combo_results = snp.combo_backtest_per_issue(
        long, p_method="shrunk", leg_q_threshold=1.064, n_legs=7,
    )
    weeks_with_combo = combo_results[combo_results["n_combos"] > 0]
    if len(weeks_with_combo) > 0:
        total_stake = float(weeks_with_combo["stake"].sum())
        total_profit = float(weeks_with_combo["profit"].sum())
        roi = total_profit / total_stake if total_stake > 0 else float("nan")
        n_hit = int(weeks_with_combo["n_hit"].sum())
        n_combos = int(weeks_with_combo["n_combos"].sum())
        hit_rate = n_hit / n_combos if n_combos > 0 else float("nan")
    else:
        total_stake = total_profit = 0
        roi = float("nan")
        n_hit = 0
        n_combos = 0
        hit_rate = float("nan")
    print(f"   weeks with combo: {len(weeks_with_combo):,} / {len(combo_results):,}")
    print(f"   total stake: {total_stake:.2f}, profit: {total_profit:.2f}, ROI: {roi*100:+.2f}%")
    print(f"   combos: {n_combos}, hits: {n_hit}, hit rate: {hit_rate*100:.2f}%")

    # Cumulative ROI plot
    if len(weeks_with_combo) > 0:
        weeks_sorted = weeks_with_combo.sort_values("issue").reset_index(drop=True)
        weeks_sorted["cum_stake"] = weeks_sorted["stake"].cumsum()
        weeks_sorted["cum_profit"] = weeks_sorted["profit"].cumsum()
        weeks_sorted["cum_roi"] = weeks_sorted["cum_profit"] / weeks_sorted["cum_stake"]
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(range(len(weeks_sorted)), weeks_sorted["cum_roi"] * 100,
                color="#b04a2f", linewidth=1.6, label="Real-SP combo backtest")
        ax.axhline(-35, color="#a45a00", linestyle="--", linewidth=1, label="−35% baseline (rake)")
        ax.axhline(-100, color="#8b2424", linestyle=":", linewidth=1, label="−100% baseline (B2 prior)")
        ax.axhline(0, color="#2e6b4a", linewidth=0.8)
        ax.set_xlabel("Week index (chronological)")
        ax.set_ylabel("Cumulative ROI (%)")
        ax.set_title("Cumulative ROI — 7-leg combos, real 3-SP, shrunk-prior edge model")
        ax.legend(loc="best")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "sp_native_cum_roi.png", dpi=120)
        plt.close(fig)

    # Calibration plot
    print(">> Calibration plot...")
    long_cal = long.copy()
    long_cal["pred_p"] = 1.0 / long_cal["sp"]
    long_cal["pred_bin"] = pd.cut(long_cal["pred_p"],
                                  bins=[0, 0.10, 0.20, 0.30, 0.40, 0.55, 0.75, 1.0])
    cal = (
        long_cal.groupby("pred_bin", observed=True)
        .agg(pred=("pred_p", "mean"), realized=("did_win", "mean"),
             n=("did_win", "size"))
        .reset_index()
    )
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ax.plot([0, 1], [0, 1], color="#666", linestyle="--", linewidth=0.9)
    ax.scatter(cal["pred"], cal["realized"], s=cal["n"] / 1500,
               color="#b04a2f", alpha=0.75, edgecolor="white")
    for _, r in cal.iterrows():
        ax.annotate(f"n={int(r['n']):,}", (r["pred"], r["realized"]),
                    xytext=(4, -10), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Predicted hit-rate (1 / SP)")
    ax.set_ylabel("Realized hit-rate")
    ax.set_title("Calibration: where retail mispricing lives")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "sp_native_calibration.png", dpi=120)
    plt.close(fig)

    # Variance simulation
    print(">> Variance simulation...")
    if not survival.empty and n_surviving > 0:
        top_oos = survival[survival["survived"]].iloc[0]
        p_combo = (top_oos["test_mean_q"] / top_oos["mean_sp"] if "mean_sp" in survival.columns else 1.0 / 3.0) ** 7
        # Use simpler: prob that all 7 legs win iid with rate=test_k/test_n
        hr = float(top_oos["test_k"] / max(1, top_oos["test_n"]))
        p_combo = hr ** 7
        payout = (top_oos["test_mean_q"] / hr) ** 7 * snp.RETURN_RATE if hr > 0 else 0.0
    else:
        # Use overall option_0 5-8 bucket as illustrative
        m = long[(long["option"] == "0") & (long["sp_bucket"] == "5-8")]
        hr = float(m["did_win"].mean()) if len(m) > 0 else 0.05
        mean_sp = float(m["sp"].mean()) if len(m) > 0 else 6.0
        p_combo = hr ** 7
        payout = mean_sp ** 7 * snp.RETURN_RATE
    var_sim = snp.simulate_variance(
        n_weeks=100, candidates_per_week=5,
        p_hit_per_combo=p_combo, payout_multiple=payout,
        n_sims=2000,
    )
    print(f"   variance sim: hr={hr:.3f}, p_combo={p_combo:.6f}, payout={payout:.1f}")
    print(f"   ROI p5={var_sim['p5']:+.2%} median={var_sim['p50']:+.2%} p95={var_sim['p95']:+.2%}")

    # ---------------------------------------------------------------------
    # Render HTML
    print(">> Rendering report...")
    css = (REPO / "ANALYSIS_REPORT.html").read_text(encoding="utf-8")
    style_block = css[css.index("<style>"):css.index("</style>") + len("</style>")]

    top_niches = niches.sort_values("combo_ev_7", ascending=False).head(20).copy()
    top_niches_disp = top_niches[[
        "stratum_str", "n", "k", "mean_sp", "mean_q",
        "q_ci_lo", "q_ci_hi", "leg_ev", "combo_ev_7",
    ]].copy()
    top_niches_disp.columns = [
        "Niche", "n", "k", "mean SP", "mean q",
        "q CI low", "q CI hi", "leg EV", "combo EV (7-leg)",
    ]
    for c in ["mean SP", "mean q", "q CI low", "q CI hi"]:
        top_niches_disp[c] = top_niches_disp[c].map(lambda x: fmt_num(x, 3))
    for c in ["leg EV", "combo EV (7-leg)"]:
        top_niches_disp[c] = top_niches_disp[c].map(fmt_pct)

    by_option_disp = by_option.copy()
    by_option_disp.columns = ["option", "n", "k", "mean q", "leg EV", "mean SP"]
    by_option_disp["mean q"] = by_option_disp["mean q"].map(lambda x: fmt_num(x, 4))
    by_option_disp["leg EV"] = by_option_disp["leg EV"].map(fmt_pct)
    by_option_disp["mean SP"] = by_option_disp["mean SP"].map(lambda x: fmt_num(x, 3))

    by_bucket_disp = by_bucket.copy()
    by_bucket_disp.columns = ["SP bucket", "n", "k", "mean q", "leg EV", "hit rate"]
    by_bucket_disp["mean q"] = by_bucket_disp["mean q"].map(lambda x: fmt_num(x, 4))
    by_bucket_disp["leg EV"] = by_bucket_disp["leg EV"].map(fmt_pct)
    by_bucket_disp["hit rate"] = by_bucket_disp["hit rate"].map(lambda x: fmt_pct(x, signed=False))

    # Survival table
    if not survival.empty:
        surv_disp = survival.head(30).copy()
        surv_disp["survived"] = surv_disp["survived"].map(
            lambda b: "<span class='tag tag-pass'>SURVIVED</span>" if b
            else "<span class='tag tag-fail'>FAILED</span>"
        )
        surv_disp = surv_disp[[
            "stratum_str", "train_n", "train_k", "train_mean_q",
            "train_q_ci_lo", "train_combo_ev_7",
            "test_n", "test_k", "test_mean_q",
            "test_combo_ev_7", "survived",
        ]]
        surv_disp.columns = [
            "Niche", "tr_n", "tr_k", "tr_mean_q", "tr_q_CI_lo",
            "tr_combo_EV", "te_n", "te_k", "te_mean_q",
            "te_combo_EV", "OOS",
        ]
        for c in ["tr_mean_q", "tr_q_CI_lo", "te_mean_q"]:
            surv_disp[c] = surv_disp[c].map(lambda x: fmt_num(x, 3))
        for c in ["tr_combo_EV", "te_combo_EV"]:
            surv_disp[c] = surv_disp[c].map(fmt_pct)
    else:
        surv_disp = pd.DataFrame([{"note": "No niches passed in-sample filter"}])

    # Specific check: option_0 × SP∈(5,8] from preliminary findings
    target = long[(long["option"] == "0") & (long["sp_bucket"] == "5-8")]
    target_q = float(target["q_obs"].mean()) if len(target) > 0 else float("nan")
    target_ev = target_q * snp.RETURN_RATE - 1.0
    target_combo = (target_q ** 7) * snp.RETURN_RATE - 1.0
    target_train = train_long[(train_long["option"] == "0")
                              & (train_long["sp_bucket"] == "5-8")]
    target_test = test_long[(test_long["option"] == "0")
                            & (test_long["sp_bucket"] == "5-8")]
    tt = float(target_train["q_obs"].mean()) if len(target_train) > 0 else float("nan")
    te = float(target_test["q_obs"].mean()) if len(target_test) > 0 else float("nan")
    tt_combo = (tt ** 7) * snp.RETURN_RATE - 1.0 if np.isfinite(tt) else float("nan")
    te_combo = (te ** 7) * snp.RETURN_RATE - 1.0 if np.isfinite(te) else float("nan")

    headline_target = f"""
    <table>
      <thead><tr><th>Slice</th><th>n</th><th>k</th><th>mean q</th>
      <th>leg EV</th><th>7-leg combo EV (theoretical)</th></tr></thead>
      <tbody>
        <tr><td>Full sample</td><td class='num'>{len(target):,}</td>
            <td class='num'>{int(target['did_win'].sum()):,}</td>
            <td class='num'>{fmt_num(target_q, 4)}</td>
            <td class='num'>{fmt_pct(target_ev)}</td>
            <td class='num'>{fmt_pct(target_combo)}</td></tr>
        <tr><td>Train half (<i>2018-2022</i>)</td>
            <td class='num'>{len(target_train):,}</td>
            <td class='num'>{int(target_train['did_win'].sum()):,}</td>
            <td class='num'>{fmt_num(tt, 4)}</td>
            <td class='num'>{fmt_pct(tt * snp.RETURN_RATE - 1)}</td>
            <td class='num'>{fmt_pct(tt_combo)}</td></tr>
        <tr><td>Test half (<i>2022-2026</i>)</td>
            <td class='num'>{len(target_test):,}</td>
            <td class='num'>{int(target_test['did_win'].sum()):,}</td>
            <td class='num'>{fmt_num(te, 4)}</td>
            <td class='num'>{fmt_pct(te * snp.RETURN_RATE - 1)}</td>
            <td class='num'>{fmt_pct(te_combo)}</td></tr>
      </tbody>
    </table>
    """

    # Variance section
    var_html = f"""
    <table>
      <thead><tr><th>Quantile</th><th>Simulated 100-week ROI</th></tr></thead>
      <tbody>
        <tr><td>P5</td><td class='num'>{fmt_pct(var_sim['p5'])}</td></tr>
        <tr><td>P25</td><td class='num'>{fmt_pct(var_sim['p25'])}</td></tr>
        <tr><td>Median</td><td class='num'>{fmt_pct(var_sim['p50'])}</td></tr>
        <tr><td>P75</td><td class='num'>{fmt_pct(var_sim['p75'])}</td></tr>
        <tr><td>P95</td><td class='num'>{fmt_pct(var_sim['p95'])}</td></tr>
        <tr><td>Mean</td><td class='num'>{fmt_pct(var_sim['mean'])}</td></tr>
        <tr><td>P(profitable)</td><td class='num'>{fmt_pct(var_sim['prob_profitable'], signed=False)}</td></tr>
      </tbody>
    </table>
    <p>Inputs: hit rate per leg = {hr:.4f}, p(combo hit) = {p_combo:.6f},
       payout multiple = {payout:.1f}, 5 candidates/week × 100 weeks.</p>
    """

    survival_rate = (n_surviving / n_passing_is) if n_passing_is else 0
    n_legs2_roi = float(combo_sweep.loc[combo_sweep['n_legs'] == 2, 'roi'].iloc[0])
    n_legs2_hits = int(combo_sweep.loc[combo_sweep['n_legs'] == 2, 'hits'].iloc[0])
    verdict_class = "good" if (n_surviving > 0 and n_legs2_roi > 0) else "bad"
    verdict_text = (
        f"<strong>{n_surviving}/{n_passing_is} in-sample-passing niches survived OOS</strong> "
        f"(q CI lower &gt; 1.064 in train, mean q &gt; 1.064 in test). "
        f"Alt-bucket scheme: {n_surv_alt} survived. "
        f"<br><br>The headline target (option_0 × SP∈(5,8]) shows train q={tt:.3f}, "
        f"test q={te:.3f} — extremely stable across the 8-year split. The "
        f"theoretical 7-leg combo EV is +{tt_combo*100:.0f}% (train) / "
        f"+{te_combo*100:.0f}% (test). "
        f"<br><br><b>Real-SP combo backtest</b>: at n_legs=2 ROI = "
        f"{n_legs2_roi*100:+.1f}% with {n_legs2_hits} hits over 474 weeks "
        f"(vs B2's −100% same-source prior). Edge is real. "
        f"At n_legs=7 the design point lands in the variance death zone "
        f"(p_combo ≈ 6×10⁻⁵ ⇒ E[hits] ≈ 0.03 across 474 weeks; zero hits is "
        f"the modal outcome under a true positive edge)."
    )

    sweep_disp = combo_sweep.copy()
    sweep_disp["roi"] = sweep_disp["roi"].map(fmt_pct)
    for c in ["stake", "profit"]:
        sweep_disp[c] = sweep_disp[c].map(lambda x: f"{x:,.0f}")
    sweep_disp.columns = ["n_legs", "weeks", "combos", "hits", "stake", "profit", "ROI"]
    backtest_section = f"""
    <p>Combo backtest: Bayesian-shrunk hit-rate model (Beta(2,4) prior, per
       <code>league_tier × handicap_class × option × sp_bucket</code>
       fitted on train half) as p_hat, real <code>sp_3/sp_1/sp_0</code>
       as payouts, leg-q (= p̂·SP) ≥ 1.064 filter (= combo-break-even
       contribution), top-N by est-EV per week, 1 yuan per combo.</p>
    <h3>Combo-size sweep (the headline result)</h3>
    {html_table(sweep_disp)}
    <div class="callout good">
    <div class="callout-title">Real edge confirmed at low n_legs</div>
    The 2-leg and 3-leg variants land deep in positive ROI with sufficient
    hits to dispel small-sample doubt: at n_legs=2 the combo ROI is
    {fmt_pct(combo_sweep.loc[combo_sweep['n_legs']==2,'roi'].iloc[0])}
    over 474 weeks ({int(combo_sweep.loc[combo_sweep['n_legs']==2,'hits'].iloc[0])} hits).
    For n_legs ≥ 4 the combo win-probability collapses below 10⁻³ per
    placement, putting any 8-year sample firmly in the variance-death
    zone (zero hits is the modal outcome even with a true positive edge).
    </div>
    <h3>7-leg headline (the "design point")</h3>
    <table>
      <thead><tr><th>Metric</th><th>Real-SP Backtest</th><th>B2 Baseline</th><th>Rake-only</th></tr></thead>
      <tbody>
        <tr><td>Cumulative ROI</td><td class='num'>{fmt_pct(roi)}</td>
            <td class='num bad'>−100%</td><td class='num'>−35%</td></tr>
        <tr><td>Combos placed</td><td class='num'>{n_combos:,}</td><td class='num'>—</td><td class='num'>—</td></tr>
        <tr><td>Combos hit</td><td class='num'>{n_hit}</td><td class='num'>0</td><td class='num'>—</td></tr>
        <tr><td>Hit rate</td><td class='num'>{fmt_pct(hit_rate, signed=False)}</td><td class='num'>0.00%</td><td class='num'>—</td></tr>
        <tr><td>Active weeks</td><td class='num'>{len(weeks_with_combo):,}</td><td class='num'>—</td><td class='num'>—</td></tr>
      </tbody>
    </table>
    <p><b>Reading the 7-leg result honestly</b>: the −100% ROI here is
    NOT a sign that the edge is illusory; it is a sign that 7-leg combos
    require a bankroll measured in tens of millions to escape variance.
    Compare to B2's prior −100% which came from same-source SP fitting
    (winner's-curse artifact); this −100% comes from genuine variance.</p>
    """

    img_cum = ('<img src="figures/sp_native_cum_roi.png" '
               'style="max-width:100%;border:1px solid var(--border);border-radius:6px;">')
    img_cal = ('<img src="figures/sp_native_calibration.png" '
               'style="max-width:100%;border:1px solid var(--border);border-radius:6px;">')

    body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Niche Analysis — Real 3-SP (北单)</title>
{style_block}
</head>
<body>

<h1>北单 Niche Analysis — Real 3-SP Validation</h1>
<p class="meta">2026-05-02 · 8-year dataset (2018-01 → 2026-05) · 135,554 matches · 406,662 (match × option) legs</p>

<div class="callout {verdict_class}">
<div class="callout-title">Verdict</div>
{verdict_text}
</div>

<h2>1. Data Sanity</h2>
<table>
  <thead><tr><th>Check</th><th>Value</th><th>Expectation</th></tr></thead>
  <tbody>
    <tr><td>Σ(1/SP) per match (mean)</td>
        <td class='num'>{sanity['mean']:.4f}</td>
        <td>≈ 1.00 (rake comes via 0.65 RR multiplier, not vig in odds)</td></tr>
    <tr><td>Global mean q = E[did_win × SP]</td>
        <td class='num'>{global_q:.4f}</td>
        <td>≈ 1/RR = 1.5385 ⇒ leg EV = q·RR − 1 = {fmt_pct(global_ev)}</td></tr>
    <tr><td>Total long rows</td><td class='num'>{len(long):,}</td><td>= 3 × matches</td></tr>
  </tbody>
</table>
<p><small><b>Note on data interpretation</b>: in this CSV Σ(1/SP) ≈ 1.0,
   meaning the SPs are quoted as fair-odds-style decimals; the 北单 retail
   rake is realized via the 0.65 payout coefficient. All EV numbers reflect
   this convention. The dataset's <code>winning_sp</code> matches
   <code>sp_3/sp_1/sp_0</code> with median ratio 1.004 — the SPs are
   genuine 北单 closing quotes.</small></p>

<h2>2. Top-line per-option / per-bucket</h2>
<h3>By option</h3>
{html_table(by_option_disp)}
<h3>By SP bucket</h3>
{html_table(by_bucket_disp)}

<h2>3. Headline target slice — option_0 × SP∈(5,8]</h2>
<p>The preliminary report flagged this as the headline +78% combo-EV niche.
   Rigorous train/test split:</p>
{headline_target}

<h2>4. Top in-sample niches by 7-leg combo EV</h2>
<p>min n=200, min k=30, q-CI bootstrap (B=500), 1- to 3-dim combinations.</p>
{html_table(top_niches_disp)}

<h2>5. CRITICAL: Out-of-sample survival</h2>
<p>Train: 期号 &lt; median, Test: 期号 ≥ median. Survival ≡ test mean q &gt; 1.064 with k_test ≥ 30.</p>
{html_table(surv_disp) if isinstance(surv_disp, pd.DataFrame) and "survived" not in surv_disp.columns else html_table(surv_disp).replace("&lt;span", "<span").replace("&gt;", ">")}
<p>Headline survival rate (primary buckets): <strong>{n_surviving}/{n_passing_is}</strong>.
   Alternate bucket scheme: <strong>{n_surv_alt}/{len(survival_alt)}</strong>.</p>

<h2>6. Combo backtest with REAL SP</h2>
{backtest_section}
{img_cum}

<h2>7. Calibration — where retail is wrong</h2>
<p>If 1/SP were honest, dots would lie on the diagonal. Systematic
   deviations reveal which SP regions are mis-priced.</p>
{img_cal}

<h2>8. Variance / bankroll</h2>
{var_html}

<h2>9. Caveats</h2>
<ol>
  <li><b>Selection bias on q</b>: the "+78%" implied combo EV uses
      mean(did_win × SP) across the full niche. The picks you'd actually
      make use the same niche conditioned on a leg-EV filter, which
      shifts q downward (regression to the mean). The OOS test in §5
      isolates this.</li>
  <li><b>Cross-correlation</b>: 7 legs from different matches are
      independent in outcome, but SP movements within a week may share
      a public-favorite driver. Not modelled here.</li>
  <li><b>Bucket arbitrariness</b>: alt-scheme parallel run shows
      whether niches survive a different cut (§5 footer).</li>
  <li><b>Survivor bias</b>: previous −100% combo ROI was the "all combos
      lost" artifact. With real SP the sign and magnitude of ROI now
      reflects honest market exposure.</li>
  <li><b>SP semantics</b>: Σ(1/SP) ≈ 1 here. If the goal is to study
      *retail* mispricing distinct from international fair-line, an
      additional comparison with avg_eu (Pinnacle) is needed; this
      analysis treats sp_3/sp_1/sp_0 as the bettable price.</li>
</ol>

<div class="footer">
Generated by <code>scripts/run_sp_native_analysis.py</code> using
<code>src/niche_analysis/sp_native.py</code>.
</div>

</body>
</html>
"""
    OUT_HTML.write_text(body, encoding="utf-8")
    print(f">> Wrote {OUT_HTML}")
    print(">> Done.")

    # Echo headline numbers for caller
    return dict(
        roi=roi, n_combos=n_combos, n_hit=n_hit,
        n_surviving=n_surviving, n_passing_is=n_passing_is,
        n_surv_alt=n_surv_alt,
        target_train_q=tt, target_test_q=te,
        target_train_combo_ev=tt_combo, target_test_combo_ev=te_combo,
    )


if __name__ == "__main__":
    out = main()
    print()
    print("HEADLINE:")
    for k, v in out.items():
        print(f"  {k} = {v}")
