#!/usr/bin/env python3
"""Build and verify the Issue #250 assessment-only source census."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_census.census import PACKAGE_NAME, build_package, resolve_data_root, verify_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    package = ROOT / "results" / PACKAGE_NAME
    if args.verify_only:
        verdict = verify_package(package)
        print(f"VERIFIED={verdict['verified']}")
        for problem in verdict["problems"]:
            print(problem)
        return 0 if verdict["verified"] else 1
    data_root = resolve_data_root(args.data_root)
    package = build_package(ROOT, data_root, package)
    verdict = verify_package(package)
    print(f"PACKAGE={package.relative_to(ROOT)}")
    print(f"VERIFIED={verdict['verified']}")
    return 0 if verdict["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
