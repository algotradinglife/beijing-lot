#!/usr/bin/env python3
"""Build Issue #352 retrospective annual diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.multin_r_diagnostic import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo_root / "results/multin_r_diagnostic"
    print(json.dumps(build_package(args.repo_root, output, args.data_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
