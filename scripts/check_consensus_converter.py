"""Independent fixed-consensus accounting/role replay; never used for settlement."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--study",required=True);args=p.parse_args();root=Path(args.study)
    frozen=json.loads((root/"frozen.json").read_text());r=frozen["receipt"]
    assert stable_json_hash(r)==frozen["seal"]
    verify_implementation_closure(Path.cwd(),r["implementation"])
    verify_clean_file_bindings({**r["source_hashes"],**r["report_files"],**r["plan_hashes"]},repository_root=Path.cwd())
    result=json.loads((root/"results.json").read_text())
    receipt=json.loads((root/"plans-frozen.json").read_text())
    assert hashlib.sha256(receipt["canonical_json"].encode()).hexdigest()==receipt["seal"]
    receipt=json.loads(receipt["canonical_json"])
    assert hashlib.sha256((root/"results.json").read_bytes()).hexdigest()==receipt["result_sha256"]
    audits={k:v for k,v in receipt["source_hashes"].items() if k.endswith("settlement-audit.json")}
    verify_clean_file_bindings(audits,repository_root=Path.cwd())
    audit=json.loads(Path(next(iter(audits))).read_text())["rows"]
    labels={(a["issue"],a["slot"],a["provider_id"]):a for a in audit}
    saved={(a["issue"],a["policy"]):a for a in result["rows"]}
    assert len(saved)==((len(r["conversion_budget_fractions"])+3)*len(r["issues"]) if r["design"]=="independent" else 192)
    excluded={}
    if "filter_ledgers" in r:
        import pandas as pd
        factors=json.loads(Path("data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json").read_text())
        frame=pd.DataFrame(factors["rows"])
        for issue,entry in r["filter_ledgers"].items():
            ledger=entry["receipt"]
            assert stable_json_hash(ledger)==entry["seal"]
            original=frame[frame.issue==issue]
            dropped=[]
            for row in original.to_dict("records"):
                po=sorted("WDL",key=lambda d:(-row["p_"+d],"WDL".index(d)))[:2]
                qo=sorted("WDL",key=lambda d:(-row["q_"+d],"WDL".index(d)))[:2]
                if row["handicap"]==0 and set(po)!=set(qo):dropped.append(int(row["slot"]))
            assert sorted(dropped)==ledger["dropped_slots"]
            kept=original[~original.slot.isin(dropped)]
            assert stable_json_hash(kept.sort_values("slot").to_json(orient="records"))==ledger["retained_sha256"]
            assert ledger["input_count"]==len(original) and ledger["retained_count"]==len(kept)
            excluded[issue]=set(dropped)
        reference=json.loads((Path(r["filtered_reference"])/"results.json").read_text())["rows"]
        assert result["reference_rows"]==reference
    groups_checked=0
    for issue in r["issues"]:
        z=json.loads(gzip.decompress((root/"plans"/f"{issue}.json.gz").read_bytes()))
        assert stable_json_hash({k:v for k,v in z.items() if k!="seal"})==z["seal"]
        sk=z["skeletons"]
        plans=z["plans"]
        if issue in excluded:
            assert all(leg["slot"] not in excluded[issue] for plan in plans.values()
                       for part in plan["components"] for leg in part["legs"])
            assert all(plan["input_sha256"]==r["filter_ledgers"][issue]["receipt"]["retained_sha256"]
                       for plan in plans.values())
        if r["design"]=="paired":
            assert max(Counter(s for g in sk for s in g).values(),default=0)<=3
            assert all(len(set(a)&set(b))<=5 for a,b in itertools.combinations(sk,2))
            primaries=[part for part in plans["COMPLEMENT"]["components"] if not part["complement"]]
            assert primaries==plans["MATCHED_PRIMARY"]["components"]
            old=Path("data/derived/fundamentals_417/cap-depth-grid-v1/plans")/f"{issue}.json.gz"
            original=json.loads(gzip.decompress(old.read_bytes()))["D2_U6_P5_BASE"]["plan"]
            plans=dict(plans,OLD_D2_U6_P5=dict(components=[original],stake=original["stake"],cash_cny=original["cash_cny"]))
        else:
            for env in plans.values():
                actual_groups=[{leg["slot"] for leg in part["legs"]} for part in env["components"]]
                assert max(Counter(s for g in actual_groups for s in g).values(),default=0)<=6
                assert all(len(a&b)<=5 for a,b in itertools.combinations(actual_groups,2))
                if r["anchor_max_uses"] is not None:
                    singles=Counter(leg["slot"] for part in env["components"] for leg in part["legs"] if len(leg["support"])==1)
                    assert max(singles.values(),default=0)<=r["anchor_max_uses"]
                    assert all(sum(len(leg["support"])==1 for leg in part["legs"])==2 for part in env["components"])
                alloc=env["allocation"]
                for kind,label in [(False,"primary"),(True,"converter")]:
                    actual_spend=sum(p["stake"] for p in env["components"] if p["complement"]==kind)
                    assert actual_spend==alloc[label+"_spend_cny"]<=alloc[label+"_quota_cny"]
            previous=json.loads((Path(r["reference_root"])/"results.json").read_text())
            for reference in previous["rows"]:
                if reference["issue"]==issue and reference["policy"] in ["PRIMARY_FILL","COMPLEMENT","OLD_D2_U6_P5"]:
                    expected=dict(reference,policy="PREVIOUS_"+reference["policy"])
                    assert saved[issue,expected["policy"]]==expected
        for name,env in plans.items():
            gross=0.;hits=0;stake=0;groups=0
            for part in env["components"]:
                assert stable_json_hash({k:v for k,v in part.items() if k!="seal"})==part["seal"]
                for group in range(1,part["groups"]+1):
                    legs=sorted([a for a in part["legs"] if a["group"]==group],key=lambda a:a["slot"])
                    tickets=[t for t in part["tickets"] if t["group"]==group]
                    expected={"".join(c) for c in itertools.product(*(a["support"] for a in legs))}
                    assert len(legs)==7 and len({a["slot"] for a in legs})==7
                    assert {t["code"] for t in tickets}==expected and len(tickets)==len(expected)
                    assert all(t["units"]==1 for t in tickets)
                    if name!="OLD_D2_U6_P5":
                        assert Counter(a["role"] for a in legs)==Counter(A=2,D=4,C=1)
                        for a in legs:
                            po=sorted(range(3),key=lambda j:(-a["p_"+"WDL"[j]],j))
                            qo=sorted(range(3),key=lambda j:(-a["q_"+"WDL"[j]],j))
                            if a["role"]=="A":
                                assert po[0]==qo[0] and a["q_"+"WDL"[qo[0]]]>=.5
                                support="310"[po[0]]
                            elif a["role"]=="D":
                                assert set(po[:2])==set(qo[:2])
                                support="".join("310"[j] for j in sorted(po[:2]))
                            else:
                                assert set(po[:2])!=set(qo[:2])
                                ids=po[2:] if part["complement"] else po[:2]
                                support="".join("310"[j] for j in sorted(ids))
                            assert a["support"]==support
                    actual=[labels[issue,a["slot"],a["provider_id"]] for a in legs]
                    assert all(a["handicap"]==b["handicap"] for a,b in zip(legs,actual))
                    outcome="".join(dict(W="3",D="1",L="0")[a["actual_direction"]] for a in actual)
                    stake+=2*len(expected);groups+=1
                    if outcome in expected:
                        hits+=1;gross+=2*.65*math.prod(a["spf_sp"] for a in actual)
            s=saved[issue,name]
            assert stake==s["stake"]==env["stake"]
            assert stake+env["cash_cny"]==1024
            assert (groups,hits)==(s["groups"],s["hits"])
            assert math.isclose(gross,s["gross"],abs_tol=1e-7)
            assert math.isclose(gross-stake,s["net"],abs_tol=1e-7)
            groups_checked+=groups
    print("PASS",len(saved),"policy/issue results;",groups_checked,"groups; Cartesian tickets, role eligibility, budgets, caps and one-factor payouts")
