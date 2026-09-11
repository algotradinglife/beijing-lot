import copy
import pytest
from tests.test_fundamentals_consensus_portfolio import inputs
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
from src.fundamentals_within_group_singles import reselect_group_singles

@pytest.mark.parametrize("policy,w",[("RETENTION_P",0),("RETENTION_Q",1),("RETENTION_MIX",.5)])
def test_fixed_retention_ranking_and_no_mutation(inputs,policy,w):
    f,cuts=inputs
    f.loc[f.slot==1,["p_W","p_D","p_L","q_W","q_D","q_L"]]=[.55,.4,.05,.7,.2,.1]
    f.loc[f.slot==2,["p_W","p_D","p_L","q_W","q_D","q_L"]]=[.8,.15,.05,.55,.35,.1]
    f.loc[f.slot==3,["p_W","p_D","p_L","q_W","q_D","q_L"]]=[.65,.2,.15,.6,.35,.05]
    kw=dict(cutoffs=cuts,conversion_budget_fraction=0,budget_cny=256,minimum_anchor_market=.5,
        max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    source=independent_consensus_portfolio(f,**kw);before=copy.deepcopy(source)
    z=reselect_group_singles(source,f,cutoffs=cuts,policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)
    assert source==before and z["stake"]==source["stake"] and z["cash_cny"]==source["cash_cny"]
    for a,b in zip(source["components"],z["components"]):
        assert [l["slot"] for l in a["legs"]]==[l["slot"] for l in b["legs"]]
        expected=[]
        for l in a["legs"]:
            p=sorted("WDL",key=lambda d:(-l["p_"+d],"WDL".index(d)))
            q=sorted("WDL",key=lambda d:(-l["q_"+d],"WDL".index(d)))
            if p[0]!=q[0] or l["q_"+q[0]]<.5:continue
            mass={d:(1-w)*l["p_"+d]+w*l["q_"+d] for d in "WDL"}
            expected.append((-mass[p[0]]/sum(mass[d] for d in p[:2]),l["slot"]))
        selected={s for _,s in sorted(expected)[:2]}
        assert {l["slot"] for l in b["legs"] if len(l["support"])==1}==selected
        assert len(b["tickets"])==32
    with pytest.raises(ValueError):reselect_group_singles(source,f.assign(actual_direction="W"),cutoffs=cuts,policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)

def test_insufficient_qualified_singles_fails(inputs):
    f,cuts=inputs
    f[["q_W","q_D","q_L"]]=[.45,.35,.2]
    source=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,budget_cny=256,
        minimum_anchor_market=.3,max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    # Introduce a C candidate, since otherwise the original planner has no groups.
    f.loc[f.slot==7,["q_W","q_D","q_L"]]=[.35,.2,.45]
    source=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,budget_cny=256,
        minimum_anchor_market=.3,max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    assert source["components"]
    with pytest.raises(ValueError,match="eligible"):
        reselect_group_singles(source,f,cutoffs=cuts,policy="RETENTION_P",budget_cny=256,unit_cny=2,payout_factor=.65)

def test_fixed_group_archive_preserves_exposure(tmp_path):
    import gzip,hashlib,json,subprocess,sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/fixed_group_retention.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    r=json.loads(saved["files"]["results.json"])
    assert len(r["rows"])==384 and len(r["issue_order"])==48
    for issue in r["issue_order"]:
        for uses in (3,6):
            rows=[x for x in r["rows"] if x["issue"]==issue and x["uses"]==uses]
            assert len(rows)==4 and len({(x["groups"],x["stake"],x["cash_cny"]) for x in rows})==1
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",
        "tests/fixtures/fixed_group_retention.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==r
