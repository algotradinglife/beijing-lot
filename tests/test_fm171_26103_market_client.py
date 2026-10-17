"""Deterministic CLI contracts; source I/O is injected, not live HTTP."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

import pytest

from beidan_backend import unified_sources
from beidan_backend.extraction_cache import CacheMissError

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src/fm171_26103_collect_full_markets.py"


def test_import_is_inert(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Import must not construct a cache or scrape")
    monkeypatch.setattr(unified_sources, "SourceClient", forbidden)
    runpy.run_path(str(CLIENT), run_name="client_import_test")


def test_offline_capture_resume_and_tamper_rejection(monkeypatch, tmp_path):
    hot = tmp_path / "hot"
    hot.mkdir()
    monkeypatch.setenv("BEIDAN_HOT_ROOT", str(hot))
    body = json.dumps([dict(ModifyTime="20261008120000", PanKou="2.5",
        HomeOdds="0.9", AwayOdds="0.95", HappenTime="", Score="早")]).encode()
    calls = []
    class FakeClient:
        def request(self, source, url, **kwargs):
            assert source == "titan" and kwargs["cache_only"] and kwargs["reuse_raw"]
            calls.append(url)
            return dict(data=body, receipt=dict(network_attempts=0,
                sha256=hashlib.sha256(body).hexdigest(), capture_id=1,
                observed_at="2026-10-17T00:00:00Z", url=url))
    monkeypatch.setattr(unified_sources, "SourceClient", FakeClient)
    monkeypatch.setattr(sys, "argv", [str(CLIENT), "--root", str(ROOT),
        "--output", "hot:collector-contract", "--slots", "1", "--cache-only"])
    runpy.run_path(str(CLIENT), run_name="__main__")
    status = json.loads((hot / "collector-contract/collection-status.json").read_text())
    assert status["parsed_channels"] == 2 and status["collection_complete"]
    assert not status["full_fm_analysis_accepted"] and not status["historical_admission"]
    asian = json.loads(json.loads((hot / "collector-contract/26103_1-asian.json").read_text())['payload'])
    assert asian["snapshots"][0]["line_value"] == -2.5
    assert len(calls) == 2
    runpy.run_path(str(CLIENT), run_name="__main__")
    assert len(calls) == 2
    target = hot / "collector-contract/26103_1-total.json"
    envelope = json.loads(target.read_text())
    data = json.loads(envelope['payload'])
    data["snapshots"][0]["line_value"] = 9.5
    envelope['payload'] = json.dumps(data)
    target.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="integrity"):
        runpy.run_path(str(CLIENT), run_name="__main__")


def test_missing_cache_has_failure_ledger_and_nonzero_exit(monkeypatch, tmp_path):
    hot = tmp_path / "hot"
    hot.mkdir()
    monkeypatch.setenv("BEIDAN_HOT_ROOT", str(hot))
    class MissingClient:
        def request(self, *args, **kwargs):
            raise CacheMissError("No frozen response exists")
    monkeypatch.setattr(unified_sources, "SourceClient", MissingClient)
    monkeypatch.setattr(sys, "argv", [str(CLIENT), "--root", str(ROOT),
        "--output", "hot:collector-missing", "--slots", "1", "--cache-only"])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(CLIENT), run_name="__main__")
    assert error.value.code == 2
    status = json.loads((hot / "collector-missing/collection-status.json").read_text())
    assert status["traversal_complete"] and not status["collection_complete"]
    assert status["failed_or_missing_channels"] == 2
    for kind in ("asian", "total"):
        row = json.loads(json.loads((hot / f"collector-missing/26103_1-{kind}.json").read_text())['payload'])
        assert row["state"] == "CACHE_MISS" and row["network_attempts"] == 0


@pytest.mark.parametrize('body,state,exit_code', [
    (b'[]', 'OBSERVED_EMPTY', None), (b'WAF response', 'PARSE_FAILED', 2)])
def test_source_empty_is_distinct_from_parser_failure(monkeypatch,tmp_path,body,state,exit_code):
    hot = tmp_path / 'hot'
    hot.mkdir()
    monkeypatch.setenv('BEIDAN_HOT_ROOT', str(hot))
    class RawClient:
        def request(self,*args,**kwargs):
            return dict(data=body,receipt=dict(network_attempts=0,sha256=hashlib.sha256(body).hexdigest()))
    monkeypatch.setattr(unified_sources,'SourceClient',RawClient)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--root',str(ROOT),'--output','hot:raw-states','--slots','1','--cache-only'])
    if exit_code is None:
        runpy.run_path(str(CLIENT),run_name='__main__')
    else:
        with pytest.raises(SystemExit) as error:
            runpy.run_path(str(CLIENT),run_name='__main__')
        assert error.value.code==exit_code
    result=json.loads(json.loads((hot/'raw-states/26103_1-total.json').read_text())['payload'])
    assert result['state']==state
    summary=json.loads((hot/'raw-states/collection-status.json').read_text())
    assert summary['observed_empty_channels']==(2 if state=='OBSERVED_EMPTY' else 0)
    assert summary['collection_complete']==(state=='OBSERVED_EMPTY')


@pytest.mark.parametrize('interruption',['before','after'])
def test_interrupted_atomic_publication_resumes(monkeypatch,tmp_path,interruption):
    hot=tmp_path/'hot';hot.mkdir()
    monkeypatch.setenv('BEIDAN_HOT_ROOT',str(hot))
    body=json.dumps([dict(ModifyTime='20261008120000',PanKou='2.5',
        HomeOdds='.9',AwayOdds='.95',HappenTime='',Score='早')]).encode()
    calls=[]
    class OfflineClient:
        def request(self,*args,**kwargs):
            calls.append(args)
            return dict(data=body,receipt=dict(network_attempts=0))
    monkeypatch.setattr(unified_sources,'SourceClient',OfflineClient)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--root',str(ROOT),'--output','hot:atomic','--slots','1','--cache-only'])
    original_replace=os.replace
    triggered=[]
    def interrupt_replace(path,target):
        if Path(target).name=='26103_1-total.json' and not triggered:
            triggered.append(True)
            if interruption=='after':
                original_replace(path,target)
            raise KeyboardInterrupt('simulated termination at publication')
        return original_replace(path,target)
    monkeypatch.setattr(os,'replace',interrupt_replace)
    with pytest.raises(KeyboardInterrupt):
        runpy.run_path(str(CLIENT),run_name='__main__')
    monkeypatch.setattr(os,'replace',original_replace)
    runpy.run_path(str(CLIENT),run_name='__main__')
    status=json.loads((hot/'atomic/collection-status.json').read_text())
    assert status['collection_complete'] and status['parsed_channels']==2
    assert len(calls)==(3 if interruption=='before' else 2)
    for kind in ['total','asian']:
        envelope=json.loads((hot/f'atomic/26103_1-{kind}.json').read_text())
        assert hashlib.sha256(envelope['payload'].encode()).hexdigest()==envelope['sha256']


def test_explicit_five_second_cadence_uses_shared_cache(monkeypatch, tmp_path):
    hot = tmp_path / 'hot'
    hot.mkdir()
    monkeypatch.setenv('BEIDAN_HOT_ROOT', str(hot))
    intervals = []
    class Cache:
        def extract(self, source, url, parser, **kwargs):
            assert source == 'titan' and kwargs['reuse_raw']
            intervals.append(kwargs['min_interval'])
            return dict(data=b'[]', receipt=dict(network_attempts=0))
    class Client:
        cache = Cache()
    monkeypatch.setattr(unified_sources, 'SourceClient', Client)
    monkeypatch.setattr(sys, 'argv', [str(CLIENT), '--root', str(ROOT),
        '--output', 'hot:five-second-test', '--slots', '1', '--cache-only',
        '--min-interval-seconds', '5'])
    runpy.run_path(str(CLIENT), run_name='__main__')
    assert intervals == [5.0, 5.0]
    binding = json.loads((hot/'five-second-test/input-binding.json').read_bytes())
    assert binding['min_interval_seconds'] == 5
