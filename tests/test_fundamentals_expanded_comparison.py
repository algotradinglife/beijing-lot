import gzip
import hashlib
import json
from pathlib import Path
import pytest
from src.fundamentals_expanded_comparison import read_verified_report_archive, merge_variant_reports
from src.temporal_learning.core import stable_json_hash


def test_archive_bytes_and_freeze(tmp_path):
    seal = stable_json_hash({'scope': 'test'})
    files = {'results.json': json.dumps({'freeze_seal': seal, 'rows': []}),
             'plans-frozen.json': json.dumps({'seal': seal, 'receipt': {'scope': 'test'}})}
    archive = {'files': files, 'hashes': {n: hashlib.sha256(b.encode()).hexdigest() for n, b in files.items()}}
    path = tmp_path / 'report.gz'
    path.write_bytes(gzip.compress(json.dumps(archive).encode()))
    assert read_verified_report_archive(path)[0]['rows'] == []
    archive['files']['results.json'] = json.dumps({'freeze_seal': 'wrong'})
    path.write_bytes(gzip.compress(json.dumps(archive).encode()))
    with pytest.raises(ValueError, match='bytes'):
        read_verified_report_archive(path)
    archive['hashes']['results.json'] = hashlib.sha256(archive['files']['results.json'].encode()).hexdigest()
    path.write_bytes(gzip.compress(json.dumps(archive).encode()))
    with pytest.raises(ValueError, match='freeze'):
        read_verified_report_archive(path)
    archive['files']['extra'] = ''
    path.write_bytes(gzip.compress(json.dumps(archive).encode()))
    with pytest.raises(ValueError, match='scope'):
        read_verified_report_archive(path)
    archive['files'] = {}
    archive['files']['results.json'] = json.dumps({'freeze_seal': seal})
    archive['files']['plans-frozen.json'] = json.dumps({'seal': seal, 'receipt': {'scope': 'changed'}})
    archive['hashes'] = {n: hashlib.sha256(b.encode()).hexdigest() for n, b in archive['files'].items()}
    path.write_bytes(gzip.compress(json.dumps(archive).encode()))
    with pytest.raises(ValueError, match='receipt'):
        read_verified_report_archive(path)


def test_union_shared_controls_and_pending():
    a = dict(issue='001', policy='BASE', net=None, partition='OLD')
    b = dict(a, partition='NEW')
    c = dict(b, policy='TV20', net=5.)
    result = merge_variant_reports([a], [b, c])
    assert len(result) == 2 and result[0]['net'] is None
    assert result[0]['issue'] == '001' and a['partition'] == 'OLD'
    with pytest.raises(ValueError, match='Conflicting'):
        merge_variant_reports([a], [dict(b, net=0)])
    with pytest.raises(ValueError, match='duplicate'):
        merge_variant_reports([a, a], [b])
    with pytest.raises(ValueError, match='scopes'):
        merge_variant_reports([a], [dict(b, issue='002')])
    with pytest.raises(ValueError, match='Empty'):
        merge_variant_reports([], [b])
    with pytest.raises(ValueError, match='Invalid'):
        merge_variant_reports([dict(a, issue=1)], [b])


def test_published_before_reports_have_seventy_two_distinct_variants():
    root = Path(__file__).resolve().parent / 'fixtures'
    a, _ = read_verified_report_archive(root / 'clean_validation_report.json.gz')
    b, _ = read_verified_report_archive(root / 'market_conflict_report.json.gz')
    rows = merge_variant_reports(a['rows'], b['rows'])
    assert len(rows) == 3456 and len({r['policy'] for r in rows}) == 72
    assert len({r['issue'] for r in rows}) == 48
