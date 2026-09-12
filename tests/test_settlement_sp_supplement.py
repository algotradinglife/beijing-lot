import copy
import pytest
from src.settlement_sp_supplement import parse_500_bf, build_sp_supplement


def test_parse_original_html_and_sale_day_boundary():
    html = '''<table><tr class="vs_lines" fid="123" value="{index:'12',homeTeam:'A',guestTeam:'B',leagueName:'L',scheduleDate:'2010-02-27'}">
    <td></td><td></td><td title="比赛时间：01:00"></td>
    <td><a title="析" class="red eng">2:2</a></td><td class="h_br"><span class="eng red">13.03</span></td></tr></table>'''
    row = parse_500_bf(html.encode('gb18030'))[0]
    assert row['kickoff'] == '2010-02-28 01:00'
    assert row['raw_sp'] == '13.03' and row['score'] == '2-2'
    assert parse_500_bf(html.replace('01:00', '20:30').encode('gb18030'))[0]['kickoff'] == '2010-02-27 20:30'
    for bad in ('<html></html>', html+html, html.replace('13.03','NaN'), html.replace('13.03','0')):
        with pytest.raises(ValueError):
            parse_500_bf(bad.encode('gb18030'))


def test_exact_missing_only_and_quarantine():
    n = dict(issue='100213', play='bf', slot=12, home='A', away='B', league='L',
             kickoff_time='02-27 20:30', score='2-2', expected_option='2:2', native_match_id='0001',
             source_sha256='b'*64, options=[dict(option='2:2',raw_sp='',sp=None)])
    p = dict(slot=12, home='A', away='B', league='L', kickoff='2010-02-27 20:30',
             score='2-2',raw_sp='13.03', provider_id='123')
    kwargs = dict(issue='100213',source_sha256='a'*64,aliases={})
    result = build_sp_supplement([n],[p],**kwargs)
    assert len(result['corrections']) == 1
    assert result['corrections'][0]['replacement_sp'] == 13.03
    assert n['options'][0]['sp'] is None
    for field in ('home','away','league','kickoff','score'):
        q=copy.deepcopy(p); q[field]='wrong'
        assert build_sp_supplement([n],[q],**kwargs)['audit'][0]['status']=='quarantined'
    for raw, value in [('1',1),('0',0),('invalid',None)]:
        m=copy.deepcopy(n);m['options'][0].update(raw_sp=raw,sp=value)
        assert not build_sp_supplement([m],[p],**kwargs)['corrections']
    for rows in ([],[p,p]):
        with pytest.raises(ValueError):build_sp_supplement([n],rows,**kwargs)
    m=copy.deepcopy(n);m['expected_option']='1:1'
    with pytest.raises(ValueError):build_sp_supplement([m],[p],**kwargs)
    p['away']='Alias'
    kwargs['aliases']={'Alias':'B'}
    assert len(build_sp_supplement([n],[p],**kwargs)['corrections'])==1
