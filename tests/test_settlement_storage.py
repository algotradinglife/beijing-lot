from pathlib import Path
import pytest
from src.settlement_storage import validate_settlement_storage


def test_storage_boundaries_and_mount(tmp_path, monkeypatch):
    root = tmp_path / 'data'; root.mkdir()
    target = root / 'new.sqlite'
    assert validate_settlement_storage(root, [target]) == [target]
    with pytest.raises(FileNotFoundError):
        validate_settlement_storage(tmp_path / 'missing', [target])
    with pytest.raises(ValueError, match='directory'):
        target.touch(); validate_settlement_storage(target, [target])
    with pytest.raises(ValueError, match='Distinct'):
        validate_settlement_storage(root, [target, target])
    with pytest.raises(ValueError, match='Distinct'):
        validate_settlement_storage(root, [])
    for path in [root, root / '..' / 'outside.sqlite']:
        with pytest.raises(ValueError, match='escapes'):
            validate_settlement_storage(root, [path])
    (root / 'link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match='escapes'):
        validate_settlement_storage(root, [root / 'link' / 'escape.sqlite'])
    monkeypatch.setattr(Path, 'is_mount', lambda p: False)
    with pytest.raises(ValueError, match='mount'):
        validate_settlement_storage(root, [target], mountpoint=tmp_path)
    monkeypatch.setattr(Path, 'is_mount', lambda p: True)
    assert validate_settlement_storage(root, [target], mountpoint=tmp_path) == [target]
    outside = tmp_path / 'other'; outside.mkdir()
    with pytest.raises(ValueError, match='mount'):
        validate_settlement_storage(root, [target], mountpoint=outside)


def test_persistent_runtime_contract_uses_retained_nas():
    import json
    repo = Path(__file__).resolve().parents[1]
    contract = json.loads((repo / 'config/persistent_data_layout.json').read_bytes())
    assert contract['data_root'] == '/mnt/nas/Data/beijing-lot'
    assert contract['mountpoint'] == '/mnt/nas/Data'
    assert 'Sandisk' not in json.dumps(contract)
    for relative in contract['paths'].values():
        assert not Path(relative).is_absolute()
        assert '..' not in Path(relative).parts
