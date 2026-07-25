#!/usr/bin/env python3
"""Verify a BJ-BET-SLIP-001 bundle against its immutable source package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.betting_slip import BettingSlipError, verify_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument("--font-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = verify_bundle(args.bundle, args.source_package, args.font_file)
    except (BettingSlipError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "error": str(exc)}))
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
