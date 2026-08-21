#!/usr/bin/env python3
"""Analyze the bounded #284 joint N×K×generator×subset screen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--artifact-name", default="joint_action_grid_confirmatory")
    parser.add_argument("--bootstrap-draws", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=284_901)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    raw = pd.read_parquet(output / f"{args.artifact_name}.parquet")
    if raw["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ joint analysis seal violated")
    subset_actions = _collapse_nuisance_replicas(raw)
    issue_actions = _collapse_subset_replicates(subset_actions)
    curve, yearly = _fixed_action_curve(
        issue_actions, draws=args.bootstrap_draws, seed=args.seed
    )
    family_curve = _family_curve(subset_actions)
    generator_lift = _generator_lift(issue_actions)
    reliability = _year_rank_reliability(yearly)
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-joint-screen",
        "issues": int(issue_actions["issue"].nunique()),
        "raw_rows": int(len(raw)),
        "subset_actions": int(len(subset_actions)),
        "fixed_actions": int(len(curve)),
        "n": sorted(int(value) for value in curve["n"].unique()),
        "generators": sorted(curve["generator"].unique()),
        "requested_k": sorted(int(value) for value in curve["requested_k"].unique()),
        "proposal_families": sorted(raw["proposal_family"].unique()),
        "weighted_stream_replicas": int(
            raw.loc[raw["generator"].eq("WEIGHTED_WR"), "stream_replica"].nunique()
        ),
        "mean_pairwise_year_action_rank_spearman": reliability["mean"],
        "median_pairwise_year_action_rank_spearman": reliability["median"],
        "best_descriptive_action": _record(curve.iloc[0]),
        "best_ex_largest_action": _record(
            curve.sort_values("ex_largest_roi_pct", ascending=False).iloc[0]
        ),
        "sealed_years_opened": [],
        "interpretation": (
            "DESCRIPTIVE INTERACTION SCREEN ONLY; realized action winners are not "
            "eligible training labels without chronological selection and nuisance "
            "replication."
        ),
    }
    _atomic_csv(curve, output / "joint_action_curve.csv")
    _atomic_csv(yearly, output / "joint_action_yearly.csv")
    _atomic_csv(family_curve, output / "joint_family_curve.csv")
    _atomic_csv(generator_lift, output / "joint_generator_lift.csv")
    _atomic_json(receipt, output / "joint_action_analysis_receipt.json")
    _plot_heatmaps(curve, output / "joint_action_roi_heatmaps.png")
    _plot_expected_realized(curve, output / "joint_expected_vs_realized.png")
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _collapse_nuisance_replicas(raw: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "issue",
        "issue_year",
        "n",
        "proposal_family",
        "subset_id",
        "generator",
        "requested_k",
    ]
    return (
        raw.groupby(keys, as_index=False)
        .agg(
            realized_roi_pct=("normalized_pnl_cny100", "mean"),
            expected_roi_pct=("model_expected_pnl_cny100", "mean"),
            effective_k=("effective_k", "mean"),
            stream_replicas=("stream_replica", "nunique"),
            alias_fraction=("is_effective_k_alias", "mean"),
        )
        .sort_values(keys)
    )


def _collapse_subset_replicates(subset_actions: pd.DataFrame) -> pd.DataFrame:
    keys = ["issue", "issue_year", "n", "generator", "requested_k"]
    return (
        subset_actions.groupby(keys, as_index=False)
        .agg(
            realized_roi_pct=("realized_roi_pct", "mean"),
            expected_roi_pct=("expected_roi_pct", "mean"),
            subsets=("subset_id", "nunique"),
            families=("proposal_family", "nunique"),
            alias_fraction=("alias_fraction", "mean"),
        )
        .sort_values(keys)
    )


def _fixed_action_curve(
    issue_actions: pd.DataFrame, *, draws: int, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, float | int | str]] = []
    years: list[pd.DataFrame] = []
    rng = np.random.default_rng(seed)
    for key, group in issue_actions.groupby(["n", "generator", "requested_k"]):
        group = group.sort_values(["issue_year", "issue"])
        realized = group["realized_roi_pct"].to_numpy(float)
        expected = group["expected_roi_pct"].to_numpy(float)
        boot = np.empty(draws, dtype=float)
        for draw in range(draws):
            boot[draw] = rng.choice(realized, len(realized), replace=True).mean()
        annual = (
            group.groupby("issue_year", as_index=False)
            .agg(
                realized_roi_pct=("realized_roi_pct", "mean"),
                expected_roi_pct=("expected_roi_pct", "mean"),
                issues=("issue", "nunique"),
            )
            .assign(n=key[0], generator=key[1], requested_k=key[2])
        )
        years.append(annual)
        capital = 100_000.0 + np.cumsum(realized)
        prior_peak = np.maximum.accumulate(np.r_[100_000.0, capital])[:-1]
        drawdown = (prior_peak - capital) / prior_peak
        rows.append(
            {
                "n": key[0],
                "generator": key[1],
                "requested_k": key[2],
                "issues": len(group),
                "mean_roi_pct": realized.mean(),
                "expected_roi_pct": expected.mean(),
                "median_issue_roi_pct": np.median(realized),
                "positive_issue_fraction": np.mean(realized > 0),
                "positive_years": int((annual["realized_roi_pct"] > 0).sum()),
                "ex_largest_roi_pct": (
                    (realized.sum() - realized.max()) / (len(realized) - 1)
                ),
                "bootstrap_low_pct": np.quantile(boot, 0.025),
                "bootstrap_high_pct": np.quantile(boot, 0.975),
                "bootstrap_probability_positive": np.mean(boot > 0),
                "ending_capital_cny": capital[-1],
                "max_issue_drawdown_fraction": drawdown.max(),
                "longest_losing_issue_streak": _longest_run(realized < 0),
                "alias_fraction": group["alias_fraction"].mean(),
            }
        )
    curve = pd.DataFrame(rows).sort_values(
        ["mean_roi_pct", "ex_largest_roi_pct"], ascending=False
    )
    yearly = pd.concat(years, ignore_index=True)
    return curve, yearly


def _family_curve(subset_actions: pd.DataFrame) -> pd.DataFrame:
    keys = ["n", "proposal_family", "generator", "requested_k"]
    return (
        subset_actions.groupby(keys, as_index=False)
        .agg(
            mean_roi_pct=("realized_roi_pct", "mean"),
            expected_roi_pct=("expected_roi_pct", "mean"),
            median_subset_roi_pct=("realized_roi_pct", "median"),
            positive_subset_fraction=("realized_roi_pct", lambda value: (value > 0).mean()),
            subsets=("subset_id", "nunique"),
        )
        .sort_values("mean_roi_pct", ascending=False)
    )


def _generator_lift(issue_actions: pd.DataFrame) -> pd.DataFrame:
    pivot = issue_actions.pivot(
        index=["issue", "issue_year", "n", "requested_k"],
        columns="generator",
        values="realized_roi_pct",
    ).dropna()
    pivot["weighted_minus_top_pct"] = pivot["WEIGHTED_WR"] - pivot["TOP_VALUE"]
    return (
        pivot.reset_index()
        .groupby(["n", "requested_k"], as_index=False)
        .agg(
            mean_lift_pct=("weighted_minus_top_pct", "mean"),
            median_lift_pct=("weighted_minus_top_pct", "median"),
            positive_lift_fraction=("weighted_minus_top_pct", lambda value: (value > 0).mean()),
        )
        .sort_values("mean_lift_pct", ascending=False)
    )


def _year_rank_reliability(yearly: pd.DataFrame) -> dict[str, float]:
    pivot = yearly.pivot(
        index=["n", "generator", "requested_k"],
        columns="issue_year",
        values="realized_roi_pct",
    )
    correlations: list[float] = []
    columns = list(pivot.columns)
    for left, year_left in enumerate(columns):
        for year_right in columns[left + 1 :]:
            correlation = spearmanr(pivot[year_left], pivot[year_right]).statistic
            if np.isfinite(correlation):
                correlations.append(float(correlation))
    return {
        "mean": float(np.mean(correlations)),
        "median": float(np.median(correlations)),
    }


def _longest_run(mask: np.ndarray) -> int:
    longest = current = 0
    for value in mask:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _record(row: pd.Series) -> dict[str, float | int | str]:
    return {
        "n": int(row["n"]),
        "generator": str(row["generator"]),
        "requested_k": int(row["requested_k"]),
        "mean_roi_pct": float(row["mean_roi_pct"]),
        "ex_largest_roi_pct": float(row["ex_largest_roi_pct"]),
        "bootstrap_low_pct": float(row["bootstrap_low_pct"]),
        "bootstrap_high_pct": float(row["bootstrap_high_pct"]),
        "positive_years": int(row["positive_years"]),
    }


def _plot_heatmaps(curve: pd.DataFrame, path: Path) -> None:
    generators = list(curve["generator"].drop_duplicates())
    figure, axes = plt.subplots(1, len(generators), figsize=(14, 5), squeeze=False)
    limits = np.nanpercentile(curve["mean_roi_pct"], [5, 95])
    bound = max(abs(limits[0]), abs(limits[1]))
    for axis, generator in zip(axes[0], generators):
        matrix = curve.loc[curve["generator"].eq(generator)].pivot(
            index="n", columns="requested_k", values="mean_roi_pct"
        )
        image = axis.imshow(
            matrix,
            aspect="auto",
            cmap="RdYlGn",
            vmin=-bound,
            vmax=bound,
            origin="lower",
        )
        axis.set_xticks(range(len(matrix.columns)), matrix.columns)
        axis.set_yticks(range(len(matrix.index)), matrix.index)
        axis.set(xlabel="K", ylabel="N", title=f"{generator}: realized mean ROI")
        for row in range(len(matrix.index)):
            for column in range(len(matrix.columns)):
                axis.text(column, row, f"{matrix.iloc[row, column]:.1f}", ha="center", va="center", fontsize=7)
    figure.colorbar(image, ax=axes.ravel().tolist(), label="Pre-tax ROI (%)")
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _plot_expected_realized(curve: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 6))
    for generator, group in curve.groupby("generator"):
        axis.scatter(
            group["expected_roi_pct"],
            group["mean_roi_pct"],
            alpha=0.75,
            label=generator,
        )
    axis.axhline(0, color="black", linewidth=1)
    axis.axvline(0, color="black", linewidth=1)
    axis.set(
        xlabel="Model-expected ROI (%)",
        ylabel="Historical realized mean ROI (%)",
        title="Expected surface versus realized joint actions",
    )
    axis.legend()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.csv")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
