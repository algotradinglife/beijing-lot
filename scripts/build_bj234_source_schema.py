#!/usr/bin/env python3
"""Build / verify / execute CLI for the Issue #234 contract package.

Usage:
    python scripts/build_bj234_source_schema.py build   # census + publish
    python scripts/build_bj234_source_schema.py verify  # semantic verify
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from source_schema import builder, contract, verify  # noqa: E402


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    package = ROOT / "results" / contract.PACKAGE_DIR_NAME

    if command == "build":
        target = builder.build_package(ROOT, package, force=True)
        print(f"BUILT {target}")
        verdict = verify.verify_package(target, ROOT)
        print("VERIFIED" if verdict["verified"] else "VERIFY FAILED")
        if verdict["problems"]:
            for problem in verdict["problems"]:
                print("  -", problem)
        return 0 if verdict["verified"] else 1

    if command == "verify":
        if not package.exists():
            print(f"package missing: {package}; run build first", file=sys.stderr)
            return 1
        verdict = verify.verify_package(package, ROOT)
        print("VERIFIED" if verdict["verified"] else "VERIFY FAILED")
        if verdict["problems"]:
            for problem in verdict["problems"]:
                print("  -", problem)
        return 0 if verdict["verified"] else 1

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
