import hashlib
import json
import pytest
from src.total_draw_inputs import read_total_draw_inputs


def test_verified_total_inputs(tmp_path):
    f=dict(issue='000001',slot=1,provider_id='01',handicap=0,q_W=.4,q_D=.3,q_L=.3,
           lambda_home=1.2,lambda_away=1.3,cutoff_utc='2011-01-01T00:00:00+00:00')
    p=tmp_path/'p.json';p.write_text(json.dumps(dict(fixtures=[f],cutoffs={'000001':{'1':f['cutoff_utc']}})))
    m=tmp_path/'m.json';m.write_text(json.dumps(dict(sources=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())])))
    digest=hashlib.sha256(m.read_bytes()).hexdigest()
    x=json.loads(read_total_draw_inputs(str(m),digest));assert x['rows'][0]['lambda_total']==2.5
    assert x['rows'][0]['provider_id']=='01'
    with pytest.raises(ValueError): read_total_draw_inputs(str(m),'bad')
    p.write_text('{}')
    with pytest.raises(ValueError): read_total_draw_inputs(str(m),digest)
    for fixtures in ([],[f,f],[dict(f,lambda_home=-1)]):
        p.write_text(json.dumps(dict(fixtures=fixtures,cutoffs={'000001':{'1':f['cutoff_utc']}})))
        m.write_text(json.dumps(dict(sources=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())])))
        with pytest.raises(ValueError):
            read_total_draw_inputs(str(m),hashlib.sha256(m.read_bytes()).hexdigest())
