import hashlib
import json
import pytest
from src import zero_purchase_history_inputs as mod


def setup_case(tmp_path, monkeypatch, kind='fixtures'):
    f = dict(issue='001', slot=1, provider_id='0004', handicap=0,
             p_W=.5, p_D=.3, p_L=.2, q_W=.5, q_D=.3, q_L=.2)
    bundle = dict(issue='001', cutoffs={'1':'2020-01-01T00:00:00Z'},
                  expanded_pool=dict(fixtures=[f]))
    monkeypatch.setattr(mod, 'read_verified_bundle_json', lambda path, sha: json.dumps(bundle))
    row = dict(f, odds_W=2., odds_D=3., odds_L=4., cutoff_utc='2020-01-01T08:00:00+08:00')
    obj = {'fixtures':[row]} if kind=='fixtures' else {'market':{'rows':[row]}} if kind=='market' else {'rows':[row]}
    source=tmp_path/'quotes.json';source.write_text(json.dumps(obj))
    m=dict(sources=[dict(kind=kind,issues=['001'],path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())],
           bundles=[dict(issue='001',path='bound-bundle',sha256='bound-hash')])
    return m,source,bundle


def run_case(tmp_path,m):
    p=tmp_path/'manifest.json';p.write_text(json.dumps(m))
    return json.loads(mod.read_zero_purchase_history(p,hashlib.sha256(p.read_bytes()).hexdigest()))


@pytest.mark.parametrize('kind',['fixtures','market','euro'])
def test_explicit_containers_identity_epoch_and_label_exclusion(tmp_path,monkeypatch,kind):
    m,p,b=setup_case(tmp_path,monkeypatch,kind)
    z=run_case(tmp_path,m)
    assert z['rows'][0]['provider_id']=='0004'
    assert z['rows'][0]['odds_D']==3
    assert z['historical_learning']=='NONE'
    assert 'actual_direction' not in z['rows'][0]


@pytest.mark.parametrize('change',['identity','epoch','odds','handicap','projection','duplicate'])
def test_invalid_quote_contract_fails(tmp_path,monkeypatch,change):
    m,p,b=setup_case(tmp_path,monkeypatch);obj=json.loads(p.read_text());r=obj['fixtures'][0]
    if change=='identity':r['provider_id']='wrong'
    if change=='epoch':r['cutoff_utc']='2020-01-02T00:00:00Z'
    if change=='odds':r['odds_W']=None
    if change=='handicap':r['handicap']=1
    if change=='projection':r['q_D']=.2
    if change=='duplicate':obj['fixtures'].append(r.copy())
    p.write_text(json.dumps(obj));m['sources'][0]['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError):run_case(tmp_path,m)


def test_duplicate_assignment_changed_bytes_and_missing_scope(tmp_path,monkeypatch):
    m,p,b=setup_case(tmp_path,monkeypatch)
    m['sources'].append(m['sources'][0].copy())
    with pytest.raises(ValueError,match='Repeated'):run_case(tmp_path,m)
    m['sources'].pop();m['bundles'][0]['issue']='other'
    with pytest.raises(ValueError,match='scope'):run_case(tmp_path,m)
    m['bundles'][0]['issue']='001';p.write_text('{}')
    with pytest.raises(ValueError,match='Changed input'):run_case(tmp_path,m)
