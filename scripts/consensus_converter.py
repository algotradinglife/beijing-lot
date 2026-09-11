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
from src.fundamentals_consensus_portfolio import consensus_portfolios, independent_consensus_portfolio, consensus_candidates
from src.fundamentals_n7_twocover import settle_n7_twocover
from src.fundamentals_n7_single import settle_n7_single
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("phase",choices=["freeze","settle"])
    parser.add_argument("--study",required=True)
    parser.add_argument("--design",choices=["paired","independent"],default="paired")
    parser.add_argument("--exclude-zero-top2-disagreement",action="store_true")
    parser.add_argument("--anchor-max-uses",type=int,choices=range(1,7))
    args=parser.parse_args()
    if args.phase=="freeze" and args.anchor_max_uses is not None and (args.design!="independent" or not args.exclude_zero_top2_disagreement):
        parser.error("Anchor experiment requires independent design and exclusion")
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
        reports=[("quarto/95_consensus_converter.qmd" if args.design=="paired" else "quarto/96_independent_converter.qmd"),"r/fundamentals_pure_report.R",
                 "r/fundamentals_missed_summary.R","r/fundamentals_equity_curves.R"]
        if args.exclude_zero_top2_disagreement:reports[0]="quarto/98_candidate_exclusion.qmd"
        if args.anchor_max_uses is not None:reports[0]="quarto/99_unique_single.qmd"
        receipt=dict(anchor_max_uses=args.anchor_max_uses,exclude_zero_top2_disagreement=args.exclude_zero_top2_disagreement,scope="EXPOSED_FIXED_CONSENSUS_NOT_FITTED",design=args.design,issues=issues,parameters=params,
            source_hashes={**data["source_hashes"],**previous["receipt"]["plan_hashes"],
                           str(pure):hashlib.sha256(pure.read_bytes()).hexdigest(),
                           str(prior/"plans-frozen.json"):hashlib.sha256((prior/"plans-frozen.json").read_bytes()).hexdigest()},
            implementation=implementation_closure(Path.cwd(),["scripts.consensus_converter"],distributions=["numpy","pandas","scipy"]),
            report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports})
        if args.design=="independent":
            reference=Path("data/derived/fundamentals_417/consensus-converter-v3")
            witness=json.loads((reference/"plans-frozen.json").read_text())
            assert hashlib.sha256(witness["canonical_json"].encode()).hexdigest()==witness["seal"]
            assert json.loads(witness["canonical_json"])["result_sha256"]==hashlib.sha256((reference/"results.json").read_bytes()).hexdigest()
            receipt["reference_mode"]="INVENTORIED_PRIOR_PAIRED_EVIDENCE_NOT_CURRENT_MODEL_REPLAY"
            receipt["reference_root"]=str(reference)
            receipt["source_hashes"].update({str(reference/p):hashlib.sha256((reference/p).read_bytes()).hexdigest() for p in ["results.json","plans-frozen.json"]})
            params=dict(budget_cny=1024,minimum_anchor_market=.5,max_uses=6,max_pair_overlap=5,
                        unit_cny=2,payout_factor=.65,seed=41902)
            receipt["parameters"]=params
            receipt["conversion_budget_fractions"]=[0,.25,.5,.75,1]
            if args.anchor_max_uses is not None:
                params["anchor_max_uses"]=args.anchor_max_uses
                receipt["conversion_budget_fractions"]=[0]
        if args.exclude_zero_top2_disagreement:
            filtered_reference=Path("data/derived/fundamentals_417")/("consensus-converter-v3" if args.design=="paired" else "independent-converter-v1")
            if args.anchor_max_uses is not None:
                filtered_reference=Path("data/derived/fundamentals_417/candidate-exclusion-v1/independent")
                ancestor=json.loads((filtered_reference/"frozen.json").read_text())
                assert stable_json_hash(ancestor["receipt"])==ancestor["seal"]
                verify_clean_file_bindings(ancestor["receipt"]["plan_hashes"],repository_root=Path.cwd())
                receipt["source_hashes"].update(ancestor["receipt"]["plan_hashes"])
                receipt["source_hashes"][str(filtered_reference/"frozen.json")]=hashlib.sha256((filtered_reference/"frozen.json").read_bytes()).hexdigest()
            witness=json.loads((filtered_reference/"plans-frozen.json").read_text())
            assert hashlib.sha256(witness["canonical_json"].encode()).hexdigest()==witness["seal"]
            assert json.loads(witness["canonical_json"])["result_sha256"]==hashlib.sha256((filtered_reference/"results.json").read_bytes()).hexdigest()
            receipt["filtered_reference"]=str(filtered_reference)
            receipt["source_hashes"].update({str(filtered_reference/p):hashlib.sha256((filtered_reference/p).read_bytes()).hexdigest() for p in ["results.json","plans-frozen.json"]})
            receipt["filter_ledgers"]={}
        (out/"plans").mkdir(parents=True)
        (out/"contract.json").write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
        frame=pd.DataFrame(data["rows"]);hashes={}
        for issue in issues:
            f=frame[frame.issue==issue].copy()
            cuts={str(s):Cutoff.decision_epoch(issue,data["cutoffs"][issue][str(s)]) for s in f.slot}
            if args.exclude_zero_top2_disagreement:
                f,filter_ledger=exclude_zero_top2_disagreement(f,cutoffs=cuts)
                receipt["filter_ledgers"][issue]=filter_ledger
                cuts={str(s):cuts[str(s)] for s in f.slot}
            if args.design=="paired":
                bundle=consensus_portfolios(f,cutoffs=cuts,**params)
            else:
                plans={}
                if args.anchor_max_uses is not None:
                    baseline=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,**dict(params,anchor_max_uses=None))
                    ancestor_plan=json.loads(gzip.decompress((filtered_reference/"plans"/f"{issue}.json.gz").read_bytes()))["plans"]["INDEPENDENT_C000"]
                    assert baseline["components"]==ancestor_plan["components"]
                    assert baseline["stake"]==ancestor_plan["stake"] and baseline["cash_cny"]==ancestor_plan["cash_cny"]
                for fraction in receipt["conversion_budget_fractions"]:
                    plan=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=fraction,**params)
                    plans[plan["strategy"]]=plan
                _,_,eligible,_=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False)
                bundle=dict(plans=plans,skeletons=[],pool_counts=dict(zip("ADC",map(int,eligible.sum(axis=0)))))
                bundle["seal"]=stable_json_hash(bundle)
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
            if r["design"]=="paired":
                reference=json.loads(gzip.decompress((prior/"plans"/f"{issue}.json.gz").read_bytes()))["D2_U6_P5_BASE"]["plan"]
                s=settle_n7_single(reference,a)
                rows.append(dict(s,policy="OLD_D2_U6_P5",budget_cny=reference["budget_cny"],
                                 cash_cny=reference["cash_cny"],n6_hits=0,n7_hits=s["hits"]))
        if r["design"]=="independent":
            previous=json.loads((Path(r["reference_root"])/"results.json").read_text())
            rows.extend(dict(x,policy="PREVIOUS_"+x["policy"]) for x in previous["rows"]
                        if x["policy"] in ["PRIMARY_FILL","COMPLEMENT","OLD_D2_U6_P5"])
        expected=len(r["conversion_budget_fractions"])+3 if r["design"]=="independent" else 4
        assert len(rows)==expected*len(r["issues"]) and all(x["status"] in ["COMPLETE","NO_BET"] for x in rows)
        payload=dict(rows=rows,pools=pools,legs=leg_rows,issue_order=r["issues"],parameters=r["parameters"],
                     upstream_freeze_seal=frozen["seal"],historical_admission=False,design=r["design"])
        if r["exclude_zero_top2_disagreement"]:
            payload["filter_ledgers"]=r["filter_ledgers"]
            payload["reference_rows"]=json.loads((Path(r["filtered_reference"])/"results.json").read_text())["rows"]
            payload["reference_mode"]="INVENTORIED_UNFILTERED_RESULTS_NOT_CURRENT_MODEL_REPLAY"
        target=out/"results.json";target.write_text(json.dumps(payload))
        verification=dict(scope="PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC",
                          plan_freeze_seal=frozen["seal"],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                          source_hashes={**r["source_hashes"],**r["plan_hashes"],**audits},
                          implementation=r["implementation"],report_files=r["report_files"])
        canonical=json.dumps(verification,sort_keys=True,separators=(",",":"))
        (out/"plans-frozen.json").write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print("SETTLED",len(rows),"policy/issue rows")
