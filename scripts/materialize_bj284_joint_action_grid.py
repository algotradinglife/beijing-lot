#!/usr/bin/env python3
"""Materialize the bounded #284 N×K×generator interaction pilot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue282.labels import divergence_value_surface  # noqa: E402
from issue284.labels import settle_sampled_action_grid  # noqa: E402
from issue284.sampler import PROPOSAL_FAMILIES  # noqa: E402

OUTCOMES = ("3", "1", "0")
OUTCOME_TO_POSITION = {outcome: position for position, outcome in enumerate(OUTCOMES)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    parser.add_argument(
        "--issue209-results",
        type=Path,
        default=None,
        help="Directory containing the reusable #209 probability/value parquet files.",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--subsets-per-family", type=int, default=1)
    parser.add_argument(
        "--n-values",
        type=int,
        nargs="+",
        default=list(range(3, 11)),
    )
    parser.add_argument(
        "--stream-seeds",
        type=int,
        nargs="+",
        default=[284_501],
        help="Fixed nuisance replicas for WEIGHTED_WR; never optimized.",
    )
    parser.add_argument(
        "--k-values",
        type=int,
        nargs="+",
        default=[8, 16, 32, 64, 128, 256, 512],
    )
    parser.add_argument("--artifact-name", default="joint_action_grid_pilot")
    parser.add_argument(
        "--outcome-modes",
        nargs="+",
        choices=("CELL_VALUE", "MARKET_PROBABILITY", "DIVERGENCE_VALUE"),
        default=["CELL_VALUE"],
    )
    parser.add_argument(
        "--generators",
        nargs="+",
        choices=("TOP_VALUE", "WEIGHTED_WR"),
        default=["TOP_VALUE", "WEIGHTED_WR"],
    )
    parser.add_argument(
        "--proposal-families",
        nargs="+",
        choices=PROPOSAL_FAMILIES,
        default=list(PROPOSAL_FAMILIES),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = args.artifact_root.resolve()
    output = args.output.resolve()
    issue209_results = (
        args.issue209_results.resolve()
        if args.issue209_results is not None
        else artifact_root / "results/issue-209"
    )
    if args.subsets_per_family <= 0:
        raise ValueError("subsets per family must be positive")
    if not args.stream_seeds:
        raise ValueError("at least one weighted-stream seed is required")
    k_values = tuple(sorted(set(args.k_values)))
    if not k_values or k_values[0] <= 0:
        raise ValueError("K values must be positive")
    n_values = tuple(sorted(set(args.n_values)))
    if not n_values or min(n_values) < 3 or max(n_values) > 10:
        raise ValueError("N values must be inside the frozen [3, 10] range")
    profile = pd.read_parquet(output / "subset_profile.parquet")
    selected = (
        profile.loc[
            profile["proposal_family"].isin(args.proposal_families)
            & profile["n"].isin(n_values)
        ]
        .sort_values(["issue", "n", "proposal_family", "subset_id"])
        .groupby(["issue", "n", "proposal_family"], as_index=False)
        .head(args.subsets_per_family)
        .copy()
    )
    selected["match_ids"] = selected["match_ids"].map(json.loads)
    probabilities = pd.read_parquet(
        issue209_results / "market_only_probabilities.parquet"
    )
    values = pd.read_parquet(issue209_results / "cell_value_distribution.parquet")
    tensor = build_tensor()
    units = build_match_units(tensor)
    if tensor["issue_year"].ge(2024).any() or units["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ joint-grid seal violated")
    if not units.index.equals(probabilities.index) or not units.index.equals(values.index):
        raise RuntimeError("#209 unit/probability/value indexes are not aligned")

    winners = (
        tensor.loc[tensor["Y"].eq(1), ["issue", "match_idx", "SP_SETTLE"]]
        .drop_duplicates(["issue", "match_idx"])
        .assign(issue=lambda frame: frame["issue"].astype(str))
    )
    winner_sp = {
        str(issue): group.set_index(group["match_idx"].astype(str))["SP_SETTLE"].to_dict()
        for issue, group in winners.groupby("issue", sort=False)
    }
    units = units.loc[units["snapshot_kind"].eq("10h")].copy()
    units["issue"] = units["issue"].astype(str)
    selected_by_issue = {
        issue: group for issue, group in selected.groupby("issue", sort=False)
    }
    issue_frames: list[pd.DataFrame] = []
    for issue_number, (issue, group) in enumerate(units.groupby("issue", sort=True), 1):
        subsets = selected_by_issue.get(str(issue))
        if subsets is None:
            continue
        indexes = group.index
        match_ids = group["match_idx"].astype(str).tolist()
        position = {match_id: offset for offset, match_id in enumerate(match_ids)}
        probability = probabilities.reindex(indexes)[list(OUTCOMES)].to_numpy(float)
        cell_value = values.reindex(indexes)[
            [f"ev_raw_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(float)
        divergence = group[
            [f"eu_vs_line_divergence_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(float)
        realized = np.array(
            [OUTCOME_TO_POSITION[str(outcome)] for outcome in group["realized_outcome"]],
            dtype=int,
        )
        sp_lookup = winner_sp.get(str(issue), {})
        winning_sp = np.array(
            [float(sp_lookup.get(match_id, np.nan)) for match_id in match_ids]
        )
        subset_frames: list[pd.DataFrame] = []
        for subset in subsets.itertuples(index=False):
            local = np.array([position[str(match_id)] for match_id in subset.match_ids])
            local_value = cell_value[local]
            local_probability = probability[local]
            local_divergence = divergence[local]
            mode_frames: list[pd.DataFrame] = []
            for outcome_mode in args.outcome_modes:
                if outcome_mode == "CELL_VALUE":
                    proposal_surface = local_value
                elif outcome_mode == "MARKET_PROBABILITY":
                    proposal_surface = local_probability
                else:
                    proposal_surface = divergence_value_surface(
                        local_value, local_probability, local_divergence
                    )
                replicas: list[pd.DataFrame] = []
                if "TOP_VALUE" in args.generators:
                    top = settle_sampled_action_grid(
                        subset_id=str(subset.subset_id),
                        cell_value=local_value,
                        probability=local_probability,
                        proposal_surface=proposal_surface,
                        outcome_weight_mode=outcome_mode,
                        realized_outcomes=realized[local],
                        winning_sp=winning_sp[local],
                        generators=("TOP_VALUE",),
                        k_values=k_values,
                        seed=0,
                    )
                    top["stream_replica"] = 0
                    replicas.append(top)
                if "WEIGHTED_WR" in args.generators:
                    for replica, seed in enumerate(args.stream_seeds, 1):
                        weighted = settle_sampled_action_grid(
                            subset_id=str(subset.subset_id),
                            cell_value=local_value,
                            probability=local_probability,
                            proposal_surface=proposal_surface,
                            outcome_weight_mode=outcome_mode,
                            realized_outcomes=realized[local],
                            winning_sp=winning_sp[local],
                            generators=("WEIGHTED_WR",),
                            k_values=k_values,
                            seed=seed,
                        )
                        weighted["stream_replica"] = replica
                        replicas.append(weighted)
                mode_frames.append(pd.concat(replicas, ignore_index=True))
            action = pd.concat(mode_frames, ignore_index=True)
            action["issue"] = str(issue)
            action["issue_year"] = int(group["issue_year"].iloc[0])
            action["issue_match_count"] = int(len(group))
            action["n"] = int(subset.n)
            action["proposal_family"] = str(subset.proposal_family)
            action["match_ids"] = json.dumps(subset.match_ids, separators=(",", ":"))
            subset_frames.append(action)
        issue_frames.append(pd.concat(subset_frames, ignore_index=True))
        if issue_number % 50 == 0:
            print(f"processed issues={issue_number}", flush=True)
    result = pd.concat(issue_frames, ignore_index=True)
    result["action_key"] = (
        result["outcome_weight_mode"]
        + "_N"
        + result["n"].astype(str)
        + "_"
        + result["generator"]
        + "_K"
        + result["effective_k"].astype(str)
    )
    result["issue_training_weight"] = 1.0 / result.groupby("issue")[
        "issue"
    ].transform("size")
    weight_sum = result.groupby("issue")["issue_training_weight"].sum()
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-joint-grid-pilot",
        "issues": int(result["issue"].nunique()),
        "rows": int(len(result)),
        "subsets": int(result["subset_id"].nunique()),
        "subsets_per_issue_n_family": args.subsets_per_family,
        "stream_seeds": list(args.stream_seeds),
        "n": sorted(int(value) for value in result["n"].unique()),
        "generators": sorted(result["generator"].unique()),
        "outcome_weight_modes": sorted(result["outcome_weight_mode"].unique()),
        "requested_k": sorted(int(value) for value in result["requested_k"].unique()),
        "effective_alias_rows": int(result["is_effective_k_alias"].sum()),
        "maximum_issue_weight_error": float(np.abs(weight_sum - 1.0).max()),
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_N_FOLD_TICKET",
        "sealed_years_opened": [],
    }
    _atomic_parquet(result, output / f"{args.artifact_name}.parquet")
    _atomic_json(receipt, output / f"{args.artifact_name}_receipt.json")
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


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
