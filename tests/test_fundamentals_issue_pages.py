"""Offline designated roster inventory contracts; no source requests."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.fundamentals_issue_pages import issue_analysis_pages, issue_analysis_pages_with_quarantine

FIXTURE = Path(__file__).parent / 'fixtures/fundamentals_census/roster-130511-type8.html.gz'
URL = 'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'


def test_full_issue_inventory_preserves_scope_and_provenance():
    raw = gzip.decompress(FIXTURE.read_bytes())
    provenance = json.loads(FIXTURE.with_suffix('.provenance.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == provenance['sha256']
    rows = issue_analysis_pages(raw, roster_url=URL, issue='130511')
    assert len(rows) == 83
    assert [r['slot'] for r in rows] == list(range(1, 84))
    assert rows[0]['provider_id'] == '844632'
    assert (rows[0]['home'], rows[0]['away']) == ('FC首尔', '北京国安')
    assert (rows[0]['home_id'], rows[0]['away_id']) == ('741', '43')
    assert rows[0]['clock'] == '18:30'
    assert rows[0]['date_group'] == '2013-05-21'
    assert all(r['pairing_status'] == 'UNVERIFIED' for r in rows)
    assert all('score' not in r and 'sp' not in r for r in rows)


@pytest.mark.parametrize('change', ['issue', 'slot', 'link', 'duplicate_link', 'team',
                                  'native', 'same_team', 'empty', 'duplicate_row'])
def test_invalid_roster_fails_closed(change):
    soup = BeautifulSoup(gzip.decompress(FIXTURE.read_bytes()).decode('utf-8-sig'), 'html.parser')
    row = soup.select_one('tr#row_1')
    if change == 'issue':
        soup.select_one('option[selected]')['value'] = '130512'
    elif change == 'slot':
        row['matchid'] = '0'
    elif change == 'link':
        row.find('a', string='析')['href'] = 'https://example.org/844632cn.html'
    elif change == 'duplicate_link':
        row.append(BeautifulSoup('<a href="//live.nowscore.com/analysis/844632cn.html">析</a>', 'html.parser'))
    elif change == 'team':
        row.select_one('#HomeTeam_844632').decompose()
    elif change == 'native':
        row.select_one('#HomeTeam_844632')['onmouseover'] = ''
    elif change == 'same_team':
        row.select_one('#HomeTeam_844632')['onmouseover'] = '/temp/844632_43.htm'
    elif change == 'empty':
        for node in soup.select('tr[id^="row_"]'):
            node.decompose()
    elif change == 'duplicate_row':
        soup.append(BeautifulSoup(str(row), 'html.parser'))
    with pytest.raises(ValueError):
        issue_analysis_pages(str(soup).encode(), roster_url=URL, issue='130511')


@pytest.mark.parametrize('url,issue', [(URL, '130512'), (URL, 130511),
                                     (URL.replace('https:', 'http:'), '130511'),
                                     (URL.replace('cp.nowscore.com', 'cp.nowscore.com.evil'), '130511')])
def test_invalid_designated_url(url, issue):
    with pytest.raises(ValueError):
        issue_analysis_pages(b'', roster_url=url, issue=issue)


def test_zero_team_ids_preserve_distinct_names_without_asserting_pairing():
    soup = BeautifulSoup(gzip.decompress(FIXTURE.read_bytes()).decode('utf-8-sig'), 'html.parser')
    row = soup.select_one('tr#row_1')
    import re
    for prefix in ['HomeTeam', 'GuestTeam']:
        node = row.select_one(f'a[id^="{prefix}_"]')
        node['onmouseover'] = re.sub(r'_(\d+)\.htm', '_0.htm', node['onmouseover'])
    result = issue_analysis_pages(str(soup).encode(), roster_url=URL, issue='130511')
    assert result[0]['home_id'] == result[0]['away_id'] == '0'
    assert result[0]['pairing_status'] == 'UNVERIFIED'
    row.select_one('a[id^="GuestTeam_"]').string = row.select_one('a[id^="HomeTeam_"]').get_text()
    with pytest.raises(ValueError, match='same home and away'):
        issue_analysis_pages(str(soup).encode(), roster_url=URL, issue='130511')


def test_nonplayed_minus_one_analysis_is_explicitly_quarantined():
    soup = BeautifulSoup(gzip.decompress(FIXTURE.read_bytes()).decode('utf-8-sig'), 'html.parser')
    row = soup.select_one('tr#row_1')
    row.find('a', string='析')['href'] = '//live.nowscore.com/analysis/-1cn.html'
    for prefix in ['HomeTeam', 'GuestTeam']:
        node = row.select_one(f'a[id^="{prefix}_"]')
        node['id'] = f'{prefix}_-1'
    row.append(' 中断')
    valid, quarantined = issue_analysis_pages_with_quarantine(
        str(soup).encode(), roster_url=URL, issue='130511', quarantine_unavailable=True)
    assert len(valid) == 82 and len(quarantined) == 1
    assert quarantined[0]['slot'] == 1
    assert quarantined[0]['source_status'] == '中断'
    assert quarantined[0]['quarantine_reason'] == 'UNAVAILABLE_ANALYSIS_ID'
    assert quarantined[0]['home_id'].isdigit() and quarantined[0]['away_id'].isdigit()


def test_all_selected_nonplayed_slots_return_quarantine_evidence():
    soup = BeautifulSoup(gzip.decompress(FIXTURE.read_bytes()).decode('utf-8-sig'), 'html.parser')
    row = soup.select_one('tr#row_1')
    row.find('a', string='析')['href'] = '//live.nowscore.com/analysis/-1cn.html'
    for prefix in ['HomeTeam', 'GuestTeam']:
        node = row.select_one(f'a[id^="{prefix}_"]')
        node['id'] = f'{prefix}_-1'
    row.append(' 中断')
    valid, quarantined = issue_analysis_pages_with_quarantine(
        str(soup).encode(), roster_url=URL, issue='130511', slots=[1],
        quarantine_unavailable=True)
    assert valid == [] and [row['slot'] for row in quarantined] == [1]


def test_explicit_subset_quarantines_repeated_identity_without_renumbering():
    soup = BeautifulSoup(gzip.decompress(FIXTURE.read_bytes()).decode('utf-8-sig'), 'html.parser')
    duplicate = BeautifulSoup(str(soup.select_one('tr#row_1')), 'html.parser').tr
    duplicate['id'] = 'row_84'
    duplicate['matchid'] = '84'
    soup.append(duplicate)
    raw = str(soup).encode()
    with pytest.raises(ValueError, match='duplicate analysis'):
        issue_analysis_pages(raw, roster_url=URL, issue='130511')
    audited = issue_analysis_pages(raw, roster_url=URL, issue='130511', allow_repeated_provider_ids=True)
    assert len(audited) == 84
    assert audited[0]['provider_id'] == audited[-1]['provider_id']
    selected = issue_analysis_pages(raw, roster_url=URL, issue='130511', slots=[2, 4])
    assert [r['slot'] for r in selected] == [2, 4]
    for slots in ([0], [True], [1, 1], [], [99]):
        with pytest.raises(ValueError, match='slot set'):
            issue_analysis_pages(raw, roster_url=URL, issue='130511', slots=slots)
