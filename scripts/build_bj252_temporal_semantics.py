#!/usr/bin/env python3
"""Build or verify the sealed #252 temporal-semantics evidence package."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bj252_build import PACKAGE_NAME, build  # noqa: E402
from bj252_temporal_package import verify_package  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, default=ROOT)
parser.add_argument("--output", type=Path, default=None)
parser.add_argument("--verify", action="store_true")
args = parser.parse_args()
target = args.output or args.root / "results" / PACKAGE_NAME
if args.verify:
    print(verify_package(target))
else:
    print(f"BUILT {build(args.root, target)}")
