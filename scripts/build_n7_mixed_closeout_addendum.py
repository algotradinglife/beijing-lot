#!/usr/bin/env python3
"""Deterministically (re)build the #399 close-out addendum package.

Contract BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1 (issue #399, parent #394).

Reads ONLY the committed frozen #394 artifacts
(`results/n7_mixed_full_history/bundles.parquet` and `matched_contrasts.csv`),
reproduces the frozen matched-contrasts board exactly (parity gate), computes
the two corrected statistics, authors the corrected report, executes the
addendum notebook, and publishes the immutable addendum package with
source-merge binding.

Usage:
    PYTHONPATH=. python scripts/build_n7_mixed_closeout_addendum.py [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n7_mixed_full_history.closeout import (  # noqa: E402
    ADDENDUM_PACKAGE,
    CONTRACT_ID,
    build_addendum_package,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    receipt = build_addendum_package(root, force=args.force)
    print(
        json.dumps(
            {
                "contract": CONTRACT_ID,
                "package": ADDENDUM_PACKAGE,
                "receipt": receipt,
                "status": "BUILT",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()