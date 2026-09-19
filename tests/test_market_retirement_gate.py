import hashlib
import json
import sqlite3

import pytest

import src.market_retirement_gate as gate


def test_content_gate_composes_checks_and_rejects_changed_backup(tmp_path, monkeypatch):
    database = tmp_path / 'live.sqlite'
    sqlite3.connect(database).close()
    backup = tmp_path / 'backup.sqlite'
    backup.write_bytes(b'backup')
    inventory = dict(backup=str(backup), backup_sha256='verified-backup')
    ip = tmp_path / 'inventory.json'
    ip.write_text(json.dumps(inventory))
    accepted = dict(state='SQLITE_BATCH_ACCEPTED', batch_id='b', database=str(database),
                    issues=['1'], implementation_hashes={'x': 'hash'},
                    evidence={'inventory': dict(path=ip.name, sha256=hashlib.sha256(ip.read_bytes()).hexdigest())})
    ap = tmp_path / 'acceptance.json'
    ap.write_text(json.dumps(accepted))
    ref = dict(path=ap.name, sha256=hashlib.sha256(ap.read_bytes()).hexdigest())
    plan = dict(batch_id='b', candidates=[dict(path='markets/raw/a.json', sha256='a' * 64)])
    monkeypatch.setattr(gate, 'prepare_market_storage_acceptance', lambda *args, **kwargs: accepted)
    monkeypatch.setattr(gate, 'query_market_records', lambda *args, **kwargs: [dict(
        batch_id='b', kind='capture', source_sha256='a' * 64, data={'path': 'markets/raw/a.json'})])
    connections = []

    def verify(connection, path, *, batch_id):
        assert path == backup and batch_id == 'b'
        connections.append(connection)
        return 'verified-backup'

    monkeypatch.setattr(gate, 'verify_market_batch_backup', verify)
    result = gate.verify_retirement_content(tmp_path, plan, acceptance_reference=ref)
    assert result['raw_deletion_authorized'] is False
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute('select 1')
    mapped = 'markets/raw/verified-responses/' + 'a' * 64 + '.json'
    mp = tmp_path / 'path-map.json'
    mp.write_text(json.dumps({'/old/markets/raw/a.json': str(tmp_path / mapped)}))
    relocated = dict(plan, candidates=[dict(path=mapped, sha256='a' * 64)],
                     relocation=dict(path=mp.name, sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),
                                     original_root='/old'))
    assert gate.verify_retirement_content(tmp_path, relocated, acceptance_reference=ref)['candidate_bindings']['candidates'] == 1
    mp.write_text('{}')
    with pytest.raises(ValueError):
        gate.verify_retirement_content(tmp_path, relocated, acceptance_reference=ref)
    monkeypatch.setattr(gate, 'verify_market_batch_backup', lambda *args, **kwargs: 'changed')
    with pytest.raises(ValueError, match='backup hash'):
        gate.verify_retirement_content(tmp_path, plan, acceptance_reference=ref)
    monkeypatch.setattr(gate, 'prepare_market_storage_acceptance', lambda *args, **kwargs: {})
    with pytest.raises(ValueError, match='content acceptance changed'):
        gate.verify_retirement_content(tmp_path, plan, acceptance_reference=ref)
    with pytest.raises(ValueError, match='accepted retirement batch'):
        gate.verify_retirement_content(tmp_path, dict(plan, batch_id='other'), acceptance_reference=ref)
