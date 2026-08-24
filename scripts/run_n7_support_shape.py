#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n7_support_shape.pipeline import build_notebook_and_report, build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output or root / "results/n7_support_shape").resolve()
    decision = build_package(root, output, args.data_root, force=args.force)
    build_notebook_and_report(root, output)
    print(decision)


if __name__ == "__main__":
    main()