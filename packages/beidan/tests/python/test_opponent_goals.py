"""Shared chronology, weight mass and boundary invariance for opponent inputs."""
from pathlib import Path
from copy import deepcopy
import pytest
from beidan_backend.opponent_goals import prepare_opponent_goals, verify_opponent_preparation
from beidan_backend.temporal_learning import (Cutoff,prepare_learning_context,
    AvailabilityFilter,AvailabilityPolicy,PartitionPolicy,WeightingPolicy)

ROOT=Path(__file__).resolve().parents[4]
FIXTURE=dict(fixture_id='26102:6',issue_id='26102',provider_id='TARGET',
    home_id='A',away_id='B',competition_id='35',neutral_reported=False)
POLICY=dict(recent_n=8,alpha=.5,minimum_recent_matches=12,minimum_recent_ess=8)


@pytest.fixture
def rows():
    return [dict(row_key=f'r{i}',match_id=f'm{i}',event_date=f'2020-01-{i+1:02}',
        home_id='A' if i%2==0 else 'B',away_id='B' if i%2==0 else 'A',
        home_score=2,away_score=1,score_scope='SOURCE_PUBLISHED_FULL_TIME',
        competition_id='35',neutral_reported=False) for i in range(24)]


def test_mass_receipts_and_full_replay(rows):
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    out=prepare_opponent_goals(rows,FIXTURE,['TARGET','FUTURE'],cutoff,{'source':'a'*64},ROOT,POLICY)
    assert out['admitted_matches']==24
    assert len(out['observations'])==48
    assert len(out['contexts'])==4
    for c in out['contexts']:
        assert c.weight_ledger.long_mass.sum()==pytest.approx(.5)
        assert c.weight_ledger.recent_mass.sum()==pytest.approx(.5)
        assert c.receipt.payload['maximum_training_label_timestamp']<cutoff.cutoff_ts.isoformat()
    assert verify_opponent_preparation(out,FIXTURE,cutoff,ROOT) is out


def test_sparse_opponents_shrink_to_long_history(rows):
    out=prepare_opponent_goals(rows[:8],FIXTURE,['TARGET'],Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z'),{'source':'a'*64},ROOT,POLICY)
    assert all(not s['recent_active'] for s in out['support'])
    assert all(c.weight_ledger.recent_mass.sum()==0 for c in out['contexts'])


def test_future_and_exact_target_mutation_invariance(rows):
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    extra=[{**rows[0],'row_key':'future','match_id':'future','event_date':'2020-02-01'},
           {**rows[0],'row_key':'target','match_id':'TARGET'},
           {**rows[0],'row_key':'bad-future-roster','match_id':'FUTURE'}]
    a=prepare_opponent_goals(rows+extra,FIXTURE,['TARGET','FUTURE'],cutoff,{'source':'a'*64},ROOT,POLICY)
    changed=deepcopy(extra)
    for r in changed:r['home_score']=99;r['competition_id']='999'
    b=prepare_opponent_goals(rows+changed,FIXTURE,['TARGET','FUTURE'],cutoff,{'source':'a'*64},ROOT,POLICY)
    assert a['observations']==b['observations']
    assert a['support']==b['support']
    assert a['admission'].receipt.payload['cache_key']!=b['admission'].receipt.payload['cache_key']
    later=prepare_opponent_goals(rows+extra,FIXTURE,['TARGET','FUTURE'],Cutoff.decision_epoch('26102','2020-02-05T00:00:00Z'),{'source':'a'*64},ROOT,POLICY)
    assert later['admitted_matches']==25
    assert later['admission'].receipt.payload['cache_key']!=a['admission'].receipt.payload['cache_key']


def test_duplicate_agreement_and_conflict(rows):
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    duplicated=rows+[{**rows[0],'row_key':'duplicate'}]
    out=prepare_opponent_goals(duplicated,FIXTURE,['TARGET'],cutoff,{'source':'a'*64},ROOT,POLICY)
    assert out['duplicates_removed']==1
    duplicated[-1]['home_score']=3
    with pytest.raises(ValueError,match='Conflicting prior'):
        prepare_opponent_goals(duplicated,FIXTURE,['TARGET'],cutoff,{'source':'a'*64},ROOT,POLICY)


def test_export_mutations_are_rejected(rows):
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    out=prepare_opponent_goals(rows,FIXTURE,['TARGET'],cutoff,{'source':'a'*64},ROOT,POLICY)
    with pytest.raises(ValueError,match='fixture/cutoff'):
        verify_opponent_preparation(out,{**FIXTURE,'away_id':'C'},cutoff,ROOT)
    out['observations'][0]['weight']=10
    with pytest.raises(ValueError,match='Exported'):
        verify_opponent_preparation(out,FIXTURE,cutoff,ROOT)


def test_independently_valid_wrong_group_policy_is_rejected(rows):
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    out=prepare_opponent_goals(rows,FIXTURE,['TARGET'],cutoff,{'source':'a'*64},ROOT,POLICY)
    c=out['contexts'][0]
    different=prepare_learning_context(c.eligible,cutoff,source_hashes=c.receipt.payload['source_hashes'],
        repository_root=ROOT,implementation_modules=('beidan_backend.opponent_goals',),
        implementation_distributions=('pandas','numpy'),availability=AvailabilityFilter(
            AvailabilityPolicy.historical_proxy('DATE_PLUS_ONE_UTC_OPPONENT_NETWORK_DIAGNOSTIC'),
            data_available_column='data_available_ts'),intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1))
    out['contexts'][0]=different
    with pytest.raises(ValueError,match='Group weighting policy'):
        verify_opponent_preparation(out,FIXTURE,cutoff,ROOT)


@pytest.mark.parametrize('mutation', ['missing','score','venue','policy','cutoff'])
def test_invalid_input_fails_closed(rows,mutation):
    policy=deepcopy(POLICY);cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    if mutation=='missing':rows[0]['competition_id']=None
    if mutation=='score':rows[0]['home_score']=-1
    if mutation=='venue':rows[0]['neutral_reported']='false'
    if mutation=='policy':policy['alpha']=1
    if mutation=='cutoff':cutoff=None
    with pytest.raises(ValueError):
        prepare_opponent_goals(rows,FIXTURE,['TARGET'],cutoff,{'source':'a'*64},ROOT,policy)
