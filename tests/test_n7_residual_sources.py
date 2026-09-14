import hashlib
import json
import pytest
from src.n7_residual_sources import verify_refill_sources,verify_paired_audit


def test_refill_member_cannot_drift_after_receipt_binding(tmp_path):
    path=tmp_path/'candidates.json';path.write_text('{"opening_depth":12}')
    receipt={'files':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()}}
    raw=json.dumps(receipt).encode();(tmp_path/'prediction-freeze.json').write_bytes(raw)
    sha=hashlib.sha256(raw).hexdigest()
    assert verify_refill_sources(tmp_path,sha)==receipt
    path.write_text('{"opening_depth":13}')
    with pytest.raises(ValueError,match='member'):verify_refill_sources(tmp_path,sha)
    with pytest.raises(ValueError,match='receipt'):verify_refill_sources(tmp_path,'wrong')


def test_residual_audit_must_match_control_even_after_relocation(tmp_path):
    reference={'audit_study':'/original','settlement_inputs':{}}
    for name in ['plans-frozen.json','audit-snapshot.json','evaluation-receipt.json']:
        path=tmp_path/name;path.write_text(name)
        reference['settlement_inputs']['/original/'+name]=hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(verify_paired_audit(tmp_path,reference))==3
    (tmp_path/'audit-snapshot.json').write_text('revised valid outcomes')
    with pytest.raises(ValueError,match='Paired audit'):verify_paired_audit(tmp_path,reference)
