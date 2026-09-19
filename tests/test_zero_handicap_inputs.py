import hashlib
import json
from pathlib import Path

import pytest

from src.zero_handicap_inputs import read_zero_handicap_inputs, verified_zero_json


def packet(tmp_path):
    directory = tmp_path / 'batch-000'
    (directory / 'probabilities').mkdir(parents=True)
    row = dict(issue='001', slot=1, provider_id='0004', handicap=0,
               cutoff_utc='2020-01-01T00:00:00Z', odds_W=2., odds_D=3., odds_L=4.,
               q_W=.5, q_D=.3, q_L=.2)
    projection = dict(fixtures=[row], grids={'001/1': [
        dict(home_goals=1, away_goals=0, probability=.5),
        dict(home_goals=0, away_goals=0, probability=.3),
        dict(home_goals=0, away_goals=1, probability=.2)]},
        parameters=dict(method='EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2'),
        historical_admission=False, implementation_hashes={}, issue_order=['001'], exclusions=[])
    inputs = dict(fixtures=[row], total_quotes=[])
    prediction = dict(rows=[dict(row, new_W=.4, new_D=.4, new_L=.2, version='fixture')])
    files = {}
    for name, value in [('projected.json', projection), ('projection-inputs.json', inputs),
                        ('probabilities/predictions.json', prediction)]:
        path = directory / name
        path.write_text(json.dumps(value))
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = directory / 'batch-receipt.json'
    receipt.write_text(json.dumps(dict(files=files, issues=['001'])))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(study=str(tmp_path), batches=[dict(
        batch='batch-000', receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest())])))
    return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_preserves_ids_and_replays_grid(tmp_path):
    path, sha = packet(tmp_path)
    x = json.loads(read_zero_handicap_inputs(path, sha, tmp_path))
    assert x['rows'][0]['provider_id'] == '0004'
    assert x['rows'][0]['p_D'] == .4
    assert x['coverage'][0]['zero_line'] == 1
    assert x['historical_learning'] == 'NONE'


@pytest.mark.parametrize('name', ['manifest.json', 'batch-000/projected.json',
    'batch-000/batch-receipt.json', 'batch-000/probabilities/predictions.json'])
def test_changed_bytes_fail(tmp_path, name):
    path, sha = packet(tmp_path)
    with (tmp_path / name).open('a') as handle:
        handle.write(' ')
    with pytest.raises(ValueError, match='Changed input'):
        read_zero_handicap_inputs(path, sha, tmp_path)


def test_missing_and_invalid_hash(tmp_path):
    with pytest.raises(FileNotFoundError):
        verified_zero_json(tmp_path / 'missing', 'x')
    path, _ = packet(tmp_path)
    with pytest.raises(ValueError):
        verified_zero_json(path, 'x')


@pytest.mark.parametrize('mutation', ['duplicate', 'grid', 'odds', 'scope'])
def test_bound_but_invalid_contract_fails(tmp_path, mutation):
    path, _ = packet(tmp_path)
    target = tmp_path / 'batch-000/projected.json'
    data = json.loads(target.read_text())
    if mutation == 'duplicate':
        data['fixtures'].append(data['fixtures'][0])
    elif mutation == 'grid':
        data['grids']['001/1'][0]['probability'] = .6
    elif mutation == 'odds':
        data['fixtures'][0]['odds_W'] = 9
    else:
        data['fixtures'][0]['provider_id'] = 'other'
    target.write_text(json.dumps(data))
    rp = target.parent / 'batch-receipt.json'
    receipt = json.loads(rp.read_text())
    receipt['files']['projected.json'] = hashlib.sha256(target.read_bytes()).hexdigest()
    rp.write_text(json.dumps(receipt))
    manifest = json.loads(path.read_text())
    manifest['batches'][0]['receipt_sha256'] = hashlib.sha256(rp.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        read_zero_handicap_inputs(path, hashlib.sha256(path.read_bytes()).hexdigest(), tmp_path)
