import copy
import hashlib
import json
from pathlib import Path
import pytest
from src.fundamentals_census import read_response
from src.fundamentals_titan_total import total_triplet, parse_titan_total_html, titan_total_inputs
from src.temporal_learning import Cutoff
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes


def test_triplets_asian_lines_and_invalid_prices():
    assert total_triplet('2/2.5','0.9','0.8')['line']==2.25
    assert total_triplet('3','1','2')['line']==3
    for line in ('x','2/3','2.25','-1','31'):
        with pytest.raises(ValueError): total_triplet(line,'1','1')
    for price in ('nan','inf','0','-1',''):
        with pytest.raises(ValueError): total_triplet('2.5',price,'1')


def test_saved_html_identity_hidden_live_and_mojibake():
    _, raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    text=raw.decode(); p=parse_titan_total_html(text)
    assert p['provider_id']=='356283'
    assert (p['home_team_id'],p['away_team_id'])==('55','376')
    assert p['kickoff_local']=='2010-01-02 23:00'
    assert len(p['overview'])==20 and len(p['changes'])==38
    assert all(r['line']==2.5 for r in p['overview'])
    assert any(r['line']==2.25 for r in p['changes'])
    assert p['overview'][0]['over_hk']==.9
    # Hidden wholeLastOdds contains 7.5 live line but cannot affect inputs.
    mutated=text.replace('>7.5<','>29.5<')
    assert parse_titan_total_html(mutated)==p
    live=parse_titan_total_html(text.replace('background: #FFFFFF','background: #eaeaff'))
    assert any(r['phase']=='LIVE' for r in live['changes'])
    unknown=parse_titan_total_html(text.replace('background: #FFFFFF','background: #123456'))
    assert any(r['phase']=='UNKNOWN' for r in unknown['changes'])
    with pytest.raises(ValueError): parse_titan_total_html('<html>WAF</html>')
    with pytest.raises(ValueError): parse_titan_total_html(text.replace('id="oddsDetail"','id="other"'))
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356276.json'))
    damaged=parse_titan_total_html(raw.decode())
    assert damaged['text_encoding_status']=='READER_MOJIBAKE'
    assert len(damaged['changes'])==202


def test_partial_clock_year_rollover_strict_cutoff_and_mutation():
    rows=[dict(quote_id='1',company='A',quoted_local='12-30 20:31',line=2.5,over_hk=.9,under_hk=.8),
          dict(quote_id='2',company='A',quoted_local='1-2 22:00',line=2.5,over_hk=.8,under_hk=.9),
          dict(quote_id='3',company='A',quoted_local='1-2 22:30',line=3,over_hk=1.,under_hk=1.)]
    args=dict(anchor_utc='2010-01-02T15:00:00Z',timezone='Asia/Shanghai',maximum_days=31,
        cutoff=Cutoff.decision_epoch('100101','2010-01-02T14:30:00Z'),
        source_hashes={'capture':'hash'},implementation_hashes={'code':'hash'})
    x=diagnostic_monthday_quotes(rows,**args)
    assert x['rows'][0]['quote_id']=='2'
    assert x['window']['rows'][0]['quoted_at'].startswith('2009-12-30')
    y=copy.deepcopy(rows);y[-1]['over_hk']=99
    assert diagnostic_monthday_quotes(y,**args)['rows']==x['rows']
    assert diagnostic_monthday_quotes([],**args)['rows']==[]
    with pytest.raises(ValueError): diagnostic_monthday_quotes(rows,**{**args,'maximum_days':180})
    for clock in ('2-30 10:00','not-a-clock'):
        with pytest.raises(ValueError):
            diagnostic_monthday_quotes([dict(rows[0],quoted_local=clock)],**args)
    tied=rows+[dict(rows[1],quote_id='10/A',over_hk=2)]
    selected=diagnostic_monthday_quotes(tied,**args)
    assert selected['rows'][0]['quote_id']=='2'
    assert selected['policy']['tie_ledger'][0]['superseded_id']=='10/A'
    assert diagnostic_monthday_quotes(list(reversed(tied)),**args)['rows']==selected['rows']
    with pytest.raises(ValueError, match='Numeric source row'):
        diagnostic_monthday_quotes([dict(rows[0],quote_id='bad')],**args)
    with pytest.raises(ValueError, match='Duplicate company/source row'):
        diagnostic_monthday_quotes(rows+[dict(rows[1],quote_id='2/A')],**args)
    earlier=diagnostic_monthday_quotes(rows,**{**args,'cutoff':Cutoff.decision_epoch('100101','2009-12-29T00:00:00Z')})
    assert earlier['rows']==[]


def test_total_inputs_identity_receipts_and_strict_contracts(monkeypatch):
    import src.fundamentals_titan_total as m
    ep=Path('tests/fixtures/fundamentals_titan_euro/356276.json')
    meta,_=read_response(ep)
    cuts={'100101':{'3':'2010-01-02T14:30:00Z'}}
    row=dict(provider_id='356276',issue='100101',slot=3,status='OK_DIAGNOSTIC',
        cutoff_utc=cuts['100101']['3'],capture_path=str(ep),capture_sha256=hashlib.sha256(ep.read_bytes()).hexdigest())
    artifact=dict(rows=[row],historical_admission=False)
    encoded=json.dumps(artifact)
    euro=dict(artifact,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest())
    paths=['tests/fixtures/fundamentals_titan_total/356276.json']
    args=dict(cutoffs=cuts,repository_root='.',timezone='Asia/Shanghai',maximum_days=31)
    x=titan_total_inputs(euro,paths,**args)
    assert x['rows'][0]['status']=='OK_DIAGNOSTIC'
    assert x['selected'] and x['receipts']
    assert x['historical_admission'] is False
    assert hashlib.sha256(x['canonical_json'].encode()).hexdigest()==x['seal']
    assert all(r['quoted_at']<'2010-01-02T22:30' for r in x['selected'])
    with pytest.raises(ValueError): titan_total_inputs(euro,paths*2,**args)
    # A rescheduled match may be listed again under a later issue. Reuse raw
    # bytes, but never reuse the earlier issue's selected quote window.
    repeated=copy.deepcopy(artifact)
    repeated['rows'].append(dict(row,issue='100102',slot=7,cutoff_utc='2009-12-01T00:00:00Z'))
    encoded_repeated=json.dumps(repeated)
    repeated_euro=dict(repeated,canonical_json=encoded_repeated,seal=hashlib.sha256(encoded_repeated.encode()).hexdigest())
    repeated_result=titan_total_inputs(repeated_euro,paths,**{**args,'cutoffs':{**cuts,'100102':{'7':'2009-12-01T00:00:00Z'}}})
    assert len(repeated_result['rows'])==2
    assert repeated_result['rows'][0]['status']=='OK_DIAGNOSTIC'
    assert repeated_result['rows'][1]['status']=='NO_PRIOR_PREMATCH_QUOTES'
    assert all(r['issue']=='100101' for r in repeated_result['selected'])
    repeated['rows'][1]=dict(row)
    encoded_repeated=json.dumps(repeated)
    with pytest.raises(ValueError,match='Duplicate Euro fixture'):
        titan_total_inputs(dict(repeated,canonical_json=encoded_repeated,seal=hashlib.sha256(encoded_repeated.encode()).hexdigest()),paths,**args)
    with pytest.raises(ValueError): titan_total_inputs(euro,[],**args)
    with pytest.raises(ValueError): titan_total_inputs(euro,paths,**{**args,'cutoffs':{'100101':{'3':'2009-01-01T00:00:00Z'}}})
    changed=copy.deepcopy(euro);changed['rows'][0]['status']='bad'
    with pytest.raises(ValueError): titan_total_inputs(changed,paths,**args)
    original=m.parse_titan_total_html
    def mismatched(text):
        return dict(original(text),home_team_id='999')
    monkeypatch.setattr(m,'parse_titan_total_html',mismatched)
    assert titan_total_inputs(euro,paths,**args)['rows'][0]['status']=='IDENTITY_OR_DISPLAY_CLOCK_MISMATCH'


def test_partial_clock_source_order_ties_preserve_all_evidence():
    rows=[dict(quote_id=f'{i}/35',company='35',quoted_local='5-13 19:59',
               line=2.75,over_hk=over,under_hk=under)
          for i,over,under in [(3,.83,1.03),(4,.88,.98),(10,.9,1.)]]
    args=dict(anchor_utc='2010-05-13T12:00:00Z',timezone='Asia/Shanghai',maximum_days=31,
        cutoff=Cutoff.decision_epoch('100510','2010-05-13T12:00:00Z'),
        source_hashes={'capture':'hash'},implementation_hashes={'code':'hash'})
    original=copy.deepcopy(rows)
    result=diagnostic_monthday_quotes(rows,**args)
    assert result['rows'][0]['quote_id']=='3/35'
    assert result['rows'][0]['over_hk']==.83
    assert len(result['window']['rows'])==3 and len(result['policy']['tie_ledger'])==2
    assert rows==original
    assert diagnostic_monthday_quotes(rows[::-1],**args)['rows']==result['rows']
    # A tied minute equal to the decision epoch is never admitted.
    args['cutoff']=Cutoff.decision_epoch('100510','2010-05-13T11:59:00Z')
    assert diagnostic_monthday_quotes(rows,**args)['rows']==[]


def test_partial_clock_excludes_old_quotes_with_raw_ledger():
    old=dict(quote_id='9/A',company='A',quoted_local='12-6 11:46',line=2.,over_hk=.93,under_hk=.95)
    recent=dict(old,quote_id='1/A',quoted_local='6-11 20:00')
    args=dict(anchor_utc='2010-06-11T14:00:00Z',timezone='Asia/Shanghai',maximum_days=31,
        cutoff=Cutoff.decision_epoch('100606','2010-06-11T13:30:00Z'),
        source_hashes={'capture':'hash'},implementation_hashes={'code':'hash'})
    result=diagnostic_monthday_quotes([recent,old],**args)
    assert result['rows'][0]['quote_id']=='1/A'
    assert result['policy']['excluded_outside_horizon']==[dict(row=old,reason='OUTSIDE_ANCHOR_HORIZON')]
    assert diagnostic_monthday_quotes([old],**args)['rows']==[]
    boundary=dict(recent,quoted_local='5-11 22:00')
    assert diagnostic_monthday_quotes([boundary],**args)['rows']
    boundary['quoted_local']='5-11 21:59'
    assert diagnostic_monthday_quotes([boundary],**args)['rows']==[]
    with pytest.raises(ValueError,match='Unique quote IDs'):
        diagnostic_monthday_quotes([old,old],**args)
    mutated=dict(old,over_hk=99)
    changed=diagnostic_monthday_quotes([recent,mutated],**args)
    assert changed['rows']==result['rows']
    assert changed['policy']['input_sha256']!=result['policy']['input_sha256']


def test_explicit_no_companies_is_empty_not_parser_failure():
    from bs4 import BeautifulSoup
    _,raw=read_response(Path('tests/fixtures/fundamentals_titan_total/356283.json'))
    soup=BeautifulSoup(raw.decode('utf-8'),'html.parser')
    table=soup.select_one('table#odds')
    for tr in list(table.select('tr')):
        if tr.select_one('input[name="oddsShow"]'): tr.decompose()
    marker=soup.new_tag('tr');cell=soup.new_tag('td');cell.string='暂无公司开盘';marker.append(cell);table.append(marker)
    for tr in list(soup.select('table#oddsDetail tr'))[1:]:tr.decompose()
    p=parse_titan_total_html(str(soup))
    assert p['overview']==[] and p['changes']==[]
    assert p['provider_id']=='356283'
    for codec in ('gb18030','gbk'):
        cell.string='暂无公司开盘'.encode('utf-8').decode(codec,errors='replace')
        assert parse_titan_total_html(str(soup))['changes']==[]
    cell.string='鏆傛棤鍏徃寮€鐩�'
    assert parse_titan_total_html(str(soup))['changes']==[]
    cell.string='未知错误'
    with pytest.raises(ValueError,match='overview'):
        parse_titan_total_html(str(soup))
