from pathlib import Path

import pytest

from src.fundamentals_census import read_response
from src.market_sqlite_extract import extract_market_source
from src.market_sqlite import canonical_market_record


def test_euro_history_preserves_order_year_and_invalid_values():
    body=b'var game=Array("1|r|Company|0.5|||x");var gameDetail=Array("r^2|3|4|12-31 23:00|a|b|c|2010;0|bad||01-01 00:00|a|b|c|2011;");'
    result=extract_market_source(body,market='euro')
    assert len(result['records'])==3
    assert result['records'][2]['fields'][:3]==['0','bad','']
    assert result['records'][2]['fields'][-1]=='2011'
    assert result['records'][2]['quote_ordinal']==1
    assert result['anomalies'][0]['code']=='NORMALIZED_PARSE_ERROR'
    canonical_market_record(result)


def test_saved_euro_snapshot_and_total():
    for market,path in [('euro','fundamentals_titan_euro/357841.json'),('total','fundamentals_titan_total/356283.json')]:
        _,body=read_response(Path('tests/fixtures')/path)
        result=extract_market_source(body,market=market)
        assert result['records']
        assert result['normalized'] is not None
        canonical_market_record(result)
        if market=='total':
            assert any('7.5'==cell['text'] for r in result['records'] for cell in r['cells'])


def test_broken_source_is_anomaly_not_valid_empty():
    result=extract_market_source(b'<html>blocked</html>',market='euro')
    assert result['normalized'] is None
    assert any(a['code']=='NO_SOURCE_RECORDS' for a in result['anomalies'])
    with pytest.raises(ValueError):
        extract_market_source(b'x',market='unsupported')


def test_javascript_single_quotes_and_strict_json_have_same_source_records():
    field='1|id|company|1.2'
    strict=extract_market_source(('var game=Array("'+field+'");').encode(),market='euro')
    javascript=extract_market_source(("var game=Array('"+field+"');").encode(),market='euro')
    assert strict['records']==javascript['records']


def test_malformed_euro_retains_identity_and_anomaly():
    payload=b'var ScheduleID=123;var hometeamID=1;var guestteamID=2;var MatchTime="2010-01-01 12:00";var game=Array(7,null,{x:1});'
    result=extract_market_source(payload,market='euro')
    assert result['source_identity']['ScheduleID']==['123']
    assert sum(a['code']=='NON_STRING_ROW' for a in result['anomalies'])==3
    assert result['normalized'] is None


def test_invalid_total_retains_header_and_bookmaker_id():
    payload=b'<div class="analyhead"><a href="/team/Summary/123.html">Home</a></div><table id="odds"><tr><td><input name="oddsShow" data-id="9">bad price</td></tr></table><table id="oddsDetail"></table>'
    result=extract_market_source(payload,market='total')
    assert result['source_identity']['headers'][0]['elements'][0]['attributes']['href'].endswith('123.html')
    assert result['records'][0]['cells'][0]['elements'][0]['attributes']['data-id']=='9'
    assert result['normalized'] is None
