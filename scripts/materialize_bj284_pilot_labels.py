#!/usr/bin/env python3
"""Materialize the one-seed #284 activity pilot on sampled N×3 subsets."""

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
from issue284.labels import settle_sampled_subset  # noqa: E402
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
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--k", type=int, default=128)
    parser.add_argument("--seed", type=int, default=284_101)
    parser.add_argument("--subsets-per-family", type=int, default=1)
    parser.add_argument("--output-stem", default="pilot_subset_labels")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = args.artifact_root.resolve()
    output = args.output.resolve()
    profile_path = output / "subset_profile.parquet"
    probability_path = artifact_root / "results/issue-209/market_only_probabilities.parquet"
    value_path = artifact_root / "results/issue-209/cell_value_distribution.parquet"
    for path in (profile_path, probability_path, value_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    profile = pd.read_parquet(profile_path)
    profile = profile[profile["proposal_family"].isin(PROPOSAL_FAMILIES)].copy()
    if args.subsets_per_family <= 0:
        raise ValueError("subsets per family must be positive")
    pilot = (
        profile.sort_values(["issue", "n", "proposal_family", "subset_id"])
        .groupby(["issue", "n", "proposal_family"], as_index=False)
        .head(args.subsets_per_family)
        .copy()
    )
    pilot["match_ids"] = pilot["match_ids"].map(json.loads)
    tensor = build_tensor()
    units = build_match_units(tensor)
    if units["issue_year"].ge(2024).any() or tensor["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ pilot-label seal violated")
    probabilities = pd.read_parquet(probability_path)
    values = pd.read_parquet(value_path)
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
    unit_h = units.loc[units["snapshot_kind"].eq("10h")].copy()
    unit_h["issue"] = unit_h["issue"].astype(str)
    rows: list[dict[str, object]] = []
    missing_winning_sp_matches = 0
    pilot_by_issue = {issue: group for issue, group in pilot.groupby("issue", sort=False)}
    for issue, group in unit_h.groupby("issue", sort=True):
        selected = pilot_by_issue.get(str(issue))
        if selected is None:
            continue
        indexes = group.index
        match_ids = group["match_idx"].astype(str).tolist()
        position = {match_id: offset for offset, match_id in enumerate(match_ids)}
        probability = probabilities.reindex(indexes)[list(OUTCOMES)].to_numpy(float)
        cell_value = values.reindex(indexes)[
            [f"ev_raw_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(float)
        realized = np.array(
            [OUTCOME_TO_POSITION[str(outcome)] for outcome in group["realized_outcome"]],
            dtype=int,
        )
        sp_lookup = winner_sp.get(str(issue), {})
        winning_sp = np.array([float(sp_lookup.get(match_id, np.nan)) for match_id in match_ids])
        missing_winning_sp_matches += int((~np.isfinite(winning_sp)).sum())
        for subset in selected.itertuples(index=False):
            subset_positions = np.array([position[str(match_id)] for match_id in subset.match_ids])
            settled = settle_sampled_subset(
                subset_id=str(subset.subset_id),
                cell_value=cell_value[subset_positions],
                probability=probability[subset_positions],
                realized_outcomes=realized[subset_positions],
                winning_sp=winning_sp[subset_positions],
                k=args.k,
                seed=args.seed,
            )
            rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(group["issue_year"].iloc[0]),
                    "issue_match_count": int(len(group)),
                    "n": int(subset.n),
                    "proposal_family": str(subset.proposal_family),
                    "subset_id": str(subset.subset_id),
                    "match_ids": json.dumps(subset.match_ids, separators=(",", ":")),
                    **settled,
                }
            )
    labels = pd.DataFrame(rows).sort_values(
        ["issue_year", "issue", "n", "proposal_family", "subset_id"]
    )
    labels["issue_training_weight"] = 1.0 / labels.groupby("issue")[
        "issue"
    ].transform("size")
    weight_sum = labels.groupby("issue")["issue_training_weight"].sum()
    if not np.allclose(weight_sum, 1.0):
        raise AssertionError("pilot issue weights do not sum to one")
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-pilot",
        "issues": int(labels["issue"].nunique()),
        "subset_labels": int(len(labels)),
        "n_min": int(labels["n"].min()),
        "n_max": int(labels["n"].max()),
        "proposal_families": sorted(labels["proposal_family"].unique()),
        "outcome_weight_mode": "CELL_VALUE",
        "generator": "WEIGHTED_WR",
        "k": args.k,
        "subsets_per_issue_n_family": args.subsets_per_family,
        "ticket_stream_seeds": [args.seed],
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_N_FOLD_TICKET",
        "missing_winning_sp_matches": missing_winning_sp_matches,
        "missing_winning_sp_semantics": "TICKETS_TOUCHING_MISSING_SP_CANNOT_PAY",
        "maximum_issue_weight_error": float(np.abs(weight_sum - 1.0).max()),
        "sealed_years_opened": [],
    }
    _atomic_parquet(labels, output / f"{args.output_stem}.parquet")
    _atomic_json(receipt, output / f"{args.output_stem}_receipt.json")
    print(json.dumps(receipt, indent=2), flush=True)
    print(
        labels.groupby("n").agg(
            rows=("subset_id", "size"),
            positive_fraction=("pnl_cny", lambda values: float((values > 0).mean())),
            mean_normalized_pnl=("normalized_pnl_cny100", "mean"),
        ).to_string(),
        flush=True,
    )
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
