#!/usr/bin/env python3
"""Extend #396's frozen v1 settlement package using frozen Nowscore probes."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.bj396_settlement.pipeline import extend_package_amendment_v2


parser = argparse.ArgumentParser()
parser.add_argument("--baseline-root", type=Path, required=True)
parser.add_argument("--nowscore-raw-root", type=Path, required=True)
parser.add_argument("--package-root", type=Path, required=True)
args = parser.parse_args()
print(extend_package_amendment_v2(args.baseline_root, args.nowscore_raw_root, args.package_root))
