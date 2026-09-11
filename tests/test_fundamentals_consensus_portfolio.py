import copy
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_consensus_portfolio import consensus_component, consensus_portfolios
from src.fundamentals_n7_twocover import settle_n7_twocover


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


def test_role_pair_complete_complement_and_settlement(inputs):
    f,cuts=inputs;f=f.iloc[:7];cuts={str(i):cuts[str(i)] for i in f.slot}
    roles={i:("A" if i<3 else "D" if i<7 else "C") for i in range(1,8)}
    before=f.copy(deep=True)
    plans=[consensus_component(f,roles,cutoffs=cuts,complement=b,unit_cny=2,payout_factor=.65,seed=0) for b in (False,True)]
    assert [p["stake"] for p in plans]==[64,32]
    assert Counter(len(r["support"]) for r in plans[0]["legs"])=={1:2,2:5}
    for a,b in zip(plans[0]["legs"],plans[1]["legs"]):
        if a["role"]=="C":
            assert set(a["support"]).isdisjoint(b["support"])
            assert set(a["support"]+b["support"])==set("310")
        else:assert a["support"]==b["support"]
    env=dict(issue="001",strategy="PAIR",funding="UNIT",stake=96,budget=96,model_any_hit=None,components=plans)
    env["seal"]=stable_json_hash(env)
    for direction in "WDL":
        audit=f[["issue","slot","provider_id","handicap"]].copy()
        audit["actual_direction"]="W";audit.loc[audit.slot==7,"actual_direction"]=direction
        audit["status"]="READY";audit["spf_sp"]=2.
        s=settle_n7_twocover(env,audit)
        assert s["hits"]==1 and s["gross"]==pytest.approx(2*.65*2**7)
        audit.loc[audit.slot==1,"actual_direction"]="L"
        assert settle_n7_twocover(env,audit)["hits"]==0
    pd.testing.assert_frame_equal(before,f)
    with pytest.raises(ValueError):consensus_component(f,roles,cutoffs={},complement=False,unit_cny=2,payout_factor=.65,seed=0)
    with pytest.raises(ValueError):consensus_component(f,{i:"A" for i in range(1,8)},cutoffs=cuts,complement=False,unit_cny=2,payout_factor=.65,seed=0)


def test_budget_roles_caps_prefix_and_no_labels(inputs):
    f,cuts=inputs
    kw=dict(cutoffs=cuts,budget_cny=256,minimum_anchor_market=.5,skeleton_max_uses=3,
            skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    z=consensus_portfolios(f,**kw)
    assert z==consensus_portfolios(f,**kw)
    assert len(z["skeletons"])==4
    assert z["plans"]["PRIMARY_FILL"]["stake"]==256
    assert z["plans"]["COMPLEMENT"]["stake"]==256
    assert z["plans"]["MATCHED_PRIMARY"]["stake"]==192
    paired=z["plans"]["COMPLEMENT"]["components"];matched=z["plans"]["MATCHED_PRIMARY"]["components"]
    assert [p for p in paired if not p["complement"]]==matched
    for a in z["skeletons"]:
        assert Counter(a.values())=={"A":2,"D":4,"C":1}
    assert max(Counter(s for g in z["skeletons"] for s in g).values())<=3
    for i,a in enumerate(z["skeletons"]):
        assert all(len(set(a)&set(b))<=5 for b in z["skeletons"][:i])
    assert all(p["stake"]+p["cash_cny"]==256 for p in z["plans"].values())
    with pytest.raises(ValueError):consensus_portfolios(f.assign(actual_direction="W"),**kw)
    with pytest.raises(ValueError):consensus_portfolios(f,**dict(kw,minimum_anchor_market=1))
    bad=copy.deepcopy(cuts);bad["1"]=Cutoff.decision_epoch("002","2010-01-01T00:00:00Z")
    with pytest.raises(ValueError):consensus_portfolios(f,**dict(kw,cutoffs=bad))


def test_insufficient_pool_and_budget_hold_cash(inputs):
    f,cuts=inputs
    kw=dict(cutoffs=cuts,budget_cny=1024,minimum_anchor_market=.99,skeleton_max_uses=3,
            skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    z=consensus_portfolios(f,**kw)
    assert z["skeletons"]==[]
    assert all(p["stake"]==0 and p["cash_cny"]==1024 for p in z["plans"].values())
    z=consensus_portfolios(f,**dict(kw,minimum_anchor_market=.5,budget_cny=32))
    assert all(p["stake"]==0 for p in z["plans"].values())


def test_solver_failure_is_not_infeasibility(inputs,monkeypatch):
    from types import SimpleNamespace
    import src.fundamentals_consensus_portfolio as module
    monkeypatch.setattr(module,"milp",lambda *a,**k:SimpleNamespace(status=1,message="time limit"))
    f,cuts=inputs
    with pytest.raises(RuntimeError,match="prove"):
        consensus_portfolios(f,cutoffs=cuts,budget_cny=1024,minimum_anchor_market=.5,
                             skeleton_max_uses=3,skeleton_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)

def test_archived_report_fixture_restores_with_verified_hashes(tmp_path):
    import gzip
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/consensus_converter.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    result=json.loads(saved["files"]["results.json"])
    assert len(result["rows"])==192 and len(result["issue_order"])==48
    assert {r["policy"] for r in result["rows"]}=={"COMPLEMENT","MATCHED_PRIMARY","PRIMARY_FILL","OLD_D2_U6_P5"}
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture","tests/fixtures/consensus_converter.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==result
    assert json.loads((out/"archive.json").read_text())["mode"]=="ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY"

def test_frozen_report_binds_upstream_audit_pointer(tmp_path):
    import gzip
    import json
    from pathlib import Path
    from src.fundamentals_clean_receipts import verify_clean_file_bindings
    saved=json.loads(gzip.decompress(Path("tests/fixtures/consensus_converter.json.gz").read_bytes()))
    wrapper=json.loads(saved["files"]["plans-frozen.json"])
    receipt=json.loads(wrapper["canonical_json"])
    paths=[p for p in receipt["source_hashes"] if p.endswith("cap-depth-grid-v1/plans-frozen.json")]
    assert len(paths)==1
    # A changed post-freeze audit pointer must fail verification before labels load.
    changed=tmp_path/"plans-frozen.json"
    changed.write_text('{"source_hashes":{"different-audit.json":"changed"}}')
    with pytest.raises(ValueError):
        verify_clean_file_bindings({str(changed):receipt["source_hashes"][paths[0]]},repository_root=tmp_path)

@pytest.mark.parametrize("fraction",[0,.25,.5,.75,1])
def test_independent_converter_budget_and_actual_group_caps(inputs,fraction):
    from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
    f,cuts=inputs
    kw=dict(cutoffs=cuts,conversion_budget_fraction=fraction,budget_cny=256,
            minimum_anchor_market=.5,max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    plan=independent_consensus_portfolio(f,**kw)
    assert plan==independent_consensus_portfolio(f,**kw)
    assert plan["stake"]+plan["cash_cny"]==256
    assert plan["allocation"]["converter_spend_cny"]<=256*fraction
    assert plan["allocation"]["primary_spend_cny"]<=256*(1-fraction)
    groups=[{r["slot"] for r in p["legs"]} for p in plan["components"]]
    assert max(Counter(s for g in groups for s in g).values(),default=0)<=6
    assert all(len(a&b)<=5 for i,a in enumerate(groups) for b in groups[:i])
    for p in plan["components"]:
        assert p["stake"]==(32 if p["complement"] else 64)
        assert sum(len(r["support"])==1 for r in p["legs"])==(3 if p["complement"] else 2)
    if fraction==0:assert all(not p["complement"] for p in plan["components"])
    if fraction==1:assert all(p["complement"] for p in plan["components"])


def test_candidates_converter_ranks_actual_omitted_market_direction(inputs):
    from src.fundamentals_consensus_portfolio import consensus_candidates
    import numpy as np
    f,cuts=inputs
    a,_,ea,oa=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=False)
    b,_,eb,ob=consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=.5,converter_market=True)
    assert np.array_equal(ea,eb) and np.allclose(oa[:,:2],ob[:,:2])
    # Converter row7 baseline Top2=.8 versus omitted market L=.5.
    assert oa[6,2]==pytest.approx(-np.log(.8)+1e-10*20)
    assert ob[6,2]==pytest.approx(-np.log(.5)+1e-10*20)
    with pytest.raises(ValueError):consensus_candidates(f,cutoffs=cuts,minimum_anchor_market=0,converter_market=True)


def test_independent_converter_more_groups_and_failed_contracts(inputs):
    from src.fundamentals_consensus_portfolio import independent_consensus_portfolio, next_consensus_roles
    f,cuts=inputs
    kw=dict(cutoffs=cuts,budget_cny=256,minimum_anchor_market=.5,max_uses=6,
            max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0)
    primary=independent_consensus_portfolio(f,conversion_budget_fraction=0,**kw)
    convert=independent_consensus_portfolio(f,conversion_budget_fraction=1,**kw)
    assert len(convert["components"])>len(primary["components"])
    assert convert["stake"]<=256
    with pytest.raises(ValueError):independent_consensus_portfolio(f.assign(actual_direction="W"),conversion_budget_fraction=.5,**kw)
    with pytest.raises(ValueError):independent_consensus_portfolio(f,conversion_budget_fraction=.3,**kw)
    with pytest.raises(ValueError):next_consensus_roles(f,[{1:"A"}],cutoffs=cuts,minimum_anchor_market=.5,
        converter_market=False,max_uses=6,max_overlap=5,disjoint=False)
    with pytest.raises(ValueError):next_consensus_roles(f,[],cutoffs=cuts,minimum_anchor_market=.5,
        converter_market=False,max_uses=0,max_overlap=5,disjoint=False)
    empty=independent_consensus_portfolio(f,conversion_budget_fraction=.5,**dict(kw,minimum_anchor_market=.99))
    assert empty["components"]==[] and empty["cash_cny"]==256

def test_independent_archive_fixture_and_reference_scope(tmp_path):
    import gzip
    import hashlib
    import json
    import subprocess
    import sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/independent_converter.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    result=json.loads(saved["files"]["results.json"])
    assert result["design"]=="independent" and len(result["rows"])==384
    assert len({r["policy"] for r in result["rows"]})==8
    assert all(r["stake"]+r["cash_cny"]==1024 for r in result["rows"])
    out=tmp_path/"independent-archive"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture","tests/fixtures/independent_converter.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==result
