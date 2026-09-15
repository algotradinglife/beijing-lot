import gzip
import hashlib
import json
import pytest
from src.strategy_diagnostic_inputs import read_diagnostic_fixtures


@pytest.mark.parametrize('mutation',['none','catalog','bundle','duplicate','identity','empty'])
def test_frozen_diagnostic_reader(tmp_path,mutation):
    f=dict(issue='001',slot=1,provider_id='0002',handicap=0,p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.3,q_L=.3,result='must not return')
    fixtures=[f,f] if mutation=='duplicate' else [f]
    if mutation=='identity':f['provider_id']=2
    if mutation=='empty':fixtures=[]
    b=tmp_path/'bundle.json.gz';b.write_bytes(gzip.compress(json.dumps(dict(issue='001',expanded_pool=dict(fixtures=fixtures))).encode()))
    c=tmp_path/'catalog.json';c.write_text(json.dumps(dict(issues=[dict(issue='001',path=str(b),sha256=hashlib.sha256(b.read_bytes()).hexdigest())])))
    sha=hashlib.sha256(c.read_bytes()).hexdigest()
    if mutation=='catalog':c.write_text('{}')
    if mutation=='bundle':b.write_bytes(b'changed')
    if mutation!='none':
        with pytest.raises(ValueError):read_diagnostic_fixtures(str(c),sha)
    else:
        r=read_diagnostic_fixtures(str(c),sha)
        assert r['rows'][0]['provider_id']=='0002'
        assert r['rows'][0]['slot']==1 and 'result' not in r['rows'][0]
        assert len(r['source_hashes'])==2


def test_epoch_reader_verifies_same_bytes_and_preserves_clocks(tmp_path):
    from src.strategy_diagnostic_inputs import read_verified_bundle_json, read_diagnostic_epoch_fixtures
    f=dict(issue='001',slot=1,provider_id='0002',handicap=0,p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.3,q_L=.3)
    body=dict(issue='001',expanded_pool=dict(fixtures=[f]),cutoffs={'1':'2011-01-01T10:00:00+08:00'})
    b=tmp_path/'b.gz';b.write_bytes(gzip.compress(json.dumps(body).encode()))
    sha=hashlib.sha256(b.read_bytes()).hexdigest()
    c=tmp_path/'c.json';c.write_text(json.dumps(dict(issues=[dict(issue='001',path=str(b),sha256=sha)])))
    cs=hashlib.sha256(c.read_bytes()).hexdigest()
    assert json.loads(read_verified_bundle_json(b,sha))==body
    row=json.loads(read_diagnostic_epoch_fixtures(c,cs))['rows'][0]
    assert row['fixture_decision_ts']==body['cutoffs']['1']
    assert row['last_fixture_cutoff']=='2011-01-01T02:00:00+00:00'
    b.write_bytes(gzip.compress(b'{}'))
    with pytest.raises(ValueError):read_verified_bundle_json(b,sha)
    with pytest.raises(ValueError):read_diagnostic_epoch_fixtures(c,cs)
