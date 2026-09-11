"""Independent Cartesian, roles, exposure and arithmetic replay; no strategy ranking."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--study",required=True);args=p.parse_args();root=Path(args.study)
    f=json.loads((root/"frozen.json").read_text());r=f["receipt"]
    assert stable_json_hash(r)==f["seal"]
    verify_implementation_closure(Path.cwd(),r["implementation"])
    verify_clean_file_bindings({**r["source_hashes"],**r["plan_hashes"],**r["report_files"]},repository_root=Path.cwd())
    witness=json.loads((root/"plans-frozen.json").read_text())
    assert hashlib.sha256(witness["canonical_json"].encode()).hexdigest()==witness["seal"]
    witness=json.loads(witness["canonical_json"])
    assert hashlib.sha256((root/"results.json").read_bytes()).hexdigest()==witness["result_sha256"]
    verify_clean_file_bindings(witness["source_hashes"],repository_root=Path.cwd())
    audits=[k for k in witness["source_hashes"] if k.endswith("settlement-audit.json")]
    assert len(audits)==1
    labels={(a["issue"],a["slot"],a["provider_id"]):a for a in json.loads(Path(audits[0]).read_text())["rows"]}
    result=json.loads((root/"results.json").read_text())
    saved={(a["issue"],a["policy"]):a for a in result["rows"]};assert len(saved)==192
    total=0
    for issue in r["issues"]:
        plans=json.loads(gzip.decompress((root/"plans"/f"{issue}.json.gz").read_bytes()))
        for name,env in plans.items():
            n=int(name[1]);uses=int(name[-1]);cost=2*2**(n-2)
            assert stable_json_hash({k:v for k,v in env.items() if k!="seal"})==env["seal"]
            groups=[set(l["slot"] for l in c["legs"]) for c in env["components"]]
            assert max(Counter(s for g in groups for s in g).values(),default=0)<=uses
            assert all(len(a&b)<=5 for a,b in itertools.combinations(groups,2))
            assert env["stake"]==cost*len(groups) and env["stake"]+env["cash_cny"]==1024
            gross=0.;hits=0
            for part in env["components"]:
                assert stable_json_hash({k:v for k,v in part.items() if k!="seal"})==part["seal"]
                legs=part["legs"];assert len(legs)==n and part["n"]==n and part["stake"]==cost
                assert Counter(l["role"] for l in legs)==dict(A=2,D=n-3,C=1)
                assert sum(len(l["support"])==1 for l in legs)==2
                for l in legs:
                    assert l["slot"] not in r["filter_ledgers"][issue]["receipt"]["dropped_slots"]
                    p=sorted(range(3),key=lambda j:(-l["p_"+"WDL"[j]],j))
                    q=sorted(range(3),key=lambda j:(-l["q_"+"WDL"[j]],j))
                    role=l["role"]
                    if role=="A":assert p[0]==q[0] and l["q_"+"WDL"[q[0]]]>=.5
                    else:assert (set(p[:2])==set(q[:2]))==(role=="D")
                    assert l["support"]=="".join("310"[j] for j in sorted(p[:1] if role=="A" else p[:2]))
                expected={"".join(x) for x in itertools.product(*(l["support"] for l in legs))}
                assert len(part["tickets"])==len(expected)==cost//2
                assert {t["code"] for t in part["tickets"]}==expected
                assert all(t["units"]==1 and t["group"]==1 for t in part["tickets"])
                actual=[labels[(issue,l["slot"],l["provider_id"])] for l in legs]
                assert all(a["handicap"]==l["handicap"] for a,l in zip(actual,legs))
                code="".join("310"["WDL".index(a["actual_direction"])] for a in actual)
                if code in expected:
                    hits+=1;gross+=2*.65*math.prod(a["spf_sp"] for a in actual)
                total+=1
            row=saved[(issue,name)]
            assert row["hits"]==hits and row["groups"]==len(groups) and row["stake"]==env["stake"]
            assert math.isclose(row["gross"],gross,abs_tol=1e-8)
            assert math.isclose(row["net"],gross-env["stake"],abs_tol=1e-8)
    print("PASS:192 issue/policy rows;",total,"groups; support, caps and single payout factor replayed")
