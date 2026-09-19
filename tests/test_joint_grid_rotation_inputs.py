import gzip,hashlib,json
import pytest
from src.joint_grid_rotation_inputs import read_rotation_members_json


def test_members_projection_is_byte_verified(tmp_path):
    b=dict(issue='001',expanded_pool=dict(fixtures=[dict(slot=1)]),sleeves=[dict(id=0,fixture_indices=[0],enumeration={'large':'ignored'})])
    p=tmp_path/'bundle.json.gz';p.write_bytes(gzip.compress(json.dumps(b).encode()))
    h=hashlib.sha256(p.read_bytes()).hexdigest()
    x=json.loads(read_rotation_members_json(str(p),h))
    assert x==dict(issue='001',fixtures=[dict(slot=1)],sleeves=[dict(id=0,fixture_indices=[0])])
    with pytest.raises(ValueError):read_rotation_members_json(str(p),'0'*64)
