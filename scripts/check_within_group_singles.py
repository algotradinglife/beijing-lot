"""Independent support-choice, equal-exposure and settlement replay."""
import gzip,hashlib,itertools,json,math,sys,argparse
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
    saved={(a["issue"],a["policy"]):a for a in result["rows"]};assert len(saved)==144
    total=0
    for issue in r["issues"]:
        plans=json.loads(gzip.decompress((root/"plans"/f"{issue}.json.gz").read_bytes()))
        ancestor=json.loads(gzip.decompress((Path(r["source_root"])/"plans"/f"{issue}.json.gz").read_bytes()))["plans"]["INDEPENDENT_C000"]
        assert plans["ORIGINAL_D2"]==ancestor
        for name,env in plans.items():
            assert stable_json_hash({k:v for k,v in env.items() if k!="seal"})==env["seal"]
            assert env["cutoffs"]==ancestor["cutoffs"]
            assert len(env["components"])==len(ancestor["components"])
            assert env["stake"]==ancestor["stake"] and env["cash_cny"]==ancestor["cash_cny"]
            gross=0.;hits=0
            for old,part in zip(ancestor["components"],env["components"]):
                assert stable_json_hash({k:v for k,v in part.items() if k!="seal"})==part["seal"]
                legs=part["legs"]
                assert [l["slot"] for l in legs]==[l["slot"] for l in old["legs"]]
                assert part["cutoffs"]==old["cutoffs"] and part["stake"]==64
                assert sum(len(l["support"])==1 for l in legs)==2
                for a,b in zip(legs,old["legs"]):
                    assert all(a[k]==b[k] for k in ["issue","slot","provider_id","handicap","p_W","p_D","p_L","q_W","q_D","q_L"])
                    assert a["slot"] not in r["filter_ledgers"][issue]["receipt"]["dropped_slots"]
                if name!="ORIGINAL_D2":
                    ranks=[]
                    for l in legs:
                        d=sorted("WDL",key=lambda d:(-l["q_"+d],"WDL".index(d)))[0]
                        score=l["q_"+d] if name=="WITHIN_GROUP_MARKET" else l["p_"+d]/l["q_"+d]
                        ranks.append((-score,l["slot"],"310"["WDL".index(d)]))
                    chosen={s:d for _,s,d in sorted(ranks)[:2]}
                    for l in legs:
                        top=sorted(range(3),key=lambda j:(-l["p_"+"WDL"[j]],j))[:2]
                        assert l["support"]==chosen.get(l["slot"],"".join("310"[j] for j in sorted(top)))
                expected={"".join(x) for x in itertools.product(*(l["support"] for l in legs))}
                assert len(expected)==32 and {t["code"] for t in part["tickets"]}==expected
                assert len(part["tickets"])==32 and all(t["units"]==1 for t in part["tickets"])
                actual=[labels[issue,l["slot"],l["provider_id"]] for l in legs]
                assert all(a["handicap"]==l["handicap"] for a,l in zip(actual,legs))
                outcome="".join({"W":"3","D":"1","L":"0"}[a["actual_direction"]] for a in actual)
                if outcome in expected:
                    hits+=1;gross+=2*.65*math.prod(a["spf_sp"] for a in actual)
                total+=1
            s=saved[issue,name]
            assert s["groups"]==len(env["components"]) and s["hits"]==hits and s["stake"]==64*s["groups"]
            assert s["stake"]+s["cash_cny"]==1024
            assert math.isclose(s["gross"],gross,abs_tol=1e-7) and math.isclose(s["net"],gross-s["stake"],abs_tol=1e-7)
    print("PASS144rows,",total,"groups: same fixtures/stake, exact singles, cutoff/source bindings, independent payout")
