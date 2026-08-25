#!/usr/bin/env python3
"""Build the portable #396 package from frozen raw 500.com pages."""
from __future__ import annotations
import argparse
from pathlib import Path
from src.bj396_settlement import build_package

parser = argparse.ArgumentParser()
parser.add_argument("--raw-root", type=Path, required=True)
parser.add_argument("--package-root", type=Path, required=True)
args = parser.parse_args()
print(build_package(args.raw_root, args.package_root))
