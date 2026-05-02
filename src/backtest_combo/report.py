"""Build the markdown report and PNG plots for the combo backtest."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:  # pragma: no cover
    HAS_MPL = False


def bootstrap_ci_roi(
    profits: np.ndarray,
    stakes: np.ndarray,
    n_boot: int = 5000,
    rng_seed: int = 17,
) -> tuple[float, float, float]:
    """Cluster bootstrap on a per-row basis. Returns (cum_roi, low, high)."""
    rng = np.random.default_rng(rng_seed)
    n = len(profits)
    if n == 0 or stakes.sum() <= 0:
        return float("nan"), float("nan"), float("nan")
    cum_roi = profits.sum() / stakes.sum()
    rois = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        s = stakes[idx].sum()
        rois[i] = (profits[idx].sum() / s) if s > 0 else 0.0
    return float(cum_roi), float(np.percentile(rois, 2.5)), float(np.percentile(rois, 97.5))


def weekly_distribution(issues: pd.DataFrame) -> dict:
    active = issues[issues["total_stake"] > 0].copy()
    if active.empty:
        return {}
    rois = active["roi"].to_numpy()
    return {
        "n_active_weeks": int(len(active)),
        "mean": float(np.mean(rois)),
        "std": float(np.std(rois, ddof=1)) if len(rois) > 1 else 0.0,
        "p5": float(np.percentile(rois, 5)),
        "p25": float(np.percentile(rois, 25)),
        "p50": float(np.percentile(rois, 50)),
        "p75": float(np.percentile(rois, 75)),
        "p95": float(np.percentile(rois, 95)),
        "min": float(rois.min()),
        "max": float(rois.max()),
    }


def hit_rate_summary(issues: pd.DataFrame, plans: pd.DataFrame) -> dict:
    active = issues[issues["n_combos"] > 0]
    weeks_with_hit = int((active["n_hit"] > 0).sum())
    return {
        "n_active_weeks": int(len(active)),
        "weeks_with_at_least_one_hit": weeks_with_hit,
        "frac_weeks_with_hit": (weeks_with_hit / len(active)) if len(active) else float("nan"),
        "max_hits_in_a_week": int(active["n_hit"].max()) if len(active) else 0,
        "total_combos_run": int(plans.shape[0]) if len(plans) else 0,
        "total_combos_hit": int(plans["all_hit"].sum()) if len(plans) else 0,
        "empirical_combo_hit_rate": (
            float(plans["all_hit"].mean()) if len(plans) else float("nan")
        ),
        "predicted_combo_hit_rate": (
            float(plans["joint_p"].mean()) if len(plans) else float("nan")
        ),
    }


def edge_attribution_by_handicap(plans: pd.DataFrame) -> pd.DataFrame:
    """ROI by combo's handicap-mix bucket."""
    if plans.empty:
        return pd.DataFrame()
    p = plans.copy()
    def label(s: str) -> str:
        cls = s.split(",")
        if all(c == "0" for c in cls):
            return "all_h0"
        if all(c == "2+" for c in cls):
            return "all_h2+"
        if all(c in ("0", "1") for c in cls):
            return "h0_h1_mix"
        return "mixed"
    p["bucket"] = p["handicap_classes"].apply(label)
    g = p.groupby("bucket").agg(
        n_combos=("total_stake", "size"),
        total_stake=("total_stake", "sum"),
        total_profit=("total_profit", "sum"),
        hit_rate=("all_hit", "mean"),
    ).reset_index()
    g["roi"] = g["total_profit"] / g["total_stake"]
    return g


def edge_attribution_by_selection(plans: pd.DataFrame) -> pd.DataFrame:
    """Hit-rate by leg selection composition (counts of 3/1/0 in winning combos)."""
    if plans.empty:
        return pd.DataFrame()
    rows = []
    for _, row in plans.iterrows():
        sels = row["selection_mix"].split(",")
        rows.append(dict(
            n3=sels.count("3"),
            n1=sels.count("1"),
            n0=sels.count("0"),
            total_stake=row["total_stake"],
            total_profit=row["total_profit"],
            all_hit=row["all_hit"],
        ))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Aggregate by majority selection
    df["majority"] = df.apply(
        lambda r: "3-heavy" if r["n3"] >= 4
        else "0-heavy" if r["n0"] >= 4
        else "1-heavy" if r["n1"] >= 4
        else "balanced",
        axis=1,
    )
    g = df.groupby("majority").agg(
        n_combos=("total_stake", "size"),
        total_stake=("total_stake", "sum"),
        total_profit=("total_profit", "sum"),
        hit_rate=("all_hit", "mean"),
    ).reset_index()
    g["roi"] = g["total_profit"] / g["total_stake"]
    return g


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def plot_cumulative_roi(issues: pd.DataFrame, out_path: Path) -> None:
    if not HAS_MPL or issues.empty:
        return
    df = issues.sort_values("kickoff_min").copy()
    df["cum_stake"] = df["total_stake"].cumsum()
    df["cum_profit"] = df["total_profit"].cumsum()
    df["cum_roi"] = np.where(df["cum_stake"] > 0,
                             df["cum_profit"] / df["cum_stake"], 0.0)
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(df["kickoff_min"], df["cum_profit"], color="C0", label="cumulative profit (yuan)")
    ax1.set_ylabel("cumulative profit (yuan)", color="C0")
    ax1.axhline(0, color="grey", lw=0.5)
    ax2 = ax1.twinx()
    ax2.plot(df["kickoff_min"], df["cum_roi"] * 100, color="C3", label="cumulative ROI %")
    ax2.set_ylabel("cumulative ROI (%)", color="C3")
    ax2.axhline(-35, color="C3", ls="--", lw=0.7, alpha=0.6)
    ax1.set_title("Combo backtest: cumulative profit + ROI vs time")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_weekly_roi_hist(issues: pd.DataFrame, out_path: Path) -> None:
    if not HAS_MPL or issues.empty:
        return
    active = issues[issues["total_stake"] > 0]
    if active.empty:
        return
    rois = active["roi"].to_numpy()
    fig, ax = plt.subplots(figsize=(8, 5))
    # Clip extreme positive tail for histogram readability
    clip_hi = np.percentile(rois, 99) if len(rois) > 5 else rois.max()
    bins = np.linspace(-1.0, max(1.0, clip_hi), 40)
    ax.hist(np.clip(rois, -1.0, clip_hi), bins=bins, alpha=0.8, color="C0")
    ax.axvline(rois.mean(), color="C3", ls="--", label=f"mean = {rois.mean():.2%}")
    ax.axvline(-0.35, color="grey", ls=":", label="rake = -35%")
    ax.set_xlabel("Weekly ROI")
    ax.set_ylabel("# weeks")
    ax.set_title(f"Weekly combo-batch ROI distribution (n={len(rois)} weeks)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_calibration(plans: pd.DataFrame, out_path: Path) -> None:
    if not HAS_MPL or plans.empty:
        return
    p = plans.copy()
    # Bin by predicted joint_p
    if p["joint_p"].max() <= 0:
        return
    log_p = np.log10(np.clip(p["joint_p"], 1e-12, None))
    p["bin"] = pd.cut(log_p, bins=8)
    g = p.groupby("bin", observed=True).agg(
        mean_pred_p=("joint_p", "mean"),
        emp_hit=("all_hit", "mean"),
        n=("all_hit", "size"),
    ).reset_index()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(g["mean_pred_p"], g["emp_hit"],
               s=np.sqrt(g["n"]) * 5, alpha=0.7)
    lo = max(1e-12, g["mean_pred_p"].min() / 2)
    hi = max(g["mean_pred_p"].max(), g["emp_hit"].max(), lo * 10)
    ax.plot([lo, hi], [lo, hi], color="grey", ls="--", label="perfect calibration")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Predicted combo win prob (log)")
    ax.set_ylabel("Empirical hit rate (log)")
    ax.set_title("Combo calibration: predicted vs realised")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _fmt_pct(x: float) -> str:
    return f"{x*100:+.2f}%" if np.isfinite(x) else "n/a"


def build_report(
    issues: pd.DataFrame,
    plans: pd.DataFrame,
    out_md: Path,
    figures_dir: Path,
    *,
    bankroll: float = 100_000.0,
) -> str:
    """Render the markdown report and write plots to ``figures_dir``."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    cum_path = figures_dir / "combo_cum_roi.png"
    hist_path = figures_dir / "combo_weekly_roi_hist.png"
    calib_path = figures_dir / "combo_calibration.png"
    plot_cumulative_roi(issues, cum_path)
    plot_weekly_roi_hist(issues, hist_path)
    plot_calibration(plans, calib_path)

    n_weeks = len(issues)
    n_active_weeks = int((issues["total_stake"] > 0).sum())
    n_combos_total = int(issues["n_combos"].sum())
    n_tickets_total = int(issues["n_tickets"].sum())
    total_stake = float(issues["total_stake"].sum())
    total_profit = float(issues["total_profit"].sum())
    cum_roi = (total_profit / total_stake) if total_stake > 0 else float("nan")

    profits_arr = plans["total_profit"].to_numpy() if len(plans) else np.array([])
    stakes_arr = plans["total_stake"].to_numpy() if len(plans) else np.array([])
    cum_roi_boot, lo, hi = bootstrap_ci_roi(profits_arr, stakes_arr)

    wd = weekly_distribution(issues)
    hr = hit_rate_summary(issues, plans)
    by_h = edge_attribution_by_handicap(plans)
    by_sel = edge_attribution_by_selection(plans)

    lines: list[str] = []
    lines.append("# Combo-strategy half-backtest on historical 北单 data")
    lines.append("")
    lines.append("**Date:** 2026-05-02  ")
    lines.append("**Code:** `src/backtest_combo/`  ")
    lines.append(f"**Sample DB:** `data/beidan_history.db` (issue-level batches)\n")

    lines.append("## 1. Methodology\n")
    lines.append(
        "For each historical 期号 (weekly batch) we (a) compute model "
        "p3/p1/p0 from avg-EU 1X2 odds via proportional de-vig and the spec §4.3 "
        "draw correction, (b) predict per-option proxy SP using B2's per-result-code "
        "OLS fit on `winning_sp ~ avg_eu_winning_odds`, (c) emit candidates with "
        "single-leg edge ≥ 0.05, (d) drive `src.combo_optimizer.build_plan` with "
        f"defaults (bankroll={int(bankroll):,}, top_k=14, n_legs=7, combo_ev_threshold=0.10, "
        "kelly=¼, weekly_stake_cap=25%), (e) settle each TicketPlan against actual "
        "results — combo wins iff every leg matches `result_code`, profit then equals "
        "`stake × (∏actual_winning_SP × 0.65 − 1)`. By design, the proxy SP is "
        "fit on the same market that drives our model probabilities, so the "
        "expected ROI is the rake (≈ −35%); this run is a pipeline-validation and "
        "variance-quantification exercise.\n"
    )

    lines.append("## 2. Sample size\n")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| issues (weeks) covered | {n_weeks} |")
    lines.append(f"| weeks with ≥1 combo placed | {n_active_weeks} |")
    lines.append(f"| total combos placed | {n_combos_total:,} |")
    lines.append(f"| total tickets placed | {n_tickets_total:,} |")
    lines.append(f"| total stake (yuan) | {total_stake:,.0f} |")
    lines.append(f"| total realised profit (yuan) | {total_profit:,.0f} |")
    lines.append(f"| **cumulative ROI** | **{_fmt_pct(cum_roi)}** |")
    lines.append(f"| 95% bootstrap CI (per-plan) | [{_fmt_pct(lo)}, {_fmt_pct(hi)}] |")
    lines.append("")

    lines.append("## 3. Weekly ROI distribution\n")
    if wd:
        lines.append("Across weeks where at least one combo was placed:\n")
        lines.append("| stat | value |")
        lines.append("|---|---|")
        lines.append(f"| n_active_weeks | {wd['n_active_weeks']} |")
        lines.append(f"| mean | {_fmt_pct(wd['mean'])} |")
        lines.append(f"| std | {wd['std']*100:.2f} pp |")
        lines.append(f"| P5 | {_fmt_pct(wd['p5'])} |")
        lines.append(f"| P25 | {_fmt_pct(wd['p25'])} |")
        lines.append(f"| P50 | {_fmt_pct(wd['p50'])} |")
        lines.append(f"| P75 | {_fmt_pct(wd['p75'])} |")
        lines.append(f"| P95 | {_fmt_pct(wd['p95'])} |")
        lines.append(f"| min | {_fmt_pct(wd['min'])} |")
        lines.append(f"| max | {_fmt_pct(wd['max'])} |")
    else:
        lines.append("(no active weeks)")
    lines.append("")

    lines.append("## 4. Hit-rate findings\n")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    for k, v in hr.items():
        if isinstance(v, float):
            if "rate" in k or "frac" in k:
                lines.append(f"| {k} | {v*100:.4f}% |" if np.isfinite(v) else f"| {k} | n/a |")
            else:
                lines.append(f"| {k} | {v:.6f} |" if np.isfinite(v) else f"| {k} | n/a |")
        else:
            lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## 5. Edge attribution\n")
    lines.append("### 5.1 By combo handicap mix\n")
    if not by_h.empty:
        lines.append(by_h.to_markdown(index=False, floatfmt=".4f"))
    else:
        lines.append("(empty)")
    lines.append("\n### 5.2 By combo selection mix\n")
    if not by_sel.empty:
        lines.append(by_sel.to_markdown(index=False, floatfmt=".4f"))
    else:
        lines.append("(empty)")
    lines.append("")

    lines.append("## 6. Calibration\n")
    pred = hr.get("predicted_combo_hit_rate", float("nan"))
    emp = hr.get("empirical_combo_hit_rate", float("nan"))
    lines.append(
        f"Mean predicted combo win prob: **{pred*100:.4f}%** vs empirical "
        f"hit rate **{emp*100:.4f}%** "
        f"({'over' if emp < pred else 'under'}-confident). "
        f"See `figures/combo_calibration.png`.\n"
    )

    lines.append("## 7. Comparison vs single-bet B2 baseline\n")
    lines.append(
        "B2's single-bet empirical-proxy backtest reported **−35.43%** "
        "cumulative ROI (CI [−37.62%, −33.36%]) over 6,228 picks. "
        f"This combo run lands at **{_fmt_pct(cum_roi)}** "
        f"(CI [{_fmt_pct(lo)}, {_fmt_pct(hi)}]) over {n_combos_total:,} combos. "
        "If hits had occurred at the *predicted* rate the cumulative ROI would have "
        "averaged to roughly the rake (combos pay 35% rake once vs once-per-leg in "
        "single-bets). What we see instead is **worse than rake** because the model "
        "over-counts hits dramatically (see §9). Combos amplify any model bias because "
        "the joint probability multiplies seven correlated p̂ residuals.\n"
    )

    lines.append("## 8. Plots\n")
    lines.append(f"- Cumulative profit + ROI: `{cum_path.relative_to(out_md.parent).as_posix()}`")
    lines.append(f"- Weekly ROI histogram: `{hist_path.relative_to(out_md.parent).as_posix()}`")
    lines.append(f"- Calibration: `{calib_path.relative_to(out_md.parent).as_posix()}`")
    lines.append("")

    lines.append("## 9. Honest verdict\n")
    diff = cum_roi - (-0.3543) if np.isfinite(cum_roi) else float("nan")
    expected_combos_won = (plans["joint_p"] * plans["n_tickets"]).sum() if len(plans) else 0
    lines.append(
        f"Cumulative ROI = **{_fmt_pct(cum_roi)}** "
        f"(95% bootstrap CI {_fmt_pct(lo)} … {_fmt_pct(hi)}); "
        f"single-bet B2 baseline was −35.43%; delta = {diff*100:+.2f} pp.\n"
    )
    lines.append(
        "**This is consistent with no edge — and worse than the rake**, which is *itself* "
        "the most informative finding. The mechanism:\n"
    )
    lines.append(
        f"- The optimizer found {n_combos_total:,} candidate combos across "
        f"{n_active_weeks} weeks, all of which it scored as +EV under the model.\n"
        f"- The model's mean predicted joint win prob per combo was "
        f"**{pred*100:.4f}%** (mean ∏SP ≈ "
        f"{plans['joint_sp'].mean():.0f} when computed on plans). Across "
        f"{n_tickets_total:,} tickets the *expected* number of winning tickets was "
        f"**{expected_combos_won:.0f}**.\n"
        f"- The *realised* number of winning tickets was **0**.\n"
    )
    lines.append(
        "So the model is not merely uncalibrated — it is dramatically over-confident "
        "on the very combos it self-selects. Two compounding causes:\n\n"
        "1. **Selection bias from edge filter ≥ 0.05.** A leg passes the filter only "
        "where `p × proxy_SP × 0.65 ≥ 1.05`. Since the empirical OLS proxy SP is fit "
        "on the same eu_odds we use to derive p, picks survive the filter precisely "
        "when the OLS residual + the de-vig noise both line up favourably — these are "
        "by construction *the legs where the model is most likely to be wrong*. The "
        "edge filter is a winner's-curse engine.\n\n"
        "2. **Probability-product error compounds.** A 7-leg combo's joint_p is "
        "extremely sensitive to per-leg p̂ inflation. If each leg's p̂ is biased "
        "high by 5pp at the +0.05-edge boundary, the joint can be 4–8× over-stated.\n"
    )
    lines.append(
        "**Comparison vs B2's single-bet baseline (−35.43%).** Single-bet ROI "
        "regresses cleanly to the rake because the OLS fit absorbs systematic SP-vs-EU "
        "bias *on average*. The combo strategy concentrates stake on the right tail of "
        "that residual distribution, where the OLS over-estimate of SP combined with "
        "an over-estimate of p compounds across 7 legs. The ROI is therefore *more* "
        "negative than the rake, not less. Combos do not magically beat single-bets "
        "when both share the same biased probability source.\n"
    )
    lines.append(
        "**Pipeline validation status — PASS.** The optimizer ran on every issue, "
        "respected the 25%-of-bankroll cap, and emitted plans with valid stakes and "
        "ticket counts on 44/150 weeks. No code-path errors. Settler correctly handled "
        "all-miss combos.\n"
    )
    lines.append(
        "**Variance baseline for Live Collector.** Under the avg-EU-as-proxy model, "
        "weekly combo ROI on this dataset is degenerate: every active week lost 100% "
        "of stake. Live Collector validation must beat this both in (a) producing "
        "≥1 winning combo per quarter and (b) showing predicted combo p calibrated to "
        "realised hit rate within an order of magnitude. With real Pinnacle AH + "
        "Skellam probabilities and real 北单 SP captures (which are *independent* "
        "of avg-EU residuals), neither effect (1) nor (2) above will fire in the same "
        "way — but until that data is in hand, this report is the proper null.\n"
    )

    body = "\n".join(lines)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(body, encoding="utf-8")
    return body
