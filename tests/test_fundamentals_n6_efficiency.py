import copy
import itertools
import math
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_n6_efficiency import n6_efficiency_catalog,n6_efficiency_plan


@pytest.fixture
def source():
    groups=[list(range(1,7)),[1,2,3,4,5,7],list(range(8,14))]
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for s in range(1,14)}
    legs=[];tickets=[]
    for g,slots in enumerate(groups,1):
        current=[]
        for j,s in enumerate(slots):
            l=dict(issue='001',slot=s,provider_id=str(s),handicap=0,group=g,
                p_W=.7,p_D=.2,p_L=.1,q_W=.7,q_D=.2,q_L=.1,
                decision_probabilities=[.7,.2,.1],support='3' if j==0 else '31')
            current.append(l);legs.append(l)
        tickets.extend(dict(group=g,code=''.join(c),units=1) for c in itertools.product(*(l['support'] for l in current)))
    body=dict(issue='001',cutoffs={s:c.cutoff_ts.isoformat() for s,c in cuts.items()},
        input_sha256='a'*64,unit_cny=2,payout_factor=.65,market_weight=.5,groups=3,
        stake=192,cash_cny=832,budget_cny=1024,legs=legs,tickets=tickets,
        selector='FIXED',shape='N6_C1_RETENTION',funding='UNIT')
    plan=dict(**body,seal=stable_json_hash(body))
    return plan,cuts


def test_catalog_shared_scenarios_and_price_neutrality(source):
    plan,cuts=source;original=copy.deepcopy(plan)
    cat=n6_efficiency_catalog(plan,cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=106,scenario_draws=8192)
    assert plan==original
    assert cat==n6_efficiency_catalog(plan,cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=106,scenario_draws=8192)
    # When model equals price-implied q all full groups have exactly -35% EV.
    assert all(m['expected_net']==pytest.approx(-.35*64) for m in cat['metrics'])
    assert all(m['probability']==pytest.approx(.7*.9**5) for m in cat['metrics'])
    kw=dict(cutoffs=cuts,spend_cap_cny=128,budget_cny=1024,unit_cny=2,payout_factor=.65)
    chosen=n6_efficiency_plan(cat,method='MARGINAL',**kw)
    assert 3 in chosen['selected_source_groups'] and len(chosen['selected_source_groups'])==2
    assert n6_efficiency_plan(cat,method='PROBABILITY',**kw)['selected_source_groups']==[1,2]
    assert n6_efficiency_plan(cat,method='EXPECTED_NET',**kw)['selected_source_groups']==[1,2]


@pytest.mark.parametrize('method',['ORIGINAL','EXTRA_PROB','EXTRA_VALUE','PROBABILITY','MARGINAL','EXPECTED_NET'])
def test_plans_are_subsets_with_complete_tickets_and_cash(source,method):
    plan,cuts=source
    cat=n6_efficiency_catalog(plan,cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=106,scenario_draws=257)
    frozen=copy.deepcopy(cat)
    z=n6_efficiency_plan(cat,cutoffs=cuts,method=method,spend_cap_cny=1024,budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert cat==frozen
    shape=z['shape_plan'];extra=method.startswith('EXTRA_')
    assert shape['groups']==3 and shape['stake']==(96 if extra else 192)
    assert shape['stake']+shape['cash_cny']==1024
    assert shape['seal']==stable_json_hash({k:v for k,v in shape.items() if k!='seal'})
    for g,s in enumerate(z['selected_source_groups'],1):
        legs=[l for l in shape['legs'] if l['group']==g]
        old=[l for l in plan['legs'] if l['group']==s]
        assert [l['slot'] for l in legs]==[l['slot'] for l in old]
        assert all(set(l['support'])<=set(o['support']) for l,o in zip(legs,old))
        assert sum(len(l['support'])==1 for l in legs)==(2 if extra else 1)
        assert {t['code'] for t in shape['tickets'] if t['group']==g}=={
            ''.join(c) for c in itertools.product(*(l['support'] for l in legs))}
    if method=='ORIGINAL':
        assert shape['legs']==plan['legs'] and shape['tickets']==plan['tickets']


def test_errors_zero_cap_and_cutoff_isolation(source):
    plan,cuts=source
    kw=dict(cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=106,scenario_draws=32)
    cat=n6_efficiency_catalog(plan,**kw)
    args=dict(cutoffs=cuts,method='MARGINAL',spend_cap_cny=0,budget_cny=1024,unit_cny=2,payout_factor=.65)
    zero=n6_efficiency_plan(cat,**args)
    assert zero['plan']['components']==[] and zero['plan']['cash_cny']==1024
    for bad in [dict(cutoffs={}),dict(method='INVALID'),dict(spend_cap_cny=65),dict(budget_cny=512),dict(payout_factor=1)]:
        with pytest.raises(ValueError):n6_efficiency_plan(cat,**{**args,**bad})
    for bad in [dict(cutoffs={}),dict(scenario_seed=-1),dict(scenario_draws=0)]:
        with pytest.raises(ValueError):n6_efficiency_catalog(plan,**{**kw,**bad})
    changed=copy.deepcopy(cat);changed['metrics'][0]['probability']=.9
    with pytest.raises(ValueError):n6_efficiency_plan(changed,**args)
    altered=copy.deepcopy(plan);altered.pop('seal');altered['legs'][0]['actual_direction']='W';altered['seal']=stable_json_hash(altered)
    with pytest.raises(ValueError):n6_efficiency_catalog(altered,**kw)
    altered=copy.deepcopy(plan);altered.pop('seal');altered['legs'][0]['decision_probabilities']=[.8,.1,.1];altered['seal']=stable_json_hash(altered)
    with pytest.raises(ValueError):n6_efficiency_catalog(altered,**kw)
    earlier={s:Cutoff.decision_epoch('001','2009-01-01T00:00:00Z') for s in cuts}
    with pytest.raises(ValueError):n6_efficiency_plan(cat,**{**args,'cutoffs':earlier})


def test_compression_value_can_choose_different_position(source):
    plan,cuts=source;plan=copy.deepcopy(plan);plan.pop('seal')
    for l in plan['legs']:
        if l['slot']==2:
            l.update(p_W=.82,p_D=.08,p_L=.1,q_W=.7,q_D=.2,q_L=.1)
        if l['slot']==3:
            l.update(p_W=.82,p_D=.08,p_L=.1,q_W=.3,q_D=.6,q_L=.1)
        l['decision_probabilities']=[.5*(l['p_'+d]+l['q_'+d]) for d in 'WDL']
    plan['seal']=stable_json_hash(plan)
    cat=n6_efficiency_catalog(plan,cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=1,scenario_draws=32)
    kw=dict(cutoffs=cuts,spend_cap_cny=1024,budget_cny=1024,unit_cny=2,payout_factor=.65)
    a=n6_efficiency_plan(cat,method='EXTRA_PROB',**kw)
    b=n6_efficiency_plan(cat,method='EXTRA_VALUE',**kw)
    assert a['shape_plan']['efficiency_selection'][0]['compression']['slot']==2
    assert b['shape_plan']['efficiency_selection'][0]['compression']['slot']==3

def test_portable_report_fixture(tmp_path):
    import gzip,hashlib,json,subprocess,sys
    from pathlib import Path
    path=Path("tests/fixtures/n6_efficiency.json.gz")
    pkg=json.loads(gzip.decompress(path.read_bytes()))
    assert all(hashlib.sha256(v.encode()).hexdigest()==pkg["hashes"][k] for k,v in pkg["files"].items())
    result=json.loads(pkg["files"]["results.json"])
    assert len(result["rows"])==576 and len(result["issue_order"])==48
    original={r["issue"]:r for r in result["rows"] if r["policy"]=="ORIGINAL"}
    assert sum(r["hits"]>0 for r in original.values())==41
    for row in result["rows"]:
        assert row["stake"]+row["cash_cny"]==1024
        assert row["net"]==pytest.approx(row["gross"]-row["stake"])
        assert row["hits"]<=original[row["issue"]]["hits"]
        assert row["gross"]<=original[row["issue"]]["gross"]+1e-8
        if row["method"].startswith("EXTRA_"):
            assert row["stake"]==original[row["issue"]]["stake"]/2
    out=tmp_path/"restored"
    subprocess.run([sys.executable,"scripts/prepare_n7_single_fixture.py","--fixture",str(path),"--output",str(out)],check=True)
    assert json.loads((out/"results.json").read_text())==result
