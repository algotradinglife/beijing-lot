"""Independent output replay checks for #422; no fitting or strategy changes."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from src.fundamentals_n7_single import settle_n7_single
from src.temporal_learning.provenance import verify_implementation_closure


def verify_experiment(output, replay, *, repository_root):
    """Validate byte receipts, repeat-process equality, probabilities and settlement.

    Verifies every frozen source and current transitive implementation. Reprojects
    WDL independently from saved score cells; re-settles saved plans with the
    authoritative settlement API. Raises on any mismatch; no writes/network.
    """
    out,again,root=Path(output),Path(replay),Path(repository_root)
    receipt=json.loads((out/"receipt.json").read_text())
    second=json.loads((again/"receipt.json").read_text())
    if receipt["historical_admission"] or second["historical_admission"]:
        raise ValueError("Diagnostic receipts required")
    if receipt["files"]!=second["files"]:
        raise ValueError("Independent process replay differs")
    for directory in (out,again):
        for name,expected in receipt["files"].items():
            if Path(name).name!=name:raise ValueError("Unsafe output path")
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=expected:
                raise ValueError("Output bytes changed: "+name)
    contract=json.loads((out/"contract.json").read_text())
    verify_implementation_closure(root,contract["implementation"])
    for name,expected in contract["report_implementation_hashes"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError("Implementation changed: "+name)
    for name,expected in contract["source_hashes"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise ValueError("Source changed: "+name)
    observations=pd.read_csv(out/"observations.csv",dtype={"issue":str,"provider_id":str})
    returns=pd.read_csv(out/"returns.csv",dtype={"issue":str})
    audit_paths=[p for p in contract["source_hashes"] if p.endswith("/settlement-audit.json")]
    audit=pd.DataFrame(json.loads(Path(audit_paths[0]).read_text())["rows"]) if len(audit_paths)==1 else None
    verified_cells=0;artifacts=0;plans=0
    for path in out.glob("*-artifact.json"):
        value=json.loads(path.read_text());cut=pd.Timestamp(value["cutoff_ts"])
        if pd.Timestamp(value["maximum_source_time"])>=cut or pd.Timestamp(value["maximum_training_label_timestamp"])>=cut:
            raise ValueError("Training crossed cutoff")
        sets=[set(value["partition"][k+"_issues"]) for k in ("fit","tune","calibration")]
        if any(value["target_issue"] in s for s in sets) or any(sets[i]&sets[j] for i in range(3) for j in range(i)):
            raise ValueError("Partition leakage")
        artifacts+=1
    for path in out.glob("*-scores.json"):
        issue,method=path.stem.removesuffix("-scores").split("-",1)
        cells=pd.DataFrame(json.loads(path.read_text()))
        for slot,g in cells.groupby("slot"):
            if g.duplicated(["home_goals","away_goals"]).any() or not np.isfinite(g.probability).all() or (g.probability<0).any() or not np.isclose(g.probability.sum(),1,rtol=0,atol=1e-9):
                raise ValueError("Invalid saved score distribution")
            match=observations[(observations.issue==issue)&(observations.slot==slot)&(observations.method==method)]
            if len(match)!=1:raise ValueError("Score/observation identity mismatch")
            line=float(match.handicap.iloc[0]);net=g.home_goals-g.away_goals+line
            projected=np.array([g.probability[net>0].sum(),g.probability[net==0].sum(),g.probability[net<0].sum()])
            if not np.allclose(projected,match[["p_W","p_D","p_L"]].to_numpy()[0],rtol=0,atol=1e-10):
                raise ValueError("Score projection differs")
            verified_cells+=len(g)
    for path in out.glob("*-plans.json"):
        issue=path.stem.removesuffix("-plans")
        for key,plan in json.loads(path.read_text()).items():
            method,selection=key.split("/")
            original=returns[(returns.issue==issue)&(returns.method==method)&(returns.selection==selection)]
            if len(original)!=1:raise ValueError("Plan/return identity mismatch")
            if audit is None:
                if plan["groups"]:raise ValueError("Audited settlement source required")
                check=settle_n7_single(plan,pd.DataFrame())
            else:
                check=settle_n7_single(plan,audit[audit.issue==issue])
            for field in ("stake","gross","net"):
                if not np.isclose(check[field],float(original[field].iloc[0]),rtol=0,atol=1e-7):
                    raise ValueError("Settlement replay differs")
            plans+=1
    return dict(status="PASS",issues=receipt["issues"],fixtures=receipt["fixtures"],
        score_cells=verified_cells,artifacts=artifacts,plans=plans,
        independent_process_byte_equality=True,source_and_implementation_hashes=True,
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
