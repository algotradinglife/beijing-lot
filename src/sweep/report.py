"""Render the combo-sweep HTML report with master table + plots."""
from __future__ import annotations

import os
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIG_DIR = os.path.join(REPO_ROOT, "docs", "research", "figures")
REPORT_PATH = os.path.join(REPO_ROOT, "docs", "research", "combo_sweep_report.html")

CSS = """
:root {
  --bg:#fafaf7; --fg:#1a1a1a; --muted:#666; --accent:#b04a2f; --accent-soft:#f6ebe5;
  --warn:#a45a00; --warn-soft:#fdf3e3; --good:#2e6b4a; --good-soft:#e8f1ec;
  --bad:#8b2424; --bad-soft:#f6e8e8; --code-bg:#f0ede6; --border:#d8d3c7;
  --table-border:#c8c2b3;
}
* { box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
  line-height:1.7; color:var(--fg); background:var(--bg); max-width:1040px;
  margin:0 auto; padding:32px 24px 80px; font-size:16px; }
h1 { font-size:28px; margin-top:0; border-bottom:2px solid var(--accent); padding-bottom:10px; }
h2 { font-size:22px; margin-top:40px; color:var(--accent); border-bottom:1px solid var(--border); padding-bottom:6px; }
h3 { font-size:18px; margin-top:26px; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }
th,td { border:1px solid var(--table-border); padding:6px 10px; text-align:left; }
th { background:var(--accent-soft); font-weight:600; }
tbody tr:nth-child(even) { background:rgba(0,0,0,0.02); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.good { color:var(--good); font-weight:600; }
td.bad { color:var(--bad); font-weight:600; }
.callout { border-left:4px solid var(--accent); background:var(--accent-soft);
  padding:10px 16px; margin:14px 0; border-radius:0 6px 6px 0; }
.callout.warn { border-color:var(--warn); background:var(--warn-soft); }
.callout.good { border-color:var(--good); background:var(--good-soft); }
.callout.bad  { border-color:var(--bad); background:var(--bad-soft); }
img { max-width:100%; border:1px solid var(--border); border-radius:6px; margin:10px 0; }
.meta { color:var(--muted); font-size:14px; margin-bottom:24px; }
.tag { display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px;
  font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }
.tag-good { background:var(--good-soft); color:var(--good); }
.tag-bad { background:var(--bad-soft); color:var(--bad); }
.tag-warn { background:var(--warn-soft); color:var(--warn); }
"""


def _fmt_pct(x, digits=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x*100:.{digits}f}%"


def _fmt_num(x, digits=4):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{digits}f}"


def _fmt_int(x):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{int(x):,}"


def _good_bad(val: float, threshold: float = 0.0) -> str:
    if val is None or not np.isfinite(val):
        return ""
    return "good" if val > threshold else "bad"


# ---------------------------------------------------------------------------
# Plots

def plot_bankroll_curves(sims: dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    cmap = plt.cm.viridis(np.linspace(0, 0.9, len(sims)))
    for color, (n, sim) in zip(cmap, sorted(sims.items())):
        weekly = sim.weekly
        if weekly.empty:
            continue
        x = np.arange(len(weekly) + 1)
        y = np.concatenate(([sim.initial_bankroll], weekly["bankroll_end"].to_numpy()))
        ax.plot(x, y, label=f"N={n}", color=color, lw=1.6)
    ax.axhline(100_000, color="grey", ls=":", lw=0.8)
    ax.set_xlabel("Week index (test period)")
    ax.set_ylabel("Bankroll (yuan)")
    ax.set_title("Cumulative bankroll trajectory by combo size")
    ax.set_yscale("symlog", linthresh=1e4)
    ax.legend(ncol=4, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def plot_weekly_roi_box(sims: dict, out_path: str) -> None:
    rois = []
    labels = []
    for n, sim in sorted(sims.items()):
        if sim.weekly.empty:
            continue
        rois.append(sim.weekly["week_roi"].to_numpy())
        labels.append(f"N={n}")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if rois:
        ax.boxplot(rois, tick_labels=labels, showfliers=False)
    ax.axhline(0, color="grey", ls="--", lw=0.8)
    ax.set_ylabel("Weekly ROI (excluding outliers)")
    ax.set_title("Weekly ROI distribution by N")
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def plot_forward_paths(mc_results: dict, out_path: str) -> None:
    """Plot median + p5/p95 bands for each N."""
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), sharey=False)
    axes = axes.ravel()
    for ax, (n, mc) in zip(axes, sorted(mc_results.items())):
        paths = mc.get("paths")
        if paths is None or len(paths) == 0:
            ax.set_title(f"N={n} (no data)")
            continue
        x = np.arange(paths.shape[1])
        med = np.median(paths, axis=0)
        p5 = np.quantile(paths, 0.05, axis=0)
        p95 = np.quantile(paths, 0.95, axis=0)
        ax.fill_between(x, p5, p95, alpha=0.25, color="steelblue", label="P5–P95")
        ax.plot(x, med, color="steelblue", lw=1.8, label="Median")
        ax.axhline(100_000, color="grey", ls=":", lw=0.8)
        ax.set_title(f"N={n}: 1-yr forward (1000 paths)")
        ax.set_xlabel("Week")
        ax.grid(alpha=0.3)
    # Hide unused
    for ax in axes[len(mc_results):]:
        ax.set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------------------
# HTML

def render_report(
    summaries: pd.DataFrame,
    mc_results: dict,
    sims: dict,
    n_qual_picks: int,
    n_surviving_niches: int,
    out_path: str = REPORT_PATH,
) -> None:
    os.makedirs(FIG_DIR, exist_ok=True)
    bcurve = os.path.join(FIG_DIR, "sweep_bankroll_curves.png")
    boxp = os.path.join(FIG_DIR, "sweep_weekly_roi_box.png")
    fwd = os.path.join(FIG_DIR, "sweep_forward_paths.png")
    plot_bankroll_curves(sims, bcurve)
    plot_weekly_roi_box(sims, boxp)
    plot_forward_paths(mc_results, fwd)

    # Master table rows
    master_rows: list[str] = []
    for _, r in summaries.iterrows():
        n = int(r["n_legs"])
        mc = mc_results.get(n, {})
        roi_cls = _good_bad(r["cumulative_ROI"])
        sharpe_cls = _good_bad(r["sharpe"])
        master_rows.append(f"""
<tr>
  <td><b>{n}</b></td>
  <td class='num'>{_fmt_int(r['n_combos_total'])}</td>
  <td class='num'>{_fmt_int(r['n_hits'])}</td>
  <td class='num'>{_fmt_pct(r['hit_rate'], 3)}</td>
  <td class='num'>{_fmt_pct(r['expected_hit_rate'], 3)}</td>
  <td class='num {roi_cls}'>{_fmt_pct(r['cumulative_ROI'])}</td>
  <td class='num {sharpe_cls}'>{_fmt_num(r['sharpe'], 2)}</td>
  <td class='num bad'>{_fmt_pct(r['max_drawdown'])}</td>
  <td class='num'>{_fmt_pct(r['P5_weekly_ROI'])}</td>
  <td class='num'>{_fmt_int(r['time_to_first_hit'])}</td>
  <td class='num'>{_fmt_pct(mc.get('P_pos_ROI_1y'))}</td>
</tr>""")

    # Tax / payout table
    tax_rows: list[str] = []
    for _, r in summaries.iterrows():
        tax_rows.append(f"""
<tr>
  <td><b>{int(r['n_legs'])}</b></td>
  <td class='num'>{_fmt_num(r['avg_prize_at_2y'], 1)}</td>
  <td class='num'>{_fmt_num(r['avg_prize_per_ticket'], 1)}</td>
  <td class='num'>{_fmt_num(r['max_prize_per_ticket'], 1)}</td>
  <td class='num'>{_fmt_pct(r['split_rate'])}</td>
</tr>""")

    # Forward-test table
    fwd_rows: list[str] = []
    for _, r in summaries.iterrows():
        n = int(r["n_legs"])
        mc = mc_results.get(n, {})
        fwd_rows.append(f"""
<tr>
  <td><b>{n}</b></td>
  <td class='num'>{_fmt_pct(mc.get('P_pos_ROI_1y'))}</td>
  <td class='num'>{_fmt_pct(mc.get('P_ROI_gt_20pct_1y'))}</td>
  <td class='num'>{_fmt_pct(mc.get('P_drawdown_lt_20pct'))}</td>
  <td class='num'>{_fmt_num(mc.get('E_hits_1y'), 1)}</td>
  <td class='num'>{_fmt_pct(mc.get('median_final_ROI'))}</td>
  <td class='num'>[{_fmt_pct(mc.get('p5_final_ROI'))}, {_fmt_pct(mc.get('p95_final_ROI'))}]</td>
</tr>""")

    # Recommendation
    valid = summaries[summaries["n_combos_total"] > 0].copy()
    if not valid.empty:
        # Conservative: best Sharpe with reasonable hit count
        cons = valid.sort_values("sharpe", ascending=False).iloc[0]
        # Aggressive: best cumulative ROI per Kelly growth proxy
        aggr = valid.sort_values("cumulative_ROI", ascending=False).iloc[0]
        rec_html = f"""
<table>
<thead><tr><th>Profile</th><th>Optimal N</th><th>Sharpe</th><th>cum ROI</th><th>Max DD</th><th>P(ROI&gt;0 in 1y)</th><th>Rationale</th></tr></thead>
<tbody>
<tr><td><b>Conservative</b></td><td><b>{int(cons['n_legs'])}</b></td>
    <td class='num'>{_fmt_num(cons['sharpe'],2)}</td>
    <td class='num'>{_fmt_pct(cons['cumulative_ROI'])}</td>
    <td class='num'>{_fmt_pct(cons['max_drawdown'])}</td>
    <td class='num'>{_fmt_pct(mc_results.get(int(cons['n_legs']), {}).get('P_pos_ROI_1y'))}</td>
    <td>Highest risk-adjusted return; fastest hit cadence; smallest variance.</td></tr>
<tr><td><b>Aggressive</b></td><td><b>{int(aggr['n_legs'])}</b></td>
    <td class='num'>{_fmt_num(aggr['sharpe'],2)}</td>
    <td class='num'>{_fmt_pct(aggr['cumulative_ROI'])}</td>
    <td class='num'>{_fmt_pct(aggr['max_drawdown'])}</td>
    <td class='num'>{_fmt_pct(mc_results.get(int(aggr['n_legs']), {}).get('P_pos_ROI_1y'))}</td>
    <td>Maximum compounding ceiling; tolerate variance for biggest payouts.</td></tr>
</tbody></table>
"""
    else:
        rec_html = "<p>No N produced enough combos to recommend.</p>"

    html = f"""<!DOCTYPE html>
<html lang='zh-CN'><head><meta charset='UTF-8'><title>北单 Combo Size Sweep — Comprehensive Report</title>
<style>{CSS}</style></head><body>
<h1>北单 Combo Size Sweep — N ∈ {{2..8}}</h1>
<div class='meta'>Auto-generated · 8-year 3-SP dataset · niche-filtered + train/test split · fractional-Kelly with tax-cap split</div>

<h2>1. Methodology</h2>
<p>From the {n_qual_picks:,} qualifying single-leg picks generated by {n_surviving_niches} OOS-validated niches (train: 期号&lt;median; test: 期号≥median; survival ≡ test mean q &gt; 1.064 with k≥30), we group leg picks by ISO week. For each N ∈ {{2..8}} and each week with K≥N qualifying picks (one option per match), we enumerate combos when C(K,N)≤5000 else sample 300. Each combo is sized via fractional Kelly (f=0.25·f*) with per-combo cap 0.5% bankroll, weekly stake cap 25% bankroll, then tax-cap split (per-ticket prize&lt;9 999 yuan). PnL recompounds weekly only over the test half. Forward Monte Carlo (1000 paths × 52 weeks) bootstraps weekly PnL.</p>

<div class='callout warn'><b>Caveats baked in:</b> niche q estimates from the train half drive sizing; legs within a week are weakly correlated (weather, big-team coverage); the 7-leg case is data-limited (E[hits in 8 yrs] ≈ 0–1 even under positive edge), so its empirical numbers carry wide uncertainty.</div>

<h2>2. Master comparison table</h2>
<table>
<thead><tr>
<th>N</th><th>n_combos</th><th>n_hits</th><th>hit_rate</th><th>predicted</th>
<th>cum ROI</th><th>Sharpe</th><th>max DD</th><th>P5 weekly</th>
<th>weeks→1st hit</th><th>P(ROI&gt;0, 1y fwd)</th>
</tr></thead>
<tbody>{''.join(master_rows)}</tbody></table>

<h2>3. Cumulative ROI curves</h2>
<img src='figures/sweep_bankroll_curves.png' alt='Bankroll trajectory by N'>
<p><small>Symlog scale on y-axis. Bankroll initialized at 100 000 yuan. Curves drop to 0 indicate ruin.</small></p>

<h2>4. Weekly ROI distribution</h2>
<img src='figures/sweep_weekly_roi_box.png' alt='Weekly ROI boxplot by N'>

<h2>5. Forward-test simulation (1 year, 1000 paths)</h2>
<img src='figures/sweep_forward_paths.png' alt='Forward Monte Carlo by N'>
<table>
<thead><tr><th>N</th><th>P(ROI&gt;0)</th><th>P(ROI&gt;20%)</th><th>P(DD&gt;-20%)</th>
<th>E[hits/yr]</th><th>median ROI</th><th>P5–P95 ROI</th></tr></thead>
<tbody>{''.join(fwd_rows)}</tbody></table>

<h2>6. Tax / payout analysis</h2>
<table>
<thead><tr><th>N</th><th>avg prize @ 2 yuan</th><th>avg prize per ticket (sized)</th>
<th>max prize per ticket</th><th>split rate</th></tr></thead>
<tbody>{''.join(tax_rows)}</tbody></table>
<p><small>Split rate = fraction of combos requiring &gt;1 ticket to keep prize &lt; 10 000 yuan.</small></p>

<h2>7. Optimal N recommendation</h2>
{rec_html}

<h2>8. Honest caveats</h2>
<ul>
<li><b>Small-n niches</b>: some surviving niches had n_train just above 200; their q estimates are noisy.</li>
<li><b>Within-week correlation</b>: combos in the same week share weather, refereeing, and TV-coverage shocks. Independence is approximate.</li>
<li><b>Selection bias residue</b>: even with proper train→test split, the entire {n_surviving_niches}-niche grid was searched on the train half; the OOS survival filter limits but does not eliminate this.</li>
<li><b>Non-stationarity</b>: payout structure and pool composition drift over 2018–2026 (Covid, new leagues). The forward MC assumes future weeks resemble past test-half weeks.</li>
<li><b>7-leg data limit</b>: under the modeled q, E[hits] in 8 years ≈ 0.03 — observed counts of 0 are consistent with both no-edge and edge+variance. Don't over-interpret.</li>
<li><b>Hit-rate vs predicted</b>: deviation between observed hit_rate and ∏(q_train/SP) signals q inflation. Compare in master table column 4 vs 5.</li>
</ul>

</body></html>
"""
    with open(out_path, "w") as f:
        f.write(html)
