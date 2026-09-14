#!/usr/bin/env python3
"""Verify frozen #453 bytes and independently replay every new selection."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.n7_quality_replay import replay_quality, validate_quality_manifest, validate_quality_funded

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
args = parser.parse_args()
root = args.directory
freeze_bytes = (root / "plans-frozen.json").read_bytes()
receipt = json.loads(freeze_bytes)
validate_quality_manifest(receipt)
for name, expected in receipt["files"].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
        raise ValueError(f"changed frozen bytes: {name}")
rows = pd.read_csv(root / "predictions.csv", dtype={"issue": str})
funded = pd.read_csv(root / "funded.csv", dtype={"issue": str})
settings = {"NEAR95_UNION": (.95, "UNION"), "NEAR90_UNION": (.90, "UNION"),
            "NEAR95_OVERLAP": (.95, "OVERLAP")}
count = 0
for (issue, seed), plans in rows.groupby(["issue", "seed"], sort=False):
    with gzip.open(root / f"replay-{issue}-{seed}.json.gz", "rt") as stream:
        snapshot = json.load(stream)
    if snapshot["cutoffs"] != receipt["cutoffs"][issue]:
        raise ValueError("cutoff differs from prediction freeze")
    for plan in plans.itertuples():
        if plan.variant not in settings:
            continue
        fraction, selector = settings[plan.variant]
        selected = replay_quality(snapshot, snapshot["cutoffs"], plan.budget_cny, fraction, selector)
        expected_ids = [snapshot["options"][j - 1]["sleeve_id"] for j in selected]
        actual = funded[(funded.issue == issue) & (funded.seed == seed) & (funded.arm == plan.arm)]
        if expected_ids != actual.sleeve_id.tolist():
            raise ValueError(f"selection replay differs: {issue} {seed} {plan.arm}")
        validate_quality_funded(snapshot, selected, actual.to_dict("records"))
        cost = sum(snapshot["options"][j - 1]["stake"] for j in selected)
        if cost != plan.stake or plan.cash != plan.budget_cny - cost:
            raise ValueError("independent capital accounting differs")
        count += 1
if count != 5400 or len(rows) != 9000:
    raise ValueError("incomplete 200-period comparison")
print(json.dumps({"status": "PASS", "new_plans_replayed": count,
                  "freeze_sha256": hashlib.sha256(freeze_bytes).hexdigest(),
                  "implementation": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in (Path(__file__), Path(__file__).resolve().parents[1] / "src/n7_quality_replay.py")},
                  "scope": "frozen byte identity, independent selector and stake replay; no settlement"}))
