"""CLI/import boundary regressions; transport/parser algorithms use package tests."""
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'src/global_dynamic_26104_capture_20261018.py'


def test_import_does_not_capture_or_publish(monkeypatch):
    """Importing a domain command must not construct a client or open storage."""
    import beidan_backend.unified_sources as sources
    import beidan_backend.versioning as versioning
    def forbidden(*args, **kwargs):
        raise AssertionError('Import produced a source/storage side effect')
    monkeypatch.setattr(sources, 'SourceClient', forbidden)
    monkeypatch.setattr(versioning, 'write_json_atomically', forbidden)
    module = runpy.run_path(str(CLIENT), run_name='import_contract_only')
    assert module['__name__'] == 'import_contract_only'


def test_cadence_and_required_inputs_fail_before_opening_source(tmp_path):
    """Unsupported frequency is refused by argparse, without output creation."""
    result = subprocess.run([sys.executable, str(CLIENT), '--root', str(ROOT),
        '--output', 'hot:must-not-be-created', '--min-interval-seconds', '1','--maximum-channel-attempts','2'],
        capture_output=True, text=True, env=os.environ.copy(), timeout=30)
    assert result.returncode == 2
    assert 'invalid choice' in result.stderr


def test_fixture_scope_rejects_incomplete_input_without_network(tmp_path, monkeypatch):
    """A malformed109-fixture roster cannot silently shrink the cohort."""
    import beidan_backend.catalog.paths as paths
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'inputs.json').write_text('{"issue_id":"26104","fixtures":[]}')
    monkeypatch.setattr(paths, 'location', lambda token: work)
    monkeypatch.setattr(sys, 'argv', [str(CLIENT), '--root', str(ROOT),
        '--output', 'hot:fixture', '--min-interval-seconds', '5', '--maximum-channel-attempts','2','--cache-only'])
    import pytest
    with pytest.raises(ValueError, match='Exact109-fixture26104 input required'):
        runpy.run_path(str(CLIENT), run_name='__main__')
    assert not (work / 'capture-binding.json').exists()


def test_failed_channel_recovers_once_without_refetching_sealed_successes(tmp_path, monkeypatch):
    """A transient failed receipt is retained while only that channel is retried."""
    import json
    from types import SimpleNamespace
    import pytest
    import beidan_backend.catalog.paths as paths
    import beidan_backend.unified_sources as sources
    import beidan_backend.temporal_learning as shared
    work=tmp_path/'capture';work.mkdir()
    fixtures=[dict(fixture_id=f'26104:{i}',provider_id=str(i),home_id='H',away_id='A',
        kickoff_at='2026-10-14T12:00:00+00:00',cutoff_utc='2026-10-13T12:00:00+00:00') for i in range(1,110)]
    (work/'inputs.json').write_text(json.dumps(dict(issue_id='26104',fixtures=fixtures,provenance=[])))
    calls=[]
    def extract(source,url,parser,**kwargs):
        calls.append(url)
        if len(calls)==1: raise RuntimeError('temporary timeout')
        return dict(data=b'[]',receipt=dict(network_attempts=0))
    monkeypatch.setattr(paths,'location',lambda token:work)
    monkeypatch.setattr(sources,'SourceClient',lambda:SimpleNamespace(cache=SimpleNamespace(extract=extract)))
    monkeypatch.setattr(shared,'implementation_closure',lambda *args,**kwargs:{})
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--root',str(ROOT),'--output','hot:fixture',
        '--min-interval-seconds','5','--maximum-channel-attempts','2','--cache-only'])
    with pytest.raises(SystemExit) as exc: runpy.run_path(str(CLIENT),run_name='__main__')
    assert exc.value.code==2
    assert len(calls)==218
    assert not (work/'metadata.json').exists()
    runpy.run_path(str(CLIENT),run_name='__main__')
    assert len(calls)==219
    assert len(list((work/'failed-attempts').glob('*.json')))==1
    assert json.loads((work/'capture-status.json').read_text())['collection_complete']
    before=(work/'metadata.json').read_bytes()
    runpy.run_path(str(CLIENT),run_name='__main__')
    assert len(calls)==219
    assert (work/'metadata.json').read_bytes()==before
