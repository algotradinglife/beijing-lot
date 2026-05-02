"""Glue: run all 14 variants × full sims, time-stratified, build HTML report.

Run with:  python -m src.dual_sweep.report
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

from src.dual_sweep.metrics import full_metrics
from src.dual_sweep.pareto_plot import (
    equity_overlay,
    pareto_scatter,
    small_multiples,
)
from src.dual_sweep.simulator import simulate_window
from src.dual_sweep.time_stratify import SUB_PERIODS, run_sub_periods
from src.dual_sweep.variants import build_all_variants


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCS_RES = os.path.join(REPO_ROOT, "docs", "research")
FIG_DIR = os.path.join(DOCS_RES, "figures")
OUT_HTML = os.path.join(DOCS_RES, "dual_archetype_report.html")
OUT_CSV = os.path.join(DOCS_RES, "dual_archetype_decision_table.csv")
B_NICHES_CSV = os.path.join(REPO_ROOT, "data", "raw", "archetype_B_niches.csv")


def _bb_curve(sim) -> np.ndarray:
    if sim.weekly.empty:
        return np.array([sim.initial_bankroll])
    return np.concatenate(([sim.initial_bankroll], sim.weekly["bankroll_end"].to_numpy()))


def _fmt_pct(x: float, dp: int = 1) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x*100:.{dp}f}%"


def _fmt_num(x: float, dp: int = 2) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:.{dp}f}"


def _fmt_yuan(x: float) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:,.0f}"


def run_full() -> None:
    os.makedirs(FIG_DIR, exist_ok=True)
    print("[dual_sweep] building variants...")
    variants, info = build_all_variants()
    print(f"  Archetype A picks: {info['n_a_picks']:,}, niches: {info['n_a_niches']}")
    print(f"  Archetype B picks: {info['n_b_picks']:,}, niches: {info['n_b_niches']}")
    print(f"  Archetype B threshold: {info['archetype_b_threshold']}")

    # Save Archetype B niches as required
    if not variants[1].surv_niches.empty:
        os.makedirs(os.path.dirname(B_NICHES_CSV), exist_ok=True)
        variants[1].surv_niches.to_csv(B_NICHES_CSV, index=False)

    # ---- Full-period sims (Track 4) -------------------------------------
    print("[dual_sweep] running 14 full-period simulations...")
    full_metrics_rows: list[dict] = []
    curves: dict[str, np.ndarray] = {}
    for v in variants:
        sim = simulate_window(
            v.qual, v.n_legs,
            initial_bankroll=100_000.0,
            test_only=False,  # use entire period; selection used train-only via niche disc
        )
        m = full_metrics(sim, v.name)
        m["archetype"] = v.archetype
        m["n_legs"] = v.n_legs
        m["sp_range"] = "[5,8]" if v.archetype == "A" else "[1.5,4.5]"
        full_metrics_rows.append(m)
        curves[v.name] = _bb_curve(sim)
        print(f"  {v.name}: weeks={m['n_weeks']}, hits={m['n_hits']}, "
              f"cum_roi={_fmt_pct(m['cum_roi'])}, "
              f"sharpe={_fmt_num(m['sharpe'])}, "
              f"calmar={_fmt_num(m['calmar'])}")

    metrics_df = pd.DataFrame(full_metrics_rows)
    # Reorder columns for the decision table
    decision_cols = [
        "variant", "archetype", "n_legs", "sp_range",
        "cagr", "cum_roi", "sharpe", "sortino", "calmar",
        "max_dd", "p5_weekly_roi", "final_bankroll",
        "mean_weekly_stake", "mean_weekly_stake_pct",
        "weekly_win_rate", "win_loss_ratio", "profit_factor",
        "n_weeks", "n_hits", "stake_cap_bind_pct", "max_losing_streak",
        "max_single_week_loss",
    ]
    decision_df = metrics_df[decision_cols].copy()
    decision_df = decision_df.sort_values("calmar", ascending=False, na_position="last")
    decision_df.to_csv(OUT_CSV, index=False)

    # ---- Time-stratified (Track 3) --------------------------------------
    print("[dual_sweep] time-stratified sub-period sims...")
    period_rows: list[dict] = []
    period_curves: dict[str, dict[str, np.ndarray]] = {p[0]: {} for p in SUB_PERIODS}
    for v in variants:
        for name, lo, hi in SUB_PERIODS:
            sim = simulate_window(
                v.qual, v.n_legs, initial_bankroll=100_000.0,
                expect_lo=lo, expect_hi=hi, test_only=False,
            )
            m = full_metrics(sim, f"{v.name}__{name}")
            m["archetype"] = v.archetype
            m["n_legs"] = v.n_legs
            m["period"] = name
            period_rows.append(m)
            period_curves[name][v.name] = _bb_curve(sim)
    period_df = pd.DataFrame(period_rows)

    # ---- Plots ----------------------------------------------------------
    pareto_path = os.path.join(FIG_DIR, "dual_archetype_pareto.png")
    eq_path = os.path.join(FIG_DIR, "dual_archetype_equity.png")
    sm_path = os.path.join(FIG_DIR, "dual_archetype_subperiods.png")
    pareto_scatter(metrics_df, pareto_path)
    equity_overlay(curves, eq_path,
                   title="Cumulative bankroll — 14 variants (start 100,000元)")
    small_multiples(period_curves, sm_path)

    # ---- HTML render ---------------------------------------------------
    html = render_html(
        info=info,
        variants=variants,
        decision_df=decision_df,
        full_df=metrics_df,
        period_df=period_df,
        b_niches=variants[1].surv_niches,
        pareto_path=os.path.relpath(pareto_path, DOCS_RES),
        equity_path=os.path.relpath(eq_path, DOCS_RES),
        small_path=os.path.relpath(sm_path, DOCS_RES),
    )
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[dual_sweep] report written to {OUT_HTML}")
    print(f"[dual_sweep] decision table → {OUT_CSV}")
    print(f"[dual_sweep] niches → {B_NICHES_CSV}")


# ---------------------------------------------------------------------------
# HTML rendering

CSS = """
:root {
  --bg:#fafaf7; --fg:#1a1a1a; --muted:#666;
  --accent:#b04a2f; --accent-soft:#f6ebe5;
  --warn:#a45a00; --warn-soft:#fdf3e3;
  --good:#2e6b4a; --good-soft:#e8f1ec;
  --bad:#8b2424; --bad-soft:#f6e8e8;
  --code-bg:#f0ede6; --border:#d8d3c7; --table-border:#c8c2b3;
}
* { box-sizing: border-box; }
body {
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",
              "PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  line-height:1.6; color:var(--fg); background:var(--bg);
  max-width:1100px; margin:0 auto; padding:32px 24px 80px; font-size:15px;
}
h1 { font-size:26px; margin-top:0; border-bottom:2px solid var(--accent); padding-bottom:10px; }
h2 { font-size:20px; margin-top:36px; color:var(--accent);
     border-bottom:1px solid var(--border); padding-bottom:6px; }
h3 { font-size:16px; margin-top:22px; }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:13px; }
th, td { border:1px solid var(--table-border); padding:5px 8px; text-align:left; }
th { background:var(--accent-soft); font-weight:600; }
tbody tr:nth-child(even) { background:rgba(0,0,0,0.02); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.good { color:var(--good); font-weight:600; }
td.bad  { color:var(--bad);  font-weight:600; }
.callout { border-left:4px solid var(--accent); background:var(--accent-soft);
           padding:10px 16px; margin:14px 0; border-radius:0 6px 6px 0; }
.callout.warn { border-color:var(--warn); background:var(--warn-soft); }
.callout.good { border-color:var(--good); background:var(--good-soft); }
.callout.bad  { border-color:var(--bad);  background:var(--bad-soft); }
.meta { color:var(--muted); font-size:13px; margin-bottom:24px; }
.cards { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:14px 0; }
.card  { border:1px solid var(--border); border-radius:6px; padding:12px 14px;
         background:#fff; }
.card h3 { margin-top:0; font-size:14px; color:var(--muted); text-transform:uppercase;
           letter-spacing:0.6px; }
.card .big { font-size:22px; font-weight:600; color:var(--accent); }
.tag { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px;
       background:var(--accent-soft); color:var(--accent); }
.tag.B { background:#e2e8ef; color:#324a6b; }
img { max-width:100%; border:1px solid var(--border); border-radius:4px; }
.highlight-row { background:#fff7e0 !important; font-weight:600; }
"""


def _row_class(rank: int) -> str:
    return "highlight-row" if rank < 3 else ""


def _decision_table_html(df: pd.DataFrame) -> str:
    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        cls = _row_class(i)
        rows.append(
            f'<tr class="{cls}">'
            f'<td>{r["variant"]} <span class="tag {"B" if r["archetype"]=="B" else "A"}">{r["archetype"]}</span></td>'
            f'<td>{r["sp_range"]}</td>'
            f'<td class="num">{_fmt_pct(r["cagr"])}</td>'
            f'<td class="num">{_fmt_pct(r["cum_roi"])}</td>'
            f'<td class="num">{_fmt_num(r["sharpe"])}</td>'
            f'<td class="num">{_fmt_num(r["sortino"])}</td>'
            f'<td class="num">{_fmt_num(r["calmar"])}</td>'
            f'<td class="num">{_fmt_pct(r["max_dd"])}</td>'
            f'<td class="num">{_fmt_pct(r["p5_weekly_roi"])}</td>'
            f'<td class="num">{_fmt_yuan(r["final_bankroll"])}</td>'
            f'<td class="num">{_fmt_pct(r["mean_weekly_stake_pct"])}</td>'
            f'<td class="num">{_fmt_pct(r["weekly_win_rate"])}</td>'
            f'<td class="num">{_fmt_pct(r["stake_cap_bind_pct"])}</td>'
            f'<td class="num">{int(r["n_hits"])}</td>'
            f'</tr>'
        )
    return (
        '<table><thead><tr>'
        '<th>Variant</th><th>SP</th><th>CAGR</th><th>Cum ROI</th>'
        '<th>Sharpe</th><th>Sortino</th><th>Calmar</th>'
        '<th>Max DD</th><th>P5 wk ROI</th><th>8yr final 元</th>'
        '<th>Mean wk stake %</th><th>Wkly win %</th>'
        '<th>Cap-bind %</th><th>#Hits</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table>'
    )


def _b_niche_table_html(b: pd.DataFrame) -> str:
    if b is None or b.empty:
        return "<p><em>No Archetype B niches survived (even at permissive 1.040).</em></p>"
    rows = []
    cols = ["stratum_str", "train_n", "train_k", "train_mean_q",
            "train_q_ci_lo", "test_n", "test_k", "test_mean_q"]
    for _, r in b.iterrows():
        rows.append(
            "<tr>"
            f"<td>{r['stratum_str']}</td>"
            f"<td class='num'>{int(r['train_n'])}</td>"
            f"<td class='num'>{int(r['train_k'])}</td>"
            f"<td class='num'>{_fmt_num(r['train_mean_q'],3)}</td>"
            f"<td class='num'>{_fmt_num(r['train_q_ci_lo'],3)}</td>"
            f"<td class='num'>{int(r['test_n'])}</td>"
            f"<td class='num'>{int(r['test_k'])}</td>"
            f"<td class='num'>{_fmt_num(r['test_mean_q'],3)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Stratum</th><th>Train n</th><th>Train k</th>"
        "<th>Train mean q</th><th>Train q CI lo</th>"
        "<th>Test n</th><th>Test k</th><th>Test mean q</th>"
        "</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _period_table_html(period_df: pd.DataFrame) -> str:
    pivot = period_df.pivot_table(
        index=["n_legs", "archetype"],
        columns="period",
        values="cagr",
        aggfunc="first",
    )
    rows = []
    for (n, a), r in pivot.iterrows():
        cells = "".join(f"<td class='num'>{_fmt_pct(r[c])}</td>" for c in pivot.columns)
        rows.append(f"<tr><td>N={n} {a}</td>{cells}</tr>")
    head = "<th>Variant</th>" + "".join(f"<th>{c}</th>" for c in pivot.columns)
    return (
        f"<p>Each cell = sub-period CAGR for a fresh 10万 sim "
        f"(period start = 100,000元, no cross-period compounding).</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def _capital_table_html(metrics_df: pd.DataFrame) -> str:
    rows = []
    for _, r in metrics_df.sort_values(["archetype", "n_legs"]).iterrows():
        flag = ""
        if r["archetype"] == "B" and r["mean_weekly_stake_pct"] > 0.30:
            flag = " <span class='tag' style='background:#f6e8e8;color:#8b2424'>cap-bound</span>"
        rows.append(
            "<tr>"
            f"<td>{r['variant']}{flag}</td>"
            f"<td class='num'>{_fmt_pct(r['mean_weekly_stake_pct'])}</td>"
            f"<td class='num'>{_fmt_yuan(r['mean_weekly_stake'])}</td>"
            f"<td class='num'>{_fmt_yuan(r['mean_weekly_pnl'])}</td>"
            f"<td class='num'>{_fmt_pct(r['stake_cap_bind_pct'])}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Variant</th>"
        "<th>Mean wk stake %BR</th><th>Mean wk stake 元</th>"
        "<th>Mean wk PnL 元</th><th>Cap-bind freq</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _verdict(decision_df: pd.DataFrame) -> str:
    top = decision_df.head(3).reset_index(drop=True)
    if top.empty:
        return "<p>No variant produced PnL.</p>"
    pick = top.iloc[0]
    a_best = decision_df[decision_df["archetype"] == "A"].iloc[0] \
        if (decision_df["archetype"] == "A").any() else None
    b_best = decision_df[decision_df["archetype"] == "B"].iloc[0] \
        if (decision_df["archetype"] == "B").any() else None
    lines = [
        f"<p><strong>Top pick by Calmar:</strong> {pick['variant']} "
        f"(SP {pick['sp_range']}) — CAGR {_fmt_pct(pick['cagr'])}, "
        f"Sharpe {_fmt_num(pick['sharpe'])}, Calmar {_fmt_num(pick['calmar'])}, "
        f"Max DD {_fmt_pct(pick['max_dd'])}, "
        f"final {_fmt_yuan(pick['final_bankroll'])}元.</p>"
    ]
    if a_best is not None:
        lines.append(
            f"<p><strong>Best Archetype A</strong>: {a_best['variant']} — "
            f"CAGR {_fmt_pct(a_best['cagr'])}, Sharpe {_fmt_num(a_best['sharpe'])}.</p>"
        )
    if b_best is not None:
        lines.append(
            f"<p><strong>Best Archetype B</strong>: {b_best['variant']} — "
            f"CAGR {_fmt_pct(b_best['cagr'])}, Sharpe {_fmt_num(b_best['sharpe'])}.</p>"
        )
    lines.append(
        "<h3>Kill criteria (forward live)</h3>"
        "<ul>"
        "<li>Realized 12-week rolling CAGR drops below −20%.</li>"
        "<li>Realized max DD exceeds the in-sample max DD by >50%.</li>"
        "<li>Niche stratum hit-rate diverges from in-sample by >30% over 200 legs.</li>"
        "<li>Weekly stake cap binds in &gt; 70% of weeks (capital-constrained).</li>"
        "</ul>"
    )
    return "\n".join(lines)


def render_html(
    *, info: dict, variants, decision_df, full_df, period_df,
    b_niches, pareto_path, equity_path, small_path,
) -> str:
    top3 = decision_df.head(3)
    a_best = decision_df[decision_df["archetype"] == "A"].iloc[0] \
        if (decision_df["archetype"] == "A").any() else None
    b_best = decision_df[decision_df["archetype"] == "B"].iloc[0] \
        if (decision_df["archetype"] == "B").any() else None
    pick = decision_df.iloc[0] if not decision_df.empty else None

    summary_card_a = (
        f"<div class='card'><h3>Best Archetype A</h3>"
        f"<div class='big'>{a_best['variant']}</div>"
        f"<p>CAGR <b>{_fmt_pct(a_best['cagr'])}</b> · Sharpe <b>{_fmt_num(a_best['sharpe'])}</b><br>"
        f"Calmar {_fmt_num(a_best['calmar'])} · Max DD {_fmt_pct(a_best['max_dd'])}</p></div>"
    ) if a_best is not None else ""
    summary_card_b = (
        f"<div class='card'><h3>Best Archetype B</h3>"
        f"<div class='big'>{b_best['variant']}</div>"
        f"<p>CAGR <b>{_fmt_pct(b_best['cagr'])}</b> · Sharpe <b>{_fmt_num(b_best['sharpe'])}</b><br>"
        f"Calmar {_fmt_num(b_best['calmar'])} · Max DD {_fmt_pct(b_best['max_dd'])}</p></div>"
    ) if b_best is not None else ""
    summary_card_pick = (
        f"<div class='card'><h3>Recommendation</h3>"
        f"<div class='big'>{pick['variant']}</div>"
        f"<p>{pick['sp_range']} · 8yr final <b>{_fmt_yuan(pick['final_bankroll'])}元</b><br>"
        f"Calmar <b>{_fmt_num(pick['calmar'])}</b> · Mean wk stake {_fmt_pct(pick['mean_weekly_stake_pct'])}</p></div>"
    ) if pick is not None else ""

    cards = (
        f"<div class='cards'>{summary_card_a}{summary_card_b}{summary_card_pick}</div>"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    body_parts = [
        f"<h1>北单 双原型 (Archetype A/B) 量化评估</h1>",
        f"<div class='meta'>Generated {timestamp} · 8-year full 3-SP data ({info['n_a_picks'] + info['n_b_picks']:,} qualifying legs total) · 1/4-Kelly 10万元 bankroll · 25% weekly cap · 0.5% per-combo cap</div>",
        "<h2>1. Executive summary</h2>", cards,
        "<div class='callout'>",
        f"<strong>Archetype A</strong> (SP[5,8], rare-hit): {info['n_a_niches']} surviving niches, "
        f"{info['n_a_picks']:,} qualifying legs.<br>"
        f"<strong>Archetype B</strong> (SP[1.5,4.5], frequent-hit): {info['n_b_niches']} surviving niches "
        f"({info['archetype_b_threshold']}), {info['n_b_picks']:,} qualifying legs.</div>",

        "<h2>2. Track 1 — Archetype B surviving niches</h2>",
        f"<p>Threshold used: <code>{info['archetype_b_threshold']}</code></p>",
        _b_niche_table_html(b_niches),

        "<h2>3. Master decision table (Track 7)</h2>",
        "<p>Sorted by Calmar (CAGR / |Max DD|). Top-3 highlighted.</p>",
        _decision_table_html(decision_df),

        "<h2>4. Pareto: hit-rate × P/L (Track 5)</h2>",
        f"<img src='{pareto_path}' alt='Pareto scatter'>",
        "<p>X = weekly win rate · Y = avg-win/|avg-loss| · size = cum ROI · color = Sharpe.</p>",

        "<h2>5. Time-period stratification (Track 3)</h2>",
        _period_table_html(period_df),

        "<h2>6. Cumulative equity curves (10万元 start)</h2>",
        f"<img src='{equity_path}' alt='Equity curves'>",

        "<h2>7. Sub-period equity curves (small multiples)</h2>",
        f"<img src='{small_path}' alt='Sub-period equity'>",

        "<h2>8. Capital constraint analysis (Track 6)</h2>",
        _capital_table_html(full_df),

        "<h2>9. Honest verdict</h2>",
        _verdict(decision_df),
    ]

    html = (
        f"<!DOCTYPE html>\n<html lang='zh-CN'><head>"
        f"<meta charset='UTF-8'>"
        f"<title>北单 双原型评估</title>"
        f"<style>{CSS}</style></head><body>"
        + "\n".join(body_parts)
        + "</body></html>"
    )
    return html


if __name__ == "__main__":
    run_full()
