#!/usr/bin/env python3
"""Render the PI synthesis figures for Issue #167 from immutable chart sources."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1"
ASSETS = ROOT / "docs" / "research-notes" / "assets"
PACKAGE_MANIFEST_SHA256 = "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313"
PACKAGE_CONTENT_IDENTITY_SHA256 = "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7"

STRICT_SELECTOR = "S2_ESP300_GM305_P_MIN_LOWP20_VALUE_FIRST_K1"
HISTORIC_SELECTOR = "S1_NO_GATE_K4"
BEST_BROAD_FULL = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package(package: Path) -> dict[str, str]:
    manifest_path = package / "SHA256SUMS.json"
    identity_path = package / "CONTENT_IDENTITY.json"
    if sha256(manifest_path) != PACKAGE_MANIFEST_SHA256:
        raise RuntimeError("#167 package manifest identity mismatch")
    if sha256(identity_path) != PACKAGE_CONTENT_IDENTITY_SHA256:
        raise RuntimeError("#167 package content identity mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, expected in manifest.items():
        path = package / relative
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"#167 package payload mismatch: {relative}")
    return manifest


def pct_axis(axis, which: str = "y") -> None:
    formatter = plt.FuncFormatter(lambda value, _position: f"{value * 100:.0f}%")
    if which == "y":
        axis.yaxis.set_major_formatter(formatter)
    else:
        axis.xaxis.set_major_formatter(formatter)


def annotate_heatmap(axis, values: np.ndarray) -> None:
    rows, cols = values.shape
    for row in range(rows):
        for col in range(cols):
            value = values[row, col]
            if np.isfinite(value):
                axis.text(col, row, f"{value * 100:.0f}", ha="center", va="center", fontsize=6)


def heatmap(axis, frame: pd.DataFrame, title: str, vmin: float = -0.35, vmax: float = 0.35) -> None:
    values = frame.to_numpy(dtype=float)
    image = axis.imshow(values, aspect="auto", cmap="RdYlGn", norm=TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax))
    axis.set_title(title)
    axis.set_xticks(range(len(frame.columns)), frame.columns, rotation=45, ha="right", fontsize=7)
    axis.set_yticks(range(len(frame.index)), frame.index, fontsize=7)
    annotate_heatmap(axis, values)
    plt.colorbar(image, ax=axis, fraction=0.025, pad=0.02, label="pre-tax ROI / lift")


def selector_surface(full: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), constrained_layout=True)

    colors = {"S1_GATE_TOPK": "#4C78A8", "S2_COMPLETE_ISSUE_LOWP": "#F58518"}
    for family, group in full.groupby("family"):
        axes[0, 0].scatter(
            group["settled_policy_count"], group["no_tax_roi"], s=24, alpha=0.62,
            label=family.replace("_", " "), color=colors.get(family, "#777777"),
        )
    axes[0, 0].axhline(0, color="black", linewidth=0.8)
    axes[0, 0].axhline(-0.0835, color="#9467BD", linewidth=1.0, linestyle="--", label="#127 legacy -8.35%")
    for selector, label in (
        (BEST_BROAD_FULL, "best FULL, support≥100"),
        (STRICT_SELECTOR, "strict allocator sweet-region selector"),
        (HISTORIC_SELECTOR, "#137/#151 selector"),
    ):
        row = full.loc[full.selector_id.eq(selector)].iloc[0]
        axes[0, 0].annotate(
            label, (row.settled_policy_count, row.no_tax_roi), xytext=(7, 7),
            textcoords="offset points", fontsize=7, arrowprops={"arrowstyle": "-", "lw": 0.6},
        )
    axes[0, 0].set(title="All 492 matched-FULL selectors", xlabel="settled issue policies", ylabel="pre-tax ROI")
    axes[0, 0].set_ylim(-0.30, 0.10)
    clipped_count = int(full.no_tax_roi.gt(0.10).sum())
    axes[0, 0].text(
        0.02, 0.97, f"{clipped_count} tiny-support selectors above +10% are clipped",
        transform=axes[0, 0].transAxes, va="top", fontsize=7,
    )
    pct_axis(axes[0, 0])
    axes[0, 0].legend(fontsize=7, loc="lower right")

    top = full.loc[full.settled_policy_count.ge(100)].nlargest(12, "no_tax_roi").sort_values("no_tax_roi")
    labels = [selector.replace("S2_", "").replace("_MIN", "") for selector in top.selector_id]
    axes[0, 1].barh(labels, top.no_tax_roi, color="#4C78A8")
    axes[0, 1].axvline(-0.0835, color="#9467BD", linestyle="--", linewidth=1)
    axes[0, 1].set(title="Best FULL selectors with ≥100 settled issues", xlabel="pre-tax ROI")
    pct_axis(axes[0, 1], "x")
    axes[0, 1].tick_params(axis="y", labelsize=6)

    s1 = full.loc[full.family.eq("S1_GATE_TOPK")].copy()
    s1["top_k"] = s1.top_k.astype(str).replace({"nan": "ALL"})
    s1_pivot = s1.pivot(index="gate_id", columns="top_k", values="no_tax_roi")
    ordered_k = [item for item in ["1", "2", "4", "8", "16", "ALL"] if item in s1_pivot.columns]
    s1_pivot = s1_pivot.reindex(columns=ordered_k)
    heatmap(axes[1, 0], s1_pivot, "S1 FULL surface: gate × top-K (cell labels are %)", -0.30, 0.05)
    axes[1, 0].set(xlabel="top-K identities", ylabel="E_SP / GM_E_SP gate")

    s2 = full.loc[full.family.eq("S2_COMPLETE_ISSUE_LOWP")].copy()
    s2["source_rank"] = s2.lowp_source.str.replace("_MIN", "", regex=False) + "/" + s2.ranker.str.replace("_FIRST", "", regex=False)
    # This is a descriptive selector envelope, not an outcome-safe selection rule.
    s2_best = s2.loc[s2.settled_policy_count.ge(25)].groupby(
        ["source_rank", "lowp_threshold"], as_index=False
    ).agg(no_tax_roi=("no_tax_roi", "max"))
    s2_pivot = s2_best.pivot(index="source_rank", columns="lowp_threshold", values="no_tax_roi")
    s2_pivot.columns = [f"p≤{value:.2f}" for value in s2_pivot.columns]
    heatmap(axes[1, 1], s2_pivot, "S2 descriptive best-FULL envelope (settled support ≥25)", -0.30, 0.05)
    axes[1, 1].set(xlabel="LOWP threshold", ylabel="probability source / ranking")

    fig.suptitle("#167 selector layer: selection improves FULL, but does not yet create robust positive ROI", fontsize=14)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def allocation_curves(dense: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    mechanisms = [
        ("WR_DUPLICATE_STAKE", None, "WR"),
        ("WOR_DISTINCT", None, "WOR"),
        ("CAPPED_REPEAT", 1.0, "cap=1"),
        ("DETERMINISTIC_TOP_MASS", None, "top-mass"),
        ("RESIDUAL_SYSTEMATIC", None, "residual"),
    ]
    palette = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2"]

    def draw_curves(axis, selector: str, weight: str, title: str) -> None:
        subset = dense.loc[dense.selector_id.eq(selector) & dense.weight_source.eq(weight)]
        for (mechanism, cap, label), color in zip(mechanisms, palette, strict=True):
            line = subset.loc[subset.mechanism.eq(mechanism)]
            if cap is not None:
                line = line.loc[line.cap.eq(cap)]
            line = line.sort_values("M")
            axis.plot(line.M, line.no_tax_roi, marker="o", markersize=2.5, linewidth=1.2, label=label, color=color)
        full_roi = subset.full_point_roi.dropna().iloc[0] if "full_point_roi" in subset else np.nan
        if np.isfinite(full_roi):
            axis.axhline(full_roi, color="black", linewidth=0.9, linestyle=":", label="matched FULL")
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_xscale("log", base=2)
        axis.set(title=title, xlabel="M tickets per identity (log2 scale)", ylabel="pre-tax ROI")
        pct_axis(axis)
        axis.legend(fontsize=7, ncol=2)

    # full_point_roi is not stored in dense chart source; reconstruct from no_tax_roi - lift.
    dense = dense.copy()
    dense["full_point_roi"] = dense.no_tax_roi - dense.matched_full_lift
    draw_curves(axes[0, 0], STRICT_SELECTOR, "MODEL_P_CAL", "Strict S2 selector + MODEL_P_CAL")
    draw_curves(axes[0, 1], HISTORIC_SELECTOR, "Q_WEIGHT", "Historical NO_GATE/K4 + Q_WEIGHT")

    for selector, weight, label, color in (
        (STRICT_SELECTOR, "MODEL_P_CAL", "strict MODEL_P", "#4C78A8"),
        (HISTORIC_SELECTOR, "Q_WEIGHT", "historic Q", "#F58518"),
    ):
        x = dense.loc[dense.selector_id.eq(selector) & dense.weight_source.eq(weight)]
        wr = x.loc[x.mechanism.eq("WR_DUPLICATE_STAKE"), ["M", "no_tax_roi"]].rename(columns={"no_tax_roi": "wr"})
        wor = x.loc[x.mechanism.eq("WOR_DISTINCT"), ["M", "no_tax_roi"]].rename(columns={"no_tax_roi": "wor"})
        delta = wor.merge(wr, on="M", validate="one_to_one").sort_values("M")
        axes[1, 0].plot(delta.M, delta.wor - delta.wr, marker="o", markersize=2.5, label=label, color=color)
    axes[1, 0].axhline(0, color="black", linewidth=0.8)
    axes[1, 0].set_xscale("log", base=2)
    axes[1, 0].set(title="WOR − WR depends on selector and weight", xlabel="M tickets", ylabel="pre-tax ROI delta")
    pct_axis(axes[1, 0])
    axes[1, 0].legend(fontsize=8)

    strict = dense.loc[dense.selector_id.eq(STRICT_SELECTOR) & dense.weight_source.eq("MODEL_P_CAL")]
    for (mechanism, cap, label), color in zip(mechanisms, palette, strict=True):
        line = strict.loc[strict.mechanism.eq(mechanism)]
        if cap is not None:
            line = line.loc[line.cap.eq(cap)]
        line = line.sort_values("capital_utilization_vs_full")
        axes[1, 1].plot(line.capital_utilization_vs_full, line.no_tax_roi, marker="o", markersize=2.5, linewidth=1, label=label, color=color)
    axes[1, 1].axhline(0, color="black", linewidth=0.8)
    axes[1, 1].set(title="Strict selector capital frontier", xlabel="stake / matched FULL stake", ylabel="pre-tax ROI")
    pct_axis(axes[1, 1])
    pct_axis(axes[1, 1], "x")
    axes[1, 1].legend(fontsize=7, ncol=2)

    fig.suptitle("#167 allocation layer: two isolated deterministic sweet regions, no global WR/WOR winner", fontsize=14)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def roi_lift_heatmaps(full: pd.DataFrame, dense: pd.DataFrame, output: Path) -> list[str]:
    chosen = [HISTORIC_SELECTOR, STRICT_SELECTOR, BEST_BROAD_FULL, "S1_NO_GATE_K1", "S1_NO_GATE_K2", "S1_NO_GATE_K8"]
    broad = full.loc[full.settled_policy_count.ge(100)].nlargest(10, "no_tax_roi").selector_id.tolist()
    chosen.extend(broad)
    selectors = list(dict.fromkeys(chosen))[:16]
    labels = {selector: selector.replace("S2_", "").replace("S1_", "") for selector in selectors}
    subset = dense.loc[
        dense.selector_id.isin(selectors)
        & dense.M.eq(64)
        & dense.mechanism.isin(["WR_DUPLICATE_STAKE", "WOR_DISTINCT"])
    ].copy()
    subset["arm"] = subset.weight_source.str.replace("_CAL", "", regex=False) + "/" + subset.mechanism.map({"WR_DUPLICATE_STAKE": "WR", "WOR_DISTINCT": "WOR"})
    absolute = subset.pivot(index="selector_id", columns="arm", values="no_tax_roi").reindex(selectors)
    lift = subset.pivot(index="selector_id", columns="arm", values="matched_full_lift").reindex(selectors)
    absolute.index = [labels[item] for item in absolute.index]
    lift.index = [labels[item] for item in lift.index]

    fig, axes = plt.subplots(1, 2, figsize=(20, 10), constrained_layout=True)
    heatmap(axes[0], absolute, "M64 absolute pre-tax ROI (%)", -0.45, 0.45)
    heatmap(axes[1], lift, "M64 allocator − matched FULL lift (pp)", -0.45, 0.45)
    fig.suptitle("#167 fixed-M allocation heatmaps: selector × probability weight × WR/WOR", fontsize=14)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return selectors


def joined_candidates(package: Path) -> pd.DataFrame:
    boot = pd.read_csv(package / "candidate_paired_bootstrap_20000.csv")
    keys = ["selector_id", "weight_source", "mechanism", "M", "seed_scope"]
    boot["cap_key"] = boot.cap.fillna("NA").astype(str)
    columns = keys + [
        "cap", "normalized_stake_yuan", "normalized_gross_pre_tax_yuan", "no_tax_roi",
        "tax_adjusted_roi", "gross_return_retention_vs_matched_full", "coverage_hit_rate",
        "ticket_hit_rate", "settled_policy_count", "seed_mean_drawdown_no_tax_yuan",
        "seed_gross_weighted_mean_issue_hhi",
    ]
    capital = pd.read_csv(package / "chart_source_capital_risk_tax_hit_v3r1.csv.gz", usecols=columns)
    capital["cap_key"] = capital.cap.fillna("NA").astype(str)
    join_keys = ["selector_id", "weight_source", "mechanism", "cap_key", "M", "seed_scope"]
    return boot.merge(capital.drop(columns=["cap"]), on=join_keys, how="left", validate="one_to_one")


def frontier_views(candidates: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), constrained_layout=True)
    display = candidates.loc[
        candidates.settled_policy_count.ge(50)
        & candidates.candidate_point_roi.between(-1, 1.25)
    ].copy()
    color = display.gross_top_issue_share.clip(0, 0.35)

    mappable = axes[0, 0].scatter(display.normalized_stake_yuan, display.candidate_point_roi, c=color, cmap="viridis_r", s=10, alpha=0.55)
    axes[0, 0].set_xscale("log")
    axes[0, 0].set(title="Capital efficiency", xlabel="normalized stake (yuan, log scale)", ylabel="pre-tax ROI")
    pct_axis(axes[0, 0])

    axes[0, 1].scatter(display.drawdown_no_tax_yuan, display.candidate_point_roi, c=color, cmap="viridis_r", s=10, alpha=0.55)
    axes[0, 1].set_xscale("log")
    axes[0, 1].set(title="Risk frontier", xlabel="pre-tax max drawdown (yuan, log scale)", ylabel="pre-tax ROI")
    pct_axis(axes[0, 1])

    axes[1, 0].scatter(display.candidate_point_roi, display.tax_adjusted_roi, c=color, cmap="viridis_r", s=10, alpha=0.55)
    limits = [-1, 1.0]
    axes[1, 0].plot(limits, limits, color="black", linewidth=0.8, linestyle=":")
    axes[1, 0].set(xlim=limits, ylim=limits, title="Tax frontier", xlabel="pre-tax ROI", ylabel="tax-adjusted ROI")
    pct_axis(axes[1, 0])
    pct_axis(axes[1, 0], "x")

    axes[1, 1].scatter(display.coverage_hit_rate, display.gross_return_retention_vs_matched_full, c=color, cmap="viridis_r", s=10, alpha=0.55)
    axes[1, 1].set(title="Hit / return frontier", xlabel="issue coverage hit rate", ylabel="gross return / matched FULL")
    pct_axis(axes[1, 1])
    pct_axis(axes[1, 1], "x")

    keys = [
        (HISTORIC_SELECTOR, "Q_WEIGHT", "DETERMINISTIC_TOP_MASS", 192, "Q top-mass M192"),
        (STRICT_SELECTOR, "MODEL_P_CAL", "CAPPED_REPEAT", 512, "strict cap1 M512"),
    ]
    for selector, weight, mechanism, M, label in keys:
        row = display.loc[
            display.selector_id.eq(selector) & display.weight_source.eq(weight)
            & display.mechanism.eq(mechanism) & display.M.eq(M)
        ].iloc[0]
        points = [
            (row.normalized_stake_yuan, row.candidate_point_roi),
            (row.drawdown_no_tax_yuan, row.candidate_point_roi),
            (row.candidate_point_roi, row.tax_adjusted_roi),
            (row.coverage_hit_rate, row.gross_return_retention_vs_matched_full),
        ]
        for axis, point in zip(axes.flat, points, strict=True):
            axis.scatter(*point, s=80, facecolor="none", edgecolor="#D62728", linewidth=1.5)
            axis.annotate(label, point, xytext=(5, 5), textcoords="offset points", fontsize=7)

    fig.suptitle("#167 discovery frontiers (support ≥50; color = largest-issue gross share)", fontsize=14)
    fig.colorbar(mappable, ax=axes, fraction=0.015, pad=0.015, label="largest-issue gross share")
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def stability_views(package: Path, candidates: pd.DataFrame, output: Path) -> None:
    quantiles = pd.read_csv(package / "chart_source_seed_ensemble_quantiles.csv.gz")
    prefix = pd.read_csv(ROOT / "results" / "bj167_gate_b_outcome_settlement_v2r3" / "prefix_convergence.csv")
    robust = pd.read_csv(package / "robust_pareto_front_exact.csv")
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)

    for selector, weight, label, color in (
        (STRICT_SELECTOR, "MODEL_P_CAL", "strict MODEL_P", "#4C78A8"),
        (HISTORIC_SELECTOR, "Q_WEIGHT", "historic Q", "#F58518"),
    ):
        for mechanism, linestyle in (("WR_DUPLICATE_STAKE", "-"), ("WOR_DISTINCT", "--")):
            line = quantiles.loc[
                quantiles.selector_id.eq(selector) & quantiles.weight_source.eq(weight)
                & quantiles.mechanism.eq(mechanism)
            ].sort_values("M")
            tag = f"{label} / {'WR' if mechanism.startswith('WR_') else 'WOR'}"
            axes[0, 0].plot(line.M, line.roi_mean, linestyle=linestyle, color=color, linewidth=1.2, label=tag)
            axes[0, 0].fill_between(line.M, line.roi_p10, line.roi_p90, color=color, alpha=0.08)
    axes[0, 0].axhline(0, color="black", linewidth=0.8)
    axes[0, 0].set_xscale("log", base=2)
    axes[0, 0].set(title="100-seed mean and p10–p90 envelope", xlabel="M tickets", ylabel="pre-tax ROI")
    pct_axis(axes[0, 0])
    axes[0, 0].legend(fontsize=7)

    if {"seed_prefix", "candidate_mean_roi"}.issubset(prefix.columns):
        xcol, ycol = "seed_prefix", "candidate_mean_roi"
    else:
        xcol = next(column for column in prefix.columns if "prefix" in column)
        ycol = next(column for column in prefix.columns if "mean" in column and "roi" in column and "lift" not in column)
    for M, group in prefix.groupby("M"):
        axes[0, 1].plot(group[xcol], group[ycol], marker="o", label=f"M{M}")
    axes[0, 1].axhline(0, color="black", linewidth=0.8)
    axes[0, 1].set(title="#137/#151 fixed-candidate seed-prefix convergence", xlabel="seed prefix", ylabel="mean pre-tax ROI")
    pct_axis(axes[0, 1])
    axes[0, 1].legend(fontsize=7)

    clipped = candidates.loc[candidates.candidate_point_roi.between(-1, 2)].copy()
    axes[1, 0].scatter(clipped.candidate_ci95_low, clipped.candidate_point_roi, s=8, alpha=0.25, color="#4C78A8", label="postscreen candidates")
    axes[1, 0].scatter(robust.candidate_ci95_low, robust.candidate_point_roi.clip(-1, 2), s=12, alpha=0.4, color="#E45756", label="robust Pareto rows")
    axes[1, 0].axvline(0, color="black", linewidth=0.8)
    axes[1, 0].axhline(0, color="black", linewidth=0.8)
    axes[1, 0].set(title="Absolute bootstrap lower bound: no cell clears zero", xlabel="20,000-bootstrap ROI lower bound", ylabel="point pre-tax ROI")
    pct_axis(axes[1, 0])
    pct_axis(axes[1, 0], "x")
    axes[1, 0].legend(fontsize=7)

    axes[1, 1].scatter(candidates.ex_largest_year_no_tax_roi.clip(-1, 2), candidates.ex_largest_issue_no_tax_roi.clip(-1, 2), s=8, alpha=0.25, color="#4C78A8")
    axes[1, 1].axvline(0, color="black", linewidth=0.8)
    axes[1, 1].axhline(0, color="black", linewidth=0.8)
    axes[1, 1].set(title="Ex-largest stability plane", xlabel="ROI excluding largest signed year", ylabel="ROI excluding largest signed issue")
    pct_axis(axes[1, 1])
    pct_axis(axes[1, 1], "x")

    fig.suptitle("#167 uncertainty: seeds reduce allocator noise, not football-history uncertainty", fontsize=14)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def baseline_bridge(package: Path, candidates: pd.DataFrame, full: pd.DataFrame, output: Path) -> pd.DataFrame:
    q_wor = candidates.loc[
        candidates.selector_id.eq(HISTORIC_SELECTOR) & candidates.weight_source.eq("Q_WEIGHT")
        & candidates.mechanism.eq("WOR_DISTINCT") & candidates.M.eq(64)
    ].iloc[0]
    q_top = candidates.loc[
        candidates.selector_id.eq(HISTORIC_SELECTOR) & candidates.weight_source.eq("Q_WEIGHT")
        & candidates.mechanism.eq("DETERMINISTIC_TOP_MASS") & candidates.M.eq(192)
    ].iloc[0]
    strict = candidates.loc[
        candidates.selector_id.eq(STRICT_SELECTOR) & candidates.weight_source.eq("MODEL_P_CAL")
        & candidates.mechanism.eq("CAPPED_REPEAT") & candidates.cap.eq(1) & candidates.M.eq(512)
    ].iloc[0]
    broad_full = full.loc[full.selector_id.eq(BEST_BROAD_FULL)].iloc[0]
    registry = pd.read_csv(package / "baseline_registry_v3r1.csv")
    transfer_159 = registry.loc[registry.baseline_id.eq("B159_N7_M64_TRANSFER")].iloc[0]
    rows = [
        {"candidate": "#127 legacy FULL", "roi": -0.0835, "low": np.nan, "high": np.nan, "grade": "legacy segment reference"},
        {"candidate": "#137/#151 3-seed Q-WOR/M64", "roi": np.mean([0.163756, 0.117736, 0.026680]), "low": np.nan, "high": np.nan, "grade": "discovery; only 3 seeds"},
        {"candidate": "#159 N7/M64 transfer", "roi": transfer_159.pre_tax_roi, "low": np.nan, "high": np.nan, "grade": "complete-issue transfer diagnostic"},
        {"candidate": "#167 100-seed Q-WOR/M64", "roi": q_wor.candidate_point_roi, "low": q_wor.candidate_ci95_low, "high": q_wor.candidate_ci95_high, "grade": "comparable incumbent bridge"},
        {"candidate": "#167 best FULL, support≥100", "roi": broad_full.no_tax_roi, "low": np.nan, "high": np.nan, "grade": "selection baseline"},
        {"candidate": "#167 Q top-mass/M192", "roi": q_top.candidate_point_roi, "low": q_top.candidate_ci95_low, "high": q_top.candidate_ci95_high, "grade": "high-return concentrated discovery"},
        {"candidate": "#167 strict MODEL_P cap1/M512", "roi": strict.candidate_point_roi, "low": strict.candidate_ci95_low, "high": strict.candidate_ci95_high, "grade": "broad-support sweet region"},
    ]
    frame = pd.DataFrame(rows)
    fig, axis = plt.subplots(figsize=(13, 6), constrained_layout=True)
    x = np.arange(len(frame))
    colors = ["#9467BD", "#F58518", "#7F7F7F", "#4C78A8", "#4C78A8", "#E45756", "#54A24B"]
    axis.scatter(x, frame.roi, s=90, color=colors, zorder=3)
    finite = frame.low.notna() & frame.high.notna()
    axis.errorbar(
        x[finite], frame.loc[finite, "roi"],
        yerr=[frame.loc[finite, "roi"] - frame.loc[finite, "low"], frame.loc[finite, "high"] - frame.loc[finite, "roi"]],
        fmt="none", ecolor="#555555", capsize=4, linewidth=1.2,
    )
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set_xticks(x, frame.candidate, rotation=18, ha="right")
    axis.set(title="#167 baseline bridge: promising point estimates remain discovery-grade", ylabel="pre-tax ROI")
    pct_axis(axis)
    for index, row in frame.iterrows():
        axis.annotate(f"{row.roi:+.1%}\n{row.grade}", (index, row.roi), xytext=(0, 9), textcoords="offset points", ha="center", fontsize=7)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return frame


def write_key_candidates(candidates: pd.DataFrame, full: pd.DataFrame, output: Path) -> None:
    filters = [
        ("INCUMBENT_Q_WOR_M64", HISTORIC_SELECTOR, "Q_WEIGHT", "WOR_DISTINCT", None, 64),
        ("HIGH_RETURN_Q_TOPMASS_M192", HISTORIC_SELECTOR, "Q_WEIGHT", "DETERMINISTIC_TOP_MASS", None, 192),
        ("BROAD_SWEET_MODEL_P_CAP1_M512", STRICT_SELECTOR, "MODEL_P_CAL", "CAPPED_REPEAT", 1, 512),
    ]
    rows = []
    for name, selector, weight, mechanism, cap, M in filters:
        found = candidates.loc[
            candidates.selector_id.eq(selector) & candidates.weight_source.eq(weight)
            & candidates.mechanism.eq(mechanism) & candidates.M.eq(M)
        ]
        if cap is not None:
            found = found.loc[found.cap.eq(cap)]
        row = found.iloc[0]
        rows.append({
            "candidate_name": name,
            "candidate_index": int(row.candidate_index),
            "selector_id": selector,
            "weight_source": weight,
            "mechanism": mechanism,
            "cap": "NA" if cap is None else cap,
            "M": M,
            "settled_policy_count": int(row.settled_policy_count),
            "pre_tax_roi": row.candidate_point_roi,
            "tax_adjusted_roi": row.tax_adjusted_roi,
            "matched_full_roi": row.full_point_roi,
            "matched_full_lift": row.paired_lift_point,
            "bootstrap_ci95_low": row.candidate_ci95_low,
            "bootstrap_ci95_high": row.candidate_ci95_high,
            "lift_ci95_low": row.lift_ci95_low,
            "lift_ci95_high": row.lift_ci95_high,
            "ex_largest_issue_roi": row.ex_largest_issue_no_tax_roi,
            "ex_largest_year_roi": row.ex_largest_year_no_tax_roi,
            "gross_issue_hhi": row.gross_issue_hhi,
            "gross_top_issue_share": row.gross_top_issue_share,
            "normalized_stake_yuan": row.normalized_stake_yuan,
            "package_manifest_sha256": PACKAGE_MANIFEST_SHA256,
        })
    pd.DataFrame(rows).to_csv(output, index=False, lineterminator="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=PACKAGE)
    parser.add_argument("--output", type=Path, default=ASSETS)
    args = parser.parse_args()
    package = args.package.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    verify_package(package)

    full = pd.read_csv(package / "chart_source_selector_full_surface_v3r1.csv.gz")
    dense = pd.read_csv(
        package / "chart_source_full_dense_m_curve_v3r1.csv.gz",
        usecols=[
            "selector_id", "family", "gate_id", "top_k", "lowp_source", "lowp_threshold",
            "ranker", "weight_source", "mechanism", "cap", "M", "seed_scope", "no_tax_roi",
            "matched_full_lift", "coverage_hit_rate", "ticket_hit_rate", "capital_utilization_vs_full",
        ],
        low_memory=False,
    )
    candidates = joined_candidates(package)

    figures = [
        ("bj167_selector_full_surface.png", selector_surface, ["chart_source_selector_full_surface_v3r1.csv.gz"], "all 492 FULL selectors; S2 envelopes are descriptive maxima"),
        ("bj167_allocation_m_curves.png", allocation_curves, ["chart_source_full_dense_m_curve_v3r1.csv.gz"], "strict MODEL_P and historic Q selectors; full dense M grid"),
        ("bj167_roi_lift_heatmaps.png", roi_lift_heatmaps, ["chart_source_full_dense_m_curve_v3r1.csv.gz", "chart_source_selector_full_surface_v3r1.csv.gz"], "representative selectors; M64 WR/WOR; six probability weights"),
        ("bj167_capital_risk_tax_hit_frontiers.png", frontier_views, ["candidate_paired_bootstrap_20000.csv", "chart_source_capital_risk_tax_hit_v3r1.csv.gz"], "postscreen candidates with settled support >=50; plotted ROI clipped for readability"),
        ("bj167_stability_and_pareto.png", stability_views, ["chart_source_seed_ensemble_quantiles.csv.gz", "candidate_paired_bootstrap_20000.csv", "robust_pareto_front_exact.csv", "../bj167_gate_b_outcome_settlement_v2r3/prefix_convergence.csv"], "100-seed quantiles, historical fixed-candidate prefixes, exact 20k bootstrap and exclusion planes"),
    ]
    manifest_rows = []
    for filename, function, sources, filters in figures:
        if function is selector_surface:
            function(full, output / filename)
        elif function is allocation_curves:
            function(dense, output / filename)
        elif function is roi_lift_heatmaps:
            function(full, dense, output / filename)
        elif function is frontier_views:
            function(candidates, output / filename)
        else:
            function(package, candidates, output / filename)
        manifest_rows.append({
            "figure": filename,
            "source_tables": ";".join(sources),
            "filters_and_scope": filters,
            "package_manifest_sha256": PACKAGE_MANIFEST_SHA256,
            "package_content_identity_sha256": PACKAGE_CONTENT_IDENTITY_SHA256,
        })

    bridge_name = "bj167_baseline_bridge.png"
    bridge = baseline_bridge(package, candidates, full, output / bridge_name)
    bridge.to_csv(output / "bj167_baseline_bridge.csv", index=False, lineterminator="\n")
    manifest_rows.append({
        "figure": bridge_name,
        "source_tables": "baseline_registry_v3r1.csv;candidate_paired_bootstrap_20000.csv;chart_source_selector_full_surface_v3r1.csv.gz;historical #127/#137/#151 contract anchors",
        "filters_and_scope": "historical champion board with explicit denominator/evidence warnings",
        "package_manifest_sha256": PACKAGE_MANIFEST_SHA256,
        "package_content_identity_sha256": PACKAGE_CONTENT_IDENTITY_SHA256,
    })
    write_key_candidates(candidates, full, output / "bj167_key_candidates.csv")
    with (output / "bj167_chart_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(json.dumps({"figures": len(manifest_rows), "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
