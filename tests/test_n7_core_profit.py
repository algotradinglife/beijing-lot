import copy
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys
import numpy as np
import pandas as pd
import pytest
from src.n7_probability_gate import probability_gate_candidates
from src.n7_incremental_coverage import incremental_coverage_plans
from src.n7_profit_periods import profit_period_plans
from src.n7_core_profit import core_profit_plans
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def test_archived_core_experiment_exact_grid_and_payout_identity():
    a=json.loads(gzip.decompress(Path('tests/fixtures/n7_core_profit.json.gz').read_bytes()))
    assert a['mode']=='ARCHIVED_ACCOUNTING_ONLY'
    assert hashlib.sha256(a['body'].encode()).hexdigest()==a['sha256']
    assert hashlib.sha256(a['diagnostics_body'].encode()).hexdigest()==a['diagnostics_sha256']
    result=json.loads(a['body']);rows=result['rows']
    tags=['PROB','PROFIT']+[f'{kind}_{frac}' for kind in ('FIXED','GAP','JOINT') for frac in (25,50,75)]
    keys=[(r['issue'],r['seed'],r['tag']) for r in rows]
    assert len(keys)==len(set(keys))==3300
    assert set(keys)=={(issue,seed,tag) for issue in result['issue_order'] for seed in (41901,41902,41903) for tag in tags}
    assert all(r['stake']==1024 and r['groups']==512 and abs(r['gross']-r['stake']-r['net'])<1e-6 for r in rows)


def test_independent_checker_rejects_rehashed_report_rate(tmp_path,monkeypatch):
    # Isolate row/plan binding; the real study separately exercises full closure.
    import src.temporal_learning
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    tags=['PROB','PROFIT']+[f'{kind}_{frac}' for kind in ('FIXED','GAP','JOINT') for frac in (25,50,75)]
    fixtures=[dict(issue='001',slot=i,provider_id=str(i),handicap=0,p_W=1.,p_D=0.,p_L=0.,q_W=.5,q_D=.25,q_L=.25) for i in range(7)]
    plan=dict(issue='001',fixtures=fixtures,fixture_indices=[list(range(7))],outcomes=[[0]*7],
        stake=2,cash_cny=1022,groups=1,parameters=dict(ranking='PROB',core_fraction=None),
        simulation=dict(seed=42,training_hit_rate=.3,evaluation_hit_rate=.3,training_profit_rate=.2,evaluation_profit_rate=.2),search={})
    plan['seal']=stable_json_hash(plan)
    (tmp_path/'plans').mkdir();path=tmp_path/'plans/001_42_PROB.json.gz'
    path.write_bytes(gzip.compress(json.dumps(plan).encode()))
    receipt=dict(issues=['001'],seeds=[42],counts=[5],implementation={},source_hashes={},
        plan_hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest()})
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (tmp_path/'plans-frozen.json').write_text(json.dumps(freeze))
    rows=[dict(issue='001',seed=42,tag=tag,ranking=tag.split('_')[0],fraction=None,model='C005',policy=f'{tag}_42',
        stake=2,groups=1,accepted=0,train_coverage=.3,eval_coverage=.3,train_profit=.9,eval_profit=.2) for tag in tags]
    (tmp_path/'results.json').write_text(json.dumps(dict(rows=rows,freeze_seal=freeze['seal'])))
    (tmp_path/'audit.json').write_text(json.dumps(dict(rows=fixtures)))
    (tmp_path/'prior-evaluation-snapshot.json').write_text('{}')
    er={key:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for key,name in
        [('freeze_sha256','plans-frozen.json'),('result_sha256','results.json'),('audit_sha256','audit.json'),('prior_receipt_sha256','prior-evaluation-snapshot.json')]}
    er['audit_path']=str(tmp_path/'audit.json')
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps(er))
    monkeypatch.setattr(sys,'argv',['checker','--study',str(tmp_path)])
    with pytest.raises(ValueError,match='Result simulated rate differs from frozen plan: train_profit'):
        runpy.run_module('scripts.check_n7_core_profit',run_name='__main__')


def test_core_gap_joint_budget_independent_replay_and_contracts():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.55,q_D=.25,q_L=.2) for i in range(1,10)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=700,tradeoffs=[0.,'PROBABILITY'])
    common=dict(cutoffs=cuts,seed=42,training_worlds=200,evaluation_worlds=300,budget_cny=1024,unit_cny=2,payout_factor=.65)
    starts=incremental_coverage_plans(pool,**common,min_probabilities=[0.])
    old=next(p for p in profit_period_plans(pool,starts,**common,swap_attempts=20,probability_proposal_weight=.5)
             if p['parameters']['ranking']=='PROFIT')
    params=dict(core_fractions=[.25,.5,.75],proposal_width=4,joint_attempts=20,min_probability=0.,payout_stress=[.8,1.,1.2])
    plans=core_profit_plans(pool,old,**common,**params)
    assert len(plans)==11
    base=plans[0]
    rng=np.random.default_rng(np.random.SeedSequence(42).spawn(2)[1])
    sim=np.array([np.searchsorted(np.array([.6,.9,1.]),rng.random(300),side='right') for _ in range(9)])
    for p in plans:
        assert p['seal']==stable_json_hash({k:v for k,v in p.items() if k!='seal'})
        assert p['stake']==1024 and p['groups']==512
        tickets={tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(p['fixture_indices'],p['outcomes'])}
        assert len(tickets)==512
        assert set(map(tuple,p['core_encoded_tickets']))<=tickets
        frac=p['parameters']['core_fraction']
        if frac is not None:assert len(p['core_encoded_tickets'])==int(np.ceil(512*frac))
        gross=np.zeros(300)
        for ii,dd in zip(p['fixture_indices'],p['outcomes']):
            gross[np.all(sim[ii]==np.array(dd)[:,None],axis=0)]+=1.3/np.prod(np.array([.55,.25,.2])[dd])
        assert np.mean(gross>1024)==p['simulation']['evaluation_profit_rate']
        assert np.mean(gross>0)==p['simulation']['evaluation_hit_rate']
        assert [np.mean(gross*s>1024) for s in params['payout_stress']]==[x['profit'] for x in p['simulation']['payout_stress']]
        if p['parameters']['ranking']=='JOINT':
            gap=next(x for x in plans if x['parameters']['ranking']=='GAP' and x['parameters']['core_fraction']==frac)
            assert p['simulation']['training_profit_rate']>=gap['simulation']['training_profit_rate']
    assert plans[1]['fixture_indices']==old['fixture_indices'] and plans[1]['outcomes']==old['outcomes']
    changed=copy.deepcopy(old);changed['simulation']['evaluation_worlds']=350
    changed['seal']=stable_json_hash({k:v for k,v in changed.items() if k!='seal'})
    other=core_profit_plans(pool,changed,**{**common,'evaluation_worlds':350},**{**params,'payout_stress':[.1,2.]})
    assert [(p['fixture_indices'],p['outcomes']) for p in plans]==[(p['fixture_indices'],p['outcomes']) for p in other]
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='COMPLETE')
    assert all(settle_single_tickets(p,audit)['status']=='COMPLETE' for p in plans)
    for bad in ({'core_fractions':[0.]},{'proposal_width':0},{'payout_stress':[-1.]},{'cutoffs':{}},{'joint_attempts':-1}):
        with pytest.raises(ValueError):core_profit_plans(pool,old,**{**common,**params,**bad})
    changed=copy.deepcopy(old);changed['stake']=0
    with pytest.raises(ValueError):core_profit_plans(pool,changed,**common,**params)


def test_no_bet_core_plans():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=1.,p_D=0.,p_L=0.,q_W=.5,q_D=.25,q_L=.25) for i in range(1,7)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=10,tradeoffs=['PROBABILITY'])
    common=dict(cutoffs=cuts,seed=1,training_worlds=10,evaluation_worlds=20,budget_cny=1024,unit_cny=2,payout_factor=.65)
    starts=incremental_coverage_plans(pool,**common,min_probabilities=[0.])
    old=next(p for p in profit_period_plans(pool,starts,**common,swap_attempts=0,probability_proposal_weight=.5)
             if p['parameters']['ranking']=='PROFIT')
    plans=core_profit_plans(pool,old,**common,core_fractions=[.5],proposal_width=2,joint_attempts=1,min_probability=0.,payout_stress=[1.])
    assert len(plans)==5
    assert all(p['groups']==0 and p['stake']==0 and p['simulation']['evaluation_profit_rate']==0 for p in plans)
