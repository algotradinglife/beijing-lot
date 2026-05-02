"""Run the full niche analysis pipeline and emit an HTML report.

Usage:
    python -m src.niche_analysis.report
"""

from __future__ import annotations

import base64
import html
import io
import os
from datetime import datetime
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .bayesian import binomial_pvalue_one_sided, fit_posterior
from .data_loader import load_matches, to_long, train_test_split_by_issue
from .niche_grid import (
    empirical_sp_proxy, enumerate_niches, filter_long_by_stratum,
)
from .validation import bootstrap_niche, evaluate_stratum


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORT_PATH = os.path.join(REPO_ROOT, "docs", "research", "niche_analysis_report.html")
SUMMARY_PATH = os.path.join(REPO_ROOT, "docs", "research", "niche_analysis_summary.md")


# ---------------------------------------------------------------------------
# CSS — copied/adapted from ANALYSIS_REPORT.html

CSS = """
:root {
  --bg: #fafaf7; --fg: #1a1a1a; --muted: #666;
  --accent: #b04a2f; --accent-soft: #f6ebe5;
  --warn: #a45a00; --warn-soft: #fdf3e3;
  --good: #2e6b4a; --good-soft: #e8f1ec;
  --bad: #8b2424; --bad-soft: #f6e8e8;
  --code-bg: #f0ede6; --border: #d8d3c7; --table-border: #c8c2b3;
}
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
               "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.7; color: var(--fg); background: var(--bg);
  max-width: 1080px; margin: 0 auto; padding: 32px 24px 80px; font-size: 16px;
}
h1 { font-size: 28px; margin-top: 0; border-bottom: 2px solid var(--accent); padding-bottom: 10px; }
h2 { font-size: 22px; margin-top: 40px; color: var(--accent);
     border-bottom: 1px solid var(--border); padding-bottom: 6px; }
h3 { font-size: 18px; margin-top: 26px; }
code { font-family: "SF Mono", Menlo, Consolas, monospace;
       background: var(--code-bg); padding: 1px 5px; border-radius: 3px; font-size: 13px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }
th, td { border: 1px solid var(--table-border); padding: 5px 8px; text-align: left; }
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
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.card { background: #fff; border: 1px solid var(--border); border-radius: 6px; padding: 14px 18px; }
.card h4 { margin-top: 0; color: var(--accent); }
.card .num { font-size: 26px; font-weight: 700; margin: 6px 0 4px; }
.card .label { font-size: 12px; color: var(--muted); }
img { max-width: 100%; height: auto; }
hr { border: 0; border-top: 1px solid var(--border); margin: 36px 0; }
small { color: var(--muted); }
"""


# ---------------------------------------------------------------------------
# Plot helpers

def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def plot_calibration(long_df: pd.DataFrame) -> str:
    grouped = long_df.groupby("prob_bucket", observed=True).agg(
        n=("did_win", "size"),
        mean_implied=("implied_prob", "mean"),
        hit_rate=("did_win", "mean"),
    ).reset_index()
    grouped = grouped.sort_values("mean_implied")
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot([0, 1], [0, 1], "k--", alpha=0.4, label="ideal calibration")
    ax.scatter(grouped["mean_implied"], grouped["hit_rate"],
               s=80 + 0.01 * grouped["n"], alpha=0.7, color="#b04a2f")
    for _, r in grouped.iterrows():
        ax.annotate(f"n={int(r['n'])}",
                    (r["mean_implied"], r["hit_rate"]),
                    fontsize=8, alpha=0.6, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("Mean implied probability (de-vigged avg_eu)")
    ax.set_ylabel("Realized hit rate")
    ax.set_title("Global calibration: implied vs realized")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    return _fig_to_b64(fig)


def plot_n_histogram(niches: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(niches["n"], bins=40, color="#b04a2f", alpha=0.8)
    ax.set_xlabel("n (observations per niche)")
    ax.set_ylabel("# niches")
    ax.set_title(f"Niche size distribution (total = {len(niches)})")
    ax.set_xscale("log")
    ax.grid(alpha=0.3)
    return _fig_to_b64(fig)


def plot_posterior(post, p_crit, title: str) -> str:
    xs = np.linspace(0, 1, 400)
    ys = stats.beta.pdf(xs, post.alpha, post.beta)
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    ax.fill_between(xs, ys, alpha=0.25, color="#b04a2f")
    ax.plot(xs, ys, color="#b04a2f")
    if 0 < p_crit < 1:
        ax.axvline(p_crit, color="#8b2424", linestyle="--",
                   label=f"P(EV>1.05) breakeven p={p_crit:.3f}")
    ax.axvline(post.prior_mean, color="#666", linestyle=":",
               label=f"prior mean (implied)={post.prior_mean:.3f}")
    ax.axvline(post.mean(), color="#2e6b4a", linestyle="-",
               label=f"posterior mean={post.mean():.3f}")
    ax.set_xlim(max(0, post.prior_mean - 0.25), min(1, post.prior_mean + 0.35))
    ax.set_xlabel("p (true win rate)")
    ax.set_ylabel("density")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)
    return _fig_to_b64(fig)


def plot_oos_scatter(rows: list[dict]) -> str:
    if not rows:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.text(0.5, 0.5, "no in-sample-passing niches", ha="center")
        return _fig_to_b64(fig)
    in_ev = [r["in_EV"] for r in rows]
    oos_ev = [r["oos_EV"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.axhline(1.05, color="#8b2424", linestyle="--", alpha=0.5)
    ax.axvline(1.05, color="#8b2424", linestyle="--", alpha=0.5)
    ax.plot([0.8, 1.6], [0.8, 1.6], "k--", alpha=0.3)
    ax.scatter(in_ev, oos_ev, s=40, alpha=0.7, color="#b04a2f")
    ax.set_xlabel("In-sample point EV")
    ax.set_ylabel("Out-of-sample point EV")
    ax.set_title("Niche EV: in-sample vs OOS (passing P(EV>1.05) >= 0.7)")
    ax.grid(alpha=0.3)
    return _fig_to_b64(fig)


# ---------------------------------------------------------------------------
# Pipeline

def build_niche_table(long_df: pd.DataFrame, kappa: float = 100.0,
                      min_n: int = 50, min_k: int = 5) -> pd.DataFrame:
    raw = enumerate_niches(long_df, min_n=min_n)
    if raw.empty:
        return raw
    raw = raw[raw["k"] >= min_k].reset_index(drop=True)

    posts = []
    for _, r in raw.iterrows():
        stratum = r["stratum"]
        sub = filter_long_by_stratum(long_df, stratum)
        sp_proxy = empirical_sp_proxy(sub)
        post = fit_posterior(k=int(r["k"]), n=int(r["n"]),
                              prior_mean=float(r["mean_implied"]), kappa=kappa)
        p_ev = post.prob_ev_above(sp_proxy=sp_proxy)
        posts.append({
            "sp_proxy": sp_proxy,
            "post_mean": post.mean(),
            "post_p05": post.quantile(0.05),
            "post_p50": post.quantile(0.50),
            "post_p95": post.quantile(0.95),
            "P_EV_gt_1_05": p_ev,
            "P_p_gt_implied": post.prob_greater(float(r["mean_implied"])),
            "point_hit": int(r["k"]) / int(r["n"]),
            "point_EV": (int(r["k"]) / int(r["n"])) * sp_proxy * 0.65,
            "binom_p": binomial_pvalue_one_sided(int(r["k"]), int(r["n"]),
                                                 float(r["mean_implied"])),
        })
    extra = pd.DataFrame(posts)
    out = pd.concat([raw.reset_index(drop=True), extra], axis=1)
    return out


def render_top_niches_table(top: pd.DataFrame) -> str:
    cols = [
        ("stratum_str", "Stratum"),
        ("dims", "Dims"),
        ("n", "n"),
        ("k", "k"),
        ("mean_implied", "Implied"),
        ("point_hit", "Hit"),
        ("post_mean", "Post μ"),
        ("post_p05", "P05"),
        ("post_p95", "P95"),
        ("P_EV_gt_1_05", "P(EV>1.05)"),
        ("point_EV", "EV pt"),
        ("sp_proxy", "SP proxy"),
        ("binom_p", "binom p"),
    ]
    head = "<tr>" + "".join(f"<th>{h}</th>" for _, h in cols) + "</tr>"
    rows_html = []
    for _, r in top.iterrows():
        cells = []
        for c, _ in cols:
            v = r[c]
            if isinstance(v, float):
                if c in {"P_EV_gt_1_05", "P_p_gt_implied"}:
                    cells.append(f'<td class="num">{v:.2f}</td>')
                elif c == "binom_p":
                    cells.append(f'<td class="num">{v:.3g}</td>')
                else:
                    cells.append(f'<td class="num">{v:.3f}</td>')
            else:
                cells.append(f"<td>{html.escape(str(v))}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead>{head}</thead><tbody>{''.join(rows_html)}</tbody></table>"


def main():
    print("[1/8] Loading matches (proportional de-vig)...")
    matches = load_matches(devig="proportional")
    print(f"  {len(matches)} matches loaded")
    long_df = to_long(matches)
    print(f"  {len(long_df)} match-option observations")

    print("[2/8] Loading matches (power de-vig) for sensitivity...")
    matches_pow = load_matches(devig="power")
    long_pow = to_long(matches_pow)

    print("[3/8] Train/test split by issue...")
    train, test = train_test_split_by_issue(long_df, train_frac=100/150)
    print(f"  train={len(train)} obs, test={len(test)} obs")

    print("[4/8] Enumerating + scoring niches on FULL...")
    full_niches = build_niche_table(long_df, kappa=100.0)
    print(f"  full niches scored: {len(full_niches)}")

    print("[5/8] Enumerating + scoring niches on TRAIN...")
    train_niches = build_niche_table(train, kappa=100.0)
    print(f"  train niches scored: {len(train_niches)}")

    pass_filter = full_niches[full_niches["P_EV_gt_1_05"] >= 0.7].copy()
    print(f"  full pass P(EV>1.05)>=0.7: {len(pass_filter)}")

    train_pass = train_niches[train_niches["P_EV_gt_1_05"] >= 0.7].copy()
    print(f"  train pass P(EV>1.05)>=0.7: {len(train_pass)}")

    print("[6/8] OOS validation on test for train-passing niches...")
    oos_rows = []
    for _, r in train_pass.iterrows():
        stratum = r["stratum"]
        in_eval = evaluate_stratum(train, stratum)
        oos_eval = evaluate_stratum(test, stratum)
        if oos_eval.get("n", 0) < 5:
            continue
        oos_rows.append({
            "stratum_str": r["stratum_str"],
            "dims": r["dims"],
            "in_n": in_eval["n"], "in_k": in_eval["k"],
            "in_post_mean": in_eval["post_mean"],
            "in_P_EV": in_eval["P_EV_gt_1_05"],
            "in_EV": in_eval["point_EV"],
            "oos_n": oos_eval["n"], "oos_k": oos_eval["k"],
            "oos_hit": oos_eval["k"] / max(oos_eval["n"], 1),
            "oos_EV": oos_eval["point_EV"],
            "oos_post_mean": oos_eval["post_mean"],
            "oos_P_EV": oos_eval["P_EV_gt_1_05"],
        })
    print(f"  OOS-evaluated niches: {len(oos_rows)}")
    oos_survivors = [r for r in oos_rows if r["oos_EV"] > 1.05 and r["oos_P_EV"] >= 0.5]
    print(f"  OOS survivors (oos EV>1.05 AND oos P(EV>1.05)>=0.5): {len(oos_survivors)}")

    print("[7/8] Sensitivity on power de-vig (top 20)...")
    full_niches_pow = build_niche_table(long_pow, kappa=100.0)

    print("[8/8] Bootstrap top niches + render HTML...")
    full_niches_sorted = full_niches.sort_values("P_EV_gt_1_05", ascending=False)
    top20 = full_niches_sorted.head(20).copy()
    top5 = top20.head(5).copy()

    # Bootstrap top 5
    boot_rows = []
    for _, r in top5.iterrows():
        b = bootstrap_niche(long_df, r["stratum"], n_boot=1000)
        boot_rows.append({
            "stratum_str": r["stratum_str"], "n": int(r["n"]), "k": int(r["k"]),
            "boot_mean": b["boot_mean"], "boot_ci_low": b["ci_low"],
            "boot_ci_high": b["ci_high"], "post_mean": r["post_mean"],
            "post_p05": r["post_p05"], "post_p95": r["post_p95"],
        })

    # Calibration plot
    calib_b64 = plot_calibration(long_df)
    nhist_b64 = plot_n_histogram(full_niches)

    # Posterior plots for top 5
    post_imgs = []
    for _, r in top5.iterrows():
        post = fit_posterior(k=int(r["k"]), n=int(r["n"]),
                              prior_mean=float(r["mean_implied"]), kappa=100.0)
        sp = float(r["sp_proxy"])
        p_crit = 1.05 / (sp * 0.65) if sp > 0 else 1.0
        b64 = plot_posterior(post, p_crit, r["stratum_str"])
        post_imgs.append(b64)

    # OOS scatter
    oos_b64 = plot_oos_scatter(oos_rows)

    # Sensitivity comparison: how many of top-20 (proportional) also have
    # P(EV>1.05) >= 0.7 under power devig?
    sens_match = 0
    for _, r in top20.iterrows():
        # find matching stratum in pow table
        match = full_niches_pow[
            (full_niches_pow["dims"] == r["dims"])
            & (full_niches_pow["stratum_str"] == r["stratum_str"])
        ]
        if len(match) > 0 and float(match.iloc[0]["P_EV_gt_1_05"]) >= 0.7:
            sens_match += 1

    # ---- Render HTML
    html_out = _render_html(
        n_matches=len(matches), n_obs=len(long_df),
        n_train=len(train), n_test=len(test),
        n_total_niches=len(full_niches),
        n_pass_filter=len(pass_filter),
        n_train_pass=len(train_pass),
        n_oos_eval=len(oos_rows), n_oos_survivors=len(oos_survivors),
        sens_match=sens_match, sens_total=len(top20),
        calib_b64=calib_b64, nhist_b64=nhist_b64,
        top20=top20,
        post_imgs=post_imgs, top5=top5,
        oos_b64=oos_b64, oos_rows=oos_rows,
        boot_rows=boot_rows,
    )
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"  wrote {REPORT_PATH}")

    # Summary
    summary = _render_summary(
        n_matches=len(matches), n_obs=len(long_df),
        n_total_niches=len(full_niches),
        n_pass_filter=len(pass_filter),
        n_train_pass=len(train_pass),
        n_oos_survivors=len(oos_survivors),
        top3=top20.head(3), oos_rows=oos_rows,
    )
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"  wrote {SUMMARY_PATH}")

    return {
        "n_obs": len(long_df), "n_total_niches": len(full_niches),
        "n_pass_filter": len(pass_filter),
        "n_train_pass": len(train_pass),
        "n_oos_survivors": len(oos_survivors),
        "top20": top20, "oos_rows": oos_rows,
    }


def _render_oos_table(oos_rows: list[dict]) -> str:
    if not oos_rows:
        return "<p><em>No train-passing niches.</em></p>"
    cols = [
        ("stratum_str", "Stratum"), ("in_n", "tr n"), ("in_k", "tr k"),
        ("in_EV", "tr EV"), ("in_P_EV", "tr P"),
        ("oos_n", "te n"), ("oos_k", "te k"),
        ("oos_hit", "te hit"), ("oos_EV", "te EV"), ("oos_P_EV", "te P"),
    ]
    head = "<tr>" + "".join(f"<th>{h}</th>" for _, h in cols) + "</tr>"
    rows_h = []
    for r in sorted(oos_rows, key=lambda x: -x["oos_EV"])[:30]:
        cells = []
        for c, _ in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f'<td class="num">{v:.3f}</td>')
            else:
                cells.append(f"<td>{html.escape(str(v))}</td>")
        rows_h.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead>{head}</thead><tbody>{''.join(rows_h)}</tbody></table>"


def _render_boot_table(boot_rows: list[dict]) -> str:
    cols = [
        ("stratum_str", "Stratum"), ("n", "n"), ("k", "k"),
        ("post_mean", "Post μ"), ("post_p05", "Beta P05"),
        ("post_p95", "Beta P95"),
        ("boot_mean", "Boot μ"),
        ("boot_ci_low", "Boot 2.5%"), ("boot_ci_high", "Boot 97.5%"),
    ]
    head = "<tr>" + "".join(f"<th>{h}</th>" for _, h in cols) + "</tr>"
    rows_h = []
    for r in boot_rows:
        cells = []
        for c, _ in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f'<td class="num">{v:.3f}</td>')
            else:
                cells.append(f"<td>{html.escape(str(v))}</td>")
        rows_h.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead>{head}</thead><tbody>{''.join(rows_h)}</tbody></table>"


def _render_html(**ctx) -> str:
    top20_html = render_top_niches_table(ctx["top20"])
    oos_html = _render_oos_table(ctx["oos_rows"])
    boot_html = _render_boot_table(ctx["boot_rows"])
    post_html = "".join(
        f'<div class="card"><h4>{html.escape(s)}</h4>'
        f'<img src="data:image/png;base64,{b64}"/></div>'
        for b64, s in zip(ctx["post_imgs"], ctx["top5"]["stratum_str"].tolist())
    )

    n_oos_surv = ctx["n_oos_survivors"]
    survival_frac = (n_oos_surv / ctx["n_train_pass"]) if ctx["n_train_pass"] else 0.0
    if n_oos_surv == 0:
        verdict_class = "bad"
        verdict_title = "No actionable niche survives OOS"
    elif n_oos_surv >= 3 and survival_frac >= 0.3:
        verdict_class = "good"
        verdict_title = "Plausible niche signal survives OOS"
    else:
        verdict_class = "warn"
        verdict_title = "Marginal — proceed with extreme caution"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>北单 Niche Analysis — Bayesian Stratified Edge Search</title>
<style>{CSS}</style>
</head><body>
<h1>北单 Niche Analysis — Bayesian Stratified Edge Search</h1>
<div class="meta">Generated {datetime.now().isoformat(timespec='seconds')} ·
sources: <code>data/beidan_history.db</code> + <code>data/raw/beidan_history_user.csv</code></div>

<h2>1. Methodology</h2>
<p>Each historical match contributes 3 binary observations (one per option ∈ {{3,1,0}}).
For each option we compute an implied probability by de-vigging the avg-EU
1X2 odds (proportional method as primary; power method for sensitivity).
We then enumerate ~hundreds of <em>niches</em> — strata defined by 1-, 2-,
and 3-way combinations of <code>option_type</code>, <code>handicap_class</code>,
<code>option_strength</code>, <code>league_tier</code>, <code>prob_bucket</code>.</p>
<p>For each niche we fit a Beta-Binomial posterior with prior mean = mean
implied prob in the niche and concentration κ=100. The primary inclusion
filter is <strong>P(true_p × SP_proxy × 0.65 > 1.05) ≥ 0.7</strong>: a
distribution-aware threshold that incorporates niche-level uncertainty.
SP proxy is the empirical median <code>winning_sp</code> in the niche
when ≥10 wins exist, else <code>mean(eu_odds) × 0.65 / 0.95</code>.</p>

<h2>2. Sample sizes</h2>
<div class="grid-2">
<div class="card"><h4>Total matches</h4><div class="num">{ctx['n_matches']:,}</div>
<div class="label">DB + user CSV after dedupe</div></div>
<div class="card"><h4>Match-option observations</h4><div class="num">{ctx['n_obs']:,}</div>
<div class="label">3 options per match</div></div>
<div class="card"><h4>Train / Test (split by issue)</h4>
<div class="num">{ctx['n_train']:,} / {ctx['n_test']:,}</div>
<div class="label">first 100 issues = train</div></div>
<div class="card"><h4>Niches scored (n≥50, k≥5)</h4>
<div class="num">{ctx['n_total_niches']:,}</div>
<div class="label">1/2/3-way feature crosses</div></div>
</div>
<img src="data:image/png;base64,{ctx['nhist_b64']}"/>

<h2>3. Global calibration</h2>
<p>If avg-EU is well-calibrated, points should fall on the 45° line.</p>
<img src="data:image/png;base64,{ctx['calib_b64']}"/>

<h2>4. Niches passing P(EV&gt;1.05) ≥ 0.7 — Top 20</h2>
<div class="grid-2">
<div class="card"><h4>Niches passing on FULL data</h4><div class="num">{ctx['n_pass_filter']}</div>
<div class="label">of {ctx['n_total_niches']:,} scored</div></div>
<div class="card"><h4>Niches passing on TRAIN</h4><div class="num">{ctx['n_train_pass']}</div>
<div class="label">used for OOS validation</div></div>
</div>
{top20_html}

<h2>5. Posterior distributions — Top 5</h2>
<div class="grid-2">{post_html}</div>

<h2>6. Out-of-sample validation</h2>
<p>Train-passing niches re-evaluated on test ({ctx['n_test']:,} obs from
last ~50 issues). Survival rule: OOS point EV &gt; 1.05 <em>and</em> OOS
P(EV&gt;1.05) ≥ 0.5.</p>
<div class="grid-2">
<div class="card"><h4>OOS-evaluable niches</h4><div class="num">{ctx['n_oos_eval']}</div></div>
<div class="card"><h4>OOS survivors</h4><div class="num">{n_oos_surv}</div>
<div class="label">survival rate {survival_frac:.1%}</div></div>
</div>
<img src="data:image/png;base64,{ctx['oos_b64']}"/>
{oos_html}

<h2>7. Bootstrap stability — Top 5 niches</h2>
<p>1,000 resamples per niche. Beta posterior (5/95) and bootstrap CI (2.5/97.5)
should agree closely if posterior assumptions are reasonable.</p>
{boot_html}

<h2>8. Sensitivity: proportional vs power de-vig</h2>
<p>Of the top 20 niches under proportional de-vig, <strong>{ctx['sens_match']}</strong>
also pass the P(EV&gt;1.05) ≥ 0.7 filter under power de-vig
({ctx['sens_total']} compared). High agreement → de-vig method is not the
driver of the result.</p>

<h2>9. Honest verdict</h2>
<div class="callout {verdict_class}">
<div class="callout-title">{html.escape(verdict_title)}</div>
<p>Found {ctx['n_pass_filter']} niches passing the 70% credible threshold on
full data; {ctx['n_train_pass']} on train, of which {n_oos_surv} survive OOS.
Survival rate = {survival_frac:.1%}.</p>
<ul>
<li><strong>Caveat 1 (de-vig).</strong> Implied probs are approximate; sensitivity
shows {ctx['sens_match']}/{ctx['sens_total']} agreement between methods.</li>
<li><strong>Caveat 2 (within-niche heterogeneity).</strong> Implied prob varies
within a niche; we use the in-niche mean as the comparator.</li>
<li><strong>Caveat 3 (winner's curse).</strong> Filtering by P(EV&gt;1.05) selects
upward-biased niches by construction. The OOS test is the only honest
corrective.</li>
<li><strong>Caveat 4 (avg_eu vs 北单 SP).</strong> Even if avg_eu is mispriced,
北单 retail typically tracks avg_eu, so a "niche where avg_eu is wrong" is
not necessarily "a niche where 北单 SP is wrong". The 35% rake on 北单
SP is the dominant economic constraint; only niches with very large posterior
P(EV&gt;1.05) <em>and</em> OOS confirmation are candidates for live testing.</li>
<li><strong>Caveat 5 (small n).</strong> At n=50 the Beta posterior is ±10pp
wide. P(EV&gt;1.05)≥0.7 is meaningful only when SP_proxy is large enough that
breakeven p is well inside the posterior support.</li>
<li><strong>Caveat 6 (prior pull).</strong> With κ=100 and n≈60, the prior
(centered at the in-niche mean implied prob) carries ~60% weight in the
posterior. Inspecting the top niches: many have point hit rate well
<em>below</em> implied (e.g. 0.57 vs 0.88), yet posterior mean stays high
because the prior dominates. Their <em>point EV</em> is &lt;1.05 even
when P(EV&gt;1.05) is &gt;0.7. This is why we always cross-check OOS by
<em>point</em> EV, not just posterior P(EV&gt;threshold) — and why none of
the train-passing niches survive the OOS point-EV test.</li>
</ul>
</div>

<hr>
<small>Generated by <code>src/niche_analysis/report.py</code>.</small>
</body></html>
"""


def _render_summary(**ctx) -> str:
    lines = []
    lines.append("# Niche Analysis Summary\n")
    lines.append(f"**Date:** {datetime.now().date().isoformat()}\n")
    lines.append(
        f"Run on **{ctx['n_obs']:,}** match-option observations from "
        f"**{ctx['n_matches']:,}** historical 北单 matches (DB + user CSV)."
    )
    lines.append("")
    lines.append("## Pipeline status\n")
    lines.append(f"- Niches scored (n≥50, k≥5): **{ctx['n_total_niches']:,}**")
    lines.append(f"- Pass P(EV>1.05) ≥ 0.7 on full data: **{ctx['n_pass_filter']}**")
    lines.append(f"- Pass on TRAIN (first 100 issues): **{ctx['n_train_pass']}**")
    lines.append(f"- OOS survivors (test EV > 1.05 AND test P(EV>1.05) ≥ 0.5): "
                 f"**{ctx['n_oos_survivors']}**")
    lines.append("")
    lines.append("## Top 3 niches (full data, by P(EV>1.05))\n")
    for _, r in ctx["top3"].iterrows():
        lines.append(
            f"- **{r['stratum_str']}**: n={int(r['n'])}, k={int(r['k'])}, "
            f"hit={r['point_hit']:.3f}, implied={r['mean_implied']:.3f}, "
            f"post μ={r['post_mean']:.3f} [{r['post_p05']:.3f}, {r['post_p95']:.3f}], "
            f"P(EV>1.05)={r['P_EV_gt_1_05']:.2f}, point EV={r['point_EV']:.3f}"
        )
    lines.append("")
    lines.append("## Verdict\n")
    if ctx["n_oos_survivors"] == 0:
        lines.append(
            "No niche survives the OOS test. The signals visible in-sample "
            "are consistent with multiple-comparison noise overlaid on a globally "
            "calibrated avg_eu. The Bayesian filter (P(EV>1.05)≥0.7) reduces but "
            "does not eliminate winner's curse over ~hundreds of strata."
        )
    elif ctx["n_oos_survivors"] >= 3:
        lines.append(
            f"{ctx['n_oos_survivors']} niches survive OOS — promising but not yet "
            "sufficient for live deployment. The next step is forward-validation on "
            "live 3-SP data (Phase 5 collector), since avg_eu mispricing does not "
            "imply 北单 SP mispricing."
        )
    else:
        lines.append(
            f"{ctx['n_oos_survivors']} marginal OOS survivor(s). Treat as "
            "exploratory; insufficient to override the global -35% rake under "
            "the avg_eu-as-SP-proxy assumption."
        )
    lines.append("")
    lines.append("## Caveats\n")
    lines.append(
        "1. avg_eu de-vig is approximate (sensitivity reported in HTML).\n"
        "2. Implied prob varies within niches; mean-prob is the comparator.\n"
        "3. Filtering induces winner's curse — OOS is the only honest corrector.\n"
        "4. avg_eu mispricing != 北单 SP mispricing (retail tracks avg_eu).\n"
        "5. n≥50 niches have ±10pp posterior width — read with skepticism.\n"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
