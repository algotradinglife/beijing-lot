"""Extract the four previously reported frozen allocations; no strategy changes.

Usage: python script.py DATA_ROOT OUTPUT_CSV. Run from repository root.
Portable archive payloads and frozen plan bytes are SHA256 checked before use.
The output has one funded group per issue/arm/seed; these DEPTH arms buy no copies.
"""
import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

root, output = map(Path, sys.argv[1:])
assert not output.exists()
arms = {"NONUNIFORM_ANY_ROI_NONE_B1024", "C8_DEPTH_ANY_O0_PROB",
        "C8_DEPTH_ANY_O60_PROB", "C8_DEPTH_ANY_O240_PROB"}
rows = []
bindings = {}
for name in ["n7_capital_study", "n7_core433_study"]:
    path = Path("tests/fixtures") / (name + ".json.gz")
    raw = path.read_bytes()
    archive = json.loads(gzip.decompress(raw))
    assert hashlib.sha256(archive["body"].encode()).hexdigest() == archive["sha256"]
    bindings[str(path)] = hashlib.sha256(raw).hexdigest()
    body = json.loads(archive["body"])
    for row in body["sleeves"]:
        if row["arm"] in arms and row["seed"] == 42501:
            assert row.get("copy_index", 1) == 1
            rows.append({k: row[k] for k in ["issue", "arm", "seed", "sleeve_id", "depth"]})
for batch in ["core45-v1", "core55-v1", "control45-v1", "control55-v1"]:
    study = root / "audits/issue435-next100-v1" / batch
    raw = (study / "plans-frozen.json").read_bytes()
    receipt = json.loads((study / "evaluation-receipt.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == receipt["freeze_sha256"]
    bindings[str(study / "plans-frozen.json")] = receipt["freeze_sha256"]
    frozen = json.loads(raw)
    for filename, expected in frozen["receipt"]["plan_hashes"].items():
        if not any(Path(filename).name.endswith(f"_42501_{arm}.json.gz") for arm in arms):
            continue
        raw = Path(filename).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        plan = json.loads(gzip.decompress(raw))
        assert plan["arm"] in arms and plan["seed"] == 42501
        for layer in plan.get("layers", [plan]):
            assert layer.get("copy_index", 1) == 1
            for group in layer["sleeve_keys"]:
                assert group["stake"] == 2 * group["depth"]
                rows.append(dict(issue=plan["issue"], arm=plan["arm"], seed=plan["seed"],
                                 sleeve_id=group["sleeve_id"], depth=group["depth"]))
keys = [(str(r["issue"]), r["arm"], r["seed"], str(r["sleeve_id"])) for r in rows]
assert len(keys) == len(set(keys))
assert len({r["issue"] for r in rows}) == 200
with output.open("w") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
output.with_suffix(".receipt.json").write_text(json.dumps(dict(
    inputs=bindings, output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    evidence_class="POST_SETTLEMENT_DIAGNOSTIC", seed=42501, rows=len(rows)), indent=2))
print(f"Extracted {len(rows)} frozen funded groups")
