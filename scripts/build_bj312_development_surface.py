#!/usr/bin/env python3
"""Build restartable 2019-2022 physical action surfaces for Issue #312."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue312.design import actions_from_registry  # noqa: E402
from issue312.surface import (  # noqa: E402
    DEVELOPMENT_SEEDS,
    DEVELOPMENT_YEARS,
    write_year_surface,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years", nargs="+", type=int, choices=DEVELOPMENT_YEARS, default=list(DEVELOPMENT_YEARS)
    )
    args = parser.parse_args()
    output = ROOT / "results/issue-312"
    registry = pd.read_csv(output / "action_registry.csv")
    actions = actions_from_registry(registry)
    # The committed probability/value tables use the full build_match_units
    # row index. Select the development rows and reset all three inputs to the
    # exact same order before any settlement builder is called.
    full_tensor = build_tensor()
    units = build_match_units(full_tensor)
    keep = units["issue_year"].lt(2023)
    probabilities = pd.read_parquet(
        ROOT / "results/issue-209/market_only_probabilities.parquet"
    ).loc[keep].reset_index(drop=True)
    values = pd.read_parquet(
        ROOT / "results/issue-209/cell_value_distribution.parquet"
    ).loc[keep].reset_index(drop=True)
    tensor = full_tensor[full_tensor["issue_year"].lt(2023)].copy().reset_index(drop=True)
    receipts = []
    for year in args.years:
        receipt = write_year_surface(
            tensor,
            probabilities,
            values,
            actions,
            output,
            year=year,
            seeds=DEVELOPMENT_SEEDS,
            prefix="development",
        )
        receipts.append(receipt)
        print(receipt, flush=True)
    print({"issue": 312, "stage": "DEVELOPMENT_SURFACE", "receipts": receipts})


if __name__ == "__main__":
    main()
