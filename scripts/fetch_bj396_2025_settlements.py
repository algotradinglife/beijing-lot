#!/usr/bin/env python3
"""Acquire frozen #396 2025 500.com settlement pages."""
from __future__ import annotations
import argparse
from pathlib import Path
from src.bj396_settlement import fetch_raw_pages

parser = argparse.ArgumentParser()
parser.add_argument("--raw-root", type=Path, required=True)
parser.add_argument("--rate-seconds", type=float, default=1.0)
args = parser.parse_args()
receipts = fetch_raw_pages(args.raw_root, rate_seconds=args.rate_seconds)
print(receipts.groupby("acquisition_result").size().to_string())
if not receipts["acquisition_result"].eq("SUCCESS").all():
    raise SystemExit("one or more acquisitions failed; raw denominator retained")
