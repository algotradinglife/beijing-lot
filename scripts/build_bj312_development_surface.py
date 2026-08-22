#!/usr/bin/env python3
"""Build restartable 2019-2022 physical action surfaces for Issue #312."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.design import actions_from_registry  # noqa: E402
from issue312.surface import (  # noqa: E402
    DEVELOPMENT_SEEDS,
    DEVELOPMENT_YEARS,
    load_causal_issue209_inputs,
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
    tensor, probabilities, values, causal_receipt = load_causal_issue209_inputs(
        ROOT / "results/issue-209/market_only_probabilities.parquet",
        ROOT / "results/issue-209/cell_value_distribution.parquet",
        years=tuple(args.years),
    )
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
    print(
        {
            "issue": 312,
            "stage": "DEVELOPMENT_SURFACE",
            "causal_read": causal_receipt,
            "receipts": receipts,
        }
    )


if __name__ == "__main__":
    main()
