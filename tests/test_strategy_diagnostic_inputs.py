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
