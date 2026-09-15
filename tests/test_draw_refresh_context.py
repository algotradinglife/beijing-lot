import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from src.draw_refresh_context import draw_refresh_context, draw_refresh_context_json
from src.temporal_learning.core import Cutoff, TemporalContractError
from src.temporal_learning.frozen_blocks import frozen_block_schedule, verify_block_target


ROOT = Path(__file__).resolve().parents[1]


def fixture_history():
    return pd.DataFrame([dict(issue_code=f'{i:06}', slot=j, provider_id=f'{i}-{j}',
        q_W=.4, q_D=.2, q_L=.4, actual='D' if j == 1 else 'W',
        fixture_decision_ts=f'2011-01-{i:02}T00:00:00Z',
        last_fixture_cutoff=f'2011-01-{i:02}T00:00:00Z')
        for i in range(1, 9) for j in range(1, 4)])


def blocks():
    return frozen_block_schedule(pd.DataFrame(dict(issue_code=['000006','000007','000008'],
        fixture_decision_ts=['2011-01-06T00:00Z','2011-01-07T00:00Z','2011-01-08T00:00Z'])), cadence=2)


def test_schedule_and_target_contract():
    b = blocks()
    assert [len(x['targets']) for x in b] == [2, 1]
    assert b[0]['excluded_issues'] == ['000006','000007','000008']
    assert verify_block_target(b[0], Cutoff.decision_epoch('000007','2011-01-07T00:00Z'))
    for cutoff in [Cutoff.decision_epoch('000007','2011-01-07T01:00Z'),
                   Cutoff.decision_epoch('000008','2011-01-08T00:00Z')]:
        with pytest.raises(TemporalContractError):
            verify_block_target(b[0], cutoff)
    bad=copy.deepcopy(b[0]); bad['cadence']=9
    with pytest.raises(TemporalContractError):
        verify_block_target(bad,Cutoff.decision_epoch('000006','2011-01-06T00:00Z'))
    for cadence in [0,-1,1.5,True]:
        with pytest.raises(TemporalContractError):
            frozen_block_schedule(pd.DataFrame(),cadence=cadence)
    with pytest.raises(TemporalContractError):
        frozen_block_schedule(pd.DataFrame(columns=['issue_code','fixture_decision_ts']),cadence=2)


def test_context_components_and_future_mutation():
    kwargs=dict(repository_root=ROOT, source_hashes={'fixture':'a'*64},delay_hours=24,
                recent_issues=3,minimum_ess=2)
    h=fixture_history(); b=blocks()[0]
    a=draw_refresh_context(h,b,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**kwargs)
    assert set(r['issue_code'] for r in a['rows']) == {'000001','000002','000003','000004'}
    assert sum(r['long_mass'] for r in a['rows']) == pytest.approx(.5)
    assert sum(r['recent_mass'] for r in a['rows']) == pytest.approx(.5)
    assert set(r['issue_code'] for r in a['rows'] if r['recent_mass']>0)=={'000002','000003','000004'}
    future=h.issue_code.isin(b['excluded_issues'])
    h.loc[future,'actual']='L'
    h.loc[future,['last_fixture_cutoff','fixture_decision_ts']]='2010-01-01T00:00:00Z'
    mutated=draw_refresh_context(h,b,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**kwargs)
    assert a['rows']==mutated['rows']
    assert a['receipt']==mutated['receipt']
    j=draw_refresh_context_json(fixture_history().to_json(orient='records'),json.dumps(b),
        source_hashes_json=json.dumps(kwargs.pop('source_hashes')),**kwargs)
    assert json.loads(j)==a
    later=draw_refresh_context(fixture_history(),blocks()[1],Cutoff.decision_epoch('000008','2011-01-08T00:00Z'),source_hashes={'fixture':'a'*64},**kwargs)
    assert a['receipt']['cache_key']!=later['receipt']['cache_key']


def test_context_failure_paths():
    h=fixture_history(); b=blocks()[0]
    kw=dict(repository_root=ROOT,source_hashes={'fixture':'a'*64},delay_hours=24,recent_issues=3,minimum_ess=2)
    for bad in [pd.concat([h,h.iloc[:1]]),h.assign(actual='?'),h.assign(q_D=1),h.drop(columns='last_fixture_cutoff')]:
        with pytest.raises(TemporalContractError):
            draw_refresh_context(bad,b,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**kw)
    with pytest.raises(TemporalContractError):
        draw_refresh_context(h,b,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**dict(kw,minimum_ess=1000))
    with pytest.raises(TemporalContractError):
        draw_refresh_context(h,b,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**dict(kw,delay_hours=0))
    bad=copy.deepcopy(b);bad['fit_cutoff_ts']='2000-01-01T00:00Z'
    with pytest.raises(TemporalContractError):
        draw_refresh_context(h,bad,Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),**kw)


def test_prior_labels_do_not_expose_block_targets(tmp_path):
    import hashlib
    from src.temporal_learning.prior_labels import read_prior_label_rows
    from src.draw_refresh_context import draw_refresh_prior_history_json
    h=fixture_history();b=blocks()[0]
    path=tmp_path/'labels.csv'
    labels=h.rename(columns={'issue_code':'issue','actual':'actual_direction'})[['issue','slot','provider_id','actual_direction']]
    labels['status']='READY';labels.loc[labels.issue>='000006','actual_direction']='INVALID_TARGET_VALUE'
    labels.to_csv(path,index=False);sha=hashlib.sha256(path.read_bytes()).hexdigest()
    fx=h.drop(columns='actual').rename(columns={'issue_code':'issue'})
    rows=json.loads(draw_refresh_prior_history_json(fx.to_json(orient='records'),json.dumps(b),
        label_path=str(path),label_sha256=sha,delay_hours=24))
    assert len(rows)==12 and {r['issue_code'] for r in rows}=={'000001','000002','000003','000004'}
    assert {r['actual'] for r in rows}=={'D','W'}
    kw=dict(cutoff=Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts']),
        issue_clocks={'000001':'2011-01-01T00:00Z'},excluded_issues=[],delay_hours=24,issue_column='issue')
    assert len(read_prior_label_rows(path,sha,**kw))==3
    with pytest.raises(TemporalContractError):read_prior_label_rows(path,'0'*64,**kw)
    with pytest.raises(TemporalContractError):read_prior_label_rows(path,sha,**dict(kw,issue_column='missing'))


def test_block_context_rejects_mismatched_epoch_and_seal():
    from src.temporal_learning.frozen_blocks import prepare_block_context
    from src.temporal_learning.core import AvailabilityFilter, AvailabilityPolicy, PartitionPolicy, WeightingPolicy
    h=fixture_history().assign(label_available_ts=lambda x:x.fixture_decision_ts,issue_year=2011)
    b=blocks()[0];cut=Cutoff.decision_epoch(b['fit_issue'],b['fit_cutoff_ts'])
    kw=dict(block=b,repository_root=ROOT,source_hashes={'source':'a'*64},implementation_modules=(),
        implementation_distributions=(),availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy('TEST')),
        intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1))
    assert len(prepare_block_context(h,cut,**kw).eligible)==15
    with pytest.raises(TemporalContractError):
        prepare_block_context(h,Cutoff.decision_epoch('000007','2011-01-07T00:00Z'),**kw)
    bad=copy.deepcopy(b);bad['cadence']=99
    with pytest.raises(TemporalContractError):prepare_block_context(h,cut,**dict(kw,block=bad))
    with pytest.raises(TemporalContractError):prepare_block_context(h.drop(columns='issue_code'),cut,**kw)
