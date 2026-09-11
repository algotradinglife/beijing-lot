from collections import Counter
import pytest
from tests.test_fundamentals_consensus_portfolio import inputs
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio, next_consensus_roles


def test_unique_singles_preserve_two_per_group_and_budget(inputs):
    f,cuts=inputs
    kw=dict(cutoffs=cuts,conversion_budget_fraction=0,budget_cny=1024,
        minimum_anchor_market=.5,max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=41902)
    baseline=independent_consensus_portfolio(f,**kw)
    capped=independent_consensus_portfolio(f,**kw,anchor_max_uses=1)
    counts=Counter(l["slot"] for p in capped["components"] for l in p["legs"] if len(l["support"])==1)
    assert len(capped["components"])==3 and max(counts.values())==1
    assert len(baseline["components"])>len(capped["components"])
    assert all(sum(len(l["support"])==1 for l in p["legs"])==2 for p in capped["components"])
    assert capped["stake"]==192 and capped["cash_cny"]==832
    assert independent_consensus_portfolio(f,**kw,anchor_max_uses=6)["components"]==baseline["components"]
    for cap in (0,7,True):
        with pytest.raises(ValueError):independent_consensus_portfolio(f,**kw,anchor_max_uses=cap)
    with pytest.raises(ValueError):
        independent_consensus_portfolio(f,**dict(kw,conversion_budget_fraction=.25),anchor_max_uses=1)


def test_used_single_can_be_reused_as_double(inputs):
    f,cuts=inputs
    previous={1:"A",2:"A",3:"D",4:"D",5:"D",6:"D",7:"C"}
    kw=dict(cutoffs=cuts,minimum_anchor_market=.5,converter_market=False,
        max_uses=6,max_overlap=5,disjoint=False,anchor_max_uses=1)
    roles,_=next_consensus_roles(f,[previous],**kw)
    assert roles[1]=="D" and roles[2]=="D"
    assert all(roles.get(s)!="A" for s in (1,2))
    assert Counter(roles.values())==Counter(A=2,D=4,C=1)
    with pytest.raises(ValueError):next_consensus_roles(f,[list(previous)],**kw)
    with pytest.raises(ValueError):next_consensus_roles(f,[previous,previous],**kw)

def test_unique_single_report_archive(tmp_path):
    import gzip,json,hashlib,subprocess,sys
    from pathlib import Path
    fixture=Path("tests/fixtures/unique_single.json.gz")
    z=json.loads(gzip.decompress(fixture.read_bytes()))
    assert all(hashlib.sha256(body.encode()).hexdigest()==z["hashes"][name] for name,body in z["files"].items())
    out=tmp_path/"archive"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",str(fixture),"--output",str(out)],check=True)
    v=json.loads((out/"results.json").read_text())
    rows=[r for r in v["rows"] if r["policy"]=="INDEPENDENT_C000"]
    assert len(rows)==48 and sum(r["groups"] for r in rows)==127
    assert all(r["stake"]+r["cash_cny"]==1024 for r in rows)
    single_counts=Counter((l["issue"],l["slot"]) for l in v["legs"] if len(l["support"])==1)
    assert max(single_counts.values())==1
    groups=Counter((l["issue"],l["component"]) for l in v["legs"] if len(l["support"])==1)
    assert len(groups)==127 and set(groups.values())=={2}
