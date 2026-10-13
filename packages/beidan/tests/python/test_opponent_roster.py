"""Provider-declared issue identity inventory, including numerical gaps."""
import gzip
import pytest
from test_unified_sources import FIXTURES
from beidan_backend.opponent_roster import parse_exclusion_roster


def test_real_full_roster_preserves_declared_gaps_and_native_ids():
    raw=gzip.decompress((FIXTURES/'roster-20064.gz').read_bytes())
    result=parse_exclusion_roster(raw,source_url='https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&all=1&issueNum=20064',
        observed_at='2026-09-05T10:26:08+00:00',content_type='text/html; charset=utf-8')
    assert result['selected_issue']=='20064'
    assert len(result['roster'])==313
    assert all(set(r)=={'issue_id','slot','provider_id'} for r in result['roster'])
    assert next(r for r in result['roster'] if r['slot']==293)['provider_id']=='1870517'
    assert '26089' in result['declared_issues'] and '26090' not in result['declared_issues']


@pytest.mark.parametrize('url',[
    'https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&all=1&issueNum=26102',
    'https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&all=0&issueNum=20064',
    'https://other.example/buy/DanChang.aspx?TypeID=5&all=1&issueNum=20064'])
def test_wrong_bound_page_and_partial_roster_fail(url):
    raw=gzip.decompress((FIXTURES/'roster-20064.gz').read_bytes())
    with pytest.raises(ValueError):
        parse_exclusion_roster(raw,source_url=url,observed_at='2026-09-05T10:26:08+00:00',content_type='text/html; charset=utf-8')
