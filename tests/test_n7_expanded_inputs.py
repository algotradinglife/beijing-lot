"""Thin-entry integration contracts using saved miniature publications."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

import pytest
from src import n7_published_markets, fundamentals_roster_handicap


@pytest.mark.parametrize('mode',['valid','changed_scope','missing_roster'])
def test_expanded_input_entry(tmp_path,monkeypatch,mode):
    old=tmp_path/'old.csv';old.write_text('issue\n000\n')
    roster=tmp_path/'roster.json';roster.write_text('{}')
    scope=tmp_path/'scope.json'
    scope.write_text(json.dumps(dict(inventories=[] if mode=='missing_roster' else [dict(issue='001',roster_path='roster.json')],
        source_hashes={'roster.json':hashlib.sha256(roster.read_bytes()).hexdigest()})))
    release=tmp_path/'merged.json';release.write_text(json.dumps(dict(issues=['001'],rows=[dict(issue='001',slot=1)])))
    cfg=dict(data_root=str(tmp_path),output=str(tmp_path/'out'),release='merged.json',
        release_sha256=hashlib.sha256(release.read_bytes()).hexdigest(),old_results=str(old),new_issue_count=1,
        scopes=[dict(path='scope.json',sha256='0'*64 if mode=='changed_scope' else hashlib.sha256(scope.read_bytes()).hexdigest())],
        archive_registries=[],source_hashes={})
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    monkeypatch.setattr(sys,'argv',['prepare',str(config)])
    monkeypatch.setattr(n7_published_markets,'read_n7_published_markets',lambda **kw:
        dict(rows=[dict(issue='001',slot=1)],source_hashes={},issue_order=kw['issues'],historical_admission=False))
    monkeypatch.setattr(fundamentals_roster_handicap,'roster_handicaps',lambda *args,**kw:
        [dict(slot=1,provider_id='42',home_handicap=-1)])
    script=Path(__file__).resolve().parents[1]/'scripts/prepare_n7_expanded_inputs.py'
    if mode!='valid':
        with pytest.raises(ValueError):runpy.run_path(str(script),run_name='__main__')
        assert not (tmp_path/'out/input-receipt.json').exists()
        return
    runpy.run_path(str(script),run_name='__main__')
    receipt=json.loads((tmp_path/'out/input-receipt.json').read_text())
    assert receipt['issues']==1 and receipt['historical_admission'] is False
    assert receipt['batches'][0]['issues']==['001']
    assert (tmp_path/'out/rosters/001.json').read_bytes()==roster.read_bytes()
    with pytest.raises(ValueError,match='already exists'):runpy.run_path(str(script),run_name='__main__')
