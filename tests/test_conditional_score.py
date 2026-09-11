"""Synthetic contract, chronology and post-cutoff mutation tests for #422."""
from pathlib import Path
import copy
import numpy as np
import pandas as pd
import pytest
from src.conditional_score.model import (NUMERIC,grid_basis,tilt_scores,score_metrics,fit_remapper,predict_remapper)
from src.conditional_score.runner import build_comparison_plan
from src.temporal_learning.core import (Cutoff,AvailabilityPolicy,AvailabilityFilter,
    WeightingPolicy,TemporalContractError)
from src.temporal_learning.issue_partitions import (IssuePartitionPolicy as PartitionPolicy,
    prepare_issue_learning_context as prepare_learning_context)

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def sample():
    rng=np.random.default_rng(42)
    cells=np.array([(h,a) for h in range(4) for a in range(4)])
    n=32;h=np.tile(cells[:,0],(n,1));a=np.tile(cells[:,1],(n,1))
    p=np.full((n,16),1/16);b=np.array([grid_basis(h[i],a[i],-1) for i in range(n)])
    rows=[]
    for i in range(n):
        date=pd.Timestamp("2010-01-01",tz="UTC")+pd.Timedelta(days=i)
        row={k:float(rng.uniform(0,2)) for k in NUMERIC}
        row.update(handicap=-1,neutral=0,competition="A" if i%2 else "B",fixture_id=str(i),
            issue_code=f"{i:06d}",issue=f"{i:06d}",issue_year=2010,
            label_available_ts=date.isoformat(),data_available_ts=(date-pd.Timedelta(hours=1)).isoformat(),
            actual_home=int(rng.integers(0,4)),actual_away=int(rng.integers(0,4)))
        rows.append(row)
    return pd.DataFrame(rows),p,b,h,a

def kwargs(cutoff,method="CONDITIONAL"):
    return dict(cutoff=cutoff,repository_root=ROOT,source_hashes={"synthetic":"a"*64},
        method=method,penalties=(.1,1),availability_policy=AvailabilityPolicy.historical_proxy("test"),
        intended_use="HISTORICAL_DIAGNOSTIC",partition_policy=PartitionPolicy(kind="PRIOR_COMPLETE_ISSUES",
            tune_issues=2,calibration_issues=2,minimum_fit_issues=4),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=4))

def test_basis_tilt_and_projection():
    h=np.array([[0,1,2,3]]);a=np.array([[0,0,1,0]])
    b=np.array([grid_basis(h[0],a[0],-1)])
    p=np.array([[.1,.2,.3,.4]]);cut=Cutoff.decision_epoch("1","2010-01-01T00:00:00Z")
    assert np.array_equal(tilt_scores(p,b,[[1]],np.zeros((1,8)),cutoff=cut),p) or np.allclose(tilt_scores(p,b,[[1]],np.zeros((1,8)),cutoff=cut),p)
    coef=np.zeros((1,8));coef[0,2]=2
    q=tilt_scores(p,b,[[1]],coef,cutoff=cut)
    assert q[0,1]+q[0,2]>.5 and q.sum()==pytest.approx(1)
    m=score_metrics(p,h,a,[-1],[2],[1])
    assert m.p_D.iloc[0]==pytest.approx(.5)
    assert m.score_logloss.iloc[0]==pytest.approx(-np.log(.3))
    assert m.conditional_total_expected.iloc[0]==pytest.approx(2.2)
    assert m.large_probability.iloc[0]==pytest.approx(.4)
    assert m.btts_probability.iloc[0]==pytest.approx(.3)
    with pytest.raises(ValueError):grid_basis([.5],[0],0)
    with pytest.raises(ValueError):grid_basis([0],[0],.5)
    with pytest.raises(ValueError):tilt_scores(p*2,b,[[1]],coef,cutoff=cut)
    with pytest.raises(ValueError):tilt_scores(p,b,[[1]],coef,cutoff=None)
    with pytest.raises(ValueError):score_metrics(p*2,h,a,[-1],[2],[1])

@pytest.mark.parametrize("method",["GLOBAL","CONDITIONAL","MARKET_CONTEXT"])
def test_fit_future_invariance_and_replay(sample,method):
    f,p,b,h,a=sample;cut=Cutoff.decision_epoch("000026","2010-01-27T00:00:00Z")
    k=kwargs(cut,method);fit=fit_remapper(f,p,b,h,a,**k)
    changed=f.copy()
    changed.loc[26:,"actual_home"]=99
    changed.loc[26:,"home_venue_goals_for_pg"]=999
    again=fit_remapper(changed,p,b,h,a,**k)
    assert np.array_equal(fit["coefficients"],again["coefficients"])
    assert fit["receipt"]["artifact_sha256"]==again["receipt"]["artifact_sha256"]
    assert "000026" not in fit["receipt"]["partition"]["fit_issues"]
    assert max(fit["receipt"]["partition"]["calibration_issues"])=="000025"
    target=f.iloc[[26]].drop(columns=["actual_home","actual_away"])
    pred=predict_remapper(fit,target,p[[26]],b[[26]],cutoff=cut)
    assert pred.sum()==pytest.approx(1)
    with pytest.raises(ValueError):predict_remapper(fit,f.iloc[[26]],p[[26]],b[[26]],cutoff=cut)
    with pytest.raises(TemporalContractError):predict_remapper(fit,target,p[[26]],b[[26]],
        cutoff=Cutoff.decision_epoch("other","2010-01-27T00:00:00Z"))
    k["intended_use"]="PROSPECTIVE_DECISION"
    with pytest.raises(TemporalContractError):fit_remapper(f,p,b,h,a,**k)
    k=kwargs(Cutoff.decision_epoch("000003","2010-01-04T00:00:00Z"),method)
    with pytest.raises(TemporalContractError):fit_remapper(f,p,b,h,a,**k)

def test_missing_and_unseen_category(sample):
    f,p,b,h,a=sample;f.loc[:12,"home_venue_goals_for_pg"]=np.nan
    cut=Cutoff.decision_epoch("000026","2010-01-27T00:00:00Z")
    model=fit_remapper(f,p,b,h,a,**kwargs(cut))
    target=f.iloc[[26]].drop(columns=["actual_home","actual_away"]).copy()
    target["competition"]="UNSEEN";target["home_venue_goals_for_pg"]=np.nan
    assert np.isfinite(predict_remapper(model,target,p[[26]],b[[26]],cutoff=cut)).all()

def test_complete_issue_and_cache(sample):
    f,p,b,h,a=sample;cut=Cutoff.decision_epoch("000026","2010-01-27T00:00:00Z")
    kw=kwargs(cut);kw={k:v for k,v in kw.items() if k not in {"method","penalties"}}
    kw["implementation_modules"]=("src.conditional_score.model",)
    kw["availability"]=AvailabilityFilter(kw.pop("availability_policy"),data_available_column="data_available_ts")
    extra=f.iloc[[20]].copy();extra.index=[32];extra["label_available_ts"]="2011-01-01T00:00:00Z"
    context=prepare_learning_context(pd.concat([f,extra]),**kw)
    assert "000020" not in context.eligible.issue_code.tolist()
    assert context.receipt.payload["partition"]["fit_issues"]
    other=prepare_learning_context(f,**{**kw,"cutoff":Cutoff.decision_epoch("000027","2010-01-28T00:00:00Z")})
    assert context.receipt.payload["cache_key"]!=other.receipt.payload["cache_key"]
    rebound=prepare_learning_context(f,**{**kw,"source_hashes":{"changed":"b"*64}})
    original=prepare_learning_context(f,**kw)
    assert original.receipt.payload["cache_key"]!=rebound.receipt.payload["cache_key"]
    # A newly seen post-cutoff row cannot remove an earlier complete issue.
    unknown=extra.copy();unknown["data_available_ts"]="2011-01-01T00:00:00Z"
    context_unknown=prepare_learning_context(pd.concat([f,unknown]),**kw)
    assert context_unknown.receipt.payload["admitted_history_sha256"]==original.receipt.payload["admitted_history_sha256"]

def test_fixed_groups_and_budget():
    f=pd.DataFrame([dict(issue="i",slot=i,provider_id=str(i),home="h",away="a",handicap=-1,
                        p_W=.6,p_D=.3,p_L=.1,q_W=.4,q_D=.3,q_L=.3) for i in range(1,29)])
    cuts={str(i):Cutoff.decision_epoch("i","2010-01-01T00:00:00Z") for i in range(1,29)}
    kw=dict(cutoffs=cuts,budget_cny=1024,unit_cny=2,payout_factor=.65,allocation_seed=422,max_uses=2)
    base=build_comparison_plan(f,**kw)
    f[["p_W","p_D","p_L"]]=[.1,.3,.6]
    new=build_comparison_plan(f,fixed_plan=base,**kw)
    assert base["stake"]==new["stake"]==1024
    assert [r["slot"] for r in base["legs"]]==[r["slot"] for r in new["legs"]]
    assert {r["support"] for r in new["legs"]}=={"10"}
    assert len(new["tickets"])==512

def test_runner_end_to_end(sample,tmp_path):
    from src.conditional_score.runner import run_experiment
    f,p,b,h,a=sample
    f=f.iloc[:12].copy();p=p[:12];b=b[:12];h=h[:12];a=a[:12]
    f["slot"]=1;f["provider_id"]=f.fixture_id;f["home"]="H";f["away"]="A"
    f["decision_ts"]=f.label_available_ts
    f["status"]="READY";f["spf_sp"]=2.
    f["actual_direction"]=np.where(f.actual_home-f.actual_away-1>0,"W",
                                  np.where(f.actual_home-f.actual_away-1==0,"D","L"))
    import hashlib
    source=tmp_path/"synthetic-input.json"
    source.write_text(f.to_json(orient="records"))
    archive=dict(frame=f,probabilities=p,basis=b,home=h,away=a,market=np.full((len(f),3),1/3),
                 source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},exclusions=[])
    kw=dict(repository_root=ROOT,penalties=(1.,),
        partition_policy=PartitionPolicy(kind="PRIOR_COMPLETE_ISSUES",tune_issues=2,
                                        calibration_issues=2,minimum_fit_issues=4),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=4),
        budget_cny=1024,unit_cny=2,payout_factor=.65,allocation_seed=422,max_uses=2,initial_bankroll_cny=100000)
    out=tmp_path/"run"
    receipt=run_experiment(archive,out,**kw)
    assert receipt["issues"]==4
    import os,shutil
    if os.environ.get("CONDITIONAL_SCORE_TEST_OUTPUT"):
        shutil.copytree(out,os.environ["CONDITIONAL_SCORE_TEST_OUTPUT"])
    from src.conditional_score.verification import verify_experiment
    identical=tmp_path/"identical"
    shutil.copytree(out,identical)
    checked=verify_experiment(out,identical,repository_root=ROOT)
    assert checked["status"]=="PASS" and checked["plans"]==32
    from unittest.mock import patch
    from importlib import metadata
    original_version=metadata.version
    with patch("src.temporal_learning.provenance.metadata.version",
               side_effect=lambda name: "different-version" if name=="numpy" else original_version(name)):
        with pytest.raises(TemporalContractError,match="implementation closure"):
            verify_experiment(out,identical,repository_root=ROOT)
    (identical/"summary.csv").write_text("changed")
    with pytest.raises(ValueError,match="Output bytes"):
        verify_experiment(out,identical,repository_root=ROOT)
    returns=pd.read_csv(out/"returns.csv")
    assert set(returns.selection)=={"FIXED","RESELECTED"}
    assert set(returns.status)=={"NO_BET"}
    assert returns.equity_cny.eq(100000).all()
    with pytest.raises(FileExistsError):run_experiment(archive,out,**kw)
    changed=copy.deepcopy(archive)
    changed["frame"].loc[10:,"actual_home"]=99
    changed["frame"].loc[10:,"home_venue_goals_for_pg"]=999
    replay=tmp_path/"replay"
    run_experiment(changed,replay,**kw)
    # Complete earlier output invariant: fit, predictions, support and routing.
    for name in ("000008-GLOBAL-artifact.json","000008-CONDITIONAL-artifact.json",
                 "000008-CONDITIONAL-scores.json","000008-plans.json"):
        assert (out/name).read_bytes()==(replay/name).read_bytes()

def test_archive_contract(tmp_path):
    import hashlib,json
    from src.conditional_score.archive import read_score_archive
    study=tmp_path/"example";(study/"projected").mkdir(parents=True)
    feature={key:1. for key in NUMERIC}
    feature.update(issue="100402",slot=1,provider_id="01",handicap=-1,lambda_home=1.,
        lambda_away=1.,market_home_goals=1.,market_away_goals=1.,
        predictor_clock_ts="2010-01-01T00:00:00Z")
    fixture=dict(issue="100402",slot=1,provider_id="01",handicap=-1,home="H",away="A")
    score=[dict(home_goals=0,away_goals=0,probability=1.,**{k:fixture[k] for k in ["issue","slot","provider_id"]})]
    packet=dict(features=[feature],control=dict(fixtures=[fixture],scores=score),
        market=dict(grids={"100402/1":score}),cutoffs={"100402":{"1":"2010-01-01T01:00:00Z"}})
    source=study/"projected/100402.json";source.write_text(json.dumps(packet))
    (study/"settlement-audit.json").write_text(json.dumps({"rows":[dict(**fixture,actual_home=0,
        actual_away=0,actual_direction="L",spf_sp=2.,status="READY")]}))
    factors=tmp_path/"new48-pure-baseline-v1";factors.mkdir()
    (factors/"factors.json").write_text(json.dumps(dict(expert_source="example",rows=[fixture],
        source_hashes={"data/derived/fundamentals_417/example/projected/100402.json":
                      hashlib.sha256(source.read_bytes()).hexdigest()})))
    kw=dict(clock_horizon=Cutoff.last_issue("100402","2011-01-01T00:00:00Z"),label_delay_hours=72)
    result=read_score_archive(tmp_path,**kw)
    assert result["frame"].provider_id.tolist()==["01"]
    assert result["probabilities"].shape==(1,1)
    source.write_text("changed")
    with pytest.raises(ValueError,match="Changed frozen source"):read_score_archive(tmp_path,**kw)


def test_model_cache_identity_and_fit_ess(sample):
    from src.temporal_learning.issue_partitions import bind_model_receipt
    f,p,b,h,a=sample
    cut=Cutoff.decision_epoch("000012","2010-01-13T00:00:00Z")
    k=kwargs(cut,"GLOBAL")
    global_fit=fit_remapper(f,p,b,h,a,**k)
    conditional=fit_remapper(f,p,b,h,a,**{**k,"method":"CONDITIONAL"})
    changed_grid=fit_remapper(f,p,b,h,a,**{**k,"penalties":(.1,10)})
    assert len({x["receipt"]["cache_key"] for x in (global_fit,conditional,changed_grid)})==3
    weights=global_fit["receipt"]["fit_weight_receipt"]
    import json
    ledger=json.loads(weights["ledger_json"])
    assert weights["rows"]==8 and weights["effective_sample_size"]==pytest.approx(8)
    assert sum(r["fit_weight"] for r in ledger)==pytest.approx(1)
    assert {r["fixture_id"] for r in ledger}==set(map(str,range(8)))
    # Twelve prior rows meet overall ESS=10 but only eight are actually fitted.
    with pytest.raises(TemporalContractError,match="in fit partition"):
        fit_remapper(f,p,b,h,a,**{**k,"weighting_policy":WeightingPolicy.expanding_equal(minimum_ess=10)})
    params={x:v for x,v in k.items() if x not in {"method","penalties"}}
    params["availability"]=AvailabilityFilter(params.pop("availability_policy"),data_available_column="data_available_ts")
    params["implementation_modules"]=("src.conditional_score.model",)
    context=prepare_learning_context(f,**params)
    with pytest.raises(TemporalContractError):
        bind_model_receipt(context,Cutoff.decision_epoch("other","2010-01-13T00:00:00Z"),
                           model_identity={"method":"GLOBAL"},model_parameters={"penalties":[1]})

def test_changed_admission_binds_cache_and_fixed_plan_scope(sample):
    f,p,b,h,a=sample
    cut=Cutoff.decision_epoch("000026","2010-01-27T00:00:00Z")
    first=fit_remapper(f,p,b,h,a,**kwargs(cut,"GLOBAL"))
    delayed=f.copy()
    delayed.label_available_ts=(pd.to_datetime(delayed.label_available_ts)+pd.Timedelta(days=1)).astype(str)
    second=fit_remapper(delayed,p,b,h,a,**kwargs(cut,"GLOBAL"))
    assert first["receipt"]["cache_key"]!=second["receipt"]["cache_key"]
    from tests.test_fundamentals_n7_baseline import sample as plan_sample
    factors,old=plan_sample(7)
    kw=dict(cutoffs=old["cutoffs"],budget_cny=1024,unit_cny=2,
            payout_factor=.65,allocation_seed=422,max_uses=2)
    plan=build_comparison_plan(factors,**kw)
    with pytest.raises(ValueError,match="issue identity"):
        build_comparison_plan(factors.assign(issue="other"),fixed_plan=plan,**kw)
    wrong={str(s):Cutoff.decision_epoch(plan["issue"],"2011-01-01T00:00:00Z") for s in factors.slot}
    with pytest.raises(ValueError,match="cutoffs"):
        build_comparison_plan(factors,fixed_plan=plan,**{**kw,"cutoffs":wrong})
    with pytest.raises(ValueError,match="fixture identity"):
        build_comparison_plan(factors.assign(provider_id="wrong"),fixed_plan=plan,**kw)

def test_issue_partitions_reject_unimplemented_recency(sample):
    f,p,b,h,a=sample
    kw=kwargs(Cutoff.decision_epoch("000026","2010-01-27T00:00:00Z"),"GLOBAL")
    kw["weighting_policy"]=WeightingPolicy.recent_state_blend(2,.6,minimum_ess=4)
    with pytest.raises(TemporalContractError,match="EXPANDING_EQUAL"):
        fit_remapper(f,p,b,h,a,**kw)
