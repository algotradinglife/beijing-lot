#!/usr/bin/env python3
"""Source-bound verifier for the BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2 package."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n6_n7_portfolio.pipeline import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-replay", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output or root / "results/n6_n7_portfolio").resolve()
    result = verify_package(root, output, check_replay=not args.no_replay)
    print(f"VERIFY OK: {result['package']}")


if __name__ == "__main__":
    main()
