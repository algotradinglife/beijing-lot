"""Thin fixed-composition diagnostic: freeze every prediction plan, then settle."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_consensus_portfolio import consensus_portfolios
from src.fundamentals_n7_twocover import settle_n7_twocover
from src.fundamentals_n7_single import settle_n7_single

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["freeze","settle"])
    parser.add_argument("--study",required=True)
    args=parser.parse_args()
    out=Path(args.study)
    pure=Path("data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json")
    prior=Path("data/derived/fundamentals_417/cap-depth-grid-v1")
    if args.phase=="freeze":
        if out.exists():raise FileExistsError("New immutable output required")
        data=json.loads(pure.read_text())
        verify_clean_file_bindings(data["source_hashes"],repository_root=Path.cwd())
        previous=json.loads((prior/"freeze-receipt.json").read_text())
        assert stable_json_hash(previous["receipt"])==previous["seal"]
        verify_clean_file_bindings(previous["receipt"]["plan_hashes"],repository_root=Path.cwd())
        issues=previous["receipt"]["issues"]
        params=dict(budget_cny=1024,minimum_anchor_market=.5,skeleton_max_uses=3,
                    skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=41902)
        reports=["quarto/95_consensus_converter.qmd","r/fundamentals_pure_report.R",
                 "r/fundamentals_missed_summary.R","r/fundamentals_equity_curves.R"]
        receipt=dict(scope="EXPOSED_FIXED_CONSENSUS_NOT_FITTED",issues=issues,parameters=params,
            source_hashes={**data["source_hashes"],**previous["receipt"]["plan_hashes"],
                           str(pure):hashlib.sha256(pure.read_bytes()).hexdigest(),
                           str(prior/"plans-frozen.json"):hashlib.sha256((prior/"plans-frozen.json").read_bytes()).hexdigest()},
            implementation=implementation_closure(Path.cwd(),["scripts.consensus_converter"],distributions=["numpy","pandas","scipy"]),
            report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports})
        (out/"plans").mkdir(parents=True)
        (out/"contract.json").write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
        frame=pd.DataFrame(data["rows"]);hashes={}
        for issue in issues:
            f=frame[frame.issue==issue].copy()
            cuts={str(s):Cutoff.decision_epoch(issue,data["cutoffs"][issue][str(s)]) for s in f.slot}
            bundle=consensus_portfolios(f,cutoffs=cuts,**params)
            target=out/"plans"/f"{issue}.json.gz"
            target.write_bytes(gzip.compress(json.dumps(bundle).encode(),mtime=0))
            hashes[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
            print("FROZEN",issue,"skeletons",len(bundle["skeletons"]),"pools",bundle["pool_counts"],flush=True)
        receipt["plan_hashes"]=hashes
        (out/"frozen.json").write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
        print("SEALED",len(issues),"issues before settlement")
    else:
        if (out/"results.json").exists():raise FileExistsError("Immutable results")
        frozen=json.loads((out/"frozen.json").read_text());r=frozen["receipt"]
        assert stable_json_hash(r)==frozen["seal"]
        verify_implementation_closure(Path.cwd(),r["implementation"])
        verify_clean_file_bindings({**r["source_hashes"],**r["report_files"],**r["plan_hashes"]},repository_root=Path.cwd())
        old=json.loads((prior/"plans-frozen.json").read_text())
        assert hashlib.sha256(old["canonical_json"].encode()).hexdigest()==old["seal"]
        old=json.loads(old["canonical_json"])
        audits={k:v for k,v in old["source_hashes"].items() if k.endswith("settlement-audit.json")}
        if len(audits)!=1:raise ValueError("Exactly one original audited result source required")
        verify_clean_file_bindings(audits,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())["rows"])
        rows=[];pools=[];leg_rows=[]
        for issue in r["issues"]:
            z=json.loads(gzip.decompress((out/"plans"/f"{issue}.json.gz").read_bytes()))
            assert stable_json_hash({k:v for k,v in z.items() if k!="seal"})==z["seal"]
            a=audit[audit.issue==issue]
            pools.append(dict(issue=issue,skeletons=len(z["skeletons"]),**z["pool_counts"]))
            for name,plan in z["plans"].items():
                s=settle_n7_twocover(plan,a)
                rows.append(dict(s,policy=name,budget_cny=plan["budget"],cash_cny=plan["cash_cny"],n6_hits=0,n7_hits=s["hits"]))
                for i,part in enumerate(plan["components"],1):
                    leg_rows.extend(dict(l,policy=name,component=i) for l in part["legs"])
            reference=json.loads(gzip.decompress((prior/"plans"/f"{issue}.json.gz").read_bytes()))["D2_U6_P5_BASE"]["plan"]
            s=settle_n7_single(reference,a)
            rows.append(dict(s,policy="OLD_D2_U6_P5",budget_cny=reference["budget_cny"],
                             cash_cny=reference["cash_cny"],n6_hits=0,n7_hits=s["hits"]))
        assert len(rows)==4*len(r["issues"]) and all(x["status"] in ["COMPLETE","NO_BET"] for x in rows)
        payload=dict(rows=rows,pools=pools,legs=leg_rows,issue_order=r["issues"],parameters=r["parameters"],
                     upstream_freeze_seal=frozen["seal"],historical_admission=False)
        target=out/"results.json";target.write_text(json.dumps(payload))
        verification=dict(scope="PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC",
                          plan_freeze_seal=frozen["seal"],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                          source_hashes={**r["source_hashes"],**r["plan_hashes"],**audits},
                          implementation=r["implementation"],report_files=r["report_files"])
        canonical=json.dumps(verification,sort_keys=True,separators=(",",":"))
        (out/"plans-frozen.json").write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print("SETTLED",len(rows),"policy/issue rows")
