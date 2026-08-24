#!/usr/bin/env python3
"""Verify the source-bound Issue #388 hardening package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.cutoff_hardening.package import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    result = verify_package(args.repo_root, args.target, args.data_root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
