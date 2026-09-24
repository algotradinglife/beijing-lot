import copy
import math
import numpy as np
import pandas as pd
import pytest
from beidan_backend.temporal_learning import Cutoff
from src.fundamentals_n7_baseline import n7_baseline_plan
from src.fundamentals_n67_overlay import n67_overlay_plan,overlay_any_hit,settle_n67_overlay


def sample(n):
    x=pd.DataFrame(dict(issue=['100101']*n,slot=range(1,n+1),provider_id=[str(i) for i in range(n)],handicap=0,
        p_W=np.linspace(.4,.7,n),p_D=.2,p_L=np.linspace(.4,.1,n),q_W=.4,q_D=.3,q_L=.3))
    cuts={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in x.slot}
    return x,dict(cutoffs=cuts,max_n6=7,max_n7=6,unit_cny=2,payout_factor=.65,allocation_seed=417)


@pytest.mark.parametrize('strategy',['N7','N6','DIRECT','CROSS'])
@pytest.mark.parametrize('funding',['UNIT','MATCHED'])
def test_overlap_constraints_budget_and_cash(strategy,funding):
    x,kw=sample(42);p=n67_overlay_plan(x,strategy=strategy,funding=funding,**kw)
    assert p==n67_overlay_plan(x.sample(frac=1,random_state=2),strategy=strategy,funding=funding,**kw)
    expected={'N7':1536,'N6':896,'DIRECT':2432,'CROSS':2432}[strategy]
    assert p['stake']==(2432 if funding=='MATCHED' else expected)
    for part in p['components']:
        assert len({r['slot'] for r in part['legs']})==part['n']*part['groups']
        for g in range(1,part['groups']+1):
            assert sum(r['group']==g for r in part['legs'])==part['n']
            assert sum(t['group']==g for t in part['tickets'])==2**part['n']
    if strategy=='CROSS':assert p['max_pair_overlap']==1
    if strategy=='DIRECT':assert p['max_pair_overlap']==6
    audit=x[['issue','slot','provider_id','handicap']].copy();audit['actual_direction']='W';audit['spf_sp']=2.;audit['status']='READY'
    r=settle_n67_overlay(p,audit)
    cash=sum(2*.65*2**part['n']*sum(t['units'] for t in part['tickets'] if t['code']=='3'*part['n']) for part in p['components'])
    assert r['gross']==pytest.approx(cash);assert r['hits']==r['groups']
    audit.loc[0,'spf_sp']=np.nan
    assert settle_n67_overlay(p,audit)['gross'] is None
    if strategy=='N7' and funding=='UNIT':
        old=n7_baseline_plan(x,cutoffs=kw['cutoffs'],selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417)
        assert p['components'][0]['legs']==old['legs']
        assert p['components'][0]['tickets']==old['tickets']
    p['stake']+=2
    with pytest.raises(ValueError,match='Plan changed'):settle_n67_overlay(p,audit)


def test_joint_probability_accounts_for_shared_fixtures_and_small_issues():
    x,kw=sample(7);p=n67_overlay_plan(x,strategy='DIRECT',funding='UNIT',**kw)
    # The N7 hit event is a subset of the N6 hit event: union is exactly N6 hit.
    six=next(c for c in p['components'] if c['n']==6)
    assert p['model_any_hit']==pytest.approx(math.prod(r['coverage'] for r in six['legs']))
    broken=copy.deepcopy(p['components']);broken[1]['legs'][0]['coverage']+=.01
    with pytest.raises(ValueError,match='Inconsistent'):overlay_any_hit(broken)
    x,kw=sample(6);p=n67_overlay_plan(x,strategy='N7',funding='MATCHED',**kw)
    assert p['stake']==0 and p['budget']==128 and p['model_any_hit']==0
    audit=x[['issue','slot','provider_id']]
    r=settle_n67_overlay(p,audit);assert r['status']=='NO_BET' and r['gross']==0 and r['roi'] is None
    x,kw=sample(5);p=n67_overlay_plan(x,strategy='CROSS',funding='MATCHED',**kw)
    assert p['budget']==p['stake']==0
    with pytest.raises(ValueError):n67_overlay_plan(x.assign(actual_home=1),strategy='CROSS',funding='UNIT',**kw)
    with pytest.raises(ValueError):n67_overlay_plan(x,strategy='BAD',funding='UNIT',**kw)
    kw['max_n6']=8
    with pytest.raises(ValueError):n67_overlay_plan(x,strategy='CROSS',funding='UNIT',**kw)

def test_cross_joint_probability_agrees_with_independent_fixture_simulation():
    x,kw=sample(42);p=n67_overlay_plan(x,strategy='CROSS',funding='UNIT',**kw)
    by_slot={r['slot']:r['coverage'] for part in p['components'] for r in part['legs']}
    rng=np.random.default_rng(417)
    draws=rng.random((50000,42))<np.array([by_slot[i] for i in range(1,43)])
    hit=np.zeros(50000,dtype=bool)
    for part in p['components']:
        for g in range(1,part['groups']+1):
            slots=[r['slot']-1 for r in part['legs'] if r['group']==g]
            hit |= draws[:,slots].all(axis=1)
    assert abs(hit.mean()-p['model_any_hit'])<.01
    with pytest.raises(ValueError,match='At most13'):overlay_any_hit([dict(groups=14,legs=[])])

@pytest.mark.parametrize('n',[5,7])
def test_independent_overlay_cash_replay_cli(tmp_path,n):
    import json
    import subprocess
    import sys
    from pathlib import Path
    x,kw=sample(n);p=n67_overlay_plan(x,strategy='DIRECT',funding='UNIT',**kw)
    a=x[['issue','slot','provider_id','handicap']].copy();a['actual_direction']='W';a['spf_sp']=2.;a['status']='READY'
    r=settle_n67_overlay(p,a)
    (tmp_path/'plans.json').write_text(json.dumps([p]))
    result=dict(results=[r],audit=a.to_dict('records'))
    (tmp_path/'settlement.json').write_text(json.dumps(result))
    cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/replay_n67_overlay.py'),str(tmp_path)]
    run=subprocess.run(cmd,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads((tmp_path/'independent-replay.json').read_text())['verified']==1
    r['gross']+=1
    (tmp_path/'settlement.json').write_text(json.dumps(result))
    assert subprocess.run(cmd,capture_output=True).returncode!=0


def test_overlay_replay_null_audit_status(tmp_path):
    import json,subprocess,sys
    from pathlib import Path
    x,kw=sample(7)
    plan=n67_overlay_plan(x,strategy="DIRECT",funding="UNIT",**kw)
    audit=x[["issue","slot","provider_id","handicap"]].assign(
        actual_direction="W",spf_sp=2.,status=None)
    settled=settle_n67_overlay(plan,audit)
    assert settled["status"]=="PENDING_AUDIT_OR_WINNING_SP"
    (tmp_path/"plans.json").write_text(json.dumps([plan]))
    (tmp_path/"settlement.json").write_text(json.dumps(dict(results=[settled],audit=audit.to_dict("records"))))
    command=[sys.executable,str(Path(__file__).resolve().parents[1]/"scripts/replay_n67_overlay.py"),str(tmp_path)]
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads((tmp_path/"independent-replay.json").read_text())["pending_verified"]==1
