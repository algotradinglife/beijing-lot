#!/usr/bin/env python3
"""Source-bound verifier for the #396 2025 settlement package."""
from __future__ import annotations
import argparse
from pathlib import Path
from src.bj396_settlement import verify_package

parser = argparse.ArgumentParser()
parser.add_argument("--package-root", type=Path, required=True)
args = parser.parse_args()
print(verify_package(args.package_root))
