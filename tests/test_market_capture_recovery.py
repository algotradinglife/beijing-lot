"""Deterministic recovery policy checks; no live requests."""
import pytest

from src.market_capture_recovery import recovery_deadline


def test_cooldown_escalates_and_caps_only_local_delay():
    assert [recovery_deadline(n, 1000) - 1000 for n in range(5)] == [60, 300, 900, 1800, 1800]
    assert recovery_deadline(0, 1000, retry_after='7200') == 8200


def test_retry_dates_and_combined_hints():
    assert recovery_deadline(0, 0, retry_after='Thu, 01 Jan 1970 01:00:00 GMT') == 3600
    assert recovery_deadline(0, 0, retry_after=120, retry_after_date='1970-01-01T02:00:00Z') == 7200
    assert recovery_deadline(0, 1000, retry_after_date='1970-01-01T00:00:00Z') == 1060


@pytest.mark.parametrize('hint', ['bad', -1, True, float('nan'), float('inf'), '2026-01-01'])
def test_invalid_hints_fail_closed(hint):
    with pytest.raises(ValueError):
        recovery_deadline(0, 1000, retry_after=hint)


@pytest.mark.parametrize('attempt,now', [(-1, 0), (True, 0), (0, float('nan')), (0, 'now')])
def test_invalid_state_rejected(attempt, now):
    with pytest.raises(ValueError):
        recovery_deadline(attempt, now)

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from src.fundamentals_capture import capture_documents
from src.fundamentals_census import read_response
from src.fundamentals_market_history import market_document
from src.market_capture_recovery import (response_deadline, valid_market_probe,
    circuit_evidence, recover_market_step, run_supervised_market_history)


@pytest.fixture
def circuit(tmp_path):
    output = tmp_path/'capture'
    output.mkdir()
    identities = []
    for n in range(3):
        directory = output/'responses'/f'total-{n}'/'attempt-01'
        capture_documents([market_document('total:356283')], directory, max_attempts=1,
            fetch=lambda url, **k: SimpleNamespace(status_code=429, url=url,
                headers={'Retry-After': '120'}, content=b'{"retryAfter":180}'))
        manifest = directory/'capture-manifest.json'
        identities.append(f'{manifest}:{hashlib.sha256(manifest.read_bytes()).hexdigest()}')
    (output/'attempt-events.jsonl').write_text(''.join(json.dumps({'manifest_identity': i})+'\n' for i in identities))
    progress = dict(state='CIRCUIT_OPEN', circuit_tripped=True, blocked_streak=0,
                    new_responses=3, completed_issues=10, accounted_manifests=identities, circuit_events=identities)
    (output/'progress.json').write_text(json.dumps(progress))
    options = dict(ledger_path=tmp_path/'ledger.sqlite', budget_id='same-budget', request_budget=20,
                   min_interval_seconds=1, min_free_bytes=0)
    (output/'policy.json').write_text(json.dumps({**options, 'ledger_path':str(options['ledger_path'])}))
    return output, options, progress


def test_verified_circuit_hints_and_success_preserve_counters(circuit):
    output, options, before = circuit
    evidence = circuit_evidence(output)
    assert evidence['key'] == 'total:356283'
    assert response_deadline(evidence['responses'][0]['path'], 0, 1000) == 1180
    calls = []
    _, raw = read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=url, headers={}, content=raw)
    state = recover_market_step(output, now=1000, fetch=fetch, **options)
    assert state['next_probe_at'] == 1180 and not calls
    assert recover_market_step(output, now=1179, fetch=fetch, **options)['state'] == 'COOLDOWN'
    state = recover_market_step(output, now=1180, fetch=fetch, **options)
    assert state['state'] == 'RESUMED' and len(calls) == 1
    after = json.loads((output/'progress.json').read_text())
    assert all(after[k] == before[k] for k in ['new_responses','completed_issues','accounted_manifests'])
    assert after['circuit_tripped'] is False
    with sqlite3.connect(options['ledger_path']) as con:
        assert con.execute('SELECT cap, interval, used FROM budgets').fetchone() == (20, 1, 1)
    assert (output/'recovery'/state['identity']/'progress-before.json').exists()


def test_probe_failure_escalates_and_honors_header(circuit):
    output, options, _ = circuit
    recover_market_step(output, now=1000, **options)
    state = recover_market_step(output, now=1180,
        fetch=lambda url, **k: SimpleNamespace(status_code=429,url=url,
            headers={'Retry-After':'3600'},content=b'busy'), **options)
    assert state['state'] == 'COOLDOWN' and state['attempt'] == 1
    assert state['next_probe_at'] == 4780
    assert json.loads((output/'progress.json').read_text())['circuit_tripped']


@pytest.mark.parametrize('status,expected', [(200,'COOLDOWN'), (503,'COOLDOWN'), (403,'MANUAL_REQUIRED'), (404,'MANUAL_REQUIRED')])
def test_invalid_or_nontransient_probe_never_clears(circuit, status, expected):
    output, options, _ = circuit
    recover_market_step(output, now=0, **options)
    state = recover_market_step(output, now=180,
        fetch=lambda url, **k: SimpleNamespace(status_code=status,url=url,headers={},content=b'<html>challenge</html>'), **options)
    assert state['state'] == expected
    assert json.loads((output/'progress.json').read_text())['circuit_tripped']


def test_local_budget_exhaustion_remains_manual(circuit):
    output, options, _ = circuit
    with sqlite3.connect(options['ledger_path']) as con:
        con.execute('CREATE TABLE budgets(id TEXT PRIMARY KEY,cap INTEGER,interval REAL,used INTEGER)')
        con.execute('INSERT INTO budgets VALUES (?,?,?,?)', ('same-budget',20,1,20))
    recover_market_step(output, now=0, **options)
    with pytest.raises(ValueError, match='budget exhausted'):
        recover_market_step(output, now=180, **options)
    assert recover_market_step(output, now=300, **options)['state'] == 'MANUAL_REQUIRED'
    assert json.loads((output/'progress.json').read_text())['circuit_tripped']


def test_crash_probing_without_manifest_waits_instead_of_repeating(circuit):
    output, options, _ = circuit
    state = recover_market_step(output, now=0, **options)
    state.update(state='PROBING', probe_dir=str(output/'recovery'/'missing'))
    (output/'recovery.json').write_text(json.dumps(state))
    result = recover_market_step(output, now=180, **options)
    assert result['state'] == 'COOLDOWN' and result['attempt'] == 1
    assert result['next_probe_at'] == 480
    assert not options['ledger_path'].exists()


def test_worker_lock_and_policy_and_disk_fail_closed(circuit):
    import fcntl
    output, options, _ = circuit
    with (output/'worker.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            recover_market_step(output,now=0,**options)
    with pytest.raises(ValueError,match='policy changed'):
        recover_market_step(output,now=0,**{**options,'request_budget':21})
    recover_market_step(output,now=0,**options)
    with pytest.raises(ValueError,match='disk space low'):
        recover_market_step(output,now=180,disk_free=lambda p:-1,**options)
    assert json.loads((output/'progress.json').read_text())['circuit_tripped']


def test_circuit_hash_and_missing_evidence_rejected(circuit):
    output, options, _ = circuit
    manifest = output/'responses'/'total-2'/'attempt-01'/'capture-manifest.json'
    manifest.write_text('{}')
    with pytest.raises(ValueError,match='manifest changed'):
        circuit_evidence(output)
    (output/'progress.json').write_text(json.dumps({'circuit_events':[]}))
    with pytest.raises(ValueError,match='no verified'):
        circuit_evidence(output)


def test_real_probe_parsers_require_correct_identity():
    assert valid_market_probe('tests/fixtures/fundamentals_titan_total/356283.json','total:356283')
    assert not valid_market_probe('tests/fixtures/fundamentals_titan_total/356283.json','total:356284')
    assert valid_market_probe('tests/fixtures/fundamentals_titan_euro/357841.json','euro:357841')


def test_supervisor_restarts_runner_only_after_cooldown(monkeypatch, circuit):
    import src.market_capture_recovery as m
    output, options, _ = circuit
    monkeypatch.setattr(m,'check_layout',lambda p: {'data_root':str(output.parent)})
    calls=[]
    for name in ('plan','index','contract'):
        (output.parent/name).write_text('{}')
    def runner(*args, **kwargs):
        calls.append('run')
        return {'state':'CIRCUIT_OPEN' if len(calls)==1 else 'OBSERVED_INVENTORY_ATTEMPTED'}
    monkeypatch.setattr(m,'run_market_history',runner)
    stamp=[1000]
    sleeps=[]
    def sleep(s):
        sleeps.append(s);stamp[0]+=s
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    result = run_supervised_market_history(output.parent/'plan',output.parent/'index',output,
        contract=output.parent/'contract',workers=5,wall_clock=lambda:stamp[0],sleeper=sleep,
        fetch=lambda url,**k:SimpleNamespace(status_code=200,url=url,headers={},content=raw),**options)
    assert result['state']=='OBSERVED_INVENTORY_ATTEMPTED' and len(calls)==2
    assert sum(sleeps)>=180 and max(sleeps)<=30


def test_ready_restart_reverifies_probe_without_duplicate_request(circuit, monkeypatch):
    import src.market_capture_recovery as m
    output, options, _ = circuit
    recover_market_step(output, now=0, **options)
    _, raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    original=m.atomic_json
    def interrupt_before_clear(path, value):
        if Path(path).name=='progress.json':
            raise RuntimeError('simulated crash')
        return original(path,value)
    monkeypatch.setattr(m,'atomic_json',interrupt_before_clear)
    with pytest.raises(RuntimeError,match='simulated crash'):
        recover_market_step(output,now=180,
            fetch=lambda url,**k:SimpleNamespace(status_code=200,url=url,headers={},content=raw),**options)
    assert json.loads((output/'recovery.json').read_text())['state']=='READY'
    monkeypatch.setattr(m,'atomic_json',original)
    assert recover_market_step(output,now=200,**options)['state']=='RESUMED'
    with sqlite3.connect(options['ledger_path']) as con:
        assert con.execute('SELECT used FROM budgets').fetchone()[0]==1


def test_both_rate_limited_endpoints_require_sequential_probes(circuit):
    output, options, _ = circuit
    # Replace the final committed event with a valid euro 429; all three still block.
    directory=output/'responses'/'euro-357841'/'attempt-01'
    capture_documents([market_document('euro:357841')],directory,max_attempts=1,
        fetch=lambda url,**k:SimpleNamespace(status_code=429,url=url,headers={},content=b'busy'))
    p=directory/'capture-manifest.json'
    lines=(output/'attempt-events.jsonl').read_text().splitlines()
    lines[-1]=json.dumps(dict(manifest_identity=f'{p}:{hashlib.sha256(p.read_bytes()).hexdigest()}'))
    (output/'attempt-events.jsonl').write_text('\n'.join(lines)+'\n')
    progress=json.loads((output/'progress.json').read_text())
    progress['circuit_events']=[json.loads(x)['manifest_identity'] for x in lines]
    (output/'progress.json').write_text(json.dumps(progress))
    state=recover_market_step(output,now=0,**options)
    assert len(state['pending_keys'])==2
    calls=[]
    def fetch(url,**kwargs):
        calls.append(url)
        path=('tests/fixtures/fundamentals_titan_euro/357841.json' if url.endswith('.js') else
              'tests/fixtures/fundamentals_titan_total/356283.json')
        return SimpleNamespace(status_code=200,url=url,headers={},content=read_response(Path(path))[1])
    first=recover_market_step(output,now=180,fetch=fetch,**options)
    assert first['state']=='COOLDOWN' and len(calls)==1
    assert json.loads((output/'progress.json').read_text())['circuit_tripped']
    second=recover_market_step(output,now=181,fetch=fetch,**options)
    assert second['state']=='RESUMED' and len(calls)==2


def test_actual_first_trip_cannot_be_hidden_by_later_429(circuit):
    from src.fundamentals_market_history import record_circuit_response
    output, options, _ = circuit
    target=output/'responses'/'forbidden'/'attempt-01'
    capture_documents([market_document('total:356283')],target,max_attempts=1,
        fetch=lambda url,**k:SimpleNamespace(status_code=403,url=url,headers={},content=b'forbidden'))
    p=target/'capture-manifest.json'
    identity=f'{p}:{hashlib.sha256(p.read_bytes()).hexdigest()}'
    prior=json.loads((output/'progress.json').read_text())
    state={}
    for ident,status in [(identity,403)]+[(i,429) for i in prior['circuit_events']]:
        record_circuit_response(state,ident,status)
    assert state['circuit_events'][0]==identity
    (output/'progress.json').write_text(json.dumps(state))
    with pytest.raises(ValueError,match='manual investigation'):
        circuit_evidence(output)


def test_unjournaled_third_block_is_reconciled_for_recovery(circuit):
    from src.fundamentals_market_history import _reconcile_uncheckpointed_attempts
    output, options, progress = circuit
    events=progress['circuit_events']
    progress.update(circuit_tripped=False,circuit_events=[],blocked_events=events[:2],
                    blocked_streak=2,accounted_manifests=events[:2],new_responses=2)
    lines=(output/'attempt-events.jsonl').read_text().splitlines()
    (output/'attempt-events.jsonl').write_text('\n'.join(lines[:2])+'\n')
    _reconcile_uncheckpointed_attempts(progress,output)
    assert progress['circuit_tripped'] and progress['new_responses']==3
    assert len(progress['circuit_events'])==3
    (output/'progress.json').write_text(json.dumps(progress))
    assert len(circuit_evidence(output)['responses'])==3


def test_supervisor_commits_receipt_before_resuming_after_clear_crash(circuit, monkeypatch):
    import src.market_capture_recovery as m
    output,options,_=circuit
    recover_market_step(output,now=0,**options)
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    original=m.atomic_json
    def crash(path,value):
        if Path(path).name=='recovery.json' and value.get('state')=='RESUMED':
            raise RuntimeError('after-clear crash')
        original(path,value)
    monkeypatch.setattr(m,'atomic_json',crash)
    with pytest.raises(RuntimeError,match='after-clear crash'):
        recover_market_step(output,now=180,fetch=lambda url,**k:SimpleNamespace(status_code=200,url=url,headers={},content=raw),**options)
    state=json.loads((output/'recovery.json').read_text())
    receipt=output/'recovery'/state['identity']/'receipt.json'
    assert not receipt.exists()
    assert not json.loads((output/'progress.json').read_text())['circuit_tripped']
    monkeypatch.setattr(m,'atomic_json',original)
    monkeypatch.setattr(m,'check_layout',lambda p:dict(data_root=str(output.parent)))
    for name in ('plan','index','contract'):
        (output.parent/name).write_text('{}')
    def runner(*args,**kwargs):
        assert receipt.exists()
        assert json.loads(receipt.read_text())['state']=='RESUMED'
        return dict(state='OBSERVED_INVENTORY_ATTEMPTED')
    monkeypatch.setattr(m,'run_market_history',runner)
    result=run_supervised_market_history(output.parent/'plan',output.parent/'index',output,
        contract=output.parent/'contract',workers=5,**options)
    assert result['state']=='OBSERVED_INVENTORY_ATTEMPTED'


def test_inflight_transport_failure_after_trip_preserves_recovery(circuit):
    import requests
    from src.fundamentals_market_history import record_circuit_response
    output, options, progress = circuit
    def timeout(url,**kwargs):
        raise requests.Timeout('offline')
    target=output/'responses'/'timeout'/'attempt-01'
    capture_documents([market_document('total:356283')],target,max_attempts=1,fetch=timeout)
    p=target/'capture-manifest.json'
    record_circuit_response(progress,f'{p}:{hashlib.sha256(p.read_bytes()).hexdigest()}',None)
    (output/'progress.json').write_text(json.dumps(progress))
    assert recover_market_step(output,now=0,**options)['state']=='COOLDOWN'
