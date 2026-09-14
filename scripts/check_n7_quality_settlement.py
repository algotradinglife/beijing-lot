#!/usr/bin/env python3
"""Independent pandas accounting of the frozen #453 purchases and rank labels."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
root = parser.parse_args().directory
receipt = json.loads((root / "evaluation-receipt.json").read_text())
freeze = json.loads((root / "plans-frozen.json").read_text())
rank_path = Path(freeze["config"]["rank_dir"]) / "ranks.csv"
for path, expected in [(root / "plans-frozen.json", receipt["freeze_sha256"]),
                       (root / "results.csv", receipt["results_sha256"]),
                       (root / "funded.csv", freeze["files"]["funded.csv"]),
                       (root / "predictions.csv", freeze["files"]["predictions.csv"]),
                       (rank_path, receipt["ranks_sha256"])]:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"identity mismatch: {path}")
keys = ["issue", "arm", "seed"]
funded = pd.read_csv(root / "funded.csv", dtype={"issue": str, "sleeve_id": str})
predictions = pd.read_csv(root / "predictions.csv", dtype={"issue": str})
results = pd.read_csv(root / "results.csv", dtype={"issue": str})
ranks = pd.read_csv(rank_path, dtype={"issue": str, "sleeve_id": str})
joined = funded.merge(ranks[["issue", "sleeve_id", "actual_rank", "actual_gross_cny"]],
                      on=["issue", "sleeve_id"], validate="many_to_one")
assert len(joined) == len(funded)
joined["hits"] = (joined.actual_rank <= joined.depth).astype(int)
# actual_gross_cny is already the accepted once-discounted label, not pre-tax SP.
joined["gross"] = joined.hits * joined.actual_gross_cny
totals = joined.groupby(keys, as_index=False)[["stake", "gross", "hits"]].sum()
expected = predictions[keys].merge(totals, on=keys, how="left", validate="one_to_one").fillna(0)
expected["net"] = expected.gross - expected.stake
paired = results.merge(expected, on=keys, suffixes=("", "_independent"), validate="one_to_one")
assert len(paired) == 9000
for field in ("stake", "gross", "hits", "net"):
    if not np.allclose(paired[field], paired[field + "_independent"], rtol=1e-12, atol=1e-7):
        raise ValueError(f"independent accounting differs: {field}")
print(json.dumps({"status": "PASS", "plans": len(paired), "selected_group_positions": len(funded),
                  "evaluation_receipt_sha256": hashlib.sha256((root / "evaluation-receipt.json").read_bytes()).hexdigest(),
                  "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "scope": "independent purchased-prefix hits, spent capital, once-discounted gross and net; inherited rank labels"}))
