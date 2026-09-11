"""Extract immutable seed-zero holdings for descriptive R diagnosis; no fitting."""
import csv
import gzip
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
base = root / "data/derived/fundamentals_417"
study = base / "updated100-strategies-v1"
out = base / "updated100-diagnosis-v1"
out.mkdir(exist_ok=True)
sources = {}
results = json.loads((study / "results.json").read_text())
policies = ["N5_NO_SWAP", "N6_NO_SWAP", "U3_BASELINE", "U6_BASELINE",
            "N5_S000", "N6_S000", "N5_SWAP_S000", "MIX_S000"]
legs, fixtures, rows = [], [], []
for cohort, issues, prefix in [("old48", results["prior_issue_order"], "prior_rows"),
                               ("new100", results["issue_order"], "rows")]:
    audit_path = (base / "new48-expanded-validation-v1" if cohort == "old48" else study) / "settlement-audit.json"
    sources[str(audit_path.relative_to(root))] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    audit = json.loads(audit_path.read_text())["rows"]
    lookup = {(str(a["issue"]), int(a["slot"]), str(a["provider_id"])): a for a in audit}
    assert len(lookup) == len(audit)
    factor_path = (base / "new48-pure-baseline-v1" if cohort == "old48" else study) / "factors.json"
    sources[str(factor_path.relative_to(root))] = hashlib.sha256(factor_path.read_bytes()).hexdigest()
    factors = json.loads(factor_path.read_text())["rows"]
    feature_lookup = {}
    for issue in issues:
        feature_path = (base / "new48-expanded-validation-v1" if cohort == "old48" else study) / "projected" / f"{issue}.json"
        sources[str(feature_path.relative_to(root))] = hashlib.sha256(feature_path.read_bytes()).hexdigest()
        for f in json.loads(feature_path.read_text())["features"]:
            feature_lookup[(issue, int(f["slot"]), str(f["provider_id"]))] = f
    for f in factors:
        key = (str(f["issue"]), int(f["slot"]), str(f["provider_id"]))
        a, feature = lookup[key], feature_lookup[key]
        fixtures.append(dict(cohort=cohort, **{k: f[k] for k in ["issue", "slot", "provider_id", "handicap", "home", "away", "p_W", "p_D", "p_L", "q_W", "q_D", "q_L"]},
                             competition=feature["competition"], actual=a["actual_direction"],
                             spf_sp=a.get("spf_sp"), goals=a["actual_home"]+a["actual_away"]))
    for issue in issues:
        bundles = {}
        directories = (["n5-n6-single10-v1", "n5-single-swaps-v1", "double-source-v1", "n5-single10-u3-mix-v1"]
                       if cohort == "old48" else ["updated100-strategies-v1"])
        for directory in directories:
            path = base / directory / "plans" / f"{issue}.json.gz"
            sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            data = json.loads(gzip.decompress(path.read_bytes()))
            if directory == "n5-single10-u3-mix-v1":
                bundles["MIX_S000"] = data["0"]
            else:
                bundles.update(data["plans"] if cohort == "new100" else data)
        for policy in policies:
            for group, wrapper in enumerate(bundles[policy]["components"], 1):
                component = wrapper.get("plan", wrapper)
                for leg in component["legs"]:
                    key = (issue, int(leg["slot"]), str(leg["provider_id"]))
                    a = lookup[key]
                    assert a["actual_direction"] in "WDL"
                    code = {"W": "3", "D": "1", "L": "0"}[a["actual_direction"]]
                    legs.append(dict(cohort=cohort, issue=issue, policy=policy, group=group,
                                     slot=leg["slot"], provider_id=leg["provider_id"], role=leg["role"],
                                     support=leg["support"], hit=int(code in leg["support"])))
    rows.extend(dict(cohort=cohort, **{k:r[k] for k in ["issue","policy","stake","gross","net","groups","hits","status"]})
                for r in results[prefix] if r["policy"] in policies)
for name, data in [("legs", legs), ("fixtures", fixtures), ("issues", rows)]:
    with (out / f"{name}.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)
sources[str((study / "results.json").relative_to(root))] = hashlib.sha256((study / "results.json").read_bytes()).hexdigest()
(out / "receipt.json").write_text(json.dumps({"scope":"POST_SETTLEMENT_DIAGNOSIS_NO_SELECTION", "historical_admission":False,
    "sources":sources, "implementation":{str(Path(__file__).relative_to(root)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    "outputs":{f"{n}.csv":hashlib.sha256((out/f"{n}.csv").read_bytes()).hexdigest() for n in ["legs","fixtures","issues"]}}, indent=2))
print(json.dumps({"legs":len(legs),"fixtures":len(fixtures),"issues":len(rows)}))
