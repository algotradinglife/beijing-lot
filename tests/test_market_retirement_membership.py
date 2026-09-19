import hashlib
import pytest
from src.market_retirement_membership import verify_reference_membership


def test_additional_reference_after_freeze_requires_new_review(tmp_path):
    folder=tmp_path/'decisions';folder.mkdir()
    source=folder/'a.json';source.write_bytes(b'{}')
    inventory=[dict(directory='decisions',pattern='**/*.json',members={'a.json':hashlib.sha256(b'{}').hexdigest()})]
    assert verify_reference_membership(tmp_path,inventory)['files']==1
    extra=folder/'new.json';extra.write_text('{"capture_path":"markets/raw/candidate.json"}')
    with pytest.raises(ValueError,match='membership or content changed'):
        verify_reference_membership(tmp_path,inventory)
    extra.unlink();source.write_text('changed')
    with pytest.raises(ValueError,match='membership or content changed'):
        verify_reference_membership(tmp_path,inventory)
    source.unlink()
    with pytest.raises(ValueError,match='membership or content changed'):
        verify_reference_membership(tmp_path,inventory)
    with pytest.raises(ValueError,match='inventories required'):
        verify_reference_membership(tmp_path,[])
