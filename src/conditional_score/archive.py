"""Read archived inputs with byte identities. Never scrape or modify raw data."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from src.conditional_score.model import grid_basis
from beidan_backend.temporal_learning.core import Cutoff
from beidan_backend.temporal_learning.diagnostic_labels import diagnostic_label_clock


def read_score_archive(source_root, *, clock_horizon, label_delay_hours):
    """Read 48-issue frozen raw baseline, features, market grids and audited labels.

    source_root is explicit; hashes are verified against the frozen factor packet.
    Returns position-aligned arrays and a one-fixture frame, with historical proxy
    source/label clocks (not observed availability). Padded cells have zero mass.
    No collection, writes, imputation, feature fitting or outcome-based admission.
    """
    root=Path(source_root)
    factor_path=root/"new48-pure-baseline-v1/factors.json"
    factors=json.loads(factor_path.read_text())
    source=root/Path(factors["expert_source"]).name
    hashes={}
    prefix="data/derived/fundamentals_417/"
    for name,expected in factors["source_hashes"].items():
        if not name.startswith(prefix): raise ValueError("Unrecognized archived source root")
        path=root/name[len(prefix):]
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=expected: raise ValueError("Changed frozen source: "+name)
        hashes[str(path)]=actual
    audit_path=source/"settlement-audit.json"
    audit=json.loads(audit_path.read_text())["rows"]
    for path in (factor_path,audit_path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    af=pd.DataFrame(audit)
    keys=["issue","slot","provider_id"]
    if af.duplicated(keys).any(): raise ValueError("Duplicate settlement identities")
    truth={tuple(r[k] for k in keys):r for r in audit}
    rows=[];grids=[];exclusions=[];market_triplets=[]
    for issue in sorted({r["issue"] for r in factors["rows"]}):
        packet=json.loads((source/"projected"/(issue+".json")).read_text())
        features={tuple(r[k] for k in keys):r for r in packet["features"]}
        if len(features)!=len(packet["features"]):raise ValueError("Duplicate features")
        scores=pd.DataFrame(packet["control"]["scores"])
        groups={k:g.sort_values(["home_goals","away_goals"]) for k,g in scores.groupby(keys)}
        for fixture in packet["control"]["fixtures"]:
            key=tuple(fixture[k] for k in keys)
            if key not in features or key not in truth or key not in groups:
                raise ValueError("Incomplete fixture/feature/audit join")
            f=features[key]; label=truth[key];g=groups[key]
            q=pd.DataFrame(packet["market"]["grids"][issue+"/"+str(fixture["slot"])])
            for v in (g,q):
                numeric=v[["home_goals","away_goals","probability"]].to_numpy(float)
                if v.duplicated(["home_goals","away_goals"]).any() or not np.isfinite(numeric).all() or (numeric<0).any() or not np.all(numeric[:,:2]==np.floor(numeric[:,:2])) or abs(v.probability.sum()-1)>1e-8:
                    raise ValueError("Invalid frozen score grid")
            if label["status"]!="READY" or f["handicap"]!=fixture["handicap"] or label["handicap"]!=fixture["handicap"]:
                raise ValueError("Audit status/handicap conflict")
            actual_net=label["actual_home"]-label["actual_away"]+fixture["handicap"]
            actual_direction="W" if actual_net>0 else ("D" if actual_net==0 else "L")
            if actual_direction!=label["actual_direction"]:
                raise ValueError("Score and settled direction conflict")
            native=packet["cutoffs"][issue][str(fixture["slot"])]
            if not f.get("predictor_clock_ts"):
                exclusions.append(dict(issue=issue,slot=fixture["slot"],reason="MISSING_PREDICTOR_CLOCK"));continue
            if pd.Timestamp(f["predictor_clock_ts"])>=pd.Timestamp(native):
                raise ValueError("Predictor proxy not strictly before native cutoff")
            row={**f,**{k:fixture[k] for k in keys},**{k:label[k] for k in ("actual_home","actual_away","spf_sp","actual_direction","status")}}
            row.update(fixture_id="/".join(map(str,key)),issue_code=issue,issue_year=pd.Timestamp(native).year,
                decision_ts=native,data_available_ts=f["predictor_clock_ts"],
                label_available_ts=diagnostic_label_clock(native,cutoff=clock_horizon,delay_hours=label_delay_hours),
                source_evidence="HISTORICAL_PROXY",tier_evidence="UNKNOWN",opponent_strength_evidence="UNKNOWN",
                home_goal_gap=f["lambda_home"]-f["market_home_goals"],
                away_goal_gap=f["lambda_away"]-f["market_away_goals"])
            d=q.home_goals-q.away_goals+fixture["handicap"]
            market_triplets.append([float(q.probability[d>0].sum()),float(q.probability[d==0].sum()),float(q.probability[d<0].sum())])
            rows.append(row);grids.append(g)
    frame=pd.DataFrame(rows)
    if frame.fixture_id.duplicated().any():raise ValueError("Duplicate fixture weighting")
    width=max(len(g) for g in grids);n=len(grids)
    p=np.zeros((n,width));h=np.zeros((n,width),int);a=np.zeros((n,width),int);b=np.zeros((n,width,8))
    for i,g in enumerate(grids):
        count=len(g);p[i,:count]=g.probability;h[i,:count]=g.home_goals;a[i,:count]=g.away_goals
        b[i,:count]=grid_basis(g.home_goals,g.away_goals,frame.iloc[i].handicap)
    return dict(frame=frame,probabilities=p,home=h,away=a,basis=b,
                market=np.asarray(market_triplets),source_hashes=hashes,exclusions=exclusions)
