from collections import Counter
import itertools,math
import pytest
from tests.test_fundamentals_n67_overlay import sample
from src.fundamentals_n7_addons import n7_addon_plan
from src.fundamentals_n7_twocover import settle_n7_twocover

@pytest.mark.parametrize('n',[5,7,11,14,21,42,50])
def test_addition_constraints_and_sequential_optimum(n):
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']}
    kw.update(max_groups=6,max_overlap=3,max_exposure=2)
    plans=[n7_addon_plan(x,additions=i,**kw) for i in range(3)]
    assert plans[1]['components']==plans[2]['components'][:len(plans[1]['components'])]
    assert plans[2]==n7_addon_plan(x.sample(frac=1,random_state=2),additions=2,**kw)
    events=[];prob={}
    for k,part in enumerate(plans[2]['components']):
        for g in range(1,part['groups']+1):
            legs=[r for r in part['legs'] if r['group']==g];e={r['slot'] for r in legs}
            assert len(e)==7
            if k:assert all(len(e&prev)<=3 for prev in events)
            events.append(e);prob.update({r['slot']:r['coverage'] for r in legs})
    assert max(Counter(s for e in events for s in e).values(),default=0)<=2
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    r=settle_n7_twocover(plans[2],a)
    assert r['gross']==pytest.approx(len(events)*2*.65*2**7)
    assert r['stake']==len(events)*256
    if n<=14 and plans[1]['actual_additions']:
        base_events=events[:plans[0]['components'][0]['groups']]
        from src.fundamentals_n7_baseline import rank_double_candidates
        ranked,_=rank_double_candidates(x,cutoffs=kw['cutoffs']);ps=dict(zip(ranked.slot,ranked.coverage))
        feasible=[math.prod(ps[s] for s in combo) for combo in itertools.combinations(x.slot,7) if all(len(set(combo)&e)<=3 for e in base_events)]
        assert plans[1]['solver_steps'][0]['hit_probability']==pytest.approx(max(feasible))
    with pytest.raises(ValueError):n7_addon_plan(x.assign(actual_home=1),additions=1,**kw)
    with pytest.raises(ValueError):n7_addon_plan(x,additions=3,**kw)

def test_solver_failure_is_not_an_infeasible_or_fallback_plan(monkeypatch):
    from types import SimpleNamespace
    x,old=sample(21);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']}
    kw.update(max_groups=6,max_overlap=3,max_exposure=2)
    monkeypatch.setattr('src.fundamentals_n7_addons.milp',lambda **kwargs:SimpleNamespace(status=1,x=None,message='time limit'))
    with pytest.raises(RuntimeError,match='not certified'):n7_addon_plan(x,additions=1,**kw)
    monkeypatch.setattr('src.fundamentals_n7_addons.milp',lambda **kwargs:SimpleNamespace(status=0,x=[1]*21,mip_gap=1e-7,message='absolute tolerance'))
    with pytest.raises(RuntimeError,match='not certified'):n7_addon_plan(x,additions=1,**kw)

@pytest.mark.parametrize('n',[5,11,21])
def test_addon_independent_replay(tmp_path,n):
    import json,subprocess,sys,copy
    from pathlib import Path
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']}
    kw.update(max_groups=6,max_overlap=3,max_exposure=2)
    plans=[n7_addon_plan(x,additions=i,**kw) for i in range(3)]
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    rows=[settle_n7_twocover(p,a) for p in plans]
    (tmp_path/'plans.json').write_text(json.dumps(plans));(tmp_path/'inputs.json').write_text(json.dumps(dict(rows=x.to_dict('records'))))
    value=dict(results=rows,audit=a.to_dict('records'))
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/replay_n7_addons.py'),str(tmp_path)]
    run=subprocess.run(cmd,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    if n==21:
        omitted=copy.deepcopy(plans)
        for p in omitted[1:]:
            p['components']=copy.deepcopy(omitted[0]['components']);p['actual_additions']=0
            p['stake']=p['budget']=omitted[0]['stake'];p['solver_steps']=[dict(status='INFEASIBLE')]
            from src.temporal_learning.core import stable_json_hash
            p.pop('seal');p['seal']=stable_json_hash(p)
        (tmp_path/'plans.json').write_text(json.dumps(omitted))
        (tmp_path/'settlement.json').write_text(json.dumps(dict(results=[settle_n7_twocover(p,a) for p in omitted],audit=a.to_dict('records'))))
        assert subprocess.run(cmd,capture_output=True).returncode!=0
        (tmp_path/'plans.json').write_text(json.dumps(plans))
    rows[0]['gross']+=1
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    assert subprocess.run(cmd,capture_output=True).returncode!=0
