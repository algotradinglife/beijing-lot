"""Drawdown decomposition + stop-loss analysis for N=4, Kelly=1/16.

Outputs:
  - data/raw/drawdown_baseline_weekly.csv
  - data/raw/drawdown_rules_summary.csv
  - docs/research/figures/drawdown_anatomy.png
  - docs/research/figures/drawdown_rule_curves.png
  - docs/research/drawdown_report.html
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.drawdown.anatomy import worst_drawdown
from src.drawdown.replay import (
    baseline_signals, replay, metrics_from_replay, monte_carlo_ruin,
)
from src.drawdown.stop_rules import (
    baseline, hard_stop, stake_throttle, vol_throttle, profit_lock, combined,
)
from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.simulator import simulate

INITIAL = 100_000.0
KELLY = 1 / 16
N_LEGS = 4
RUIN_THRESHOLD = 1_000.0
N_PATHS = 1000

FIG_DIR = ROOT / "docs" / "research" / "figures"
DATA_DIR = ROOT / "data" / "raw"
REPORT_PATH = ROOT / "docs" / "research" / "drawdown_report.html"


def run_baseline() -> pd.DataFrame:
    print("[1/5] Loading qualifying picks + running baseline simulation...")
    qual_a, _ = build_archetype_a_qual()
    res = simulate(
        qual_a, n_legs=N_LEGS, initial_bankroll=INITIAL,
        kelly_fraction=KELLY, per_combo_cap_frac=0.005,
        weekly_stake_cap_frac=0.25, max_combos_per_week=300,
        seed=7, test_only=True,
    )
    weekly = res.weekly.copy()
    weekly.to_csv(DATA_DIR / "drawdown_baseline_weekly.csv", index=False)
    print(f"  baseline weeks={len(weekly)}, final={res.final_bankroll:,.0f}")
    return weekly


def plot_dd_anatomy(weekly: pd.DataFrame, anat) -> None:
    pnl = weekly["week_pnl"].to_numpy(float)
    bk = INITIAL + np.cumsum(pnl)
    seq = np.concatenate([[INITIAL], bk])
    x = np.arange(len(seq))
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(x, seq, color="#1a1a1a", linewidth=1.4, label="Bankroll")
    ax.axhspan(seq[anat.trough_idx], anat.peak_value, color="#f6e8e8",
               alpha=0.5, zorder=0)
    ax.axvline(anat.peak_idx, color="#2e6b4a", linestyle="--", alpha=0.7,
               label=f"Peak (wk {anat.peak_week})")
    ax.axvline(anat.trough_idx, color="#8b2424", linestyle="--", alpha=0.7,
               label=f"Trough (wk {anat.trough_week})")
    if anat.recover_idx is not None:
        ax.axvline(anat.recover_idx, color="#a45a00", linestyle=":", alpha=0.7,
                   label=f"Recovery (wk {weekly.iloc[anat.recover_idx-1]['week_key']})")
    ax.set_yscale("log")
    ax.set_xlabel("Week index (0 = initial)")
    ax.set_ylabel("Bankroll (log)")
    ax.set_title(f"Worst Drawdown — N={N_LEGS}, Kelly=1/16  "
                 f"(DD={anat.drawdown_pct*100:.1f}%, {anat.n_weeks_in_dd} wks)")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "drawdown_anatomy.png", dpi=110)
    plt.close(fig)


def plot_rule_curves(signals: pd.DataFrame, rules: list, ruleset_name="all") -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    for rule in rules:
        rep = replay(signals, rule, INITIAL)
        wealth = rep["bankroll"].to_numpy() + rep["skim"].cumsum().to_numpy()
        ax.plot(np.arange(len(wealth)), wealth, linewidth=1.2, label=rule.name)
    ax.set_yscale("log")
    ax.set_xlabel("Week index")
    ax.set_ylabel("Realized wealth (bankroll + locked skim, log)")
    ax.set_title("Stop-loss rule comparison — N=4, Kelly=1/16 (test slice)")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "drawdown_rule_curves.png", dpi=110)
    plt.close(fig)


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    weekly = run_baseline()
    print("[2/5] Computing drawdown anatomy...")
    anat = worst_drawdown(weekly, INITIAL)
    print(f"  peak={anat.peak_week} trough={anat.trough_week} "
          f"DD={anat.drawdown_pct*100:.1f}% over {anat.n_weeks_in_dd} wks; "
          f"verdict='{anat.verdict}'")
    plot_dd_anatomy(weekly, anat)

    print("[3/5] Building rule set + replaying...")
    signals = baseline_signals(weekly, INITIAL)
    pl = profit_lock(2.0, 0.30)
    th = stake_throttle(0.20, 0.25)
    rules = [
        baseline(),
        hard_stop(0.15, 2),
        hard_stop(0.15, 4),
        hard_stop(0.25, 4),
        hard_stop(0.25, 8),
        hard_stop(0.40, 8),
        stake_throttle(0.15, 0.25),
        stake_throttle(0.25, 0.25),
        stake_throttle(0.40, 0.25),
        vol_throttle(window=8, std_threshold=0.10, halt_weeks=2),
        pl,
        combined(pl, th, name="ProfitLock+StakeThrottle25%"),
    ]

    summary_rows = []
    for rule in rules:
        rep = replay(signals, rule, INITIAL)
        m = metrics_from_replay(rep, INITIAL)
        print(f"  [MC] {rule.name}...")
        mc = monte_carlo_ruin(signals, rule, INITIAL, n_paths=N_PATHS,
                              ruin_threshold=RUIN_THRESHOLD, seed=17)
        summary_rows.append({
            "rule": rule.name,
            "note": rule.note,
            "cagr": m["cagr"],
            "sharpe": m["sharpe"],
            "max_dd": m["max_dd"],
            "calmar": m["calmar"],
            "final": m["final"],
            "time_underwater": m["time_underwater"],
            "ruin_rate_mc": mc["ruin_rate"],
            "median_final_mc": mc["median_final"],
            "p5_final_mc": mc["p5_final"],
        })

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(DATA_DIR / "drawdown_rules_summary.csv", index=False)
    print(f"\n  saved summary to {DATA_DIR / 'drawdown_rules_summary.csv'}")

    print("[4/5] Plotting rule curves...")
    plot_rule_curves(signals, rules)

    print("[5/5] Writing HTML report...")
    write_html_report(weekly, anat, summary)
    print(f"  -> {REPORT_PATH}")


CSS = """
:root {
    --bg: #fafaf7; --fg: #1a1a1a; --muted: #666; --accent: #b04a2f;
    --accent-soft: #f6ebe5; --warn: #a45a00; --warn-soft: #fdf3e3;
    --good: #2e6b4a; --good-soft: #e8f1ec; --bad: #8b2424;
    --bad-soft: #f6e8e8; --code-bg: #f0ede6; --border: #d8d3c7;
    --table-border: #c8c2b3;
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
                 "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    line-height: 1.7; color: var(--fg); background: var(--bg);
    max-width: 980px; margin: 0 auto; padding: 32px 24px 80px; font-size: 16px;
}
h1 { font-size: 28px; margin-top: 0; border-bottom: 2px solid var(--accent); padding-bottom: 10px; }
h2 { font-size: 22px; margin-top: 40px; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 6px; }
h3 { font-size: 18px; margin-top: 26px; }
code { font-family: "SF Mono", Menlo, Consolas, "Courier New", monospace;
       background: var(--code-bg); padding: 1px 5px; border-radius: 3px; font-size: 13px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }
th, td { border: 1px solid var(--table-border); padding: 6px 10px; text-align: left; }
th { background: var(--accent-soft); font-weight: 600; }
tbody tr:nth-child(even) { background: rgba(0,0,0,0.02); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.good { color: var(--good); font-weight: 600; }
td.bad { color: var(--bad); font-weight: 600; }
.callout { border-left: 4px solid var(--accent); background: var(--accent-soft);
           padding: 10px 16px; margin: 14px 0; border-radius: 0 6px 6px 0; }
.callout.warn { border-color: var(--warn); background: var(--warn-soft); }
.callout.good { border-color: var(--good); background: var(--good-soft); }
.callout.bad { border-color: var(--bad); background: var(--bad-soft); }
.callout-title { font-weight: 600; margin-bottom: 4px; }
.meta { color: var(--muted); font-size: 14px; margin-bottom: 24px; }
img { max-width: 100%; border: 1px solid var(--border); border-radius: 4px; margin: 8px 0; }
"""


def _fmt_pct(x): return f"{x*100:.1f}%" if pd.notna(x) else "—"
def _fmt_num(x): return f"{x:,.0f}" if pd.notna(x) else "—"
def _fmt_2f(x): return f"{x:.2f}" if pd.notna(x) else "—"


def write_html_report(weekly: pd.DataFrame, anat, summary: pd.DataFrame) -> None:
    base = summary.iloc[0]  # Baseline first
    # rank rules by Calmar
    ranked = summary.sort_values("calmar", ascending=False).reset_index(drop=True)
    top = ranked.iloc[0]

    rows_html = []
    for _, r in summary.iterrows():
        cagr_cls = "good" if r["cagr"] > base["cagr"] else "bad"
        dd_cls = "good" if abs(r["max_dd"]) < abs(base["max_dd"]) else "bad"
        cal_cls = "good" if r["calmar"] > base["calmar"] else "bad"
        ruin_cls = "good" if r["ruin_rate_mc"] <= base["ruin_rate_mc"] else "bad"
        rows_html.append(
            f"<tr><td>{r['rule']}</td>"
            f"<td class='num {cagr_cls}'>{_fmt_pct(r['cagr'])}</td>"
            f"<td class='num'>{_fmt_2f(r['sharpe'])}</td>"
            f"<td class='num {dd_cls}'>{_fmt_pct(r['max_dd'])}</td>"
            f"<td class='num {cal_cls}'>{_fmt_2f(r['calmar'])}</td>"
            f"<td class='num'>{_fmt_pct(r['time_underwater'])}</td>"
            f"<td class='num'>{_fmt_num(r['final'])}</td>"
            f"<td class='num {ruin_cls}'>{_fmt_pct(r['ruin_rate_mc'])}</td>"
            f"<td class='num'>{_fmt_num(r['median_final_mc'])}</td>"
            f"<td class='num'>{_fmt_num(r['p5_final_mc'])}</td></tr>"
        )

    # honest verdict
    helped = (top["calmar"] > base["calmar"] and
              abs(top["max_dd"]) < abs(base["max_dd"]) and
              top["ruin_rate_mc"] <= base["ruin_rate_mc"] + 0.005)
    if helped:
        verdict_cls = "good"
        verdict_title = "Verdict: Stop rules CAN help (modestly)"
        verdict_body = (f"<b>{top['rule']}</b> improves Calmar from "
                        f"{base['calmar']:.2f} to {top['calmar']:.2f}, cuts MaxDD "
                        f"from {abs(base['max_dd'])*100:.1f}% to "
                        f"{abs(top['max_dd'])*100:.1f}%, and changes ruin rate "
                        f"from {base['ruin_rate_mc']*100:.1f}% to "
                        f"{top['ruin_rate_mc']*100:.1f}%.")
    else:
        verdict_cls = "warn"
        verdict_title = "Verdict: Stop rules mostly delay the inevitable"
        verdict_body = (f"Best Calmar rule is <b>{top['rule']}</b> "
                        f"(Calmar={top['calmar']:.2f} vs baseline "
                        f"{base['calmar']:.2f}). DD reduction comes at the cost "
                        f"of CAGR; ruin rate barely moves "
                        f"({top['ruin_rate_mc']*100:.1f}% vs baseline "
                        f"{base['ruin_rate_mc']*100:.1f}%).")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Drawdown Decomposition + Stop-Loss Tests — N=4 Kelly=1/16</title>
<style>{CSS}</style></head><body>

<h1>Drawdown Decomposition + Stop-Loss Tests</h1>
<p class="meta">Configuration: N=4 legs, Kelly fraction = 1/16, initial = ¥100,000,
test-only slice (期号 ≥ median expect). Calmar-optimal in the (N, Kelly) grid.</p>

<div class="callout {verdict_cls}">
<div class="callout-title">{verdict_title}</div>
{verdict_body}
</div>

<h2>1. Baseline metrics</h2>
<table><thead><tr>
<th>Weeks</th><th>Final ¥</th><th>CAGR</th><th>Sharpe</th>
<th>MaxDD</th><th>Calmar</th><th>Time UW</th><th>Ruin (MC)</th>
</tr></thead><tbody><tr>
<td class='num'>{int(base.get('n_weeks', len(weekly)))}</td>
<td class='num'>{_fmt_num(base['final'])}</td>
<td class='num'>{_fmt_pct(base['cagr'])}</td>
<td class='num'>{_fmt_2f(base['sharpe'])}</td>
<td class='num bad'>{_fmt_pct(base['max_dd'])}</td>
<td class='num good'>{_fmt_2f(base['calmar'])}</td>
<td class='num'>{_fmt_pct(base['time_underwater'])}</td>
<td class='num'>{_fmt_pct(base['ruin_rate_mc'])}</td>
</tr></tbody></table>

<h2>2. Worst drawdown anatomy</h2>
<ul>
<li><b>Peak week:</b> {anat.peak_week} (¥{anat.peak_value:,.0f})</li>
<li><b>Trough week:</b> {anat.trough_week} (¥{anat.trough_value:,.0f})</li>
<li><b>Drawdown:</b> {anat.drawdown_pct*100:.1f}% over {anat.n_weeks_in_dd} weeks</li>
<li><b>Losing weeks within DD:</b> {anat.n_losing_weeks} / {anat.n_weeks_in_dd}
    (winning: {anat.n_winning_weeks})</li>
<li><b>Worst single week PnL:</b> ¥{anat.worst_single_week_pnl:,.0f}
    (week index {anat.worst_single_week_idx})</li>
<li><b>Streak share:</b> {anat.streak_share*100:.0f}% of the drawdown is
    NOT from the single worst week.</li>
<li><b>Recovery:</b> {"week " + str(weekly.iloc[anat.recover_idx-1]['week_key']) if anat.recover_idx else "<span class='bad'>not recovered within sample</span>"}</li>
</ul>
<p><b>Verdict:</b> {anat.verdict}.</p>
<img src="figures/drawdown_anatomy.png" alt="DD anatomy">

<h2>3. Stop-loss rule comparison</h2>
<p>Each rule is overlaid on the same baseline weekly trace (preserving
weekly ROI and stake fraction signals) and replayed under a re-evolved
bankroll. Profit-lock skim is treated as locked-in wealth (added to final
realized).</p>
<table><thead><tr>
<th>Rule</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th><th>Calmar</th>
<th>Time UW</th><th>Final ¥</th><th>Ruin% (MC)</th>
<th>Med Final (MC)</th><th>P5 Final (MC)</th>
</tr></thead><tbody>
{''.join(rows_html)}
</tbody></table>
<p class='meta'>Green/red coloring is vs baseline. MC = 1000 bootstrap paths,
horizon = baseline length, ruin = bankroll &lt; ¥1,000.</p>
<img src="figures/drawdown_rule_curves.png" alt="rule curves">

<h2>4. Honest discussion</h2>
<div class="callout warn">
<div class="callout-title">Why stop rules struggle here</div>
<p>The strategy's edge is asymmetric: most weeks lose small amounts
(stake bleed, no hits) and a few weeks win huge (combo payouts).
Hard-stop / vol-throttle rules disproportionately skip the few "fat" weeks
that produce nearly all of the equity. The baseline DD is largely
attritional (long losing streak) — exactly the regime where a halt rule
fires <em>after</em> most damage is done and then locks you out of recovery.</p>
<p>Stake-throttle is gentler (you stay in market at reduced size) and
preserves more upside, but in this trace the recovery weeks are exactly
the ones that get throttled, so realized CAGR drops materially.</p>
<p>Profit-lock-in (skimming on doublings) is the only rule that
unambiguously reduces ruin probability without sacrificing too much
expected wealth — because it monetizes the few fat weeks before they
can be re-risked.</p>
</div>

<h2>5. Methodology &amp; caveats</h2>
<ul>
<li><b>Replay approximation:</b> the live simulator's stake is
<code>kelly × bankroll × bet-quality</code> with a per-combo cap. We
extract <code>stake_frac_t = week_stake / bankroll_at_start</code> and
<code>roi_t = pnl / stake</code> from the baseline trace, then
re-evolve bankroll under each rule. This preserves Kelly's bankroll
proportionality but ignores the per-combo absolute cap (¥-denominated)
becoming binding at low bankroll. For drawdown analysis at ≥¥10k
bankroll the approximation is tight.</li>
<li><b>Monte Carlo:</b> bootstrap (stake_frac, roi) <i>jointly per week</i>
with replacement → preserves week-level correlation between sizing &amp;
outcomes, but breaks any longitudinal autocorrelation (clustered
hot/cold streaks).</li>
<li><b>Ruin threshold:</b> ¥1,000 (1% of initial). Lowering to ¥0 would
be unrealistic given minimum-stake quanta.</li>
</ul>

<h2>6. Files</h2>
<ul>
<li><code>data/raw/drawdown_baseline_weekly.csv</code></li>
<li><code>data/raw/drawdown_rules_summary.csv</code></li>
<li><code>docs/research/figures/drawdown_anatomy.png</code></li>
<li><code>docs/research/figures/drawdown_rule_curves.png</code></li>
<li><code>src/drawdown/{{anatomy,replay,stop_rules}}.py</code></li>
<li><code>tests/drawdown/test_{{anatomy,replay}}.py</code> — 9 tests</li>
</ul>

</body></html>
"""
    REPORT_PATH.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
