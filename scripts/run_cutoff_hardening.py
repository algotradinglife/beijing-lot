#!/usr/bin/env python3
"""Build the source-bound Issue #388 hardening package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cutoff_hardening.package import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    decision = build_package(
        args.repo_root,
        args.target,
        args.data_root,
        force=args.force,
    )
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
