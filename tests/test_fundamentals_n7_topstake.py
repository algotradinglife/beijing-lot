import math,copy
import pytest
from tests.test_fundamentals_n67_overlay import sample
from src.fundamentals_n7_topstake import n7_topstake_plan,settle_n7_topstake

@pytest.mark.parametrize('n',[5,7,14,42,50])
def test_top_stake_cash_supports_and_no_bet(n):
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']};kw['max_groups']=6
    plans=[n7_topstake_plan(x,top_multiplier=m,**kw) for m in [1,2,3]]
    base=plans[0]['components'][0];count=base['groups']
    probs={g:math.prod(r['coverage'] for r in base['legs'] if r['group']==g) for g in range(1,count+1)}
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    for m,p in enumerate(plans,1):
        assert p==n7_topstake_plan(x.sample(frac=1,random_state=9),top_multiplier=m,**kw)
        assert base['legs']==p['components'][0]['legs']
        assert p['stake']==count*256+(m-1)*256*bool(count)
        assert p['model_any_hit']==plans[0]['model_any_hit']
        if count:assert p['top_probability']==max(probs.values())
        r=settle_n7_topstake(p,a)
        assert r['gross']==pytest.approx((count+(m-1)*bool(count))*2*.65*2**7)
        assert r['hits']==count
        assert r['status']==('COMPLETE' if count else 'NO_BET')
    if count:
        a['spf_sp']=float('nan');r=settle_n7_topstake(plans[2],a)
        assert r['gross'] is None and r['top_group']>0
    bad=copy.deepcopy(plans[0]);bad['stake']+=2
    with pytest.raises(ValueError):settle_n7_topstake(bad,a)
    with pytest.raises(ValueError):n7_topstake_plan(x,top_multiplier=4,**kw)
    with pytest.raises(ValueError):n7_topstake_plan(x.assign(actual_home=1),top_multiplier=2,**kw)


def test_equal_probability_tie_uses_lowest_group():
    x,old=sample(14);x['p_W']=.5;x['p_D']=.3;x['p_L']=.2
    kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']};kw['max_groups']=6
    p=n7_topstake_plan(x,top_multiplier=2,**kw)
    assert p['top_group']==1
    assert all(t['units']==(2 if t['group']==1 else 1) for t in p['components'][0]['tickets'])

@pytest.mark.parametrize('n',[5,14])
def test_independent_cash_replay(tmp_path,n):
    import json,subprocess,sys
    from pathlib import Path
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']};kw['max_groups']=6
    plans=[n7_topstake_plan(x,top_multiplier=m,**kw) for m in [1,2,3]]
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    rows=[settle_n7_topstake(p,a) for p in plans]
    (tmp_path/'plans.json').write_text(json.dumps(plans))
    value=dict(results=rows,audit=a.to_dict('records'))
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/replay_n7_topstake.py'),str(tmp_path)]
    run=subprocess.run(cmd,capture_output=True,text=True);assert run.returncode==0,run.stderr
    rows[0]['gross']+=1
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    assert subprocess.run(cmd,capture_output=True).returncode!=0
