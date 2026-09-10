"""Offline restart, budget, scope and raw-integrity worker contracts."""
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from bs4 import BeautifulSoup

from src.fundamentals_bulk_capture import (atomic_json, load_inventory,
    historical_pages, attempt_receipt, run_historical_inventory)

URL = 'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'


@pytest.fixture
def setup(tmp_path):
    soup = BeautifulSoup(gzip.decompress(Path('tests/fixtures/fundamentals_census/roster-130511-type8.html.gz').read_bytes()), 'html.parser')
    for row in soup.select('tr[id^="row_"]')[1:]:
        row.decompose()
    manifest = tmp_path / 'inventory.json'
    atomic_json(manifest, {'schema': 'bj411_historical_inventory_v1', 'historical_before': '2020-01-01T00:00:00Z', 'issues': [{'issue': '130511', 'roster_url': URL}]})
    calls = []
    clock = [10000.]
    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=url, headers={}, content=str(soup).encode() if url == URL else b'page')
    def sleep(seconds):
        clock[0] += seconds
    options = dict(ledger_path=tmp_path / 'ledger.sqlite', budget_id='test', request_budget=100, min_free_bytes=0, fetch=fetch, wall_clock=lambda: clock[0], sleeper=sleep)
    return manifest, tmp_path / 'out', options, calls, soup


def test_complete_replay_and_tamper(setup):
    manifest, output, options, calls, _ = setup
    result = run_historical_inventory(manifest, output, **options)
    assert result['state'] == 'FINISHED'
    item = json.loads((output / '130511' / 'status.json').read_text())
    assert item['capture_complete'] and len(item['response_paths']) == 2
    assert len(calls) == 3
    assert run_historical_inventory(manifest, output, **options)['issues'] == result['issues']
    assert len(calls) == 3
    Path(item['response_paths'][0]).write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        run_historical_inventory(manifest, output, **options)


def test_budget_and_immutable_policy(setup):
    manifest, output, options, calls, _ = setup
    options['request_budget'] = 1
    result = run_historical_inventory(manifest, output, **options)
    assert result['state'] == 'BUDGET_EXHAUSTED' and len(calls) == 1
    assert not json.loads((output / '130511' / 'status.json').read_text())['capture_complete']
    run_historical_inventory(manifest, output, **options)
    assert len(calls) == 1
    options['request_budget'] = 10
    with pytest.raises(ValueError, match='policy mismatch'):
        run_historical_inventory(manifest, output, **options)


@pytest.mark.parametrize('failure, expected', [(503, 7), (404, 3), ('transport', 7), (429, 4)])
def test_bounded_failure_and_circuit(setup, failure, expected):
    manifest, output, options, calls, _ = setup
    original = options['fetch']
    def fetch(url, **kwargs):
        response = original(url, **kwargs)
        if url != URL:
            if failure == 'transport':
                raise requests.ConnectionError('offline failure')
            response.status_code = failure
        return response
    options['fetch'] = fetch
    result = run_historical_inventory(manifest, output, **options)
    assert len(calls) == expected
    assert not json.loads((output / '130511' / 'status.json').read_text())['capture_complete']
    run_historical_inventory(manifest, output, **options)
    assert len(calls) == expected
    if failure == 429:
        assert result['state'] == 'CIRCUIT_OPEN'


def test_scope_and_gap_and_disk(setup):
    manifest, output, options, calls, soup = setup
    inventory, cutoff, _ = load_inventory(manifest)
    row = soup.select_one('tr[id^="row_"]')
    row['id'], row['matchid'] = 'row_2', '2'
    pages, gaps = historical_pages(str(soup).encode(), roster_url=URL, issue='130511', cutoff=cutoff)
    assert len(pages) == 1 and gaps == [1]
    with pytest.raises(ValueError, match='nonhistorical'):
        historical_pages(str(soup).encode(), roster_url=URL, issue='130511', cutoff=cutoff.replace(year=2010))
    options['min_free_bytes'] = 10**30
    assert run_historical_inventory(manifest, output, **options)['state'] == 'DISK_SPACE_LOW'
    assert not calls
    inventory['issues'][0]['roster_url'] = URL.replace('TypeID=8', 'TypeID=5')
    atomic_json(manifest, inventory)
    with pytest.raises(ValueError):
        load_inventory(manifest)


def test_bad_roster_and_interrupted(setup):
    manifest, output, options, calls, soup = setup
    soup.select_one('option[selected]')['value'] = '130512'
    result = run_historical_inventory(manifest, output, **options)
    assert 'identity mismatch' in json.loads((output / '130511' / 'status.json').read_text())['roster_error']
    assert len(calls) == 1
    assert attempt_receipt(output / 'absent', {})['state'] == 'INTERRUPTED'


def test_worker_lock_and_crash_resume(setup):
    import fcntl
    manifest, output, options, calls, _ = setup
    output.mkdir()
    with (output / 'worker.lock').open('a+b') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run_historical_inventory(manifest, output, **options)
    original = options['fetch']
    def crash(url, **kwargs):
        raise RuntimeError('simulated process death after reservation')
    options['fetch'] = crash
    with pytest.raises(RuntimeError):
        run_historical_inventory(manifest, output, **options)
    options['fetch'] = original
    result = run_historical_inventory(manifest, output, **options)
    attempts = json.loads((output / '130511' / 'status.json').read_text())['page_states']['roster']['attempts']
    assert len(attempts) == 2 and attempts[0]['state'] == 'INTERRUPTED'
    assert json.loads((output / '130511' / 'status.json').read_text())['capture_complete']
    import sqlite3
    with sqlite3.connect(options['ledger_path']) as connection:
        assert connection.execute('SELECT used FROM budgets').fetchone()[0] == 4


def test_committed_raw_before_progress_update(setup, monkeypatch):
    import src.fundamentals_bulk_capture as module
    manifest, output, options, calls, _ = setup
    original = module.capture_history_batch
    def captured_then_crashed(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('death before status commit')
    monkeypatch.setattr(module, 'capture_history_batch', captured_then_crashed)
    with pytest.raises(RuntimeError):
        run_historical_inventory(manifest, output, **options)
    monkeypatch.setattr(module, 'capture_history_batch', original)
    result = run_historical_inventory(manifest, output, **options)
    assert json.loads((output / '130511' / 'status.json').read_text())['capture_complete'] and len(calls) == 3


def test_transport_receipt_chronology_and_document_identity(setup):
    manifest, output, options, calls, _ = setup
    original = options['fetch']
    def fetch(url, **kwargs):
        if url == URL:
            return original(url, **kwargs)
        raise requests.Timeout('timeout')
    options['fetch'] = fetch
    result = run_historical_inventory(manifest, output, **options)
    page = json.loads((output / '130511' / 'status.json').read_text())['page_states']['001-titan']
    assert 'Timeout' in page['error']
    directory = Path(page['attempts'][0]['directory'])
    with pytest.raises(ValueError, match='document identity'):
        attempt_receipt(directory, {'source': 'nowscore', 'url': URL, 'filename': 'response.json'})


@pytest.mark.parametrize('change', ['schema', 'future', 'naive', 'duplicate', 'empty'])
def test_inventory_validation(setup, change):
    manifest, _, _, _, _ = setup
    value = json.loads(manifest.read_text())
    if change == 'schema':
        value['schema'] = 'other'
    elif change == 'future':
        value['historical_before'] = '2099-01-01T00:00:00Z'
    elif change == 'naive':
        value['historical_before'] = '2020-01-01T00:00:00'
    elif change == 'duplicate':
        value['issues'] *= 2
    else:
        value['issues'] = []
    atomic_json(manifest, value)
    with pytest.raises(ValueError):
        load_inventory(manifest)


def test_progress_is_compact_and_published_status_complete(setup):
    manifest, output, options, _, _ = setup
    result = run_historical_inventory(manifest, output, **options)
    assert 'page_states' not in result['issues']['130511']
    checkpoint = json.loads(Path(result['issues']['130511']['progress_path']).read_text())
    published = json.loads((output / '130511' / 'status.json').read_text())
    assert checkpoint['item'] == published
    assert published['processing_complete']
    assert json.loads((output / '130511' / 'selected-responses.json').read_text()) == published['response_paths']


@pytest.mark.parametrize("asset_status", [200, 404])
def test_required_analysis_asset_capture_and_resume(setup, asset_status):
    manifest, output, options, calls, _ = setup
    original = options['fetch']
    asset_url = 'https://live.nowscore.com/analysisJs/data844632.js'
    page_url = 'https://live.nowscore.com/analysis/844632cn.html'
    def fetch(url, **kwargs):
        response = original(url, **kwargs)
        if url == page_url:
            response.content = b'<script src="/analysisJs/data844632.js"></script>'
        if url == asset_url:
            response.status_code = asset_status
            response.content = b'var h_data=[];'
        return response
    options['fetch'] = fetch
    run_historical_inventory(manifest, output, **options)
    item = json.loads((output / '130511/status.json').read_text())
    assert len(calls) == 4 and asset_url in calls
    assert len(item['response_paths']) == 2
    assert item['capture_complete'] is (asset_status == 200)
    assert item['processing_complete']
    assets = json.loads((output / '130511/selected-assets.json').read_text())
    assert bool(assets) is (asset_status == 200)
    if assets:
        assert page_url in assets
        receipt = json.loads(Path(assets[page_url]).read_text())
        assert receipt['url'] == asset_url
    run_historical_inventory(manifest, output, **options)
    assert len(calls) == 4


def test_unexpected_asset_identity_is_not_requested(setup):
    manifest, output, options, calls, _ = setup
    original = options['fetch']
    def fetch(url, **kwargs):
        response = original(url, **kwargs)
        if '/analysis/' in url and 'nowscore' in url:
            response.content = b'<script src="/analysisJs/data999.js"></script>'
        return response
    options['fetch'] = fetch
    run_historical_inventory(manifest, output, **options)
    item = json.loads((output / '130511/status.json').read_text())
    assert len(calls) == 3 and not item['capture_complete']
    assert item['page_states']['001-nowscore']['asset_error']


def test_later_issue_circuit_checkpoint_survives_root_write_crash(setup, monkeypatch):
    import src.fundamentals_bulk_capture as module
    manifest, output, options, calls, soup = setup
    inventory = json.loads(manifest.read_text())
    second_url = URL.replace('130511', '130512')
    inventory['issues'].append({'issue': '130512', 'roster_url': second_url})
    atomic_json(manifest, inventory)
    original_fetch = options['fetch']
    second_started = [False]
    def fetch(url, **kwargs):
        response = original_fetch(url, **kwargs)
        if url == second_url:
            second_started[0] = True
            response.content = str(soup).replace('value="130511"', 'value="130512"').encode()
        elif second_started[0]:
            response.status_code = 429
        return response
    options['fetch'] = fetch
    original_write = module.atomic_json
    def crash_root(path, value):
        if Path(path) == output / 'status.json' and value.get('state') == 'CIRCUIT_OPEN':
            raise RuntimeError('death after active checkpoint, before root write')
        original_write(path, value)
    monkeypatch.setattr(module, 'atomic_json', crash_root)
    with pytest.raises(RuntimeError, match='active checkpoint'):
        run_historical_inventory(manifest, output, **options)
    root = json.loads((output / 'status.json').read_text())
    assert root['active_issue'] == '130512' and root['blocked_streak'] == 2
    checkpoint = json.loads((output / '130512/progress.json').read_text())
    assert checkpoint['blocked_streak'] == 3
    previous_calls = len(calls)
    monkeypatch.setattr(module, 'atomic_json', original_write)
    result = run_historical_inventory(manifest, output, **options)
    assert result['state'] == 'CIRCUIT_OPEN'
    assert len(calls) == previous_calls


def test_native_fetch_preserves_validated_headers_and_transport(monkeypatch):
    from src import fundamentals_bulk_capture as module
    response = object()
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(module.requests, 'get', get)
    url = 'https://live.nowscore.com/analysis/844632cn.html'
    assert module.native_page_fetch(url, timeout=20, stream=True, referer=URL) is response
    assert calls[0][0] == url
    options = calls[0][1]
    assert options['headers']['Referer'] == URL
    assert 'Chrome/152' in options['headers']['User-Agent']
    assert options['timeout'] == 20 and options['stream'] is True
    assert options['allow_redirects'] is False
