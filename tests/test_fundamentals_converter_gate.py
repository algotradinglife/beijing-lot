import copy
import pytest
from tests.test_fundamentals_consensus_portfolio import inputs
from src.fundamentals_consensus_portfolio import consensus_portfolios
from src.fundamentals_converter_gate import gate_zero_converter

@pytest.mark.parametrize("handicap",[-1,0,1])
def test_gate_preserves_originals_and_cash(inputs,handicap):
    f,cuts=inputs
    f=f.assign(handicap=handicap)
    plan=consensus_portfolios(f,cutoffs=cuts,budget_cny=256,minimum_anchor_market=.5,
        skeleton_max_uses=3,skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)["plans"]["COMPLEMENT"]
    before=copy.deepcopy(plan)
    all_plan=gate_zero_converter(plan,f,cutoffs=cuts,zero_only=False,budget_cny=256)
    z=gate_zero_converter(plan,f,cutoffs=cuts,zero_only=True,budget_cny=256)
    assert all_plan["components"]==plan["components"]
    expected=[p for p in plan["components"] if not p["complement"] or handicap==0]
    assert z["components"]==expected
    assert z["stake"]+z["cash_cny"]==256
    assert plan==before
    with pytest.raises(ValueError):
        gate_zero_converter(plan,f,cutoffs={},zero_only=True,budget_cny=256)
    with pytest.raises(ValueError):
        gate_zero_converter(plan,f.assign(handicap=2),cutoffs=cuts,zero_only=True,budget_cny=256)
    with pytest.raises(ValueError):
        gate_zero_converter(plan,f.assign(actual_direction="W"),cutoffs=cuts,zero_only=True,budget_cny=256)
    bad=copy.deepcopy(plan);bad["stake"]+=2
    with pytest.raises(ValueError):
        gate_zero_converter(bad,f,cutoffs=cuts,zero_only=True,budget_cny=256)

def test_empty_plan_and_invalid_budget(inputs):
    f,cuts=inputs
    plan=consensus_portfolios(f,cutoffs=cuts,budget_cny=32,minimum_anchor_market=.5,
        skeleton_max_uses=3,skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)["plans"]["COMPLEMENT"]
    z=gate_zero_converter(plan,f,cutoffs=cuts,zero_only=True,budget_cny=32)
    assert z["components"]==[] and z["cash_cny"]==32
    with pytest.raises(ValueError):
        gate_zero_converter(plan,f,cutoffs=cuts,zero_only=True,budget_cny=1024)

def test_mixed_handicaps_only_converter_leg_matters(inputs):
    f,cuts=inputs
    f.loc[f.slot%7==0,"handicap"]=1
    f.loc[f.slot==7,"handicap"]=0
    plan=consensus_portfolios(f,cutoffs=cuts,budget_cny=256,minimum_anchor_market=.5,
        skeleton_max_uses=3,skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)["plans"]["COMPLEMENT"]
    z=gate_zero_converter(plan,f,cutoffs=cuts,zero_only=True,budget_cny=256)
    for p in z["components"]:
        if p["complement"]:
            assert next(l for l in p["legs"] if l["role"]=="C")["handicap"]==0
    assert len(z["components"])<len(plan["components"])

def test_portable_report_fixture(tmp_path):
    import gzip
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    fixture=Path("tests/fixtures/zero_converter.json.gz")
    z=json.loads(gzip.decompress(fixture.read_bytes()))
    assert set(z["files"])=={"results.json","plans-frozen.json"}
    assert all(hashlib.sha256(body.encode()).hexdigest()==z["hashes"][name] for name,body in z["files"].items())
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",str(fixture),"--output",str(out)],check=True)
    result=json.loads((out/"results.json").read_text())
    assert len(result["rows"])==576
    rows={(r["issue"],r["policy"]):r for r in result["rows"]}
    for issue in result["issue_order"]:
        for base in ["COMPLEMENT","INDEPENDENT_C000","INDEPENDENT_C025","INDEPENDENT_C050","INDEPENDENT_C075","INDEPENDENT_C100"]:
            a=rows[issue,base+"_ALL"];b=rows[issue,base+"_ZERO"]
            assert b["stake"]<=a["stake"] and b["hits"]<=a["hits"]
            assert b["stake"]+b["cash_cny"]==1024
