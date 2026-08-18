#!/usr/bin/env python3
"""Build or verify Issue #235's v2 historical relative-horizon proxy package."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bj235_package import verify_package, write_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "bj235_bj_sp_timeseries_v2",
    )
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        print(verify_package(args.output))
    else:
        print(write_package(args.output, args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
