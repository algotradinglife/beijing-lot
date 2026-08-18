#!/usr/bin/env python3
"""Build or verify the external Issue #254 integration handoff."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from schema_integration import build_integration_package, verify_integration_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    package = args.output or args.data_root.resolve() / "derived" / "bj254_schema_integration_v1"
    if not args.verify_only:
        package = build_integration_package(args.data_root, output=package)
    print(json.dumps(verify_integration_package(package), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
