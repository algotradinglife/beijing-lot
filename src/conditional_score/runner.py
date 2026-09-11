"""Issue-wise retrospective experiment; immutable receipt then target evaluation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.conditional_score.model import fit_remapper, predict_remapper, score_metrics
from src.temporal_learning.core import (Cutoff, TemporalContractError, stable_json_hash,
                                       AvailabilityPolicy)
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_n7_single import n7_single_plan, settle_n7_single


def build_comparison_plan(factors, *, cutoffs, budget_cny, unit_cny, payout_factor,
                          allocation_seed, max_uses, fixed_plan=None):
    """Use authoritative N7 full-double planner, optionally freeze baseline groups.

    No settlement inputs. Fixed groups retain the baseline fixture identities but
    choose this model's two directions. Cash/unit/payout are explicit.
    """
    kwargs=dict(unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=allocation_seed,
                max_uses=max_uses,single_rule="MAX_SINGLE",single_count=0)
    if fixed_plan is None:
        return n7_single_plan(factors,cutoffs=cutoffs,budget_cny=budget_cny,**kwargs)
    if fixed_plan["seal"] != stable_json_hash({k:v for k,v in fixed_plan.items() if k!="seal"}):
        raise ValueError("Fixed plan changed")
    if (fixed_plan["budget_cny"]!=budget_cny or fixed_plan["unit_cny"]!=unit_cny or
        fixed_plan["payout_factor"]!=payout_factor):
        raise ValueError("Fixed plan business constants differ")
    if (factors.issue.astype(str).nunique()!=1 or
        str(factors.issue.iloc[0])!=fixed_plan["issue"]):
        raise ValueError("Fixed plan issue identity differs")
    if set(cutoffs)!=set(factors.slot.astype(str)) or any(
        not isinstance(c, Cutoff) or c.target_issue!=fixed_plan["issue"] or
        c.cutoff_ts.isoformat()!=fixed_plan["cutoffs"].get(slot)
        for slot,c in cutoffs.items()):
        raise ValueError("Fixed plan native cutoffs differ")
    for leg in fixed_plan["legs"]:
        match=factors[factors.slot.eq(leg["slot"])]
        if (len(match)!=1 or str(match.provider_id.iloc[0])!=str(leg["provider_id"]) or
            float(match.handicap.iloc[0])!=float(leg["handicap"])):
            raise ValueError("Fixed plan fixture identity differs")
    result={k:v for k,v in fixed_plan.items() if k!="seal"}
    legs=[];tickets=[]
    for group in range(1,fixed_plan["groups"]+1):
        slots=[r["slot"] for r in fixed_plan["legs"] if r["group"]==group]
        subset=factors[factors.slot.isin(slots)]
        if len(subset)!=7:raise ValueError("Fixed fixture group missing")
        component=n7_single_plan(subset,cutoffs={str(s):cutoffs[str(s)] for s in slots},
                                budget_cny=unit_cny*128,**kwargs)
        legs.extend({**r,"group":group} for r in component["legs"])
        tickets.extend({**r,"group":group} for r in component["tickets"])
    result.update(legs=legs,tickets=tickets,fixed_fixture_source_seal=fixed_plan["seal"],
                  input_sha256=stable_json_hash(factors.to_json(orient="records")))
    return dict(**result,seal=stable_json_hash(result))


def run_experiment(archive, output, *, repository_root, penalties, partition_policy,
                   weighting_policy, budget_cny, unit_cny, payout_factor, allocation_seed,
                   max_uses, initial_bankroll_cny):
    """Freeze per-issue artifacts/plans before scoring targets; JSON/CSV outputs.

    Previously exposed data are diagnostic only. Incomplete prior windows are
    excluded for all methods, never substituted with an untrained fitted model.
    No RDS, source mutation or expert version changes. New output directory only.
    """
    out=Path(output)
    if out.exists():raise FileExistsError("Use a new immutable output directory")
    out.mkdir(parents=True)
    f=archive["frame"];p=archive["probabilities"];b=archive["basis"];h=archive["home"];a=archive["away"]
    if f.empty:raise ValueError("Nonempty archive required")
    implementation=implementation_closure(Path(repository_root),
        ["src.conditional_score.runner","src.conditional_score.archive"],
        distributions=["numpy","pandas","scipy","scikit-learn","matplotlib","pyarrow","nbformat","nbclient"])
    contract=dict(scope="EXPOSED_RETROSPECTIVE_DIAGNOSTIC_NOT_PROSPECTIVE",issues=sorted(f.issue.unique()),
        source_hashes=archive["source_hashes"],implementation=implementation,
        penalties=list(penalties),partition_policy=vars(partition_policy),weighting_policy=str(weighting_policy),
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=allocation_seed,
        max_uses=max_uses,initial_bankroll_cny=initial_bankroll_cny,score_protection=False)
    import hashlib
    report_paths=("r/conditional_score_report.R","quarto/93_conditional_score.qmd",
                  "scripts/run_conditional_score.py","docs/research/issue422_contract.md",
                  "config/conditional_score_runtime.json")
    contract["report_implementation_hashes"]={name:hashlib.sha256((Path(repository_root)/name).read_bytes()).hexdigest()
                                            for name in report_paths}
    (out/"contract.json").write_text(json.dumps(contract,indent=2))
    observations=[];returns=[];training=[];exclusions=list(archive["exclusions"])
    order=f.groupby("issue").decision_ts.min().sort_values().index
    for issue in order:
        target=f[f.issue.eq(issue)];idx=target.index
        cutoff=Cutoff.decision_epoch(issue,min(target.decision_ts))
        models={}
        try:
            for method in ("GLOBAL","MARKET_CONTEXT","CONDITIONAL"):
                models[method]=fit_remapper(f,p,b,h,a,cutoff=cutoff,repository_root=repository_root,
                    source_hashes=archive["source_hashes"],method=method,penalties=penalties,
                    availability_policy=AvailabilityPolicy.historical_proxy("422_ARCHIVED_PREDICTOR_AND_72H_LABEL_PROXY"),
                    intended_use="HISTORICAL_DIAGNOSTIC",partition_policy=partition_policy,
                    weighting_policy=weighting_policy)
        except TemporalContractError as error:
            if ("insufficient" not in str(error) and "no prior observations" not in str(error)
                and not str(error).startswith("effective sample size ")):raise
            exclusions.append(dict(issue=issue,slot=None,reason=str(error)))
            print("SKIP",issue,str(error),flush=True);continue
        native={str(r.slot):Cutoff.decision_epoch(issue,r.decision_ts) for r in target.itertuples()}
        grids={"BASELINE":p[idx]}
        for name,artifact in models.items():
            # Persist complete model receipt before target metric/settlement evaluation.
            (out/(issue+"-"+name+"-artifact.json")).write_text(json.dumps(artifact["receipt"],indent=2))
            pred=[]
            for position,row in target.iterrows():
                pred.append(predict_remapper(artifact,target.loc[[position]].drop(columns=["actual_home","actual_away","spf_sp","actual_direction"]),
                    p[[position]],b[[position]],cutoff=native[str(row.slot)])[0])
            grids[name]=np.asarray(pred)
            for partition,metric in artifact["receipt"]["metrics"].items():
                training.append(dict(issue=issue,method=name,partition=partition,**metric))
        factors={}
        for name,grid in grids.items():
            # Projection does not use actual outcomes: masks share the same grid.
            net=h[idx]-a[idx]+target.handicap.to_numpy()[:,None]
            triplets=np.stack([(grid*(net>0)).sum(1),(grid*(net==0)).sum(1),(grid*(net<0)).sum(1)],axis=1)
            z=target[["issue","slot","provider_id","handicap","home","away"]].copy()
            z[["p_W","p_D","p_L"]]=triplets
            z[["q_W","q_D","q_L"]]=archive["market"][idx]
            factors[name]=z
        baseplan=build_comparison_plan(factors["BASELINE"],cutoffs=native,budget_cny=budget_cny,
            unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=allocation_seed,max_uses=max_uses)
        plans={}
        for name in grids:
            for selection in ("FIXED","RESELECTED"):
                plan=build_comparison_plan(factors[name],cutoffs=native,budget_cny=budget_cny,unit_cny=unit_cny,
                    payout_factor=payout_factor,allocation_seed=allocation_seed,max_uses=max_uses,
                    fixed_plan=baseplan if selection=="FIXED" else None)
                plans[name+"/"+selection]=plan
        (out/(issue+"-plans.json")).write_text(json.dumps(plans))
        # Target evaluation begins only after all methods' plans are frozen.
        for name,grid in grids.items():
            metric=score_metrics(grid,h[idx],a[idx],target.handicap,target.actual_home,target.actual_away)
            metric[["issue","slot","provider_id"]]=target[["issue","slot","provider_id"]].to_numpy()
            metric["method"]=name;metric["partition"]="RETROSPECTIVE_WALK_FORWARD"
            metric["fit_support"]=models["GLOBAL"]["receipt"]["fit_support"]
            q=archive["market"][idx];baseline=factors["BASELINE"][["p_W","p_D","p_L"]].to_numpy()
            now=factors[name][["p_W","p_D","p_L"]].to_numpy()
            metric["conflict"]=np.where(baseline.argmax(1)==q.argmax(1),"AGREE","DISAGREE")
            metric["adjustment"]=np.where(np.max(abs(now-baseline),axis=1)<1e-8,"UNCHANGED",
                np.where((abs(now-q).sum(1)<abs(baseline-q).sum(1)),"TOWARD_MARKET","AWAY_FROM_MARKET"))
            # Directional attribution, not a proven profitable classifier.
            metric["evidence_scope"]="FITTED_DIRECTION_NOT_PROVEN_OPPORTUNITY"
            metric["competition"]=target.competition.to_numpy()
            metric["handicap"]=target.handicap.to_numpy()
            metric["actual_margin"]=(target.actual_home-target.actual_away).to_numpy()
            observations.extend(metric.to_dict("records"))
            # Save full normalized score grid for independent projection and QMD inspection.
            cells=[]
            for k,(_,row) in enumerate(target.iterrows()):
                cells.extend(dict(slot=int(row.slot),home_goals=int(h[idx[k],j]),away_goals=int(a[idx[k],j]),
                                  probability=float(value)) for j,value in enumerate(grid[k]) if p[idx[k],j]>0)
            (out/(issue+"-"+name+"-scores.json")).write_text(json.dumps(cells))
            audit=target[["issue","slot","provider_id","handicap","actual_direction","status","spf_sp"]]
            for selection in ("FIXED","RESELECTED"):
                result=settle_n7_single(plans[name+"/"+selection],audit)
                returns.append(dict(method=name,selection=selection,**result))
        print("DONE",issue,len(target),"fit",models["GLOBAL"]["receipt"]["fit_support"],flush=True)
    observations=pd.DataFrame(observations);returns=pd.DataFrame(returns);training=pd.DataFrame(training)
    if not len(observations):raise TemporalContractError("No supported evaluation issue")
    for (method,selection),positions in returns.groupby(["method","selection"]).groups.items():
        part=returns.loc[positions]
        if not part.status.isin(["COMPLETE","NO_BET"]).all():raise ValueError("Pending settlement must not be zero-filled")
        net=part.net.to_numpy(float);equity=initial_bankroll_cny+np.cumsum(net)
        peak=np.maximum.accumulate(np.r_[initial_bankroll_cny,equity])[1:]
        returns.loc[positions,"equity_cny"]=equity
        returns.loc[positions,"drawdown_cny"]=peak-equity
        returns.loc[positions,"roi_percent"]=100*part.roi
    for name,table in (("observations",observations),("returns",returns),("training",training),
                       ("exclusions",pd.DataFrame(exclusions))):
        table.to_csv(out/(name+".csv"),index=False)
    summary=(observations.groupby("method")[["score_logloss","score_brier","wdl_logloss","wdl_brier","top1","top2"]]
             .mean().reset_index())
    summary.to_csv(out/"summary.csv",index=False)
    import hashlib
    from datetime import datetime, timezone
    receipt=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
        contract_identity=stable_json_hash(contract),historical_admission=False,
        fixtures=int(observations[["issue","slot"]].drop_duplicates().shape[0]),
        issues=int(observations.issue.nunique()),implementation=implementation,
        files={v.name:hashlib.sha256(v.read_bytes()).hexdigest() for v in sorted(out.iterdir()) if v.is_file()})
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2))
    return receipt
