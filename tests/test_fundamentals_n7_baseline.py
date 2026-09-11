from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_baseline import archive_n7_inputs,n7_baseline_plan,settle_n7_baseline


def sample(n=14):
    x=pd.DataFrame(dict(issue=['100101']*n,slot=range(1,n+1),provider_id=[f'{i:04}' for i in range(n)],handicap=[0]*n,
        p_W=np.linspace(.51,.7,n),p_D=np.linspace(.29,.1,n),p_L=[.2]*n,q_W=[.5]*n,q_D=[.25]*n,q_L=[.25]*n))
    cuts={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in x.slot}
    return x,dict(cutoffs=cuts,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417)


@pytest.mark.parametrize('shape,count',[('C0E0',128),('C1E2',144),('C1E3',216)])
@pytest.mark.parametrize('funding',['UNIT','MATCHED'])
def test_complete_disjoint_budget_and_payout(shape,count,funding):
    x,kw=sample();kw.update(shape=shape,funding=funding);plan=n7_baseline_plan(x,**kw)
    assert plan['groups']==2;assert len(plan['tickets'])==2*count
    assert plan['stake']==(2*count*2 if funding=='UNIT' else 864)
    assert len({r['provider_id'] for r in plan['legs']})==14
    assert plan==n7_baseline_plan(x.sample(frac=1,random_state=42),**kw)
    audit=x[['issue','slot','provider_id','handicap']].copy();audit['actual_direction']='W';audit['spf_sp']=2.;audit['status']='READY'
    result=settle_n7_baseline(plan,audit)
    wins=[t for t in plan['tickets'] if t['code']=='3333333']
    assert result['gross']==pytest.approx(sum(t['units'] for t in wins)*2*.65*2**7)
    assert result['hits']==2
    assert result['net']==pytest.approx(result['gross']-plan['stake'])
    audit.loc[0,'spf_sp']=np.nan
    assert settle_n7_baseline(plan,audit)['status']=='PENDING_WINNING_SP'
    if shape=='C0E0':
        audit.loc[0,'actual_direction']='L' if '0' not in next(r['support'] for r in plan['legs'] if r['slot']==1) else 'D'
        assert settle_n7_baseline(plan,audit)['status']=='COMPLETE'
    audit.loc[0,'status']='spf:IDENTITY_OR_SCORE_MISMATCH'
    assert settle_n7_baseline(plan,audit)['status']=='PENDING_AUDIT'
    plan['stake']+=2
    with pytest.raises(ValueError,match='Plan changed'):settle_n7_baseline(plan,audit)


def test_cutoffs_labels_probability_contracts_and_no_bet():
    x,kw=sample(6);plan=n7_baseline_plan(x,**kw)
    assert plan['stake']==0;assert plan['groups']==0
    audit=pd.DataFrame(columns=['issue','slot','provider_id'])
    assert settle_n7_baseline(plan,audit)['status']=='NO_BET'
    for bad in [x.assign(actual_home=0),pd.concat([x,x]),x.assign(q_L=0),x.assign(handicap=.5)]:
        with pytest.raises(ValueError):n7_baseline_plan(bad,**kw)
    with pytest.raises(ValueError):n7_baseline_plan(x,**{**kw,'cutoffs':{}})
    wrong={k:Cutoff.decision_epoch('100102','2010-01-01T00:00:00Z') for k in kw['cutoffs']}
    with pytest.raises(ValueError):n7_baseline_plan(x,**{**kw,'cutoffs':wrong})
    x,kw=sample();changed=x.copy();changed.loc[0,['q_W','q_D','q_L']]=[.01,.49,.5]
    plan=n7_baseline_plan(changed,**{**kw,'selector':'VALUE'})
    assert 1 in [r['slot'] for r in plan['legs'][:7]]


def test_archive_inputs_keep_labels_separate_and_bind_sources(tmp_path):
    cuts={'100101':{'1':'2010-01-01T00:00:00Z'}}
    grid=[dict(home_goals=1,away_goals=0,probability=.6),dict(home_goals=0,away_goals=0,probability=.2),dict(home_goals=0,away_goals=1,probability=.2)]
    fixture=dict(issue='100101',slot=1,provider_id='001',scenario='baseline',handicap=0,home='A',away='B',actual_home=1,actual_away=0)
    prediction=dict(selected=dict(cutoffs=cuts,scores=[dict(**g,issue='100101',slot=1,provider_id='001',scenario='baseline') for g in grid]),market=dict(cutoffs=cuts,grids={'100101/1':grid},status=[dict(issue='100101',slot=1,provider_id='001',handicap=0,status='READY')]))
    (tmp_path/'predictions.json').write_text(json.dumps(prediction));(tmp_path/'comparison.json').write_text(json.dumps({'fixtures':[fixture]}))
    root=Path(__file__).resolve().parents[1]
    a=archive_n7_inputs([tmp_path],root)
    assert a['rows'][0]['p_W']==.6;assert 'actual_home' not in a['rows'][0]
    fixture['actual_home']=9;(tmp_path/'comparison.json').write_text(json.dumps({'fixtures':[fixture]}))
    b=archive_n7_inputs([tmp_path],root)
    assert a['rows']==b['rows'];assert a['source_hashes']!=b['source_hashes']
    prediction['market']['status'][0]['status']='MISSING';(tmp_path/'predictions.json').write_text(json.dumps(prediction))
    assert len(archive_n7_inputs([tmp_path],root)['exclusions'])==1
