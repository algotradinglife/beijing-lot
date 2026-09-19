import gzip
import hashlib
import json
import pytest
from src.n7_prepared_input_coverage import prepared_input_coverage


def test_verified_coverage_identity_and_corruption(tmp_path):
    batch=tmp_path/'batch';batch.mkdir()
    market=dict(issue_order=['01'],historical_admission=False,rows=[dict(issue='01',slot=1,market=m,status='QUOTES_PRIOR_DIAGNOSTIC',provider_id='9') for m in ['euro','total']])
    raw=gzip.compress(json.dumps(market).encode());(batch/'published-markets.json.gz').write_bytes(raw)
    sha=hashlib.sha256(raw).hexdigest()
    h=dict(rows=[dict(issue='01',slot=1,provider_id='8',home_handicap=0)],market_snapshot_sha256=sha,historical_admission=False)
    hr=json.dumps(h).encode();(batch/'handicaps.json').write_bytes(hr)
    scope=json.dumps(dict(issues=['01'])).encode();(tmp_path/'scope.json').write_bytes(scope)
    r=dict(historical_admission=False,issues=1,outputs={'scope.json':hashlib.sha256(scope).hexdigest()},batches=[dict(path=str(batch),issues=['01'],market_sha256=sha,handicap_sha256=hashlib.sha256(hr).hexdigest())])
    rr=json.dumps(r).encode();p=tmp_path/'input-receipt.json';p.write_bytes(rr);identity=hashlib.sha256(rr).hexdigest()
    x=prepared_input_coverage(p,identity)
    assert x['rows']==[dict(issue='01',fixtures=1,euro=1,total=1,both_markets=1,roster_aligned=0)]
    h['rows'][0]['provider_id']='9'
    hr=json.dumps(h).encode();(batch/'handicaps.json').write_bytes(hr)
    r['batches'][0]['handicap_sha256']=hashlib.sha256(hr).hexdigest()
    rr=json.dumps(r).encode();p.write_bytes(rr);identity=hashlib.sha256(rr).hexdigest()
    assert prepared_input_coverage(p,identity)['rows'][0]['roster_aligned']==1
    with pytest.raises(ValueError,match='receipt'):prepared_input_coverage(p,'bad')
    (batch/'handicaps.json').write_bytes(b'{}')
    with pytest.raises(ValueError,match='batch'):prepared_input_coverage(p,identity)


def test_empty_declared_issue_remains_visible(tmp_path):
    b=tmp_path/'b';b.mkdir();m=gzip.compress(json.dumps(dict(issue_order=['02'],rows=[],historical_admission=False)).encode());mh=hashlib.sha256(m).hexdigest();(b/'published-markets.json.gz').write_bytes(m)
    h=json.dumps(dict(rows=[],market_snapshot_sha256=mh,historical_admission=False)).encode();(b/'handicaps.json').write_bytes(h)
    scope=json.dumps(dict(issues=['02'])).encode();(tmp_path/'scope.json').write_bytes(scope)
    r=dict(issues=1,historical_admission=False,outputs={'scope.json':hashlib.sha256(scope).hexdigest()},batches=[dict(path=str(b),issues=['02'],market_sha256=mh,handicap_sha256=hashlib.sha256(h).hexdigest())]);raw=json.dumps(r).encode();p=tmp_path/'input-receipt.json';p.write_bytes(raw)
    assert prepared_input_coverage(p,hashlib.sha256(raw).hexdigest())['rows'][0]['fixtures']==0
