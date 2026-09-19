import gzip
from pathlib import Path

import pytest

from src.fundamentals_page_fields import observed_page_fields
from src.fundamentals_census import decode_analysis_text

FIXTURES = Path(__file__).parent/'fixtures/fundamentals_census'


def test_raw_fields_preserve_contradictions_and_all_cells():
    raw = '''<meta charset="utf-8"><title>分析</title><script>
    var hometeam="主队"; var guestteam="客队";
    var h_data=[["13-01-01",1,2,3,4,5,6,7,4,1,"1-2"]];
    var a_data=[]; var dynamic=window.unknown;
    </script><table id="outer"><tr><td colspan="2">伤停<table id="inner"><tr><td>暂无数据</td></tr></table></td></tr></table>
    <a href="/data">赛事资料</a><script src="jsData/1.js"></script>'''.encode()
    r=observed_page_fields(raw,page_url='https://zq.titan007.com/analysis/1cn.htm')
    assert r['home_observed']=='主队'
    assert r['home_history_raw'][0][-1]=='1-2'
    assert r['away_history_raw']==[] and r['head_to_head_raw'] is None
    assert 'dynamic' in r['javascript_errors']
    assert len(r['page_tables'])==2
    assert r['page_tables'][0]['rows'][0][0]['colspan']=='2'
    assert r['page_tables'][1]['rows'][0][0]['text']=='暂无数据'
    assert r['script_urls']==['https://zq.titan007.com/analysis/jsData/1.js']
    assert 'window.unknown' in r['inline_scripts'][0]


@pytest.mark.parametrize('source',['nowscore','titan'])
def test_real_archived_fields(source):
    raw=gzip.decompress((FIXTURES/f'{source}-844632.html.gz').read_bytes())
    r=observed_page_fields(raw,page_url='https://example.org/analysis/')
    assert r['home_observed']=='FC首尔'
    assert len(r['home_history_raw'])>0
    assert len(r['page_tables'])>0
    assert r['observation_status']=='RAW_ONLY_NOT_VALIDATED'


def test_error_document_and_strict_encoding():
    r=observed_page_fields('<html>页面不存在</html>'.encode(),page_url='https://example.org/')
    assert r['home_history_raw'] is None and r['page_tables']==[]
    assert r['page_text']=='页面不存在'
    assert decode_analysis_text(b'<meta charset="utf-8">')[1]=='utf-8'
    with pytest.raises(ValueError):decode_analysis_text(b'<meta charset="unknown">')
    with pytest.raises(ValueError):decode_analysis_text(b'<meta charset="utf-8">\xff')
    with pytest.raises(ValueError):decode_analysis_text(b'<meta charset="utf-8"><meta charset="gbk">')


@pytest.mark.parametrize("codec,bom", [("utf-16le", b"\xff\xfe"), ("utf-16be", b"\xfe\xff")])
def test_unicode_bom_detection(codec, bom):
    text = "var name=分析;"
    assert decode_analysis_text(bom + text.encode(codec)) == (text, codec)
    with pytest.raises(ValueError):
        decode_analysis_text(bom + b"x")
