import copy
import pytest
from tests.test_fundamentals_consensus_portfolio import inputs
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
from src.fundamentals_within_group_singles import reselect_group_singles

@pytest.mark.parametrize("policy",["MARKET","VALUE"])
def test_exact_two_singles_same_groups_and_market_direction(inputs,policy):
    f,cuts=inputs
    source=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,
        budget_cny=256,minimum_anchor_market=.5,max_uses=6,max_pair_overlap=5,
        unit_cny=2,payout_factor=.65,seed=0)
    before=copy.deepcopy(source)
    z=reselect_group_singles(source,f,cutoffs=cuts,policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)
    assert source==before and z["stake"]==source["stake"] and z["cash_cny"]==source["cash_cny"]
    for a,b in zip(source["components"],z["components"]):
        assert [l["slot"] for l in a["legs"]]==[l["slot"] for l in b["legs"]]
        assert sorted(map(len,[l["support"] for l in b["legs"]]))==[1,1,2,2,2,2,2]
        assert len(b["tickets"])==32 and all(t["units"]==1 for t in b["tickets"])
        expected=[]
        for l in b["legs"]:
            d=min("WDL",key=lambda d:(-l["q_"+d],"WDL".index(d)))
            score=l["q_"+d] if policy=="MARKET" else l["p_"+d]/l["q_"+d]
            expected.append((-score,l["slot"],"310"["WDL".index(d)]))
        selected={s:d for _,s,d in sorted(expected)[:2]}
        assert {l["slot"]:l["support"] for l in b["legs"] if len(l["support"])==1}==selected
    if policy=="VALUE":
        assert any(l["original_role"]!="A" and len(l["support"])==1 for p in z["components"] for l in p["legs"])
    for bad in ("BAD",None):
        with pytest.raises(ValueError):reselect_group_singles(source,f,cutoffs=cuts,policy=bad,budget_cny=256,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):reselect_group_singles(source,f.assign(spf_sp=2),cutoffs=cuts,policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):reselect_group_singles(source,f,cutoffs={},policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)
    source["stake"]+=2
    with pytest.raises(ValueError):reselect_group_singles(source,f,cutoffs=cuts,policy=policy,budget_cny=256,unit_cny=2,payout_factor=.65)

def test_empty_source_retains_cash(inputs):
    f,cuts=inputs
    source=independent_consensus_portfolio(f,cutoffs=cuts,conversion_budget_fraction=0,
        budget_cny=256,minimum_anchor_market=.99,max_uses=6,max_pair_overlap=5,
        unit_cny=2,payout_factor=.65,seed=0)
    z=reselect_group_singles(source,f,cutoffs=cuts,policy="MARKET",budget_cny=256,unit_cny=2,payout_factor=.65)
    assert z["components"]==[] and z["stake"]==0 and z["cash_cny"]==256


def test_portable_same_exposure_fixture(tmp_path):
    import gzip,json,hashlib,subprocess,sys
    from pathlib import Path
    fixture=Path("tests/fixtures/within_group_singles.json.gz")
    saved=json.loads(gzip.decompress(fixture.read_bytes()))
    assert all(hashlib.sha256(body.encode()).hexdigest()==saved["hashes"][n] for n,body in saved["files"].items())
    out=tmp_path/"restore"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",str(fixture),"--output",str(out)],check=True)
    v=json.loads((out/"results.json").read_text())
    assert len(v["rows"])==144
    for issue in v["issue_order"]:
        rows=[r for r in v["rows"] if r["issue"]==issue]
        assert len(rows)==3 and len({(r["groups"],r["stake"],r["cash_cny"]) for r in rows})==1
