#!/usr/bin/env python3
"""Verify the compact Issue #336 result package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.qeu_support_depth.contract import FUNDED_UNITS, ISSUE_STAKE_CNY, R_ARMS, TICKETS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    output = (args.output_dir or root / "results/qeu_support_depth").resolve()
    manifest = json.loads((output / "MANIFEST.json").read_text())
    for relative, evidence in manifest["files"].items():
        path = root / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != evidence["sha256"]:
            raise AssertionError(f"hash mismatch: {relative}")
    bundles = pd.read_parquet(output / "issue_bundles.parquet")
    if set(bundles["r"].unique()) != set(R_ARMS):
        raise AssertionError("incomplete R curve")
    if not bundles["ticket_count"].eq(TICKETS).all():
        raise AssertionError("ticket count mismatch")
    if not bundles["funded_units"].eq(FUNDED_UNITS).all():
        raise AssertionError("funded-unit mismatch")
    if not bundles["stake_cny"].eq(ISSUE_STAKE_CNY).all():
        raise AssertionError("stake mismatch")
    print(json.dumps({"status": "PASS", "files": len(manifest["files"]), "rows": len(bundles)}))


if __name__ == "__main__":
    main()
