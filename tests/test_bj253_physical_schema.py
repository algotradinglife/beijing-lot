from __future__ import annotations
import json, sqlite3, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1]; sys.path.insert(0,str(ROOT/'src'))
from unified_physical_schema import build_representative_slice, resolve_data_root, verify_snapshot

def _root(tmp_path):
    root=tmp_path/'external'; (root/'data/derived/beidan_xlsm').mkdir(parents=True)
    with sqlite3.connect(root/'data/beidan_live.db') as c:
        c.executescript('CREATE TABLE matches(match_id TEXT, issue TEXT, match_idx INTEGER); CREATE TABLE snapshots(match_id TEXT,snapshot_ts TEXT,sp_3 REAL,sp_1 REAL,sp_0 REAL); INSERT INTO matches VALUES("a","26001",1); INSERT INTO snapshots VALUES("a","2026-01-01T00:00:00Z",2,3,4);')
    with sqlite3.connect(root/'data/derived/beidan_xlsm/beidan_xlsm.sqlite') as c:
        c.executescript('CREATE TABLE matches(match_id INTEGER,issue TEXT,match_idx INTEGER); CREATE TABLE market_consensus(match_id INTEGER,market TEXT,snapshot TEXT,v1_avg REAL,v2_avg REAL,v3_avg REAL); INSERT INTO matches VALUES(1,"25001",1); INSERT INTO market_consensus VALUES(1,"euro_1x2","1h",2,3,4);')
    return root

def test_root_has_no_fallback(monkeypatch):
    monkeypatch.delenv('BEIJING_LOT_DATA_ROOT',raising=False)
    with pytest.raises(ValueError): resolve_data_root()

def test_build_m3_and_tamper_fails(tmp_path, monkeypatch):
    root=_root(tmp_path); monkeypatch.setenv('BEIJING_LOT_DATA_ROOT',str(root)); package=build_representative_slice(); verify_snapshot(package)
    with sqlite3.connect(package/'normalized.sqlite') as c: assert c.execute('SELECT COUNT(*) FROM m3_cell').fetchone()[0]==6; assert c.execute('SELECT COUNT(*) FROM settlement').fetchone()[0]==0
    manifest=package/'MANIFEST.json'; payload=json.loads(manifest.read_text()); payload['namespace_pooling_forbidden']=False; manifest.write_text(json.dumps(payload))
    with pytest.raises(AssertionError): verify_snapshot(package)
