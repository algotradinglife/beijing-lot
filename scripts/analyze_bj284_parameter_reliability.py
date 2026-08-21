#!/usr/bin/env python3
"""Quantify whether #284 parameters are estimable from pre-event issue data."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--validation-year", type=int, default=2022)
    parser.add_argument("--seeds", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    frames = {
        f"seed{seed}": pd.read_parquet(
            output
            / f"pilot_predictions_{args.validation_year}_seed{seed}.parquet"
        )
        for seed in range(1, args.seeds + 1)
    }
    selected = {name: _select(frame) for name, frame in frames.items()}
    seed_summary = _seed_summary(selected)
    pairwise = _pairwise_reliability(frames, selected)
    consensus = _issue_consensus(selected)
    ensemble_candidates, ensemble_selected = _ensemble(frames)
    ensemble_summary = _ensemble_summary(ensemble_selected)
    receipt = _receipt(
        args.validation_year,
        seed_summary,
        pairwise,
        consensus,
        ensemble_candidates,
        ensemble_selected,
        ensemble_summary,
    )

    _atomic_csv(seed_summary, output / "parameter_reliability_seed_summary.csv")
    _atomic_csv(pairwise, output / "parameter_reliability_pairwise.csv")
    _atomic_csv(consensus, output / "parameter_reliability_issue_consensus.csv")
    _atomic_parquet(
        ensemble_candidates, output / "parameter_reliability_ensemble_frontier.parquet"
    )
    _atomic_parquet(
        ensemble_selected, output / "parameter_reliability_ensemble_selected.parquet"
    )
    _atomic_json(receipt, output / "parameter_reliability_receipt.json")
    _plot_selection(seed_summary, selected, output / "parameter_reliability_n.png")
    _plot_margin(
        ensemble_selected, output / "parameter_reliability_margin_vs_seed_sd.png"
    )
    _plot_capital(
        selected,
        ensemble_selected,
        output / "parameter_reliability_capital_paths.png",
    )
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _select(frame: pd.DataFrame) -> pd.DataFrame:
    frontier = (
        frame.sort_values(
            ["issue", "n", "policy_score", "subset_id"],
            ascending=[True, True, False, True],
        )
        .groupby(["issue", "n"], as_index=False)
        .head(1)
    )
    return (
        frontier.sort_values(
            ["issue", "policy_score", "subset_id"],
            ascending=[True, False, True],
        )
        .groupby("issue", as_index=False)
        .head(1)
        .sort_values("issue")
        .reset_index(drop=True)
    )


def _seed_summary(selected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for seed, frame in selected.items():
        lift = frame["matched_lift_cny100"].to_numpy(float)
        positive_lift = lift[lift > 0]
        pnl = frame["normalized_pnl_cny100"].to_numpy(float)
        rows.append(
            {
                "seed": seed,
                "issues": len(frame),
                "selected_n_unique": int(frame["n"].nunique()),
                "pnl_cny100": float(pnl.sum()),
                "matched_lift_cny100": float(lift.sum()),
                "ex_largest_matched_lift_cny100": float(
                    lift.sum()
                    - (positive_lift.max() if len(positive_lift) else 0.0)
                ),
                "positive_issues": int((pnl > 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def _pairwise_reliability(
    frames: dict[str, pd.DataFrame], selected: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for left, right in combinations(frames, 2):
        a = selected[left].set_index("issue")
        b = selected[right].set_index("issue")
        issues = a.index.intersection(b.index)
        prediction = frames[left][
            ["subset_id", "expected_value", "policy_score"]
        ].merge(
            frames[right][["subset_id", "expected_value", "policy_score"]],
            on="subset_id",
            suffixes=("_left", "_right"),
            validate="one_to_one",
        )
        rows.append(
            {
                "left_seed": left,
                "right_seed": right,
                "n_agreement": float((a.loc[issues, "n"] == b.loc[issues, "n"]).mean()),
                "family_agreement": float(
                    (
                        a.loc[issues, "proposal_family"]
                        == b.loc[issues, "proposal_family"]
                    ).mean()
                ),
                "subset_agreement": float(
                    (a.loc[issues, "subset_id"] == b.loc[issues, "subset_id"]).mean()
                ),
                "expected_value_spearman": float(
                    spearmanr(
                        prediction["expected_value_left"],
                        prediction["expected_value_right"],
                    ).statistic
                ),
                "policy_score_spearman": float(
                    spearmanr(
                        prediction["policy_score_left"],
                        prediction["policy_score_right"],
                    ).statistic
                ),
            }
        )
    return pd.DataFrame(rows)


def _issue_consensus(selected: dict[str, pd.DataFrame]) -> pd.DataFrame:
    n = pd.DataFrame(
        {seed: frame.set_index("issue")["n"] for seed, frame in selected.items()}
    )
    family = pd.DataFrame(
        {
            seed: frame.set_index("issue")["proposal_family"]
            for seed, frame in selected.items()
        }
    )
    subset = pd.DataFrame(
        {
            seed: frame.set_index("issue")["subset_id"]
            for seed, frame in selected.items()
        }
    )
    result = pd.DataFrame(index=n.index)
    result["modal_n"] = n.mode(axis=1)[0]
    result["n_consensus_fraction"] = n.apply(_modal_fraction, axis=1)
    result["modal_family"] = family.mode(axis=1)[0]
    result["family_consensus_fraction"] = family.apply(_modal_fraction, axis=1)
    result["modal_subset_id"] = subset.mode(axis=1)[0]
    result["subset_consensus_fraction"] = subset.apply(_modal_fraction, axis=1)
    return result.reset_index()


def _modal_fraction(row: pd.Series) -> float:
    return float(row.value_counts(normalize=True).iloc[0])


def _ensemble(
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keep = [
        "issue",
        "subset_id",
        "n",
        "proposal_family",
        "normalized_pnl_cny100",
        "baseline_pnl_cny100",
        "is_matched_baseline",
        "policy_score",
    ]
    long = pd.concat(
        [frame[keep].assign(seed=seed) for seed, frame in frames.items()],
        ignore_index=True,
    )
    candidates = (
        long.groupby(
            ["issue", "subset_id", "n", "proposal_family"], as_index=False
        )
        .agg(
            realized_pnl_cny100=("normalized_pnl_cny100", "first"),
            baseline_pnl_cny100=("baseline_pnl_cny100", "first"),
            is_matched_baseline=("is_matched_baseline", "first"),
            score_mean=("policy_score", "mean"),
            score_sd=("policy_score", "std"),
            score_min=("policy_score", "min"),
            positive_score_seeds=("policy_score", lambda values: int((values > 0).sum())),
        )
    )
    frontier = (
        candidates.sort_values(
            ["issue", "n", "score_mean", "subset_id"],
            ascending=[True, True, False, True],
        )
        .groupby(["issue", "n"], as_index=False)
        .head(1)
    )
    ranked = frontier.sort_values(
        ["issue", "score_mean", "subset_id"], ascending=[True, False, True]
    ).copy()
    ranked["cross_n_rank"] = ranked.groupby("issue").cumcount() + 1
    selected = ranked.loc[ranked["cross_n_rank"].le(2)].copy()
    selected["runner_score"] = selected.groupby("issue")["score_mean"].shift(-1)
    selected = selected.loc[selected["cross_n_rank"].eq(1)].copy()
    selected["score_margin"] = selected["score_mean"] - selected["runner_score"]
    selected["margin_exceeds_seed_sd"] = selected["score_margin"].gt(
        selected["score_sd"]
    )
    selected["unanimous_positive_score"] = selected["positive_score_seeds"].eq(
        len(frames)
    )
    selected["matched_lift_cny100"] = (
        selected["realized_pnl_cny100"] - selected["baseline_pnl_cny100"]
    )
    return candidates, selected


def _ensemble_summary(selected: pd.DataFrame) -> dict[str, float | int | dict[str, int]]:
    lift = selected["matched_lift_cny100"].to_numpy(float)
    positive_lift = lift[lift > 0]
    return {
        "issues": int(len(selected)),
        "selected_n": {
            str(int(n)): int(count) for n, count in selected["n"].value_counts().items()
        },
        "pnl_cny100": float(selected["realized_pnl_cny100"].sum()),
        "matched_lift_cny100": float(lift.sum()),
        "ex_largest_matched_lift_cny100": float(
            lift.sum() - (positive_lift.max() if len(positive_lift) else 0.0)
        ),
        "margin_exceeds_seed_sd_issues": int(
            selected["margin_exceeds_seed_sd"].sum()
        ),
        "unanimous_positive_score_issues": int(
            selected["unanimous_positive_score"].sum()
        ),
    }


def _receipt(
    validation_year: int,
    seed_summary: pd.DataFrame,
    pairwise: pd.DataFrame,
    consensus: pd.DataFrame,
    ensemble_candidates: pd.DataFrame,
    ensemble_selected: pd.DataFrame,
    ensemble_summary: dict[str, object],
) -> dict[str, object]:
    value_surface_pass = pairwise["policy_score_spearman"].mean() >= 0.80
    parameter_choice_pass = (
        pairwise["n_agreement"].mean() >= 0.65
        and pairwise["family_agreement"].mean() >= 0.55
        and ensemble_selected["margin_exceeds_seed_sd"].mean() >= 0.50
    )
    capital_sign_pass = (
        (seed_summary["matched_lift_cny100"] > 0).sum() >= 4
        and (seed_summary["ex_largest_matched_lift_cny100"] > 0).sum() >= 4
    )
    return {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-reliability-pilot",
        "validation_year": validation_year,
        "model_seed_count": int(len(seed_summary)),
        "independent_historical_units": int(consensus["issue"].nunique()),
        "model_seeds_are_not_independent_historical_units": True,
        "mean_pairwise_policy_score_spearman": float(
            pairwise["policy_score_spearman"].mean()
        ),
        "mean_pairwise_n_agreement": float(pairwise["n_agreement"].mean()),
        "mean_pairwise_family_agreement": float(
            pairwise["family_agreement"].mean()
        ),
        "mean_pairwise_subset_agreement": float(
            pairwise["subset_agreement"].mean()
        ),
        "all_seed_n_consensus_issues": int(
            consensus["n_consensus_fraction"].eq(1.0).sum()
        ),
        "ensemble": ensemble_summary,
        "exploratory_reliability_gates": {
            "value_surface_rank_stability": {
                "threshold": "mean pairwise Spearman >= 0.80",
                "pass": bool(value_surface_pass),
            },
            "discrete_parameter_stability": {
                "threshold": "N agreement >= 0.65; family >= 0.55; reliable margin on >= 50% issues",
                "pass": bool(parameter_choice_pass),
            },
            "capital_sign_stability": {
                "threshold": ">=4/5 seeds positive lift and positive ex-largest lift",
                "pass": bool(capital_sign_pass),
            },
        },
        "feasibility_verdict": (
            "VALUE_SURFACE_FEASIBLE_PARAMETER_CHOICE_NOT_YET_RELIABLE"
            if value_surface_pass and not parameter_choice_pass
            else "REQUIRES_REVIEW"
        ),
        "sealed_years_opened": [],
        "candidate_rows": int(len(ensemble_candidates)),
    }


def _plot_selection(
    seed_summary: pd.DataFrame,
    selected: dict[str, pd.DataFrame],
    path: Path,
) -> None:
    del seed_summary
    counts = pd.DataFrame(
        {seed: frame["n"].value_counts() for seed, frame in selected.items()}
    ).fillna(0).sort_index()
    axis = counts.T.plot(kind="bar", stacked=True, figsize=(9, 5), colormap="viridis")
    axis.set_ylabel("Selected issues")
    axis.set_xlabel("Model seed")
    axis.set_title("#284 selected N varies materially across model seeds")
    axis.legend(title="N", ncol=4)
    axis.figure.tight_layout()
    axis.figure.savefig(path, dpi=160)
    plt.close(axis.figure)


def _plot_margin(selected: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.scatter(selected["score_sd"], selected["score_margin"], alpha=0.75)
    limit = max(float(selected["score_sd"].max()), float(selected["score_margin"].max()))
    axis.plot([0, limit], [0, limit], linestyle="--", color="black", linewidth=1)
    axis.set_xlabel("Top candidate score SD across seeds")
    axis.set_ylabel("Top-vs-runner-up mean score margin")
    axis.set_title("Only points above the diagonal have a robust action margin")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_capital(
    selected: dict[str, pd.DataFrame], ensemble: pd.DataFrame, path: Path
) -> None:
    figure, axis = plt.subplots(figsize=(10, 5))
    for seed, frame in selected.items():
        ordered = frame.sort_values("issue")
        axis.plot(
            range(1, len(ordered) + 1),
            100_000 + ordered["normalized_pnl_cny100"].cumsum(),
            alpha=0.45,
            label=seed,
        )
    ordered = ensemble.sort_values("issue")
    axis.plot(
        range(1, len(ordered) + 1),
        100_000 + ordered["realized_pnl_cny100"].cumsum(),
        color="black",
        linewidth=2,
        label="ensemble mean score",
    )
    axis.axhline(100_000, color="grey", linewidth=1)
    axis.set_xlabel("2022 issue order")
    axis.set_ylabel("CNY100,000 capital")
    axis.set_title("#284 model-seed capital-path dispersion")
    axis.legend(ncol=3)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.csv")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
