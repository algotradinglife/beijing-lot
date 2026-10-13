"""Publication receipt validation uses real shared contexts and full ledgers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from beidan_backend.opponent_goals import prepare_opponent_goals
from beidan_backend.temporal_learning import Cutoff
from beidan_backend.temporal_learning.serialized_opponent_fit import validate_serialized_opponent_fit

ROOT=Path(__file__).resolve().parents[4]


@pytest.fixture
def fitted():
    fixture=dict(fixture_id='26102:6',issue_id='26102',provider_id='TARGET',home_id='A',away_id='B',competition_id='35',neutral_reported=False)
    cutoff=Cutoff.decision_epoch('26102','2020-02-01T00:00:00Z')
    rows=[dict(row_key=f'r{i}',match_id=f'm{i}',event_date=f'2020-01-{i+1:02}',home_id='A' if i%2==0 else 'B',
        away_id='B' if i%2==0 else 'A',home_score=2,away_score=1,score_scope='SOURCE_PUBLISHED_FULL_TIME',competition_id='35',neutral_reported=False) for i in range(24)]
    prepared=prepare_opponent_goals(rows,fixture,['TARGET'],cutoff,{'source':'a'*64},ROOT,
        dict(recent_n=8,alpha=.5,minimum_recent_matches=12,minimum_recent_ess=8))
    receipt=dict(cutoff=cutoff.identity,fixture=fixture,intended_use='HISTORICAL_DIAGNOSTIC',target_label_optimization=False,
        admission=prepared['admission'].receipt.payload,
        admission_binding=prepared['receipts'][0]['source_hashes']['admission'],
        R_code_sha256=hashlib.sha256((ROOT/'packages/beidan/R/opponent_goals.R').read_bytes()).hexdigest())
    return dict(receipt=receipt,receipts=prepared['receipts'],ledgers=prepared['ledgers']),cutoff


def test_real_serialized_context_and_original_ledgers_validate(fitted):
    fit,cutoff=fitted
    assert validate_serialized_opponent_fit(fit,cutoff,ROOT) is None
    assert validate_serialized_opponent_fit(json.loads(json.dumps(fit)),cutoff,ROOT) is None


@pytest.mark.parametrize('mutation',['cutoff','future','binding','R_code','empty_ledger','masses','redistributed'])
def test_detached_or_mutated_learning_exports_fail(fitted,mutation):
    fit,cutoff=fitted;fit=deepcopy(fit)
    if mutation=='cutoff':fit['receipt']['admission']['target_issue']='26101'
    if mutation=='future':fit['receipts'][0]['maximum_source_time']='2020-02-01T00:00:00Z'
    if mutation=='binding':fit['receipt']['admission_binding']='f'*64
    if mutation=='R_code':fit['receipt']['R_code_sha256']='f'*64
    if mutation=='empty_ledger':fit['ledgers']=[]
    if mutation in ('masses','redistributed'):
        ledger=json.loads(fit['ledgers'][0]['ledger'])
        if mutation=='masses':ledger[0]['total_mass']=.7
        else:
            # Preserve aggregate mass and ESS, but exchange old/recent weights.
            for field in ['long_mass','recent_mass','total_mass','weight']:
                ledger[0][field],ledger[-1][field]=ledger[-1][field],ledger[0][field]
        fit['ledgers'][0]['ledger']=json.dumps(ledger)
    with pytest.raises(ValueError):validate_serialized_opponent_fit(fit,cutoff,ROOT)
