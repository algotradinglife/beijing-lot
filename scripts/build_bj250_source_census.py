#!/usr/bin/env python3
"""Build or externally verify the Issue #250 assessment-only source census."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_census.census import PACKAGE_NAME, build_package, resolve_data_root, verify_package  # noqa: E402


def _read_external_anchor(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise SystemExit(f"trusted anchor unreadable: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"trusted anchor is invalid JSON: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SystemExit(f"trusted anchor must be a JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--trusted-anchor", type=Path, default=None, help="independently supplied semantic anchor; required with --verify-only")
    args = parser.parse_args()
    package = ROOT / "results" / PACKAGE_NAME
    if args.verify_only:
        if args.trusted_anchor is None:
            parser.error("--verify-only requires --trusted-anchor produced outside this builder")
        verdict = verify_package(package, trusted_anchor=_read_external_anchor(args.trusted_anchor))
        print(f"VERIFIED={verdict['verified']}")
        for problem in verdict["problems"]:
            print(problem)
        return 0 if verdict["verified"] else 1
    data_root = resolve_data_root(args.data_root)
    package = build_package(ROOT, data_root, package)
    print(f"PACKAGE={package.relative_to(ROOT)}")
    print("INTERNAL_VERIFIED=True")
    if args.trusted_anchor is not None:
        verdict = verify_package(package, trusted_anchor=_read_external_anchor(args.trusted_anchor))
        print(f"EXTERNAL_VERIFIED={verdict['verified']}")
        for problem in verdict["problems"]:
            print(problem)
        return 0 if verdict["verified"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
