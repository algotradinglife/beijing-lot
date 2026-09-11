"""Independent ticket, filter, budget, identity and payout replay."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True)
    args = parser.parse_args()
    root = Path(args.study)
    frozen = json.loads((root/"frozen.json").read_text())
    receipt = frozen["receipt"]
    assert stable_json_hash(receipt) == frozen["seal"]
    verify_implementation_closure(Path.cwd(), receipt["implementation"])
    verify_clean_file_bindings({**receipt["source_hashes"],**receipt["plan_hashes"],
        **receipt["report_files"]}, repository_root=Path.cwd())
    witness = json.loads((root/"plans-frozen.json").read_text())
    assert hashlib.sha256(witness["canonical_json"].encode()).hexdigest() == witness["seal"]
    witness = json.loads(witness["canonical_json"])
    assert witness["plan_freeze_seal"] == frozen["seal"]
    assert hashlib.sha256((root/"results.json").read_bytes()).hexdigest() == witness["result_sha256"]
    verify_clean_file_bindings(witness["source_hashes"], repository_root=Path.cwd())
    paths = [p for p in witness["source_hashes"] if p.endswith("settlement-audit.json")]
    assert len(paths) == 1
    labels = json.loads(Path(paths[0]).read_text())["rows"]
    audit = {(r["issue"],r["slot"],r["provider_id"]):r for r in labels}
    assert len(audit) == len(labels)
    result = json.loads((root/"results.json").read_text())
    assert result["upstream_freeze_seal"] == frozen["seal"]
    saved = {(r["issue"],r["policy"]):r for r in result["rows"]}
    assert len(saved) == len(result["rows"]) == 192
    pure = json.loads(Path("data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json").read_text())
    factors = {(r["issue"],r["slot"]):r for r in pure["rows"]}
    total = 0
    for issue in receipt["issues"]:
        bundles = json.loads(gzip.decompress((root/"plans"/f"{issue}.json.gz").read_bytes()))
        dropped = []
        for (i,slot),r in factors.items():
            if i != issue:
                continue
            p = sorted("WDL",key=lambda d:(-r["p_"+d],"WDL".index(d)))[:2]
            q = sorted("WDL",key=lambda d:(-r["q_"+d],"WDL".index(d)))[:2]
            if r["handicap"] == 0 and set(p) != set(q):
                dropped.append(slot)
        ledger = receipt["exclusion_ledgers"][issue]
        assert stable_json_hash(ledger["receipt"]) == ledger["seal"]
        assert sorted(dropped) == ledger["receipt"]["dropped_slots"]
        for policy,entry in bundles.items():
            plan = entry["plan"]
            assert plan["seal"] == stable_json_hash({k:v for k,v in plan.items() if k != "seal"})
            n = 6 if entry["kind"] == "N6" else 7
            components = [c["plan"] for c in plan["components"]] if n == 6 else plan["components"]
            groups = []
            gross = 0.
            hits = 0
            for component in components:
                assert component["seal"] == stable_json_hash({k:v for k,v in component.items() if k != "seal"})
                legs = component["legs"]
                assert len(legs) == n and len({l["slot"] for l in legs}) == n
                assert sorted(len(l["support"]) for l in legs) == ([1]+[2]*5 if n == 6 else [1]*2+[2]*5)
                expected = {"".join(c) for c in itertools.product(*(l["support"] for l in legs))}
                assert len(component["tickets"]) == len(expected) == 32
                assert {t["code"] for t in component["tickets"]} == expected
                assert all(t["units"] == 1 for t in component["tickets"])
                assert component["stake"] == 64
                group = set()
                actual = []
                prices = []
                for l in legs:
                    original = factors[issue,l["slot"]]
                    assert original["provider_id"] == l["provider_id"] and original["handicap"] == l["handicap"]
                    label = audit[issue,l["slot"],l["provider_id"]]
                    assert label["handicap"] == l["handicap"]
                    if policy == "N6_FILTERED":
                        assert l["slot"] not in dropped
                    actual.append(dict(W="3",D="1",L="0")[label["actual_direction"]])
                    prices.append(label["spf_sp"])
                    group.add(l["slot"])
                groups.append(group)
                if "".join(actual) in expected:
                    gross += 2*.65*math.prod(prices)
                    hits += 1
            uses = 3 if policy == "U3_ORIGINAL" else 6
            assert max(Counter(s for g in groups for s in g).values(),default=0) <= uses
            assert all(len(a & b) <= 5 for a,b in itertools.combinations(groups,2))
            assert plan["stake"] == 64*len(groups) and plan["stake"]+plan["cash_cny"] == 1024
            row = saved[issue,policy]
            assert row["groups"] == len(groups) and row["hits"] == hits
            assert row["stake"] == plan["stake"] and row["cash_cny"] == plan["cash_cny"]
            assert math.isclose(row["gross"],gross,abs_tol=1e-8)
            assert math.isclose(row["net"],gross-plan["stake"],abs_tol=1e-8)
            if n == 6:
                reconstruction = entry["reconstruction"]
                assert reconstruction["seal"] == stable_json_hash({k:v for k,v in reconstruction.items() if k != "seal"})
                source = reconstruction["source_plan"]
                shape = reconstruction["shape_plan"]
                for event in shape["ledger"]:
                    seven = [l for l in source["legs"] if l["group"] == event["source_group"]]
                    mass = {l["slot"]:[.5*(l["p_"+d]+l["q_"+d]) for d in "WDL"] for l in seven}
                    top = {s:sorted(range(3),key=lambda j:(-ps[j],j)) for s,ps in mass.items()}
                    removed = min(mass,key=lambda s:(sum(mass[s][j] for j in top[s][:2]),s))
                    assert removed == event["removed_slot"]
                    retained = [s for s in mass if s != removed]
                    single = min(retained,key=lambda s:(-mass[s][top[s][0]]/sum(mass[s][j] for j in top[s][:2]),s))
                    assert event["single_slots"] == [single]
            total += len(groups)
    original = [r for r in result["rows"] if r["policy"] == "N6_ORIGINAL"]
    assert sum(r["hits"] > 0 for r in original) == 41
    assert sum(r["groups"] for r in original) == 746
    assert math.isclose(sum(r["net"] for r in original),11357.614784795136,abs_tol=1e-8)
    print("PASS",len(saved),"plans",total,"groups; filters, retention, budgets and payouts replayed")
