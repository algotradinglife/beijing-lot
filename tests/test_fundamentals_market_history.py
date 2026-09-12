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


@pytest.mark.parametrize("interval", [0, 0.9, True, float("nan"), float("inf"), "1"])
def test_invalid_interval_rejected_before_output(study, interval):
    root, options, calls = study
    with pytest.raises(ValueError, match="interval"):
        run_market_history(root/"plan.json", root/"index.json", root/"out",
                           min_interval_seconds=interval, **options)
    assert not calls and not (root/"out").exists()
