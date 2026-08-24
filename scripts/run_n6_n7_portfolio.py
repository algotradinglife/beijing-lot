#!/usr/bin/env python3
"""Run the BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2 package build (#378)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n6_n7_portfolio.pipeline import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output or root / "results/n6_n7_portfolio").resolve()
    decision = build_package(root, output, force=args.force)
    print(f"built {output}")
    print(decision.get("verdict"))


if __name__ == "__main__":
    main()
