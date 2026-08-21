#!/usr/bin/env python3
"""Analyze the issue-clustered #285 near-miss protection pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/issue-285"))
    parser.add_argument("--output", type=Path, default=Path("results/issue-285"))
    parser.add_argument("--bootstrap-replicates", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=285_901)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    tickets = pd.read_parquet(source / "near_miss_ticket_ledger.parquet")
    protection = pd.read_parquet(source / "protection_pilot_ledger.parquet")
    attribution = pd.read_parquet(
        source / "near_miss_protection_attribution.parquet"
    )
    issues = sorted(protection["issue"].unique(), key=_issue_sort_key)
    rng = np.random.default_rng(args.seed)

    distance = (
        tickets.groupby("miss_bucket", observed=True)
        .size()
        .rename("tickets")
        .reset_index()
    )
    distance["share"] = distance["tickets"] / distance["tickets"].sum()
    distance["issue_count"] = tickets["issue"].nunique()

    random = protection.loc[protection["rule"].eq("RANDOM_BUDGET_CONTROL")].set_index(
        "issue"
    )
    summary_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    for rule, group in protection.groupby("rule", sort=True):
        group = group.set_index("issue").reindex(issues)
        if group.isna().any(axis=None):
            raise RuntimeError(f"rule {rule} does not cover the common issue set")
        marginal_roi = _ratio(
            group["rescued_gross_cny"].sum() - group["extra_stake_cny"].sum(),
            group["extra_stake_cny"].sum(),
        )
        base_roi = _ratio(group["base_pnl_cny"].sum(), group["base_stake_cny"].sum())
        protected_roi = _ratio(
            group["protected_pnl_cny"].sum(), group["protected_stake_cny"].sum()
        )
        largest_issue = group["protection_lift_cny"].idxmax()
        ex_largest = group.drop(index=largest_issue)
        ex_largest_marginal_roi = _ratio(
            ex_largest["rescued_gross_cny"].sum()
            - ex_largest["extra_stake_cny"].sum(),
            ex_largest["extra_stake_cny"].sum(),
        )
        attr = attribution.loc[attribution["rule"].eq(rule)]
        boot = _bootstrap_marginal_roi(
            group,
            replicates=args.bootstrap_replicates,
            rng=rng,
        )
        paired = _bootstrap_excess_vs_random(
            group,
            random.reindex(issues),
            replicates=args.bootstrap_replicates,
            rng=rng,
        )
        continuation_excess = _bootstrap_excess_vs_continuation(
            group,
            replicates=args.bootstrap_replicates,
            rng=rng,
        )
        summary_rows.append(
            {
                "rule": rule,
                "issues": len(group),
                "base_stake_cny": group["base_stake_cny"].sum(),
                "base_pnl_cny": group["base_pnl_cny"].sum(),
                "base_roi": base_roi,
                "protected_stake_cny": group["protected_stake_cny"].sum(),
                "protected_pnl_cny": group["protected_pnl_cny"].sum(),
                "protected_roi": protected_roi,
                "extra_stake_cny": group["extra_stake_cny"].sum(),
                "protection_lift_cny": group["protection_lift_cny"].sum(),
                "marginal_protection_roi": marginal_roi,
                "marginal_continuation_roi": _ratio(
                    group["continuation_lift_cny"].sum(),
                    group["extra_stake_cny"].sum(),
                ),
                "protection_excess_roi_vs_continuation": _ratio(
                    group["protection_minus_continuation_cny"].sum(),
                    group["extra_stake_cny"].sum(),
                ),
                "protected_minus_base_roi": protected_roi - base_roi,
                "rescued_issues": int(group["portfolio_rescued"].sum()),
                "positive_lift_issues": int((group["protection_lift_cny"] > 0).sum()),
                "near_miss_tickets": int(len(attr)),
                "missed_leg_localization_rate": attr[
                    "protects_unique_missed_leg"
                ].mean(),
                "single_flip_rescue_rate": attr["alternative_rescues"].mean(),
                "largest_lift_issue": largest_issue,
                "largest_lift_cny": group.loc[largest_issue, "protection_lift_cny"],
                "ex_largest_marginal_roi": ex_largest_marginal_roi,
                "positive_lift_years": int(
                    group.groupby("issue_year")["protection_lift_cny"]
                    .sum()
                    .gt(0)
                    .sum()
                ),
                "bootstrap_marginal_roi_p025": np.quantile(boot, 0.025),
                "bootstrap_marginal_roi_p500": np.quantile(boot, 0.5),
                "bootstrap_marginal_roi_p975": np.quantile(boot, 0.975),
                "bootstrap_probability_marginal_roi_positive": (boot > 0).mean(),
                "bootstrap_excess_vs_random_p025": np.quantile(paired, 0.025),
                "bootstrap_excess_vs_random_p500": np.quantile(paired, 0.5),
                "bootstrap_excess_vs_random_p975": np.quantile(paired, 0.975),
                "bootstrap_excess_vs_continuation_p025": np.quantile(
                    continuation_excess, 0.025
                ),
                "bootstrap_excess_vs_continuation_p500": np.quantile(
                    continuation_excess, 0.5
                ),
                "bootstrap_excess_vs_continuation_p975": np.quantile(
                    continuation_excess, 0.975
                ),
            }
        )
        for year, annual in group.groupby("issue_year", sort=True):
            annual_rows.append(
                {
                    "rule": rule,
                    "issue_year": int(year),
                    "issues": len(annual),
                    "base_roi": _ratio(
                        annual["base_pnl_cny"].sum(),
                        annual["base_stake_cny"].sum(),
                    ),
                    "protected_roi": _ratio(
                        annual["protected_pnl_cny"].sum(),
                        annual["protected_stake_cny"].sum(),
                    ),
                    "marginal_protection_roi": _ratio(
                        annual["rescued_gross_cny"].sum()
                        - annual["extra_stake_cny"].sum(),
                        annual["extra_stake_cny"].sum(),
                    ),
                    "protection_lift_cny": annual["protection_lift_cny"].sum(),
                }
            )
        bootstrap_rows.extend(
            {
                "rule": rule,
                "replicate": replicate,
                "marginal_protection_roi": value,
                "excess_marginal_roi_vs_random": paired[replicate],
            }
            for replicate, value in enumerate(boot)
        )

    summary = pd.DataFrame(summary_rows).sort_values(
        "marginal_protection_roi", ascending=False
    )
    annual = pd.DataFrame(annual_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    _atomic_csv(distance, output / "near_miss_distance_summary.csv")
    _atomic_csv(summary, output / "protection_rule_summary.csv")
    _atomic_csv(annual, output / "protection_rule_by_year.csv")
    _atomic_parquet(bootstrap, output / "protection_issue_bootstrap.parquet")
    _plot_path_and_distance(protection, distance, output / "protection_pilot.png")
    receipt = {
        "independent_unit": "ISSUE",
        "nested_units": ["ticket", "subset", "stream_seed"],
        "bootstrap_replicates": args.bootstrap_replicates,
        "bootstrap_seed": args.seed,
        "issue_count": len(issues),
        "best_rule_by_marginal_roi": str(summary.iloc[0]["rule"]),
        "best_marginal_roi": float(summary.iloc[0]["marginal_protection_roi"]),
        "best_ex_largest_marginal_roi": float(
            summary.iloc[0]["ex_largest_marginal_roi"]
        ),
        "best_bootstrap_interval": [
            float(summary.iloc[0]["bootstrap_marginal_roi_p025"]),
            float(summary.iloc[0]["bootstrap_marginal_roi_p975"]),
        ],
        "decision": "PILOT_ONLY_REQUIRES_BOUNDED_FACTORIAL_CONFIRMATION",
    }
    _atomic_json(receipt, output / "protection_analysis_receipt.json")
    print(summary.to_string(index=False), flush=True)
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _bootstrap_marginal_roi(
    group: pd.DataFrame, *, replicates: int, rng: np.random.Generator
) -> np.ndarray:
    gross = group["rescued_gross_cny"].to_numpy(float)
    stake = group["extra_stake_cny"].to_numpy(float)
    indexes = rng.integers(0, len(group), size=(replicates, len(group)))
    sampled_stake = stake[indexes].sum(axis=1)
    return (gross[indexes].sum(axis=1) - sampled_stake) / sampled_stake


def _bootstrap_excess_vs_random(
    group: pd.DataFrame,
    random: pd.DataFrame,
    *,
    replicates: int,
    rng: np.random.Generator,
) -> np.ndarray:
    indexes = rng.integers(0, len(group), size=(replicates, len(group)))
    gross = group["rescued_gross_cny"].to_numpy(float)
    stake = group["extra_stake_cny"].to_numpy(float)
    random_gross = random["rescued_gross_cny"].to_numpy(float)
    random_stake = random["extra_stake_cny"].to_numpy(float)
    candidate_roi = (gross[indexes].sum(axis=1) - stake[indexes].sum(axis=1)) / stake[
        indexes
    ].sum(axis=1)
    random_roi = (
        random_gross[indexes].sum(axis=1) - random_stake[indexes].sum(axis=1)
    ) / random_stake[indexes].sum(axis=1)
    return candidate_roi - random_roi


def _bootstrap_excess_vs_continuation(
    group: pd.DataFrame, *, replicates: int, rng: np.random.Generator
) -> np.ndarray:
    excess = group["protection_minus_continuation_cny"].to_numpy(float)
    stake = group["extra_stake_cny"].to_numpy(float)
    indexes = rng.integers(0, len(group), size=(replicates, len(group)))
    return excess[indexes].sum(axis=1) / stake[indexes].sum(axis=1)


def _plot_path_and_distance(
    protection: pd.DataFrame, distance: pd.DataFrame, output: Path
) -> None:
    order = sorted(protection["issue"].unique(), key=_issue_sort_key)
    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for rule, group in protection.groupby("rule", sort=True):
        path = group.set_index("issue").reindex(order)["protection_lift_cny"].cumsum()
        axes[0].plot(range(len(path)), path, label=rule, linewidth=1.4)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("Cumulative protection lift by issue")
    axes[0].set_xlabel("Chronological issue index")
    axes[0].set_ylabel("Cumulative lift (CNY)")
    axes[0].legend(fontsize=7)
    axes[1].bar(distance["miss_bucket"], distance["share"] * 100)
    axes[1].set_title("Ticket miss-distance distribution")
    axes[1].set_xlabel("Missed legs")
    axes[1].set_ylabel("Tickets (%)")
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.png")
    figure.savefig(temporary, dpi=160)
    plt.close(figure)
    temporary.replace(output)


def _issue_sort_key(issue: str) -> tuple[int, str]:
    return (int(issue) if str(issue).isdigit() else 10**12, str(issue))


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
