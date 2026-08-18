#!/usr/bin/env python3
"""Build or verify the external Issue #253 representative package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from physical_schema import (  # noqa: E402
    build_representative_package,
    resolve_data_root,
    verify_package,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = resolve_data_root(args.data_root)
    package = args.output or root / "derived" / "bj253_physical_schema_v1"
    if not args.verify_only:
        package = build_representative_package(root, output=package)
    result = verify_package(package)
    print(json.dumps({"package": str(package), **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
