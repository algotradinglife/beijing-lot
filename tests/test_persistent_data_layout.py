import json
import subprocess
import sys
from pathlib import Path

import pytest
from src.persistent_data_layout import check_layout, confined_path


@pytest.fixture
def layout(tmp_path, monkeypatch):
    root = tmp_path / 'disk/data'
    (root / 'markets/releases/v1').mkdir(parents=True)
    (root / 'registry').mkdir()
    (root / 'markets/releases/v1/data.json').write_text('{}')
    (root / 'registry/current.json').write_text(json.dumps({'current': {'path': 'markets/releases/v1/data.json'}}))
    config = tmp_path / 'contract.json'
    config.write_text(json.dumps({'version': 1, 'mountpoint': str(tmp_path / 'disk'), 'data_root': str(root), 'directories': ['markets/releases', 'registry'], 'references': {'registry/current.json': {'current.path': {'prefix': 'markets/releases', 'type': 'file'}}}}))
    monkeypatch.setattr('src.persistent_data_layout.os.path.ismount', lambda p: True)
    return root, config


def test_check_is_read_only_and_repeatable(layout):
    root, config = layout
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert check_layout(config) == check_layout(config)
    assert check_layout(config)['status'] == 'PASS'
    assert before == {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_missing_mount_creates_nothing(layout, monkeypatch):
    root, config = layout
    monkeypatch.setattr('src.persistent_data_layout.os.path.ismount', lambda p: False)
    with pytest.raises(ValueError, match='not mounted'):
        check_layout(config)


@pytest.mark.parametrize('value', ['', '../outside', '/tmp/escape', '.', None, 'a\\b'])
def test_reject_unsafe_path(tmp_path, value):
    with pytest.raises(ValueError):
        confined_path(tmp_path, value)


def test_reject_escaped_symlink(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'escape').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='escapes'):
        confined_path(root, 'escape/file')


@pytest.mark.parametrize('value', ['registry/current.json', 'markets/releases/missing.json', '../outside'])
def test_reference_drift(layout, value):
    root, config = layout
    (root / 'registry/current.json').write_text(json.dumps({'current': {'path': value}}))
    with pytest.raises(ValueError):
        check_layout(config)


def test_missing_directory(layout):
    root, config = layout
    value = json.loads(config.read_text())
    value['directories'].append('fundamentals/raw')
    config.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Missing data directory'):
        check_layout(config)
    assert not (root / 'fundamentals').exists()


def test_root_outside_mount(layout):
    root, config = layout
    value = json.loads(config.read_text())
    value['data_root'] = str(root.parent.parent / 'other')
    config.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='declared mount'):
        check_layout(config)


def test_cli_failure_is_nonzero(tmp_path):
    result = subprocess.run([sys.executable, 'scripts/check_persistent_data_layout.py', '--contract', str(tmp_path / 'absent.json')], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stderr)['status'] == 'FAIL'


@pytest.mark.parametrize('kind,target', [('file', 'markets/releases/v1'), ('directory', 'markets/releases/v1/data.json')])
def test_wrong_reference_type(layout, kind, target):
    root, config = layout
    value = json.loads(config.read_text())
    value['references']['registry/current.json']['current.path']['type'] = kind
    config.write_text(json.dumps(value))
    (root / 'registry/current.json').write_text(json.dumps({'current': {'path': target}}))
    with pytest.raises(ValueError, match='wrong reference type'):
        check_layout(config)
