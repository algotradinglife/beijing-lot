import gzip
import hashlib
import json
from pathlib import Path

import pytest

from src.n7_union_inputs import bind_union_inputs,verify_union_binding


@pytest.fixture
def union_sources(tmp_path):
    tmp_path=tmp_path/'source';tmp_path.mkdir()
    cuts={'1':'2010-01-01T00:00:00+00:00'}
    bundle=tmp_path/'01.json.gz';bundle.write_bytes(gzip.compress(json.dumps({'issue':'01','cutoffs':cuts}).encode()))
    sha=hashlib.sha256(bundle.read_bytes()).hexdigest()
    raw=json.dumps({'seal':'original','receipt':{'issues':['01'],'source_hashes':{str(bundle):sha},'cutoffs':{'01':cuts}}}).encode()
    (tmp_path/'plans-frozen.json').write_bytes(raw);freeze_sha=hashlib.sha256(raw).hexdigest()
    rank={'sources':[{'study':str(tmp_path),'seal':'original','freeze_sha256':freeze_sha}],
        'outputs':{'ranks.csv':'label-csv-not-read'}}
    (tmp_path/'receipt.json').write_text(json.dumps(rank))
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps({'issues':[{'issue':'01','path':str(bundle),'sha256':sha}],
      'bindings':{str(tmp_path/'plans-frozen.json'):freeze_sha}}))
    return catalog,tmp_path,Path(__file__).resolve().parents[1]


def test_union_binding_roundtrip_without_labels(union_sources):
    binding=bind_union_inputs(*union_sources)
    assert verify_union_binding(binding,*union_sources)
    assert json.loads(binding)['ranks_sha256']=='label-csv-not-read'
    changed=json.loads(binding);changed['python_implementation']['files']['src/n7_union_inputs.py']='changed'
    with pytest.raises(Exception):verify_union_binding(json.dumps(changed),*union_sources)


@pytest.mark.parametrize('change',['bundle_hash','cutoff','source_receipt','duplicate_issue'])
def test_union_binding_rejects_cross_snapshot_sources(union_sources,change):
    catalog,root,repo=union_sources;data=json.loads(catalog.read_text())
    if change=='bundle_hash':data['issues'][0]['sha256']='other-snapshot'
    if change=='duplicate_issue':data['issues'].append(data['issues'][0])
    if change=='source_receipt':
        rank=json.loads((root/'receipt.json').read_text());rank['sources'][0]['freeze_sha256']='changed'
        (root/'receipt.json').write_text(json.dumps(rank))
    if change=='cutoff':
        p=Path(data['issues'][0]['path']);p.write_bytes(gzip.compress(json.dumps({'issue':'01','cutoffs':{'1':'future'}}).encode()))
    catalog.write_text(json.dumps(data))
    with pytest.raises(ValueError):bind_union_inputs(catalog,root,repo)
