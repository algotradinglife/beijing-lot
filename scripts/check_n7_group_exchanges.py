#!/usr/bin/env python3
"""Independent all-plan and fixed-prefix replay of frozen #455 selections."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

from src.n7_exchange_replay import replay_group_exchange, verify_exchange_provenance
from src.n7_quality_replay import validate_quality_manifest, validate_quality_funded

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--settlement", action="store_true")
args = parser.parse_args()
root = args.directory
freeze_bytes = (root / "plans-frozen.json").read_bytes()
freeze = json.loads(freeze_bytes)
source = Path(freeze["config"]["source_dir"])
source_bytes = (source / "plans-frozen.json").read_bytes()
if hashlib.sha256(source_bytes).hexdigest() != freeze["source_freeze_sha256"]:
    raise ValueError("source freeze changed")
prior = json.loads(source_bytes)
validate_quality_manifest(prior)
verify_exchange_provenance(freeze, prior, freeze["config"]["repository_root"])
if not {"predictions.csv", "funded.csv", "actions.csv"}.issubset(freeze["files"]):
    raise ValueError("incomplete exchange manifest")
for folder, manifest in ((root, freeze), (source, prior)):
    for name, identity in manifest["files"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != identity:
            raise ValueError(f"changed frozen artifact {folder / name}")
rows = pd.read_csv(root / "predictions.csv", dtype={"issue": str})
funded = pd.read_csv(root / "funded.csv", dtype={"issue": str})
original = pd.read_csv(source / "funded.csv", dtype={"issue": str})
count = 0
for (issue, seed), plans in rows.groupby(["issue", "seed"], sort=False):
    with gzip.open(source / f"replay-{issue}-{seed}.json.gz", "rt") as stream:
        snapshot = json.load(stream)
    if snapshot["cutoffs"] != freeze["cutoffs"][issue]:
        raise ValueError("cutoff mismatch")
    ids = {o["sleeve_id"]: j+1 for j, o in enumerate(snapshot["options"])}
    for plan in plans.itertuples():
        base_arm = f"T250_SP130_BREADTH_OPEN_FIRST_any_hit_B{plan.budget_cny}"
        base = original[(original.issue == issue) & (original.seed == seed) & (original.arm == base_arm)]
        initial = [ids[j] for j in base.sleeve_id]
        selected = initial if plan.variant == "JOINT" else replay_group_exchange(
            snapshot, snapshot["cutoffs"], initial, plan.budget_cny,
            {"EXCHANGE11": 1, "EXCHANGE12": 2}[plan.variant])
        bought = funded[(funded.issue == issue) & (funded.seed == seed) & (funded.arm == plan.arm)]
        validate_quality_funded(snapshot, selected, bought.to_dict("records"))
        stake = sum(snapshot["options"][j-1]["stake"] for j in selected)
        if stake != plan.stake or plan.cash != plan.budget_cny-stake:
            raise ValueError("capital accounting mismatch")
        count += 1
if count != 5400:
    raise ValueError("incomplete replay")
if args.settlement:
    evaluation = json.loads((root / "evaluation-receipt.json").read_bytes())
    if evaluation["freeze_sha256"] != hashlib.sha256(freeze_bytes).hexdigest():
        raise ValueError("settlement points to a different freeze")
    rank_path = Path(evaluation["ranks_path"])
    for path, identity in ((rank_path, evaluation["ranks_sha256"]),
                           (root / "results.csv", evaluation["results_sha256"])):
        if hashlib.sha256(path.read_bytes()).hexdigest() != identity:
            raise ValueError("settlement input identity mismatch")
    ranks = pd.read_csv(rank_path, dtype={"issue": str})
    settled = funded.merge(ranks[["issue", "sleeve_id", "actual_rank", "actual_gross_cny"]],
                           on=["issue", "sleeve_id"], validate="many_to_one")
    if len(settled) != len(funded):
        raise ValueError("unmatched settlement labels")
    settled["hits"] = (settled.actual_rank <= settled.depth).astype(int)
    settled["gross"] = settled.hits * settled.actual_gross_cny
    keys = ["issue", "arm", "seed"]
    totals = settled.groupby(keys, as_index=False)[["hits", "gross", "stake"]].sum()
    expected = rows[keys].merge(totals, on=keys, how="left", validate="one_to_one").fillna(0)
    expected["net"] = expected.gross-expected.stake
    results = pd.read_csv(root / "results.csv", dtype={"issue": str})
    pair = results.merge(expected, on=keys, suffixes=("", "_check"), validate="one_to_one")
    if len(pair) != 5400 or any(not np.allclose(pair[f], pair[f+"_check"], rtol=1e-12, atol=1e-7)
                              for f in ("hits", "gross", "stake", "net")):
        raise ValueError("independent settlement mismatch")
print(json.dumps(dict(status="PASS", plans=count, freeze_sha256=hashlib.sha256(freeze_bytes).hexdigest(),
                     settlement_checked=args.settlement,
                     implementation={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                         Path(__file__), Path("src/n7_exchange_replay.py"), Path("src/n7_quality_replay.py"))})))
