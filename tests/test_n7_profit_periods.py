import numpy as np
import pandas as pd
import pytest
import gzip
import hashlib
import json
from pathlib import Path
from src.n7_probability_gate import probability_gate_candidates
from src.n7_incremental_coverage import incremental_coverage_plans
from src.n7_profit_periods import profit_period_plans
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.n7_single_ticket_sampling import settle_single_tickets


def test_archived_accounting_grid_and_reported_profit_ranges():
    archive = json.loads(gzip.decompress(Path('tests/fixtures/n7_profit_periods.json.gz').read_bytes()))
    assert archive['mode'] == 'ARCHIVED_ACCOUNTING_ONLY'
    assert hashlib.sha256(archive['body'].encode()).hexdigest() == archive['sha256']
    result = json.loads(archive['body'])
    rows = pd.DataFrame(result['rows'])
    assert len(rows) == 9600
    assert not rows.duplicated(['issue', 'seed', 'count', 'ranking']).any()
    assert set(rows.issue) == set(result['issue_order'])
    selected = rows[(rows['count'] == 5) & (rows.ranking == 'PROFIT')]
    profitable = selected.assign(profit=selected.net > 0).groupby('seed').profit.sum()
    assert sorted(profitable) == [21, 23, 24]
    assert selected.stake.eq(1024).all()


def test_profit_search_controls_budget_monotonicity_and_independent_evaluation():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.55,q_D=.25,q_L=.2) for i in range(1,10)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=700,tradeoffs=[0.,'PROBABILITY'])
    common=dict(cutoffs=cuts,seed=42,training_worlds=1000,evaluation_worlds=2000,budget_cny=1024,unit_cny=2,payout_factor=.65)
    starts=incremental_coverage_plans(pool,**common,min_probabilities=[0.,.1])
    result=profit_period_plans(pool,starts,**common,swap_attempts=200,probability_proposal_weight=.5)
    assert len(result)==8
    initial={z['parameters']['ranking']:z for z in starts if z['parameters']['min_probability']==0}
    for z in result:
        assert stable_json_hash({k:v for k,v in z.items() if k!='seal'})==z['seal']
        ranking=z['parameters']['ranking']
        if z['parameters']['min_probability']==.1:
            assert z['stake']==0 and z['simulation']['evaluation_profit_rate']==0
        elif ranking!='PROFIT':
            assert z['fixture_indices']==initial[ranking]['fixture_indices']
            assert z['simulation']['evaluation_hit_rate']==initial[ranking]['simulation']['evaluation_hit_rate']
    profit=next(z for z in result if z['parameters']['ranking']=='PROFIT' and z['stake']>0)
    controls=[z for z in result if z['parameters']['ranking'] in ('PROB','COVERAGE') and z['stake']>0]
    assert profit['stake']==1024 and profit['groups']==512
    assert profit['simulation']['training_profit_rate']>=max(z['simulation']['training_profit_rate'] for z in controls)
    assert profit['optimization']['accepted']<=200 and profit['optimization']['attempted']==200
    # Independent direct training gross, includes strict break-even inequality.
    rng=np.random.default_rng(np.random.SeedSequence(42).spawn(3)[0])
    outcome=np.array([np.searchsorted(np.array([.6,.9,1.]),rng.random(1000),side='right') for _ in range(9)])
    gross=np.zeros(1000);q=np.array([.55,.25,.2])
    for ii,dd in zip(profit['fixture_indices'],profit['outcomes']):
        gross[np.all(outcome[ii]==np.array(dd)[:,None],axis=0)]+=1.3/np.prod(q[dd])
    assert profit['simulation']['training_profit_rate']==pytest.approx(np.mean(gross>1024))
    changed_common=dict(common,evaluation_worlds=3000)
    changed_starts=incremental_coverage_plans(pool,**changed_common,min_probabilities=[0.,.1])
    changed=profit_period_plans(pool,changed_starts,**changed_common,swap_attempts=200,probability_proposal_weight=.5)
    changed_profit=next(z for z in changed if z['parameters']['ranking']=='PROFIT' and z['stake']>0)
    assert changed_profit['fixture_indices']==profit['fixture_indices'] and changed_profit['outcomes']==profit['outcomes']
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    assert settle_single_tickets(profit,audit)['status']=='COMPLETE'
    for bad in (dict(swap_attempts=-1),dict(probability_proposal_weight=2),dict(cutoffs={})):
        with pytest.raises(ValueError):profit_period_plans(pool,starts,**{**common,'swap_attempts':200,'probability_proposal_weight':.5,**bad})
    with pytest.raises(ValueError):profit_period_plans(pool,starts[:-1],**common,swap_attempts=200,probability_proposal_weight=.5)


def test_all_candidates_selected_zero_swaps_and_mismatched_start():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=1.,p_D=0.,p_L=0.,q_W=.8,q_D=.1,q_L=.1) for i in range(1,9)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[0.])
    common=dict(cutoffs=cuts,seed=1,training_worlds=17,evaluation_worlds=23,budget_cny=1024,unit_cny=2,payout_factor=.65)
    starts=incremental_coverage_plans(pool,**common,min_probabilities=[1.])
    plans=profit_period_plans(pool,starts,**common,swap_attempts=0,probability_proposal_weight=.5)
    assert all(z['groups']==8 and z['simulation']['evaluation_profit_rate']==1 for z in plans)
    assert plans[-1]['optimization']['attempted']==0
    bad=[dict(z) for z in starts];bad[0]['stake']=0
    with pytest.raises(ValueError):profit_period_plans(pool,bad,**common,swap_attempts=0,probability_proposal_weight=.5)
