#!/usr/bin/env python3
"""Build the Issue #306 full N3-N10 per-seed action surface."""

from pathlib import Path
import argparse
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue306.surface import YEARS, write_surface  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, choices=YEARS, default=list(YEARS))
    parser.add_argument("--no-finalize", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tensor = build_tensor()
    probabilities = pd.read_parquet(ROOT / "results/issue-209/market_only_probabilities.parquet")
    values = pd.read_parquet(ROOT / "results/issue-209/cell_value_distribution.parquet")
    print(
        write_surface(
            tensor,
            probabilities,
            values,
            ROOT / "results/issue-306",
            years=tuple(args.years),
            finalize=not args.no_finalize,
        )
    )
