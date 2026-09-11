import numpy as np
import pytest
from tests.test_fundamentals_consensus_portfolio import inputs
from src.fundamentals_consensus_portfolio import consensus_candidates,independent_consensus_portfolio

def test_anchor_allowlist_only_changes_single_eligibility(inputs):
    f,cuts=inputs;allow=[1,2]
    _,_,a,o=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False)
    _,_,b,o2=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False,anchor_slots=allow)
    assert np.array_equal(a[:,1:],b[:,1:]) and np.array_equal(o,o2)
    assert b[:,0].sum()==2 and b[0,0]==b[1,0]==1
    kw=dict(cutoffs=cuts,conversion_budget_fraction=0,budget_cny=256,minimum_anchor_market=.5,
        max_uses=3,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    z=independent_consensus_portfolio(f,anchor_slots=allow,**kw)
    assert z==independent_consensus_portfolio(f,anchor_slots=allow,**kw)
    assert z["components"] and z["stake"]+z["cash_cny"]==256
    for part in z["components"]:
        assert {l["slot"] for l in part["legs"] if l["role"]=="A"}==set(allow)
        assert any(l["slot"] not in allow for l in part["legs"] if l["role"]!="A")
    empty=independent_consensus_portfolio(f,anchor_slots=[],**kw)
    assert empty["components"]==[] and empty["cash_cny"]==256
    for bad in ([999],[1,1],["1"],True):
        with pytest.raises(ValueError):independent_consensus_portfolio(f,anchor_slots=bad,**dict(kw,budget_cny=0))
    with pytest.raises(ValueError):independent_consensus_portfolio(f.assign(actual_direction="W"),anchor_slots=allow,**kw)

def test_mainstream_archive_contract(tmp_path):
    import gzip,hashlib,json,subprocess,sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/mainstream_singles.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    r=json.loads(saved["files"]["results.json"])
    assert len(r["rows"])==192 and len(r["issue_order"])==48
    assert set(r["allowed_competitions"])=={"英超","西甲","德甲","意甲","法甲","葡超","荷甲"}
    assert all(x["stake"]+x["cash_cny"]==1024 for x in r["rows"])
    features={(x["issue"],x["slot"],x["provider_id"]):x for x in r["features"]}
    assert all(features[l["issue"],l["slot"],l["provider_id"]]["competition"] in r["allowed_competitions"]
        for l in r["legs"] if l["policy"].endswith("MAINSTREAM") and l["role"]=="A")
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",
        "tests/fixtures/mainstream_singles.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==r
