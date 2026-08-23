#!/usr/bin/env python3
"""Build the Issue #348 multi-N R0 package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.multin_top2_r0 import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo_root / "results/multin_top2_r0"
    print(json.dumps(build_package(args.repo_root, output, args.data_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
