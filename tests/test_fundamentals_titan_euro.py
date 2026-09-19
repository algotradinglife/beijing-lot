import copy
import json
import hashlib
import base64
from pathlib import Path
import pytest
from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_titan_euro import titan_js_timestamp, parse_titan_euro, titan_euro_inputs
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_window import diagnostic_quote_window


def test_saved_titan_schema_and_rejections():
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_euro/357841.json'))
    text,_=decode_analysis_text(raw)
    p=parse_titan_euro(text)
    assert p['provider_id']=='357841'
    assert p['home_team_id']=='116' and p['away_team_id']=='109'
    assert p['kickoff_utc']=='2010-01-06T21:00:00+00:00'
    assert len(p['quotes'])>10
    assert p['company_count']==len(p['quotes'])+p['missing_last']+p['exchanges']
    assert all(min(q[k] for k in ('odds_W','odds_D','odds_L'))>1 for q in p['quotes'])
    with pytest.raises(ValueError): parse_titan_euro(text+'\nScheduleID=1;')
    with pytest.raises(ValueError): parse_titan_euro(text.replace('game=Array(', 'missing=Array('))
    with pytest.raises(ValueError): titan_js_timestamp('2010,eval(1),06,21,00,00')
    with pytest.raises(ValueError): titan_js_timestamp('2010,13-1,06,21,00,00')


def test_quote_cutoff_strict_and_mutation_invariant():
    rows=[dict(quote_id='a',quoted_at='2010-01-06T20:29:59Z',odds_W=2),
          dict(quote_id='b',quoted_at='2010-01-06T20:30:00Z',odds_W=3)]
    args=dict(cutoff=Cutoff.decision_epoch('100102','2010-01-06T20:30:00Z'),
        source_hashes={'x':'hash'},implementation_hashes={'code':'hash'})
    result=diagnostic_quote_window(rows,**args)
    assert result['rows']==rows[:1]
    assert result['receipt']['excluded_same_or_later']==1
    assert result['receipt']['historical_admission'] is False
    assert hashlib.sha256(result['receipt_json'].encode()).hexdigest()==result['receipt']['identity']
    offsets=diagnostic_quote_window([dict(quote_id='x',quoted_at='2010-01-06T21:00:00+02:00'),
        dict(quote_id='y',quoted_at='2010-01-06T20:00:00Z')],**args)
    assert offsets['receipt']['maximum_quote_time']=='2010-01-06T20:00:00+00:00'
    mutated=copy.deepcopy(rows);mutated[1]['odds_W']=1000
    assert diagnostic_quote_window(mutated,**args)['rows']==result['rows']
    assert diagnostic_quote_window([],**args)['rows']==[]
    with pytest.raises(ValueError): diagnostic_quote_window(rows+rows,**args)
    with pytest.raises(ValueError): diagnostic_quote_window(rows,**{**args,'cutoff':None})
    with pytest.raises(ValueError): diagnostic_quote_window([dict(quote_id='a',quoted_at='2010-01-01')],**args)


def test_identity_binding_and_missing_prior_prices(monkeypatch,tmp_path):
    import src.fundamentals_titan_euro as m
    f=dict(issue='100102',slot=40,provider_id='357841',kickoff_utc='2010-01-06T21:00:00Z')
    source=dict(slot=40,source='titan',home_id='116',away_id='109')
    monkeypatch.setattr(m,'issue_capture_report',lambda *a,**k:dict(input_file_hashes={'raw':'hash'}))
    monkeypatch.setattr(m,'pilot_tables',lambda *a,**k:dict(integrated_fixtures=[f],source_fixtures=[source]))
    inv=[dict(issue='100102',fixture_count=1,roster_path='unused',response_paths=[],cutoffs={'40':'2010-01-06T20:30:00Z'})]
    paths=['tests/fixtures/fundamentals_titan_euro/357841.json']
    x=titan_euro_inputs(inv,paths,repository_root='.',cache_dir=None)
    assert x['rows'][0]['status']=='OK_DIAGNOSTIC'
    assert x['rows'][0]['companies']>0 and x['receipts']
    assert hashlib.sha256(x['canonical_json'].encode()).hexdigest()==x['seal']
    receipt=json.loads(Path(paths[0]).read_text())
    other=tmp_path/'response.json'
    receipt['received_at_utc']='2026-09-09T00:00:00+00:00'
    other.write_text(json.dumps(receipt))
    changed=titan_euro_inputs(inv,[str(other)],repository_root='.',cache_dir=None)
    assert changed['rows'][0]['raw_sha256']==x['rows'][0]['raw_sha256']
    assert changed['rows'][0]['capture_sha256']!=x['rows'][0]['capture_sha256']
    assert changed['seal']!=x['seal']
    _,raw=read_response(other);text,encoding=decode_analysis_text(raw)
    late=next(q for q in parse_titan_euro(text)['quotes'] if q['quoted_at']>='2010-01-06T20:30:00+00:00')
    import re
    record=next(r for r in re.findall(r'"([^"\n]+\|[^"\n]+)"',text) if r.split('|')[0]==late['quote_id'])
    parts=record.split('|');parts[10]=str(float(parts[10])+10)
    mutated=text.replace(record,'|'.join(parts)).encode('utf-8')
    receipt.update(body_base64=base64.b64encode(mutated).decode(),byte_count=len(mutated),sha256=hashlib.sha256(mutated).hexdigest())
    other.write_text(json.dumps(receipt))
    later=titan_euro_inputs(inv,[str(other)],repository_root='.',cache_dir=None)
    assert later['companies']==x['companies']
    assert [later['rows'][0][k] for k in ('odds_W','odds_D','odds_L')]==[x['rows'][0][k] for k in ('odds_W','odds_D','odds_L')]
    source['home_id']='wrong'
    assert titan_euro_inputs(inv,paths,repository_root='.',cache_dir=None)['rows'][0]['status']=='IDENTITY_MISMATCH'
    source['home_id']='116';inv[0]['cutoffs']['40']='1900-01-01T00:00:00Z'
    assert titan_euro_inputs(inv,paths,repository_root='.',cache_dir=None)['rows'][0]['status']=='NO_PRIOR_LAST_QUOTES'
    with pytest.raises(ValueError,match='Duplicate'):titan_euro_inputs(inv,paths+paths,repository_root='.',cache_dir=None)


@pytest.mark.parametrize("month,expected", [("0", "01"), ("9", "10"), ("11", "12"), ("10-1", "10")])
def test_literal_js_month(month, expected):
    assert titan_js_timestamp(f"2010,{month},24,15,0,0") == f"2010-{expected}-24T15:00:00+00:00"


@pytest.mark.parametrize("value", ["2010,12,1,0,0,0", "2010,0-1,1,0,0,0", "2010,1,30,0,0,0", "2010,9,1,24,0,0"])
def test_invalid_js_components(value):
    with pytest.raises(ValueError):
        titan_js_timestamp(value)


def test_standard_and_javascript_arrays_normalize_identically():
    import re
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_euro/357841.json'))
    text,_=decode_analysis_text(raw)
    match=re.search(r'\bgame\s*=\s*Array\((.*?)\)\s*;',text,re.S)
    records=json.loads('['+match[1]+']')
    javascript=text[:match.start(1)]+','.join(repr(r) for r in records)+text[match.end(1):]
    assert parse_titan_euro(javascript)==parse_titan_euro(text)
