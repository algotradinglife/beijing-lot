import hashlib
import json

import pytest

from src.market_retirement_outcome import verify_market_retirement_outcome


@pytest.fixture
def outcome(tmp_path, monkeypatch):
    plan = dict(batch_id='batch', candidates=[dict(path='markets/raw/a.json')])
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    inventory = {'response': {'records': 3, 'sha256': 'a' * 64}}
    monkeypatch.setattr('src.market_retirement_outcome.query_market_batch_source_inventories',
                        lambda database, *, batch_id: inventory)
    return dict(data_root=tmp_path, plan=plan,
                result=dict(state='RAW_RETIREMENT_COMPLETE', plan_sha256=digest, removed_files=1),
                journal=dict(plan_sha256=digest, entries={'markets/raw/a.json': 'REMOVED'}),
                database=tmp_path/'database.sqlite', batch_id='batch', expected_inventories=inventory.copy())


def test_verified_absence_and_inventory(outcome):
    result = verify_market_retirement_outcome(**outcome)
    assert result['state'] == 'RETIREMENT_FILES_AND_SQLITE_VERIFIED'
    assert (result['removed_files'], result['sources']) == (1, 1)


@pytest.mark.parametrize('change', ['state', 'count', 'boolean_count', 'digest', 'journal', 'inventory', 'batch'])
def test_reject_inconsistent_evidence(outcome, change):
    if change == 'state': outcome['result']['state'] = 'PENDING'
    if change == 'count': outcome['result']['removed_files'] = 2
    if change == 'boolean_count': outcome['result']['removed_files'] = True
    if change == 'digest': outcome['journal']['plan_sha256'] = 'b' * 64
    if change == 'journal': outcome['journal']['entries']['markets/raw/a.json'] = 'DELETE_INTENT'
    if change == 'inventory': outcome['expected_inventories'] = {}
    if change == 'batch': outcome['batch_id'] = 'other'
    with pytest.raises(ValueError): verify_market_retirement_outcome(**outcome)


@pytest.mark.parametrize('symlink', [False, True])
def test_reject_present_or_dangling_file(outcome, symlink):
    path = outcome['data_root']/'markets/raw/a.json'
    path.parent.mkdir(parents=True)
    if symlink: path.symlink_to(path.parent/'missing.json')
    else: path.write_text('{}')
    with pytest.raises(ValueError): verify_market_retirement_outcome(**outcome)


def test_propagate_database_failure(outcome, monkeypatch):
    def fail(database, *, batch_id):
        raise ValueError('stored market record hash mismatch')
    monkeypatch.setattr('src.market_retirement_outcome.query_market_batch_source_inventories', fail)
    with pytest.raises(ValueError, match='record hash mismatch'):
        verify_market_retirement_outcome(**outcome)


@pytest.mark.parametrize('name', ['markets/raw/./a.json', 'markets//raw/a.json',
                                 '../a.json', '/outside/a.json', 'markets/a.json'])
def test_reject_unsafe_or_aliased_candidate(outcome, name):
    outcome['plan']['candidates'].append(dict(path=name))
    digest = hashlib.sha256(json.dumps(outcome['plan'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    outcome['result'].update(plan_sha256=digest, removed_files=2)
    outcome['journal']['plan_sha256'] = digest
    outcome['journal']['entries'][name] = 'REMOVED'
    with pytest.raises(ValueError, match='unsafe retirement path'):
        verify_market_retirement_outcome(**outcome)
