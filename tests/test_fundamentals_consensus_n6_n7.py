"""N6 extension contracts; original N7 behavior is exercised in existing tests."""
import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio, consensus_component, next_consensus_roles
from src.fundamentals_n7_twocover import settle_n7_twocover


@pytest.mark.parametrize("n", [6,7])
@pytest.mark.parametrize("uses", [3,6])
def test_size_caps_cartesian_settlement_and_inputs(n, uses):
    rows=[]
    for i in range(24):
        p,q=((.7,.2,.1),(.65,.25,.1)) if i%6<2 else (
            ((.4,.35,.25),(.4,.35,.25)) if i%6<5 else ((.45,.35,.2),(.3,.2,.5)))
        rows.append(dict(issue="001",slot=i+1,provider_id=str(i+1),handicap=-1,
            **dict(zip(["p_W","p_D","p_L"],p)),**dict(zip(["q_W","q_D","q_L"],q))))
    frame=pd.DataFrame(rows)
    cuts={str(s):Cutoff.decision_epoch("001","2010-01-01T00:00:00Z") for s in frame.slot}
    kw=dict(cutoffs=cuts,conversion_budget_fraction=0,budget_cny=1024,
        minimum_anchor_market=.5,max_uses=uses,max_pair_overlap=5,
        unit_cny=2,payout_factor=.65,seed=0,group_size=n)
    plan=independent_consensus_portfolio(frame,**kw)
    assert plan==independent_consensus_portfolio(frame,**kw)
    cost=2*2**(n-2)
    assert plan["stake"]==cost*len(plan["components"]) and plan["stake"]+plan["cash_cny"]==1024
    groups=[set(l["slot"] for l in c["legs"]) for c in plan["components"]]
    assert max(Counter(s for g in groups for s in g).values())<=uses
    assert all(len(a&b)<=5 for a,b in itertools.combinations(groups,2))
    for c in plan["components"]:
        assert c["n"]==n and len(c["legs"])==n and c["stake"]==cost
        assert Counter(l["role"] for l in c["legs"])==dict(A=2,D=n-3,C=1)
        assert sum(len(l["support"])==1 for l in c["legs"])==2
        assert {t["code"] for t in c["tickets"]}=={"".join(t) for t in itertools.product(*(l["support"] for l in c["legs"]))}
    audit=frame[["issue","slot","provider_id","handicap"]].assign(actual_direction="W",status="READY",spf_sp=2.)
    got=settle_n7_twocover(plan,audit)
    assert got["hits"]==len(groups)
    assert got["gross"]==pytest.approx(len(groups)*2*.65*2**n)
    audit["actual_direction"]="L"
    assert settle_n7_twocover(plan,audit)["hits"]==0
    # Labels cannot influence selection; incorrect chronology cannot enter.
    with pytest.raises(ValueError):independent_consensus_portfolio(frame.assign(actual_direction="W"),**kw)
    with pytest.raises(ValueError):independent_consensus_portfolio(frame,**dict(kw,cutoffs={}))
    with pytest.raises(ValueError):independent_consensus_portfolio(frame,**dict(kw,group_size=5))
    empty=independent_consensus_portfolio(frame,**dict(kw,minimum_anchor_market=.99))
    assert empty["stake"]==0 and empty["cash_cny"]==1024
    with pytest.raises(ValueError):
        next_consensus_roles(frame,[{1:"A"}],cutoffs=cuts,minimum_anchor_market=.5,
            converter_market=False,max_uses=uses,max_overlap=5,disjoint=False,group_size=n)
    for fraction in (.5,1):
        alt=independent_consensus_portfolio(frame,**dict(kw,conversion_budget_fraction=fraction))
        assert alt["stake"]+alt["cash_cny"]==1024
        assert all(c["stake"]==cost//(2 if c["complement"] else 1) for c in alt["components"])
    c=plan["components"][0]
    subset=frame[frame.slot.isin(groups[0])]
    rolemap={l["slot"]:l["role"] for l in c["legs"]}
    with pytest.raises(ValueError):
        consensus_component(subset,rolemap,cutoffs={str(s):cuts[str(s)] for s in subset.slot},
            complement=False,unit_cny=2,payout_factor=.65,seed=0,group_size=13)

def test_portable_archive_hashes_and_restore(tmp_path):
    import gzip,hashlib,json,subprocess,sys
    from pathlib import Path
    saved=json.loads(gzip.decompress(Path("tests/fixtures/consensus_n6_n7.json.gz").read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==saved["hashes"][k] for k,v in saved["files"].items())
    result=json.loads(saved["files"]["results.json"])
    assert len(result["rows"])==192 and len(result["issue_order"])==48
    assert {r["policy"] for r in result["rows"]}=={"N6_U3","N6_U6","N7_U3","N7_U6"}
    assert all(r["stake"]+r["cash_cny"]==1024 for r in result["rows"])
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",
        "tests/fixtures/consensus_n6_n7.json.gz","--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==result
