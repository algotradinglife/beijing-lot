"""Offline provenance and compact-reader tests."""
import gzip
import hashlib
import json
import pytest
from src.n7_rank_diagnostic import load_rank_issue


def test_reader_bindings_and_unknown_issue(tmp_path):
    bundle = dict(issue='001',cutoffs={'a':'epoch'},expanded_pool={'fixtures':[]},
                  sleeves=[dict(id='0',fixture_indices=list(range(7)),origin='QUALITY')])
    raw = dict(issue='001',cutoffs=bundle['cutoffs'],historical_admission=False,curves=[])
    bindings = []
    for name,obj in [('raw',raw),('bundles',bundle)]:
        p = tmp_path/name/'001.json.gz';p.parent.mkdir()
        p.write_bytes(gzip.compress(json.dumps(obj).encode()))
        bindings.append({str(p):hashlib.sha256(p.read_bytes()).hexdigest()})
    frozen = dict(seal='original-seal',receipt=dict(issues=['001'],raw_hashes=bindings[0],source_hashes=bindings[1]))
    f=tmp_path/'plans-frozen.json';f.write_text(json.dumps(frozen))
    a=tmp_path/'audit-snapshot.json';a.write_text(json.dumps({'rows':[{'issue':'001'}]}))
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps(dict(
        freeze_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),audit_sha256=hashlib.sha256(a.read_bytes()).hexdigest())))
    x=json.loads(load_rank_issue(tmp_path,'001'))
    assert x['issue']=='001' and x['freeze_seal']=='original-seal'
    assert x['evidence_class']=='POST_SETTLEMENT_DIAGNOSTIC'
    with pytest.raises(ValueError,match='Unknown'):load_rank_issue(tmp_path,'002')
    path=next(iter(bindings[0]));open(path,'ab').write(b'changed')
    with pytest.raises(ValueError,match='Source hash'):load_rank_issue(tmp_path,'001')
    a.write_text('{}')
    with pytest.raises(ValueError,match='audit binding'):load_rank_issue(tmp_path,'001')
