"""Freeze N6/N7 single choices before audited target settlement."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
from src.fundamentals_n7_twocover import settle_n7_twocover

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("phase",choices=["freeze","settle"]);p.add_argument("--study",required=True)
    args=p.parse_args();out=Path(args.study)
    source=Path("data/derived/fundamentals_417/candidate-exclusion-v1/independent")
    pure=Path("data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json")
    if args.phase=="freeze":
        if out.exists():raise FileExistsError("New immutable output required")
        original=json.loads((source/"frozen.json").read_text());old=original["receipt"]
        assert stable_json_hash(old)==original["seal"]
        verify_clean_file_bindings({**old["source_hashes"],**old["plan_hashes"]},repository_root=Path.cwd())
        data=json.loads(pure.read_text());frame=pd.DataFrame(data["rows"])
        reports=["quarto/101_consensus_n6_n7.qmd","r/fundamentals_pure_report.R","r/fundamentals_missed_summary.R","r/fundamentals_equity_curves.R"]
        r=dict(issues=old["issues"],source_root=str(source),source_hashes={**old["source_hashes"],**old["plan_hashes"],
            str(source/"frozen.json"):hashlib.sha256((source/"frozen.json").read_bytes()).hexdigest(),
            str(pure):hashlib.sha256(pure.read_bytes()).hexdigest()},
            parameters=dict(budget_cny=1024,unit_cny=2,payout_factor=.65,initial_capital_cny=100000),
            implementation=implementation_closure(Path.cwd(),["scripts.consensus_n6_n7"],distributions=["numpy","pandas","scipy"]),
            report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports},
            source_mode="FIXED_EXPOSED_N6_N7_WITH_N7_SUPPORT_REPLAY",filter_ledgers={})
        paired=source.parent/"paired"
        pr=json.loads((paired/"frozen.json").read_text())
        assert stable_json_hash(pr["receipt"])==pr["seal"]
        r["source_hashes"].update(pr["receipt"]["plan_hashes"])
        r["source_hashes"][str(paired/"frozen.json")]=hashlib.sha256((paired/"frozen.json").read_bytes()).hexdigest()
        pointer=Path("data/derived/fundamentals_417/cap-depth-grid-v1/plans-frozen.json")
        r["source_hashes"][str(pointer)]=hashlib.sha256(pointer.read_bytes()).hexdigest()
        verify_clean_file_bindings(r["source_hashes"],repository_root=Path.cwd())
        r["parameters"].update(group_sizes=[6,7],max_uses=[3,6],max_pair_overlap=5,
            minimum_anchor_market=.5,conversion_budget_fraction=0,seed=0)
        (out/"plans").mkdir(parents=True);hashes={}
        for issue in r["issues"]:
            f=frame[frame.issue==issue].copy()
            cuts={str(s):Cutoff.decision_epoch(issue,data["cutoffs"][issue][str(s)]) for s in f.slot}
            f,ledger=exclude_zero_top2_disagreement(f,cutoffs=cuts)
            cuts={str(s):cuts[str(s)] for s in f.slot};r["filter_ledgers"][issue]=ledger
            plans={}
            for n in (6,7):
                for uses in (3,6):
                    plan=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,
                        budget_cny=1024,minimum_anchor_market=.5,max_uses=uses,max_pair_overlap=5,
                        unit_cny=2,payout_factor=.65,seed=0,group_size=n)
                    name=f"N{n}_U{uses}"
                    if n==7:
                        refroot=source if uses==6 else source.parent/"paired"
                        bundle=json.loads(gzip.decompress((refroot/"plans"/f"{issue}.json.gz").read_bytes()))
                        assert stable_json_hash({k:v for k,v in bundle.items() if k!="seal"})==bundle["seal"]
                        ref=bundle["plans"]["INDEPENDENT_C000" if uses==6 else "PRIMARY_FILL"]
                        assert plan["stake"]==ref["stake"] and plan["cash_cny"]==ref["cash_cny"]
                        assert [[(l["slot"],l["support"],l["role"]) for l in c["legs"]] for c in plan["components"]]==[
                            [(l["slot"],l["support"],l["role"]) for l in c["legs"]] for c in ref["components"]]
                    plans[name]=plan
            print("FROZEN",issue,{k:len(v["components"]) for k,v in plans.items()},flush=True)
            target=out/"plans"/f"{issue}.json.gz";target.write_bytes(gzip.compress(json.dumps(plans).encode(),mtime=0))
            hashes[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
        r["plan_hashes"]=hashes
        (out/"frozen.json").write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        print("FROZEN192plans before settlement")
    else:
        if (out/"results.json").exists():raise FileExistsError("Immutable results")
        frozen=json.loads((out/"frozen.json").read_text());r=frozen["receipt"]
        assert stable_json_hash(r)==frozen["seal"]
        verify_implementation_closure(Path.cwd(),r["implementation"])
        verify_clean_file_bindings({**r["source_hashes"],**r["plan_hashes"],**r["report_files"]},repository_root=Path.cwd())
        pointer=Path("data/derived/fundamentals_417/cap-depth-grid-v1/plans-frozen.json")
        old=json.loads(pointer.read_text())
        assert hashlib.sha256(old["canonical_json"].encode()).hexdigest()==old["seal"]
        audits={k:v for k,v in json.loads(old["canonical_json"])["source_hashes"].items() if k.endswith("settlement-audit.json")}
        assert len(audits)==1
        verify_clean_file_bindings(audits,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())["rows"])
        rows=[];legs=[]
        for issue in r["issues"]:
            plans=json.loads(gzip.decompress((out/"plans"/f"{issue}.json.gz").read_bytes()))
            for name,plan in plans.items():
                s=settle_n7_twocover(plan,audit[audit.issue==issue])
                assert s["status"] in ("COMPLETE","NO_BET")
                rows.append(dict(s,policy=name,budget_cny=1024,cash_cny=plan["cash_cny"],n6_hits=s["hits"] if name.startswith("N6") else 0,n7_hits=s["hits"] if name.startswith("N7") else 0))
                for i,part in enumerate(plan["components"]):
                    legs.extend(dict(l,policy=name,component=i) for l in part["legs"])
        target=out/"results.json"
        target.write_text(json.dumps(dict(rows=rows,legs=legs,issue_order=r["issues"],upstream_freeze_seal=frozen["seal"],historical_admission=False)))
        verification=dict(scope="PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC",plan_freeze_seal=frozen["seal"],
            result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source_hashes={**r["source_hashes"],**r["plan_hashes"],**audits},
            implementation=r["implementation"],report_files=r["report_files"])
        canonical=json.dumps(verification,sort_keys=True,separators=(",",":"))
        (out/"plans-frozen.json").write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print("SETTLED",len(rows),"policy/issue rows")
