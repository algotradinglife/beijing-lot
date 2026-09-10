import itertools
import math
import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_baseline import n7_baseline_plan
from src.fundamentals_n7_selection import n7_selection_plan,n7_selection_expectation,settle_n7_selection

@pytest.mark.parametrize('selector',['COVERAGE','VALUE'])
def test_selection_grouping_expected_cash_and_invariance(selector):
    n=21
    x=pd.DataFrame(dict(issue=['100101']*n,slot=range(1,n+1),provider_id=[str(i) for i in range(n)],handicap=0,
        p_W=np.linspace(.45,.7,n),p_D=np.linspace(.35,.1,n),p_L=.2,q_W=np.linspace(.6,.35,n),q_D=.2,q_L=np.linspace(.2,.45,n)))
    cuts={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in x.slot}
    kw=dict(cutoffs=cuts,selector=selector,max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417)
    a=n7_selection_plan(x,grouping='CONCENTRATED',**kw);b=n7_selection_plan(x,grouping='SNAKE',**kw)
    old=n7_baseline_plan(x,shape='C0E0',funding='UNIT',**kw)
    assert a['legs']==old['legs'] and a['tickets']==old['tickets']
    assert {r['slot']:r['support'] for r in a['legs']}=={r['slot']:r['support'] for r in b['legs']}
    assert a['stake']==b['stake']==768
    assert b==n7_selection_plan(x.sample(frac=1,random_state=41),grouping='SNAKE',**kw)
    for plan in [a,b]:
        e=n7_selection_expectation(plan);expected=0
        assert len({r['slot'] for r in plan['legs']})==21
        for g in range(1,4):
            legs=sorted([r for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
            assert len(legs)==7
            for choices in itertools.product(*(r['support'] for r in legs)):
                ds=[dict(zip('310','WDL'))[c] for c in choices]
                expected+=2*.65*math.prod(r['p_'+d]/r['q_'+d] for r,d in zip(legs,ds))
        assert e['expected_gross']==pytest.approx(expected)
        audit=x[['issue','slot','provider_id','handicap']].copy();audit['actual_direction']='W';audit['status']='READY';audit['spf_sp']=2.
        result=settle_n7_selection(plan,audit)
        assert result['gross']==pytest.approx(3*2*.65*2**7)
        assert result['grouping']==plan['grouping'];assert result['expected_gross']==e['expected_gross']
        audit.spf_sp=100
        assert settle_n7_selection(plan,audit)['expected_gross']==e['expected_gross']
    tiny=x.head(6);kw['cutoffs']={str(i):cuts[str(i)] for i in tiny.slot}
    empty=n7_selection_plan(tiny,grouping='SNAKE',**kw)
    assert n7_selection_expectation(empty)['expected_gross']==0
    with pytest.raises(ValueError):n7_selection_plan(tiny,grouping='OTHER',**kw)
    tiny=tiny.assign(actual_home=1)
    with pytest.raises(ValueError,match='Prediction-only'):n7_selection_plan(tiny,grouping='SNAKE',**kw)
    a['stake']+=2
    with pytest.raises(ValueError,match='Plan changed'):n7_selection_expectation(a)

def test_independent_replay_accepts_no_bet_rejects_pending_and_nonzero_cash(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path
    x=pd.DataFrame(dict(issue=['100101']*6,slot=range(1,7),provider_id=[str(i) for i in range(6)],handicap=0,
                        p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.3,q_L=.3))
    cuts={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in x.slot}
    plans=[n7_selection_plan(x,cutoffs=cuts,selector=s,grouping=g,max_groups=6,unit_cny=2,
           group_budget_cny=432,payout_factor=.65,allocation_seed=417)
           for s in ['COVERAGE','VALUE'] for g in ['CONCENTRATED','SNAKE']]
    audit=x[['issue','slot','provider_id']]
    rows=[settle_n7_selection(p,audit) for p in plans]
    expectations=[dict(issue=p['issue'],selector=p['selector'],grouping=p['grouping'],**n7_selection_expectation(p)) for p in plans]
    (tmp_path/'plans.json').write_text(json.dumps(plans));(tmp_path/'expectations.json').write_text(json.dumps(expectations))
    settlement=dict(results=rows,audit=audit.to_dict('records'))
    (tmp_path/'settlement.json').write_text(json.dumps(settlement))
    cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/replay_n7_selection.py'),str(tmp_path)]
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads((tmp_path/'independent-replay.json').read_text())['status']=='PASS'
    rows[0]['status']='PENDING_AUDIT'
    (tmp_path/'settlement.json').write_text(json.dumps(settlement))
    assert subprocess.run(cmd,capture_output=True).returncode!=0
    rows[0]['status']='NO_BET';rows[0]['gross']=1
    (tmp_path/'settlement.json').write_text(json.dumps(settlement))
    assert subprocess.run(cmd,capture_output=True).returncode!=0
