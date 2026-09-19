"""Market batch policy, raw replay, scope and recovery contracts; no live HTTP."""
import gzip
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from bs4 import BeautifulSoup

from src.fundamentals_bulk_capture import atomic_json
from src.fundamentals_capture import capture_documents
from src.fundamentals_census import read_response
from src.fundamentals_history_capture import capture_rate_source
from src.fundamentals_market_history import (index_market_captures, issue_market_scope,
    market_document, market_key, plan_market_history, run_market_history, verify_market_receipt)


@pytest.fixture
def study(tmp_path):
    url = 'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    soup = BeautifulSoup(gzip.decompress(Path('tests/fixtures/fundamentals_census/roster-130511-type8.html.gz').read_bytes()), 'html.parser')
    for row in soup.select('tr[id^="row_"]')[1:]:
        row.decompose()
    roster_dir = tmp_path / 'rosters' / '130511'
    capture_documents([{'source': 'nowscore', 'url': url, 'filename': 'response.json'}], roster_dir / 'capture',
        fetch=lambda *a, **k: SimpleNamespace(status_code=200, url=url, headers={}, content=str(soup).encode()))
    atomic_json(roster_dir / 'status.json', {'roster_path': str(roster_dir / 'capture/response.json'), 'processing_complete': True})
    manifest = tmp_path / 'inventory.json'
    atomic_json(manifest, {'schema': 'bj411_historical_inventory_v1', 'historical_before': '2020-01-01T00:00:00Z',
        'completeness': 'OBSERVED', 'issues': [{'issue': '130511', 'roster_url': url}]})
    plan = plan_market_history(manifest, tmp_path / 'rosters', {})
    atomic_json(tmp_path / 'plan.json', plan)
    atomic_json(tmp_path / 'index.json', {})
    calls, stamp = [], [1000.]
    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=url, headers={}, content=b'raw unparsed market')
    def sleep(seconds):
        stamp[0] += seconds
    options = {'ledger_path': tmp_path / 'ledger.sqlite', 'budget_id': 'test', 'request_budget': 100,
               'min_free_bytes': 0, 'fetch': fetch, 'sleeper': sleep, 'wall_clock': lambda: stamp[0]}
    return tmp_path, options, calls


def test_endpoints_are_exact_and_shared_titan_rate_key():
    for key in ('euro:123', 'total:123'):
        doc = market_document(key)
        assert market_key(doc['url']) == key
        assert capture_rate_source(doc) == 'titan'
    assert capture_rate_source({'source': 'titan', 'url': 'https://zq.titan007.com/a'}) == 'titan'
    assert market_key('https://example.org/123.js') is None
    for key in ('bad:12', 'euro:../../x', 'total:'):
        with pytest.raises(ValueError):
            market_document(key)
    for doc in (None, {'source': 'independent', 'url': 'https://r.jina.ai/https://evil.test'},
                {'source': 'independent', 'url': 'https://1x2d.titan007.com/1.js?x=2'}):
        with pytest.raises(ValueError):
            capture_rate_source(doc)


def test_scope_replays_evidence_bound_name_correction(study):
    from datetime import datetime, timezone
    root, _, _ = study
    directory = root / 'rosters/130511'
    meta, raw = read_response(directory / 'capture/response.json')
    soup = BeautifulSoup(raw, 'html.parser')
    soup.select_one('#HomeTeam_844632').clear()
    original = str(soup).encode()
    capture_documents([dict(source='nowscore', url=meta['url'], filename='response.json')],
        directory / 'missing', fetch=lambda *a, **k: SimpleNamespace(
            status_code=200, url=meta['url'], headers={}, content=original))
    evidence = root / 'evidence.txt'
    evidence.write_bytes(b'checked independent identity')
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    correction = root / 'correction.json'
    atomic_json(correction, dict(source_sha256=hashlib.sha256(original).hexdigest(),
        evidence=[dict(path=str(evidence), sha256=digest)],
        corrections=[dict(slot=1, provider_id='844632', role='home', team_id='741',
                          name='FC首尔', evidence_sha256=[digest])]))
    atomic_json(directory / 'status.json', dict(roster_path=str(directory / 'missing/response.json'),
        roster_name_correction=dict(path=str(correction), sha256=hashlib.sha256(correction.read_bytes()).hexdigest())))
    entry = dict(issue='130511', roster_url=meta['url'])
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = issue_market_scope(entry, root / 'rosters', cutoff)
    assert result['state'] == 'SCOPED'
    assert result['fixtures'][0]['home'] == 'FC首尔'
    assert read_response(directory / 'missing/response.json')[1] == original
    evidence.write_bytes(b'tampered')
    assert issue_market_scope(entry, root / 'rosters', cutoff)['state'] == 'ROSTER_INVALID'
    correction.write_bytes(b'changed')
    assert issue_market_scope(entry, root / 'rosters', cutoff)['state'] == 'ROSTER_INVALID'


def test_complete_restart_hash_and_reuse(study):
    root, options, calls = study
    run = lambda: run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    result = run()
    assert result['state'] == 'OBSERVED_INVENTORY_ATTEMPTED'
    assert len(calls) == 2
    assert run()['completed_issues'] == 1 and len(calls) == 2
    receipt = json.loads((root/'out/batch-0001/130511-receipt.json').read_text())
    assert len(receipt['rows']) == 2 and receipt['acceptance'] == 'NOT_REVIEWED'
    cache = index_market_captures((root/'out').rglob('capture-manifest.json'))
    plan = plan_market_history(root/'inventory.json', root/'rosters', cache)
    assert len(plan['reused_issues']) == 1 and plan['batches'] == []
    sample = next(iter(cache.values()))['selected']
    Path(sample['path']).write_text('{}')
    with pytest.raises(ValueError, match='hash'):
        run()
    atomic_json(root/'reused-plan.json', plan)
    with pytest.raises(ValueError, match='reused roster|market response'):
        run_market_history(root/'reused-plan.json', root/'index.json', root/'reused-out', **options)


def test_replaying_saved_403_attempts_does_not_raise_circuit_streak(study):
    root, options, calls = study
    original = options['fetch']
    def fetch(url, **kw):
        response = original(url, **kw)
        response.status_code = 403
        return response
    options['fetch'] = fetch
    first = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert first['blocked_streak'] == 2 and len(calls) == 2
    second = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert second['state'] == 'OBSERVED_INVENTORY_ATTEMPTED'
    assert second['blocked_streak'] == 2 and len(calls) == 2


def test_restart_reconciles_manifest_written_before_progress_checkpoint(study, monkeypatch):
    root, options, calls = study
    original = options['fetch']
    def fetch(url, **kw):
        response = original(url, **kw)
        response.status_code = 403
        return response
    options['fetch'] = fetch
    import src.fundamentals_market_history as module
    original_atomic = module.atomic_json
    def crash(path, payload):
        if path.name == 'progress.json' and payload.get('blocked_streak') == 1:
            raise KeyboardInterrupt()
        return original_atomic(path, payload)
    monkeypatch.setattr(module, 'atomic_json', crash)
    with pytest.raises(KeyboardInterrupt):
        run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    monkeypatch.setattr(module, 'atomic_json', original_atomic)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    # The first response was committed before the progress checkpoint; the
    # restart must count it exactly once before processing the second market.
    assert result['state'] == 'OBSERVED_INVENTORY_ATTEMPTED'
    assert result['blocked_streak'] == 2 and len(calls) == 2


def test_reused_issue_publishes_discoverable_receipt(study):
    root, options, _ = study
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    cache = index_market_captures((root/'out').rglob('capture-manifest.json'))
    plan = plan_market_history(root/'inventory.json', root/'rosters', cache)
    atomic_json(root/'reuse-plan.json', plan)
    atomic_json(root/'reuse-index.json', cache)
    run_market_history(root/'reuse-plan.json', root/'reuse-index.json', root/'reuse-out', **options)
    receipt = root/'reuse-out/reused-issues/130511-receipt.json'
    assert receipt.exists() and json.loads(receipt.read_text())['provenance'] == 'REUSED_VERIFIED'


@pytest.mark.parametrize('kind, expected', [('404', 2), ('503', 4), ('transport', 4)])
def test_bounded_failure_is_not_acceptance(study, kind, expected):
    root, options, calls = study
    original = options['fetch']
    def fetch(url, **kw):
        response = original(url, **kw)
        if kind == 'transport':
            raise requests.Timeout('offline')
        response.status_code = int(kind)
        return response
    options['fetch'] = fetch
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert result['state'] == 'OBSERVED_INVENTORY_ATTEMPTED' and len(calls) == expected
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert len(calls) == expected


def test_disk_budget_policy_and_scope_fail_closed(study):
    root, options, calls = study
    options['min_free_bytes'] = 10
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', disk_free=lambda p: 0, **options)
    assert result['state'] == 'DISK_SPACE_LOW' and not calls
    options['request_budget'] = 1
    with pytest.raises(ValueError, match='policy'):
        run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out2', **options)
    assert result['state'] == 'BUDGET_EXHAUSTED' and len(calls) == 1
    plan = json.loads((root/'plan.json').read_text())
    plan['batches'] = []
    atomic_json(root/'bad-plan.json', plan)
    with pytest.raises(ValueError, match='partition'):
        run_market_history(root/'bad-plan.json', root/'index.json', root/'out3', **options)


def test_upstream_missing_invalid_and_batch_size(study, monkeypatch):
    root, options, _ = study
    import src.fundamentals_market_history as module
    inventory, cutoff, _ = module.load_inventory(root/'inventory.json')
    entry = inventory['issues'][0]
    assert issue_market_scope(entry, root/'absent', cutoff) is None
    atomic_json(root/'absent/130511/status.json', {'processing_complete': True, 'roster_error': '404'})
    assert issue_market_scope(entry, root/'absent', cutoff)['state'] == 'ROSTER_UNAVAILABLE'
    assert issue_market_scope(entry, root/'rosters', cutoff.replace(year=2010))['state'] == 'ROSTER_INVALID'
    inventory['issues'] = [{'issue': str(i), 'roster_url': entry['roster_url'].replace('130511', str(i))} for i in range(1, 206)]
    atomic_json(root/'inventory.json', inventory)
    plan = plan_market_history(root/'inventory.json', root/'absent', {})
    assert list(map(len, plan['batches'])) == [100, 100, 5]


def test_interrupted_request_uses_remaining_attempt_only(study):
    root, options, calls = study
    directory = root/'out/responses/euro-844632'
    atomic_json(directory/'attempt-01.json', {'url': market_document('euro:844632')['url'],
        'error': 'INTERRUPTED_OR_RESERVED', 'received_at_utc': '2026-01-01T00:00:00+00:00'})
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert len(calls) == 2
    assert not (directory/'attempt-01/capture-manifest.json').exists()
    assert (directory/'attempt-02/capture-manifest.json').exists()


def test_repeated_provider_id_preserves_fixture_occurrences(study):
    root, options, calls = study
    status_path = root/'rosters/130511/status.json'
    original = json.loads(status_path.read_text())
    meta, raw = read_response(Path(original['roster_path']))
    soup = BeautifulSoup(raw, 'html.parser')
    first = soup.select_one('tr[id^="row_"]')
    second = copy.deepcopy(first)
    second['id'], second['matchid'] = 'row_2', '2'
    first.insert_after(second)
    output = root/'duplicated-roster'
    capture_documents([{'source': 'nowscore', 'url': meta['url'], 'filename': 'response.json'}], output,
        fetch=lambda *a, **k: SimpleNamespace(status_code=200, url=meta['url'], headers={}, content=str(soup).encode()))
    atomic_json(status_path, {'roster_path': str(output/'response.json'), 'processing_complete': True})
    atomic_json(root/'plan.json', plan_market_history(root/'inventory.json', root/'rosters', {}))
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    rows = json.loads((root/'out/batch-0001/130511-receipt.json').read_text())['rows']
    assert len(rows) == 4 and {row['slot'] for row in rows} == {1, 2}
    assert len(calls) == 2


def test_bad_team_identity_can_be_captured_but_is_flagged(study):
    root, options, calls = study
    status_path = root/'rosters/130511/status.json'
    original = json.loads(status_path.read_text())
    meta, raw = read_response(Path(original['roster_path']))
    soup = BeautifulSoup(raw, 'html.parser')
    home = soup.select_one('a[id^="HomeTeam_"]')
    away = soup.select_one('a[id^="GuestTeam_"]')
    away['onmouseover'] = home['onmouseover']
    output = root/'same-team-roster'
    capture_documents([{'source': 'nowscore', 'url': meta['url'], 'filename': 'response.json'}], output,
        fetch=lambda *a, **k: SimpleNamespace(status_code=200, url=meta['url'], headers={}, content=str(soup).encode()))
    atomic_json(status_path, {'roster_path': str(output/'response.json'), 'processing_complete': True})
    atomic_json(root/'plan.json', plan_market_history(root/'inventory.json', root/'rosters', {}))
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    scope = json.loads((root/'out/batch-0001/130511-scope.json').read_text())
    assert scope['fixtures'][0]['identity_error'] == 'SAME_HOME_AWAY_IDENTITY'
    assert len(calls) == 2

def test_explicit_interval_is_enforced_and_immutable(study):
    import sqlite3
    root, options, calls = study
    options["min_interval_seconds"] = 1.0
    run_market_history(root/"plan.json", root/"index.json", root/"out", **options)
    assert len(calls) == 2
    policy = json.loads((root/"out/policy.json").read_text())
    assert policy["min_interval_seconds"] == 1.0
    with sqlite3.connect(root/"ledger.sqlite") as con:
        assert con.execute("SELECT interval,used FROM budgets").fetchone() == (1.0, 2)
        assert con.execute("SELECT started FROM source_clock").fetchone()[0] == 1001.0
    options["min_interval_seconds"] = 2.0
    with pytest.raises(ValueError, match="policy"):
        run_market_history(root/"plan.json", root/"index.json", root/"out", **options)


def test_parallel_overlap_global_rate_and_restart(study):
    import threading
    import sqlite3
    root, options, calls = study
    import time
    options.pop("wall_clock")
    options["sleeper"] = time.sleep
    barrier = threading.Barrier(2)
    starts = []
    guard = threading.Lock()
    def fetch(url, **kwargs):
        with guard:
            starts.append(time.monotonic())
            calls.append(url)
        barrier.wait(timeout=10)
        return SimpleNamespace(status_code=200, url=url, headers={}, content=b'parallel')
    options.update(fetch=fetch, workers=5, min_interval_seconds=1)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert result['new_responses'] == 2
    assert len(calls) == 2 and starts[1] - starts[0] >= 0.98
    with sqlite3.connect(root/'ledger.sqlite') as con:
        assert con.execute('SELECT used FROM budgets').fetchone()[0] == 2
    run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert len(calls) == 2


@pytest.mark.parametrize('workers', [0, 6, True, 1.5])
def test_invalid_workers_before_writes(study, workers):
    root, options, calls = study
    with pytest.raises(ValueError, match='workers'):
        run_market_history(root/'plan.json', root/'index.json', root/'out', workers=workers, **options)
    assert not (root/'out').exists()


def test_parallel_budget_is_not_multiplied(study):
    import sqlite3
    root, options, calls = study
    options.update(workers=5, request_budget=1, min_interval_seconds=1)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert result['state'] == 'BUDGET_EXHAUSTED'
    assert result['new_responses'] == len(calls) == 1
    with sqlite3.connect(root/'ledger.sqlite') as con:
        assert con.execute('SELECT used FROM budgets').fetchone()[0] == 1


def test_new_epoch_reuses_receipts_and_preserves_budget(study):
    from src.market_capture_epoch import prepare_market_epoch
    import sqlite3
    root, options, calls = study
    run_market_history(root/'plan.json', root/'index.json', root/'old', **options)
    receipt = prepare_market_epoch(root/'plan.json', root/'index.json', root/'old', root/'inputs', root/'new')
    assert receipt['reused_issues'] == 1 and receipt['pending_issues'] == 0
    assert receipt['budget_id'] == 'test'
    with pytest.raises(ValueError, match='inherited'):
        run_market_history(root/'inputs/plan.json', root/'inputs/existing-captures.json', root/'new',
            **{**options, 'budget_id': 'fresh-budget-not-authorized'})
    run_market_history(root/'inputs/plan.json', root/'inputs/existing-captures.json', root/'new', workers=5, **options)
    assert len(calls) == 2
    with sqlite3.connect(root/'ledger.sqlite') as con:
        assert con.execute('SELECT used FROM budgets').fetchone()[0] == 2
    with pytest.raises(FileExistsError):
        prepare_market_epoch(root/'plan.json', root/'index.json', root/'old', root/'inputs', root/'new')


def test_epoch_without_any_response_directory(study):
    from src.market_capture_epoch import prepare_market_epoch
    root, options, calls = study
    run_market_history(root/'plan.json', root/'index.json', root/'old', disk_free=lambda p: 0, **{**options, 'min_free_bytes': 1})
    assert not (root/'old/responses').exists()
    result = prepare_market_epoch(root/'plan.json', root/'index.json', root/'old', root/'inputs', root/'new')
    assert result['indexed_keys'] == 0 and result['pending_issues'] == 1
    atomic_json(root/'old/progress.json', dict(circuit_tripped=True))
    with pytest.raises(ValueError, match='circuit'):
        prepare_market_epoch(root/'plan.json', root/'index.json', root/'old', root/'other-inputs', root/'other-new')


def test_epoch_reconciles_uncheckpointed_circuit_before_publication(study):
    from src.market_capture_epoch import prepare_market_epoch
    from src.fundamentals_market_history import _capture_manifest_identity
    root, options, calls = study
    run_market_history(root/'plan.json', root/'index.json', root/'old', **options)
    progress = json.loads((root/'old/progress.json').read_text())
    progress['blocked_streak'] = 2
    atomic_json(root/'old/progress.json', progress)
    target = root/'old/responses/euro-999/attempt-01'
    url = 'https://1x2d.titan007.com/999.js'
    capture_documents([dict(source='independent', url=url, filename='page.json')], target,
        max_attempts=1, fetch=lambda *a, **kw: SimpleNamespace(status_code=429, url=url, headers={}, content=b'blocked'))
    with (root/'old/attempt-events.jsonl').open('a') as journal:
        journal.write(json.dumps(dict(manifest_identity=_capture_manifest_identity(target/'capture-manifest.json')))+'\n')
    with pytest.raises(ValueError, match='circuit'):
        prepare_market_epoch(root/'plan.json', root/'index.json', root/'old', root/'inputs', root/'new')
    assert not (root/'new').exists()


def test_epoch_carries_only_remaining_attempt(study):
    from src.market_capture_epoch import prepare_market_epoch
    root, options, calls = study
    # Create a stopped epoch with a committed first-attempt reservation only.
    old = root/'old'
    old.mkdir()
    atomic_json(old/'policy.json', dict(plan_sha256=hashlib.sha256((root/'plan.json').read_bytes()).hexdigest(),
        index_sha256=hashlib.sha256((root/'index.json').read_bytes()).hexdigest(),
        budget_id='test', request_budget=100, ledger_path=str(root/'ledger.sqlite'), min_interval_seconds=5))
    atomic_json(old/'progress.json', {})
    atomic_json(old/'responses/euro-844632/attempt-01.json', dict(url='https://1x2d.titan007.com/844632.js',
        error='INTERRUPTED_OR_RESERVED', received_at_utc='2020-01-01T00:00:00+00:00'))
    receipt = prepare_market_epoch(root/'plan.json', root/'index.json', old, root/'inputs', root/'new')
    assert receipt['carried_first_attempts'] == 1
    assert receipt['output'] == str((root/'new').resolve())
    carried_name = 'responses/euro-844632/attempt-01.json'
    assert receipt['carried_files'] == {
        carried_name: hashlib.sha256((root/'new'/carried_name).read_bytes()).hexdigest()}
    run_market_history(root/'inputs/plan.json', root/'inputs/existing-captures.json', root/'new', **options)
    assert not (root/'new/responses/euro-844632/attempt-01/capture-manifest.json').exists()
    assert (root/'new/responses/euro-844632/attempt-02/capture-manifest.json').exists()
    assert len(calls) == 2


def test_crash_replay_uses_callback_order_for_sticky_trip(tmp_path):
    from src.fundamentals_market_history import _capture_manifest_identity, _reconcile_uncheckpointed_attempts
    paths = []
    # Receive success first, but checkpoint the blocked callback first.
    for identifier, status in [(100, 200), (101, 429)]:
        target = tmp_path/f'responses/euro-{identifier}/attempt-01'
        url = f'https://1x2d.titan007.com/{identifier}.js'
        capture_documents([dict(source='independent', url=url, filename='page.json')], target,
            max_attempts=1, fetch=lambda *a, status=status, url=url, **kw:
                SimpleNamespace(status_code=status, url=url, headers={}, content=b'replay'))
        paths.append(target/'capture-manifest.json')
    (tmp_path/'attempt-events.jsonl').write_text(''.join(json.dumps(dict(
        manifest_identity=_capture_manifest_identity(path)))+'\n' for path in reversed(paths)))
    state = dict(new_responses=0, blocked_streak=2, accounted_manifests=[])
    _reconcile_uncheckpointed_attempts(state, tmp_path)
    assert state['circuit_tripped'] is True
    assert state['blocked_streak'] == 0 and state['new_responses'] == 2
    _reconcile_uncheckpointed_attempts(state, tmp_path)
    assert state['new_responses'] == 2


@pytest.mark.parametrize('status', [403, 429])
def test_parallel_circuit_stops_after_current_wave(study, monkeypatch, status):
    import src.fundamentals_market_history as module
    root, options, calls = study
    original = module.issue_market_scope
    def scope(*args):
        result = original(*args)
        fixture = result['fixtures'][0]
        result['fixtures'] = [{**fixture, 'slot': str(i), 'provider_id': str(900+i)} for i in range(6)]
        return result
    monkeypatch.setattr(module, 'issue_market_scope', scope)
    def blocked(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=status, url=url, headers={}, content=b'blocked')
    (root/'out').mkdir()
    atomic_json(root/'out/progress.json', dict(completed_batches=[], completed_issues=0,
        new_responses=0, blocked_streak=2, accounted_manifests=[]))
    options.update(workers=5, fetch=blocked, min_interval_seconds=1)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', **options)
    assert result['state'] == 'CIRCUIT_OPEN'
    assert result['new_responses'] == len(calls)
    assert 1 <= len(calls) <= 5
    assert len(set(calls)) == len(calls)
    assert result["circuit_tripped"]
    previous = len(calls)
    run_market_history(root/"plan.json", root/"index.json", root/"out", **options)
    assert len(calls) == previous


@pytest.mark.parametrize("interval", [0, 0.9, True, float("nan"), float("inf"), "1"])
def test_invalid_interval_rejected_before_output(study, interval):
    root, options, calls = study
    with pytest.raises(ValueError, match="interval"):
        run_market_history(root/"plan.json", root/"index.json", root/"out",
                           min_interval_seconds=interval, **options)
    assert not calls and not (root/"out").exists()


def test_supervised_actual_runner_circuit_probe_then_resume(study, monkeypatch):
    import src.market_capture_recovery as m
    import src.fundamentals_market_history as history
    from urllib.parse import parse_qs, urlparse
    root, options, _ = study
    monkeypatch.setattr(m, 'check_layout', lambda p: {'data_root':str(root)})
    scope = dict(issue='130511', state='SCOPED', fixtures=[dict(slot=1,provider_id='356283'),dict(slot=2,provider_id='356284')])
    monkeypatch.setattr(history,'issue_market_scope',lambda *a:scope)
    manifests=[]
    for pid in ('356283','356284'):
        target=root/('preloaded-'+pid)
        capture_documents([market_document('euro:'+pid)],target,
            fetch=lambda url,**k:SimpleNamespace(status_code=200,url=url,headers={},content=b'cached euro'))
        manifests.append(target/'capture-manifest.json')
    atomic_json(root/'index.json', index_market_captures(manifests))
    _, raw = read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    calls=[]
    def fetch(url, **kwargs):
        calls.append(url)
        if len(calls)<=3:
            return SimpleNamespace(status_code=429,url=url,headers={'Retry-After':'1'},content=b'busy')
        pid = parse_qs(urlparse(url).query)['id'][0]
        return SimpleNamespace(status_code=200,url=url,headers={},content=raw.replace(b'356283',pid.encode()))
    result=m.run_supervised_market_history(root/'plan.json',root/'index.json',root/'out',
        contract=root/'plan.json',workers=1,**{**options,'fetch':fetch,'min_interval_seconds':1})
    assert result['state']=='OBSERVED_INVENTORY_ATTEMPTED'
    assert len(calls)==5  # three 429s, one budgeted health probe, one remaining page attempt
    recovery=json.loads((root/'out/recovery.json').read_text())
    assert recovery['state']=='RESUMED'
    assert result['new_responses']==4  # health probe is distinct, not silently admitted to data
    import sqlite3
    with sqlite3.connect(options['ledger_path']) as con:
        assert con.execute('SELECT used FROM budgets').fetchone()[0]==5


def test_rolling_refills_before_slowest_finishes(study, monkeypatch):
    import threading
    import src.fundamentals_market_history as module
    root, options, _ = study
    release = threading.Event()
    seen = []
    gate = threading.Lock()
    monkeypatch.setattr(module, 'issue_market_scope', lambda *a: dict(
        fixtures=[dict(provider_id=str(i)) for i in range(4)], state='READY'))
    def worker(key, *args, **kwargs):
        with gate:
            seen.append(key)
        if key == 'euro:0':
            assert release.wait(3), 'rolling pool never replenished while first task waited'
        if key == 'total:2':
            release.set()
            return dict(indexed=None, stop='DISK_SPACE_LOW')
        return dict(indexed=None, stop=None)
    monkeypatch.setattr(module, 'capture_market_key', worker)
    result = run_market_history(root/'plan.json', root/'index.json', root/'out', workers=5, **options)
    assert release.is_set()
    assert result['state']=='DISK_SPACE_LOW'
    assert len(seen)==len(set(seen))


def test_epoch_storage_cutover_verifies_acceptance_before_publishing(study,monkeypatch):
    from src.market_capture_epoch import prepare_market_epoch
    import src.market_sqlite_capture as capture
    root,options,calls=study
    run_market_history(root/'plan.json',root/'index.json',root/'old',**options)
    def bind(index,**kwargs):
        from copy import deepcopy
        changed=deepcopy(index)
        next(iter(changed.values()))['selected']['storage']={
            'source_url':'https://1x2d.titan007.com/844632.js',
            'acceptance':{'path':str(root/'missing-acceptance.json'),'sha256':'a'*64}}
        return {'index':changed,'changed_references':1}
    monkeypatch.setattr(capture,'bind_market_capture_index',bind)
    with pytest.raises(FileNotFoundError,match='missing-acceptance'):
        prepare_market_epoch(root/'plan.json',root/'index.json',root/'old',
                             root/'inputs',root/'new',storage_cutover={})
    assert not (root/'inputs').exists() and not (root/'new').exists()
    assert len(calls)==2


def test_epoch_storage_cutover_keeps_budget_and_uses_database(study):
    from src.market_capture_epoch import prepare_market_epoch
    from src.market_sqlite import open_market_database,import_market_batch
    from src.market_sqlite_query import query_market_records
    from src.fundamentals_census import read_response
    root,options,calls=study
    run_market_history(root/'plan.json',root/'index.json',root/'old',**options)
    captured=index_market_captures(list((root/'old/responses').glob('*/attempt-*/capture-manifest.json')))
    selected=captured['euro:844632']['selected']
    meta,_=read_response(Path(selected['path']))
    meta={k:v for k,v in meta.items() if k not in {'body_base64','attempt_receipts'}}
    issues=[str(i) for i in range(50)]
    database=root/'market.sqlite';db=open_market_database(database)
    import_market_batch(db,batch_id='accepted',issues=issues,
        records=[dict(kind='capture',key='0/response',issue='0',source_sha256=selected['sha256'],
                      source_url=meta['url'],data={'metadata':meta})]+[
            dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues[1:]],receipt={'input_sha256':'a'*64})
    db.close()
    acceptance=root/'accepted.json'
    from src.market_sqlite_query import market_source_inventory
    acceptance.write_text(json.dumps({'state':'SQLITE_BATCH_ACCEPTED','batch_id':'accepted',
        'issues':issues,'database':str(database),'source_inventories':{
        '0/response':market_source_inventory(query_market_records(database,issue='0'))}}))
    cutover=dict(database=database,captures=query_market_records(database,issue='0',kind='capture'),
                 acceptance={'path':str(acceptance),'sha256':hashlib.sha256(acceptance.read_bytes()).hexdigest()})
    receipt=prepare_market_epoch(root/'plan.json',root/'index.json',root/'old',root/'inputs',root/'new',
                                 storage_cutover=cutover)
    assert receipt['sqlite_bound_references']>=1
    assert receipt['budget_id']==options['budget_id']
    new_index=json.loads((root/'inputs/existing-captures.json').read_text())
    bound=new_index['euro:844632']['selected']
    assert bound['path']==selected['path'] and bound['sha256']==selected['sha256']
    assert bound['storage']['database']==str(database)
    from src.fundamentals_market_history import verify_selected_market_receipt
    assert verify_selected_market_receipt(bound,'euro:844632')['status']==meta['status']
    assert len(calls)==2
