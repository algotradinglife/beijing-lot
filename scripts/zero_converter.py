"""Freeze a zero-handicap gate on inventoried plans, then audited settlement."""
import argparse
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_converter_gate import gate_zero_converter
from src.fundamentals_n7_twocover import settle_n7_twocover

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["freeze","settle"])
    p.add_argument("--study",required=True)
    args=p.parse_args();out=Path(args.study)
    roots=[Path("data/derived/fundamentals_417/consensus-converter-v3"),
           Path("data/derived/fundamentals_417/independent-converter-v1")]
    if args.phase=="freeze":
        if out.exists():raise FileExistsError("Immutable new directory required")
        pure=Path("data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json")
        data=json.loads(pure.read_text());frame=pd.DataFrame(data["rows"])
        bindings={str(pure):hashlib.sha256(pure.read_bytes()).hexdigest()}
        inventories=[]
        for root in roots:
            f=json.loads((root/"frozen.json").read_text())
            assert stable_json_hash(f["receipt"])==f["seal"]
            r=f["receipt"]
            verify_clean_file_bindings({**r["source_hashes"],**r["plan_hashes"]},repository_root=Path.cwd())
            bindings.update(r["source_hashes"]);bindings.update(r["plan_hashes"])
            bindings[str(root/"frozen.json")]=hashlib.sha256((root/"frozen.json").read_bytes()).hexdigest()
            inventories.append(dict(root=str(root),seal=f["seal"],mode="INVENTORIED_NOT_CURRENT_MODEL_REPLAY"))
        issues=r["issues"]
        reports=["quarto/97_zero_converter.qmd","r/fundamentals_pure_report.R","r/fundamentals_equity_curves.R","r/fundamentals_missed_summary.R"]
        receipt=dict(issues=issues,source_hashes=bindings,inventories=inventories,
            parameters=dict(budget_cny=1024,initial_capital_cny=100000,gate="C_HANDICAP_ZERO",regroup=False),
            implementation=implementation_closure(Path.cwd(),["scripts.zero_converter"],distributions=["numpy","pandas","scipy"]),
            report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports})
        (out/"plans").mkdir(parents=True)
        hashes={}
        for issue in issues:
            f=frame[frame.issue==issue].copy()
            cuts={str(s):Cutoff.decision_epoch(issue,data["cutoffs"][issue][str(s)]) for s in f.slot}
            plans={}
            for root in roots:
                original=json.loads(gzip.decompress((root/"plans"/f"{issue}.json.gz").read_bytes()))
                assert stable_json_hash({k:v for k,v in original.items() if k!="seal"})==original["seal"]
                for name,plan in original["plans"].items():
                    if root==roots[0] and name!="COMPLEMENT":continue
                    for zero in (False,True):
                        gated=gate_zero_converter(plan,f,cutoffs=cuts,zero_only=zero,budget_cny=1024)
                        plans[gated["strategy"]]=gated
            target=out/"plans"/f"{issue}.json.gz"
            target.write_bytes(gzip.compress(json.dumps(plans).encode(),mtime=0))
            hashes[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
        receipt["plan_hashes"]=hashes
        (out/"frozen.json").write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        print("FROZEN",len(issues)*12,"plans before settlement")
    else:
        if (out/"results.json").exists():raise FileExistsError("Immutable result")
        f=json.loads((out/"frozen.json").read_text());r=f["receipt"]
        assert stable_json_hash(r)==f["seal"]
        verify_implementation_closure(Path.cwd(),r["implementation"])
        verify_clean_file_bindings({**r["source_hashes"],**r["plan_hashes"],**r["report_files"]},repository_root=Path.cwd())
        pointer=Path("data/derived/fundamentals_417/cap-depth-grid-v1/plans-frozen.json")
        old=json.loads(pointer.read_text())
        assert hashlib.sha256(old["canonical_json"].encode()).hexdigest()==old["seal"]
        audits={k:v for k,v in json.loads(old["canonical_json"])["source_hashes"].items() if k.endswith("settlement-audit.json")}
        assert len(audits)==1
        verify_clean_file_bindings(audits,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())["rows"])
        rows=[];details=[]
        for issue in r["issues"]:
            plans=json.loads(gzip.decompress((out/"plans"/f"{issue}.json.gz").read_bytes()))
            a=audit[audit.issue==issue]
            for name,plan in plans.items():
                assert stable_json_hash({k:v for k,v in plan.items() if k!="seal"})==plan["seal"]
                s=settle_n7_twocover(plan,a)
                # Independent accounting replay from actual directions and SP.
                hits=0;gross=0.
                for i,part in enumerate(plan["components"]):
                    leg=next(x for x in part["legs"] if x["role"]=="C")
                    hit=True;prices=[]
                    for x in part["legs"]:
                        matched=a[(a.slot==x["slot"])&(a.provider_id==x["provider_id"])]
                        assert len(matched)==1
                        label=matched.iloc[0]
                        assert label.handicap==x["handicap"] and label.status=="READY"
                        hit=hit and {"W":"3","D":"1","L":"0"}[label.actual_direction] in x["support"]
                        prices.append(float(label.spf_sp))
                    ret=2*.65*math.prod(prices) if hit else 0.
                    hits+=int(hit);gross+=ret
                    details.append(dict(issue=issue,policy=name,component=i,complement=part["complement"],
                        handicap=leg["handicap"],stake=part["stake"],gross=ret,net=ret-part["stake"],hit=int(hit)))
                assert hits==s["hits"] and math.isclose(gross,s["gross"],abs_tol=1e-7)
                assert sum(p["stake"] for p in plan["components"])==s["stake"]
                rows.append(dict(s,policy=name,budget_cny=1024,cash_cny=plan["cash_cny"],n6_hits=0,n7_hits=s["hits"]))
        payload=dict(rows=rows,components=details,issue_order=r["issues"],historical_admission=False,upstream_freeze_seal=f["seal"])
        target=out/"results.json";target.write_text(json.dumps(payload))
        verification=dict(scope="PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC",plan_freeze_seal=f["seal"],
            result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r["source_hashes"],**r["plan_hashes"],**audits},
            implementation=r["implementation"],report_files=r["report_files"])
        canonical=json.dumps(verification,sort_keys=True,separators=(",",":"))
        (out/"plans-frozen.json").write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print("SETTLED AND INDEPENDENTLY RECONCILED",len(rows),"rows")
