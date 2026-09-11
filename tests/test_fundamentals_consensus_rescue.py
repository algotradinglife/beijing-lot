import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_consensus_portfolio import consensus_candidates, independent_consensus_portfolio

@pytest.fixture
def inputs():
    rows=[]
    for i in range(1,22):
        role=(i-1)%7
        p,q=((.7,.2,.1),(.65,.25,.1)) if role<2 else (
            ((.4,.35,.25),(.4,.35,.25)) if role<6 else ((.45,.35,.2),(.3,.2,.5)))
        rows.append(dict(issue="001",slot=i,provider_id=str(i),handicap=0,
                         **dict(zip(["p_W","p_D","p_L"],p)),**dict(zip(["q_W","q_D","q_L"],q))))
    f=pd.DataFrame(rows)
    cuts={str(i):Cutoff.decision_epoch("001","2010-01-01T00:00:00Z") for i in f.slot}
    return f,cuts



def test_retention_uses_actual_baseline_double_and_preserves_eligibility(inputs):
    f,cuts=inputs
    # Eligible A with different second direction: baseline W,D; market W,L.
    f.loc[f.slot==1,["p_W","p_D","p_L"]]=[.6,.3,.1]
    f.loc[f.slot==1,["q_W","q_D","q_L"]]=[.6,.1,.3]
    _,_,e,a=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False)
    _,_,e2,b=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False,anchor_score="RETENTION")
    assert np.array_equal(e,e2) and np.array_equal(a[:,1:],b[:,1:])
    assert b[0,0]==pytest.approx(-np.log(.6/.7))
    assert a[0,0]==pytest.approx(-np.log(.6))
    kw=dict(cutoffs=cuts,conversion_budget_fraction=0,budget_cny=1024,minimum_anchor_market=.5,
        max_uses=3,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0,group_size=7)
    plan=independent_consensus_portfolio(f,anchor_score="RETENTION",**kw)
    assert plan==independent_consensus_portfolio(f,anchor_score="RETENTION",**kw)
    assert plan["parameters"]["anchor_score"]=="RETENTION"
    assert plan["stake"]+plan["cash_cny"]==1024
    assert all(sum(l["role"]=="A" for l in p["legs"])==2 for p in plan["components"])
    with pytest.raises(ValueError):independent_consensus_portfolio(f,anchor_score="BAD",**kw)
    with pytest.raises(ValueError):independent_consensus_portfolio(f.assign(actual_direction="W"),anchor_score="RETENTION",**kw)
    with pytest.raises(ValueError):independent_consensus_portfolio(f,anchor_score="RETENTION",**dict(kw,cutoffs={}))

def test_archive_cohort_and_integrity(tmp_path):
    import gzip,hashlib,json,subprocess,sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/consensus_rescue.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    r=json.loads(saved["files"]["results.json"])
    assert len(r["rows"])==384 and len(r["issue_order"])==48
    assert len({x["policy"] for x in r["rows"]})==8
    assert all(x["stake"]+x["cash_cny"]==1024 for x in r["rows"])
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",
        "tests/fixtures/consensus_rescue.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==r
