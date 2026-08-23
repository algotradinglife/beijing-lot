#!/usr/bin/env python3
"""Verify the compact Issue #340 result package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.qeu_dynamic_r_n7 import verify_package

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--package", type=Path, default=ROOT / "results/qeu_dynamic_r_n7"
    )
    args = parser.parse_args()
    receipt = verify_package(args.repo_root, args.package)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
