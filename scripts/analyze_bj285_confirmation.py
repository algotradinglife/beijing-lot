#!/usr/bin/env python3
"""Summarize the nuisance-averaged #285 dense confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/issue-285/n8-dense/protection_confirmation_panel.parquet"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("results/issue-285/n8-dense")
    )
    parser.add_argument("--bootstrap-replicates", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=285_999)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    panel = pd.read_parquet(args.input.resolve())
    output = args.output.resolve()
    issue_keys = ["issue", "issue_year", "n", "k", "proposal_family", "rule"]
    issue_panel = panel.groupby(issue_keys, as_index=False).mean(numeric_only=True)
    rng = np.random.default_rng(args.seed)
    summary_rows: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    for action, action_frame in issue_panel.groupby(
        ["n", "k", "proposal_family"], sort=True
    ):
        by_rule = {
            rule: group.sort_values("issue").reset_index(drop=True)
            for rule, group in action_frame.groupby("rule", sort=True)
        }
        adverse = by_rule["ADVERSE_SIGNED_DIVERGENCE"]
        random = by_rule["RANDOM_BUDGET_CONTROL"]
        if not adverse["issue"].equals(random["issue"]):
            raise RuntimeError(f"rule issue sets differ for action={action}")
        indexes = rng.integers(
            0,
            len(adverse),
            size=(args.bootstrap_replicates, len(adverse)),
        )
        adverse_boot = _bootstrap_ratio(adverse, indexes, "protection_lift_cny")
        random_boot = _bootstrap_ratio(random, indexes, "protection_lift_cny")
        for rule, group in by_rule.items():
            boot = adverse_boot if rule == "ADVERSE_SIGNED_DIVERGENCE" else random_boot
            continuation_boot = _bootstrap_ratio(
                group, indexes, "protection_minus_continuation_cny"
            )
            largest_index = group["protection_lift_cny"].idxmax()
            ex_largest = group.drop(index=largest_index)
            near_miss = group["near_miss_tickets"].sum()
            summary_rows.append(
                {
                    "n": action[0],
                    "k": action[1],
                    "proposal_family": action[2],
                    "rule": rule,
                    "issues": len(group),
                    "marginal_protection_roi": _ratio(
                        group["protection_lift_cny"].sum(),
                        group["extra_stake_cny"].sum(),
                    ),
                    "ex_largest_marginal_roi": _ratio(
                        ex_largest["protection_lift_cny"].sum(),
                        ex_largest["extra_stake_cny"].sum(),
                    ),
                    "protection_excess_roi_vs_continuation": _ratio(
                        group["protection_minus_continuation_cny"].sum(),
                        group["extra_stake_cny"].sum(),
                    ),
                    "adverse_excess_roi_vs_random": _ratio(
                        adverse["protection_lift_cny"].sum(),
                        adverse["extra_stake_cny"].sum(),
                    )
                    - _ratio(
                        random["protection_lift_cny"].sum(),
                        random["extra_stake_cny"].sum(),
                    ),
                    "near_miss_tickets_mean_replica": near_miss,
                    "missed_leg_localization_rate": _ratio(
                        group["localized_near_miss_tickets"].sum(), near_miss
                    ),
                    "single_flip_rescue_rate": _ratio(
                        group["rescued_near_miss_tickets"].sum(), near_miss
                    ),
                    "positive_years": int(
                        group.groupby("issue_year")["protection_lift_cny"]
                        .sum()
                        .gt(0)
                        .sum()
                    ),
                    "largest_lift_issue": group.loc[largest_index, "issue"],
                    "bootstrap_marginal_roi_p025": np.quantile(boot, 0.025),
                    "bootstrap_marginal_roi_p500": np.quantile(boot, 0.5),
                    "bootstrap_marginal_roi_p975": np.quantile(boot, 0.975),
                    "bootstrap_excess_vs_continuation_p025": np.quantile(
                        continuation_boot, 0.025
                    ),
                    "bootstrap_excess_vs_continuation_p500": np.quantile(
                        continuation_boot, 0.5
                    ),
                    "bootstrap_excess_vs_continuation_p975": np.quantile(
                        continuation_boot, 0.975
                    ),
                    "bootstrap_adverse_minus_random_p025": np.quantile(
                        adverse_boot - random_boot, 0.025
                    ),
                    "bootstrap_adverse_minus_random_p500": np.quantile(
                        adverse_boot - random_boot, 0.5
                    ),
                    "bootstrap_adverse_minus_random_p975": np.quantile(
                        adverse_boot - random_boot, 0.975
                    ),
                }
            )
            bootstrap_rows.extend(
                {
                    "n": action[0],
                    "k": action[1],
                    "proposal_family": action[2],
                    "rule": rule,
                    "replicate": replicate,
                    "marginal_protection_roi": value,
                    "excess_roi_vs_continuation": continuation_boot[replicate],
                }
                for replicate, value in enumerate(boot)
            )
    summary = pd.DataFrame(summary_rows)
    by_seed = _group_summary(
        panel,
        ["n", "k", "proposal_family", "rule", "stream_seed"],
    )
    by_year = _group_summary(
        issue_panel,
        ["n", "k", "proposal_family", "rule", "issue_year"],
    )
    _atomic_csv(summary, output / "dense_protection_summary.csv")
    _atomic_csv(by_seed, output / "dense_protection_by_seed.csv")
    _atomic_csv(by_year, output / "dense_protection_by_year.csv")
    _atomic_parquet(
        pd.DataFrame(bootstrap_rows), output / "dense_issue_bootstrap.parquet"
    )
    _plot(summary, by_seed, output / "dense_protection_confirmation.png")
    adverse = summary.loc[summary["rule"].eq("ADVERSE_SIGNED_DIVERGENCE")]
    receipt = {
        "independent_unit": "ISSUE",
        "nuisance_aggregation": "MEAN_WITHIN_ISSUE_ACTION_ACROSS_SUBSET_AND_SEED",
        "bootstrap_replicates": args.bootstrap_replicates,
        "bootstrap_seed": args.seed,
        "adverse_all_marginal_roi_negative": bool(
            adverse["marginal_protection_roi"].lt(0).all()
        ),
        "adverse_localization_beats_random": bool(
            adverse["missed_leg_localization_rate"].min()
            > summary.loc[
                summary["rule"].eq("RANDOM_BUDGET_CONTROL"),
                "missed_leg_localization_rate",
            ].max()
        ),
        "decision": "NO_BLANKET_PROTECTION_ADVANCE_SELECTIVE_LEARNING",
    }
    _atomic_json(receipt, output / "dense_analysis_receipt.json")
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _bootstrap_ratio(
    group: pd.DataFrame, indexes: np.ndarray, numerator_column: str
) -> np.ndarray:
    numerator = group[numerator_column].to_numpy(float)
    stake = group["extra_stake_cny"].to_numpy(float)
    return numerator[indexes].sum(axis=1) / stake[indexes].sum(axis=1)


def _group_summary(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    summary = frame.groupby(keys, as_index=False).agg(
        protection_lift_cny=("protection_lift_cny", "sum"),
        extra_stake_cny=("extra_stake_cny", "sum"),
        protection_minus_continuation_cny=(
            "protection_minus_continuation_cny",
            "sum",
        ),
    )
    summary["marginal_protection_roi"] = (
        summary["protection_lift_cny"] / summary["extra_stake_cny"]
    )
    summary["excess_roi_vs_continuation"] = (
        summary["protection_minus_continuation_cny"]
        / summary["extra_stake_cny"]
    )
    return summary


def _plot(summary: pd.DataFrame, by_seed: pd.DataFrame, output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    adverse = summary.loc[summary["rule"].eq("ADVERSE_SIGNED_DIVERGENCE")]
    random = summary.loc[summary["rule"].eq("RANDOM_BUDGET_CONTROL")]
    x = np.arange(len(adverse))
    width = 0.36
    labels = [f"N{row.n}/K{row.k}" for row in adverse.itertuples(index=False)]
    axes[0].bar(
        x - width / 2, adverse["marginal_protection_roi"] * 100, width, label="Adverse"
    )
    axes[0].bar(
        x + width / 2, random["marginal_protection_roi"] * 100, width, label="Random"
    )
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Marginal protection ROI (%)")
    axes[0].set_title("Nuisance-averaged protection economics")
    axes[0].legend()
    adverse_seed = by_seed.loc[
        by_seed["rule"].eq("ADVERSE_SIGNED_DIVERGENCE")
    ]
    for k, group in adverse_seed.groupby("k", sort=True):
        axes[1].plot(
            group["stream_seed"].astype(str),
            group["marginal_protection_roi"] * 100,
            marker="o",
            label=f"K{k}",
        )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("Adverse-rule seed sensitivity")
    axes[1].set_xlabel("Ticket stream seed")
    axes[1].set_ylabel("Marginal protection ROI (%)")
    axes[1].legend()
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.png")
    figure.savefig(temporary, dpi=160)
    plt.close(figure)
    temporary.replace(output)


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else float("nan")


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.csv")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
