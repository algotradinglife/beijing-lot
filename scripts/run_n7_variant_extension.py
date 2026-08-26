#!/usr/bin/env python3
"""Build or verify the Issue #400 N7 variant extension package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.n7_variant_extension.pipeline import build_package, verify_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--no-replay", action="store_true")
    args = parser.parse_args()
    if args.verify:
        result = verify_package(
            args.repo_root, args.data_root, replay=not args.no_replay
        )
    else:
        frames = build_package(args.repo_root, args.data_root)
        result = {
            "status": "BUILT",
            "variants": int(frames["registry"]["variant"].nunique()),
            "bundles": int(len(frames["bundles"])),
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
