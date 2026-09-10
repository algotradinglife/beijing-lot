"""Approved source-row ties and horizon exclusion, independent of web parsers."""
import copy
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes


@pytest.fixture
def args():
    return dict(anchor_utc='2010-06-11T14:00:00Z',timezone='Asia/Shanghai',maximum_days=31,
        cutoff=Cutoff.decision_epoch('100601','2010-06-11T13:00:00Z'),source_hashes={'raw':'hash'},implementation_hashes={'code':'hash'})


def test_numeric_source_order_and_cutoff_mutation(args):
    rows=[dict(quote_id=f'{i}/A',company='A',quoted_local='6-11 20:00',line=2.5,over_hk=v,under_hk=.9) for i,v in [(10,.8),(2,1.0),(1,.9)]]
    x=diagnostic_monthday_quotes(rows,**args)
    assert x['rows'][0]['quote_id']=='1/A'
    assert x['policy']['same_minute_policy']=='SOURCE_ROW_ASC_NEWEST_FIRST_ASSUMPTION'
    assert len(x['policy']['tie_ledger'])==2
    assert x['policy']['input_sha256']==stable_json_hash(rows)
    assert diagnostic_monthday_quotes(rows[::-1],**args)['rows']==x['rows']
    future=dict(rows[0],quote_id='0/A',quoted_local='6-11 21:00',over_hk=99)
    assert diagnostic_monthday_quotes(rows+[future],**args)['rows']==x['rows']
    assert diagnostic_monthday_quotes([],**args)['rows']==[]
    for bad in [rows+[rows[0]], [dict(rows[0],quote_id='bad')],rows+[dict(rows[0],quote_id='10/B')]]:
        with pytest.raises(ValueError):diagnostic_monthday_quotes(bad,**args)


@pytest.mark.parametrize('clock,excluded',[('5-11 22:00',False),('5-11 21:59',True),('7-12 22:00',False),('7-12 22:01',True)])
def test_horizon_is_inclusive_and_exclusions_retain_raw(args,clock,excluded):
    row=dict(quote_id='1/A',company='A',quoted_local=clock,line=2.5,over_hk=.9,under_hk=.9)
    original=copy.deepcopy(row);x=diagnostic_monthday_quotes([row],**args)
    assert row==original
    assert x['policy']['excluded_outside_horizon_count']==int(excluded)
    if excluded:assert x['policy']['excluded_outside_horizon']==[dict(row=row,reason='OUTSIDE_ANCHOR_HORIZON')]
    assert x['policy']['input_sha256']==stable_json_hash([row])
    # Future in-horizon quotes still never cross the stricter decision cutoff.
    if clock.startswith('7-'):assert not x['rows']


@pytest.mark.parametrize('clock',['13-1 10:00','6-31 10:00','7-12 25:00','invalid'])
def test_malformed_clocks_never_become_horizon_exclusions(args,clock):
    with pytest.raises(ValueError,match='Malformed'):
        diagnostic_monthday_quotes([dict(quote_id='1/A',company='A',quoted_local=clock)],**args)
