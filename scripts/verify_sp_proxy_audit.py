#!/usr/bin/env python3
"""Verify the committed Issue #318 artifact package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sp_proxy_audit.contract import EXPECTED_MANIFEST_SHA256  # noqa: E402
from src.sp_proxy_audit.validate import validate_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", default=EXPECTED_MANIFEST_SHA256)
    args = parser.parse_args()
    if args.expected_manifest_sha256 == "UNSET":
        raise ValueError("no trusted manifest anchor is configured")
    print(json.dumps(validate_package(args.package, args.expected_manifest_sha256), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
