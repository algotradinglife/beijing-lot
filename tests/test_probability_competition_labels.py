import json
import sqlite3

import pytest

from src.probability_competition_labels import read_competition_labels


def test_labels_identity_missing_conflicts_and_provenance(tmp_path):
    db = tmp_path / 'source.sqlite'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE observation(issue,slot,native_match_id,payload_json,play)')
        c.execute('INSERT INTO observation VALUES (?,?,?,?,?)',
                  ('001', 1, '002', json.dumps({'league': '英超'}), 'spf'))
    fixtures = [dict(issue='001', slot=1, provider_id='002'),
                dict(issue='001', slot=2, provider_id='003')]
    result = read_competition_labels(db, fixtures)
    assert result['rows'][0]['competition'] == '英超'
    assert result['rows'][1]['competition'] is None
    assert result == read_competition_labels(db, fixtures)
    assert read_competition_labels(db, [])['rows'] == []
    with pytest.raises(ValueError, match='Duplicate'):
        read_competition_labels(db, fixtures * 2)
    with pytest.raises(ValueError, match='Invalid fixture'):
        read_competition_labels(db, [dict(issue=1, slot=1, provider_id='002')])
    with sqlite3.connect(db) as c:
        c.execute('INSERT INTO observation VALUES (?,?,?,?,?)',
                  ('001', 1, '002', json.dumps({'league': '英甲'}), 'spf'))
    with pytest.raises(ValueError, match='Conflicting'):
        read_competition_labels(db, fixtures)
