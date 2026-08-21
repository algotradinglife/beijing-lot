#!/usr/bin/env python3
"""Profile #284 subset coverage on the accepted pre-event issue tensor."""

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
from issue284.sampler import assign_issue_weights, sample_issue_subsets  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--epoch", type=int, default=0)
    parser.add_argument("--seed", type=int, default=284_001)
    parser.add_argument("--samples-per-family", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_root = args.artifact_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    values_path = runtime_root / "results/issue-209/cell_value_distribution.parquet"
    if not values_path.is_file():
        raise FileNotFoundError(values_path)

    tensor = build_tensor()
    units = build_match_units(tensor)
    if units["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ sampler profile seal violated")
    values = pd.read_parquet(values_path)
    if not units.index.equals(values.index):
        raise RuntimeError("#209 units and value distribution indexes are not aligned")
    horizon = units["snapshot_kind"].eq("10h")
    units_h = units.loc[horizon].copy()
    values_h = values.loc[horizon].copy()
    rows: list[pd.DataFrame] = []
    for issue, group in units_h.groupby("issue", sort=True):
        indexes = group.index
        match_ids = group["match_idx"].astype(str).tolist()
        cell_value = values_h.reindex(indexes)[
            ["ev_raw_3", "ev_raw_1", "ev_raw_0"]
        ].to_numpy(dtype=float)
        value_score = np.nanmax(cell_value, axis=1)
        divergence_score = np.nanmax(
            np.abs(
                group[
                    [
                        "eu_vs_line_divergence_3",
                        "eu_vs_line_divergence_1",
                        "eu_vs_line_divergence_0",
                    ]
                ].to_numpy(dtype=float)
            ),
            axis=1,
        )
        reliability = (
            group["mapping_accepted"].astype(float).to_numpy()
            * (1.0 + np.log1p(group["n_available_books"].astype(float).to_numpy()))
        )
        for n in range(3, 11):
            if len(group) < n:
                continue
            sampled = sample_issue_subsets(
                issue=str(issue),
                match_ids=match_ids,
                n=n,
                value_score=value_score,
                divergence_score=divergence_score,
                reliability_score=reliability,
                samples_per_family=args.samples_per_family,
                seed=args.seed,
                epoch=args.epoch,
            )
            sampled["issue_year"] = int(group["issue_year"].iloc[0])
            sampled["issue_match_count"] = int(len(group))
            rows.append(sampled)
    if not rows:
        raise RuntimeError("no sampler profile rows were produced")
    profile = assign_issue_weights(pd.concat(rows, ignore_index=True))
    weight_sums = profile.groupby(["issue", "epoch"])[
        "issue_training_weight"
    ].sum()
    if not np.allclose(weight_sums, 1.0):
        raise AssertionError("issue training weights do not sum to one")
    if profile["subset_id"].duplicated().any():
        raise AssertionError("subset identities are duplicated across the profile")

    summary = (
        profile.groupby(["issue_year", "n", "proposal_family"], as_index=False)
        .agg(
            issues=("issue", "nunique"),
            subsets=("subset_id", "nunique"),
            issue_match_count_median=("issue_match_count", "median"),
            max_match_inclusion_fraction_mean=(
                "max_match_inclusion_fraction",
                "mean",
            ),
            ordered_draw_probability_median=(
                "ordered_draw_probability",
                "median",
            ),
        )
        .sort_values(["issue_year", "n", "proposal_family"])
    )
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1",
        "runtime_root": str(runtime_root),
        "epoch": args.epoch,
        "seed": args.seed,
        "samples_per_family": args.samples_per_family,
        "issues": int(profile["issue"].nunique()),
        "rows": int(len(profile)),
        "unique_subsets": int(profile["subset_id"].nunique()),
        "n_min": int(profile["n"].min()),
        "n_max": int(profile["n"].max()),
        "maximum_issue_weight_error": float(np.abs(weight_sums - 1.0).max()),
        "duplicate_subset_rows": int(profile["subset_id"].duplicated().sum()),
        "sealed_years_opened": [],
        "outcome_columns_used_by_sampler": [],
    }
    profile_for_disk = profile.copy()
    profile_for_disk["match_indices"] = profile_for_disk["match_indices"].map(
        lambda values: json.dumps(list(values), separators=(",", ":"))
    )
    profile_for_disk["match_ids"] = profile_for_disk["match_ids"].map(
        lambda values: json.dumps(list(values), separators=(",", ":"))
    )
    _atomic_parquet(profile_for_disk, output / "subset_profile.parquet")
    _atomic_csv(summary, output / "subset_profile_summary.csv")
    _atomic_json(receipt, output / "subset_profile_receipt.json")
    print(json.dumps(receipt, indent=2), flush=True)
    print(summary.groupby("n")["issues"].max().to_string(), flush=True)
    return 0


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


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
