#!/usr/bin/env python3
"""Materialize #282 distinct-ticket historical counterfactual labels."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue282.actions import prototype_action_space  # noqa: E402
from issue282.labels import TICKET_STREAM_SEEDS, materialize_action_labels  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-282")
    parser.add_argument("--batch-issues", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.batch_issues <= 0:
        raise ValueError("--batch-issues must be positive")
    runtime_root = Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)).resolve()
    print(f"runtime_root={runtime_root}", flush=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    tensor = build_tensor()
    units = build_match_units(tensor)
    probabilities = pd.read_parquet(
        ROOT / "results/issue-209/market_only_probabilities.parquet"
    )
    values = pd.read_parquet(ROOT / "results/issue-209/cell_value_distribution.parquet")
    if units["issue_year"].ge(2024).any() or tensor["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ development seal violated")
    catalog = prototype_action_space()
    issue_meta = (
        units.loc[units["snapshot_kind"].eq("10h"), ["issue", "issue_year"]]
        .drop_duplicates()
        .assign(issue=lambda frame: frame["issue"].astype(str))
        .sort_values(["issue_year", "issue"])
    )
    for year, year_meta in issue_meta.groupby("issue_year", sort=True):
        destination = output / f"counterfactual_labels_{int(year)}.parquet"
        if args.resume and destination.exists():
            print(f"year={year} status=skip_existing path={destination}", flush=True)
            continue
        batches: list[pd.DataFrame] = []
        issues = year_meta["issue"].tolist()
        for offset in range(0, len(issues), args.batch_issues):
            batch_issues = set(issues[offset : offset + args.batch_issues])
            unit_mask = units["issue"].astype(str).isin(batch_issues)
            tensor_mask = tensor["issue"].astype(str).isin(batch_issues)
            batch = materialize_action_labels(
                units.loc[unit_mask],
                probabilities.loc[unit_mask],
                values.loc[unit_mask],
                tensor.loc[tensor_mask],
                actions=catalog,
                stream_seeds=TICKET_STREAM_SEEDS,
            )
            batches.append(batch)
            print(
                f"year={year} completed={min(offset + args.batch_issues, len(issues))}/"
                f"{len(issues)} rows={sum(len(frame) for frame in batches)}",
                flush=True,
            )
        result = pd.concat(batches, ignore_index=True)
        temporary = destination.with_suffix(".tmp.parquet")
        result.to_parquet(temporary, index=False)
        temporary.replace(destination)
        print(f"year={year} status=complete path={destination} rows={len(result)}", flush=True)

    metadata = {
        "contract": "BJ-UNIFIED-CONDITIONAL-POLICY-001/v1",
        "source": "#209 pre-2024 Mx3 tensor plus settlement labels",
        "years": sorted(int(year) for year in issue_meta["issue_year"].unique()),
        "issues": int(issue_meta["issue"].nunique()),
        "actions_per_fully_supported_issue": len(catalog),
        "ticket_stream_seeds": list(TICKET_STREAM_SEEDS),
        "k_semantics": "DISTINCT_TICKET_IDENTITIES",
        "wr_duplicate_semantics": "PROPOSAL_FREQUENCY_ONLY_NO_IMPLICIT_STAKE",
        "payout_coefficient": 0.65,
        "payout_application": "ONCE_PER_WINNING_N_FOLD_TICKET",
        "sealed_years_opened": [],
    }
    temporary = output / "counterfactual_metadata.tmp.json"
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temporary.replace(output / "counterfactual_metadata.json")
    print(json.dumps(metadata, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
