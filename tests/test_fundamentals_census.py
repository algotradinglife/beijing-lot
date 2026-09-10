"""Offline contracts for the diagnostic census; never access live sources."""
import base64
import copy
import csv
import datetime
import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest

from src import fundamentals_census as census

FIXTURES = Path(__file__).parent / 'fixtures' / 'fundamentals_census'


@pytest.mark.parametrize('source,encoding,away', [('nowscore', 'utf-8', '北京中赫国安'),
                                                ('titan', 'gbk', '北京国安')])
def test_archived_844632_identity_encoding_and_raw_provenance(source, encoding, away):
    path = FIXTURES / f'{source}-844632.html.gz'
    raw = gzip.decompress(path.read_bytes())
    provenance = json.loads(path.with_suffix('.provenance.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == provenance['sha256']
    record = census.analysis_record(raw, source=source, provider_id='844632')
    assert record['encoding'] == encoding
    assert (record['home'], record['away']) == ('FC首尔', away)
    assert (record['home_id'], record['away_id']) == ('741', '43')
    assert record['kickoff_utc'] == '2013-05-21T10:30:00+00:00'
    with pytest.raises(ValueError, match='fixture ID'):
        census.analysis_record(raw, source=source, provider_id='844633')


def test_archived_titan_single_digit_hour():
    raw = gzip.decompress((FIXTURES / 'titan-844632.html.gz').read_bytes())
    raw = raw.replace(b'18:30', b'0:30')
    record = census.analysis_record(raw, source='titan', provider_id='844632')
    assert record['kickoff_utc'] == '2013-05-20T16:30:00+00:00'


def test_archived_titan_encoding_and_clock_fail_closed():
    raw = gzip.decompress((FIXTURES / 'titan-844632.html.gz').read_bytes())
    for bad in [raw.replace(b'charset=gb2312', b'charset=unknown'),
                raw.replace(b'<head>', b'<head><meta charset="utf-8">'),
                raw.replace(b'CalcTime.asp?matchTime=', b'not-a-clock.asp?matchTime='),
                raw.replace(b'2013/5/21 18:30:00', b'2013/2/30 18:30:00'),
                raw.replace(b'2013/5/21 18:30:00', b'2013/5/21 19:30:00'),
                raw.replace(b'</head>', b'<script src="CalcTime.asp?matchTime=2013/5/21 19:30:00"></script></head>')]:
        with pytest.raises(ValueError):
            census.analysis_record(bad, source='titan', provider_id='844632')


def write_roster_capture(root, row, *, home_id, away_id):
    kickoff = datetime.datetime.fromisoformat(row['kickoff_utc'].replace('Z', '+00:00')).astimezone(
        datetime.timezone(datetime.timedelta(hours=8)))
    deadline = kickoff - datetime.timedelta(minutes=5)
    issue, slot, provider_id = row['issue'], row['slot'], row['provider_id']
    raw = f'''<html><title>让球胜平负</title><script>M[{slot}][0]={provider_id};</script>
      <select id="dropIssueNum"><option selected value="{issue}">{issue}</option></select><table>
      <tr id="row_{slot}" matchid="{slot}" polygoal="0" cansale="false"
          name="{kickoff:%Y-%m-%d}" gamename="{row['league']}">
      <td>{slot}</td><td>{row['league']}</td><td>{kickoff:%H:%M}</td>
      <td title="截止时间：{deadline:%Y-%m-%d %H:%M}">未</td>
      <td><a id="HomeTeam_{provider_id}" onmouseover="getMyHTML2('/temp/{provider_id}_{home_id}.htm')">{row['roster_home']}</a></td>
      <td>0</td><td>-</td>
      <td><a id="GuestTeam_{provider_id}" onmouseover="getMyHTML2('/temp/{provider_id}_{away_id}.htm')">{row['roster_away']}</a></td>
      <td>-</td><td><a href="/sp/danchang/{issue}_{slot}_5.html">SP</a></td>
      </tr></table></html>'''.encode()
    url = f'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum={issue}'
    receipt = dict(url=url, final_url=url, status=200, content_type='text/html',
                   started_at_utc='2026-09-05T09:59:00+00:00',
                   received_at_utc='2026-09-05T09:59:01+00:00', byte_count=len(raw),
                   sha256=hashlib.sha256(raw).hexdigest(), body_base64=base64.b64encode(raw).decode())
    (root / f'roster-{issue}.json').write_text(json.dumps(receipt))
    row['roster_sha256'] = receipt['sha256']


@pytest.fixture
def pages():
    return {source: gzip.decompress((FIXTURES / f'{source}-1870517.html.gz').read_bytes())
            for source in ('nowscore', 'titan')}


@pytest.fixture
def pair(pages):
    return {source: census.analysis_record(raw, source=source, provider_id='1870517')
            for source, raw in pages.items()}


@pytest.fixture
def corpus(tmp_path, pages, pair):
    root = tmp_path / 'input'
    (root / 'raw-browser').mkdir(parents=True)
    row = dict(issue='20064', slot=24, provider_id='1870517', league='英乙',
               period='historical', panel_kind='regression',
               roster_home=pair['nowscore']['home'], roster_away=pair['nowscore']['away'],
               kickoff_utc=pair['nowscore']['kickoff_utc'])
    write_roster_capture(root, row, home_id='1356', away_id='376')
    (root / 'panel.json').write_text(json.dumps([row]))
    (root / 'denominator.json').write_text(json.dumps([row]))
    for source, raw in pages.items():
        host = 'live.nowscore.com' if source == 'nowscore' else 'zq.titan007.com'
        suffix = 'html' if source == 'nowscore' else 'htm'
        url = f'https://{host}/analysis/1870517cn.{suffix}'
        record = dict(url=url, final_url=url, status=200, content_type='text/html',
                      started_at_utc='2026-09-05T10:00:00+00:00',
                      received_at_utc='2026-09-05T10:00:01+00:00',
                      byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                      body_base64=base64.b64encode(raw).decode())
        (root / 'raw-browser' / f'{source}-1870517.json').write_text(json.dumps(record))
    return root


def test_canonical_and_text():
    assert census.canonical({'乙': 0, 'a': None}) == '{"a":null,"乙":0}'
    assert census.plain_text('<b>甲</b>\n <i>乙</i>') == '甲 乙'
    with pytest.raises(ValueError):
        census.canonical(float('nan'))


@pytest.mark.parametrize('text, expected', [
    ('var x = [1, "a;b", null,]; more();', [1, 'a;b', None]),
    ("var x = '中文';", '中文'), ('var y=[];', None), ('var x=[];', []),
])
def test_js_literal(text, expected):
    assert census.js_value(text, 'x') == expected


@pytest.mark.parametrize('text', ['var x=[];var x=[];', 'var x=alert(1);',
                                  'var x=[1]', 'var x={a:1,a:2};'])
def test_js_rejects_ambiguous_or_executable_values(text):
    with pytest.raises(ValueError):
        census.js_value(text, 'x')


def test_real_pages_regular_scores_and_standings(pair):
    assert census.compare_pair(pair['nowscore'], pair['titan']) == []
    for data in pair.values():
        assert len(data['history']) == 75
        assert data['season_tables'] == [
            {'side': 'home', 'team_id': '1356', 'state': 'POPULATED',
             'values': [37,18,11,8,53,43,10,65,4]},
            {'side': 'away', 'team_id': '376', 'state': 'POPULATED',
             'values': [37,15,13,9,52,37,15,58,6]},
        ]
        assert data['injuries'] == []
        assert data['injury_section_present']
        assert data['previous_lineup_section_present']
        assert len(data['previous_lineup']) == 40
    # Different column positions must still identify the same historical events.
    assert [r['history_id'] for r in pair['nowscore']['history']] == [r['history_id'] for r in pair['titan']['history']]
    assert pair['nowscore']['venue'] is None
    assert pair['titan']['venue']
    first = pair['nowscore']['history'][0]
    assert (first['halftime_home_score'], first['halftime_away_score']) == (0, 0)
    assert first['score_scope'] == 'SOURCE_PUBLISHED_FULL_TIME'


@pytest.mark.parametrize('raw,source,identity', [(b'bad','nowscore','1870517'),
    (b'\xff','titan','1870517'), (b'', 'other','1870517'), (b'', 'titan','x')])
def test_analysis_failure(raw, source, identity):
    with pytest.raises(ValueError):
        census.analysis_record(raw, source=source, provider_id=identity)


def test_wrong_document_identity(pages):
    with pytest.raises(ValueError, match='fixture ID'):
        census.analysis_record(pages['nowscore'], source='nowscore', provider_id='999')
    with pytest.raises(ValueError, match='fixture ID'):
        census.analysis_record(pages['titan'], source='titan', provider_id='999')
    without_embedded_id = pages['titan'].replace(b'var scheduleID = 1870517;', b'')
    assert without_embedded_id != pages['titan']
    with pytest.raises(ValueError, match='fixture ID'):
        census.analysis_record(without_embedded_id, source='titan', provider_id='1870517')


@pytest.mark.parametrize('source,home_id,away_id', [
    ('nowscore', 0, 2), ('nowscore', 3, 3), ('titan', 0, 2), ('titan', 3, 3)])
def test_history_requires_positive_distinct_team_identities(source, home_id, away_id):
    history_id_column = 20 if source == 'nowscore' else 15
    row = [''] * (history_id_column + 1)
    row[0], row[4], row[5], row[6], row[7] = '26-08-01', home_id, '甲', away_id, '乙'
    row[8], row[9], row[10], row[history_id_column] = 1, 0, '1-0', 99
    embedded = ('<input id="hide_scheduleId" value="123">' if source == 'nowscore'
                else '<script>var scheduleID=123;</script>')
    raw = (f'<html><title>分析</title>{embedded}<input id="hide_matchTime" value="2026-09-05 20:00">'
           '<script>var hometeam="甲";var guestteam="乙";var h2h_home=1;var h2h_away=2;'
           f'var h_data={census.canonical([row])};var a_data=[];var v_data=[];</script></html>').encode()
    with pytest.raises(ValueError, match='invalid history integer'):
        census.analysis_record(raw, source=source, provider_id='123')


def test_conflicts_preserve_original_values(pair):
    original = copy.deepcopy(pair)
    right = copy.deepcopy(pair['titan'])
    right['history'][0]['home_score'] += 1
    findings = census.compare_pair(pair['nowscore'], right)
    assert findings[0]['disposition'] == 'UNRESOLVED'
    right['history'].pop(0)
    assert census.compare_pair(pair['nowscore'], right)[0]['disposition'] == 'COVERAGE_DIFFERENCE'
    right['home'] = 'different'
    assert census.compare_pair(pair['nowscore'], right)[0]['disposition'] == 'IDENTITY_AMBIGUOUS'
    assert pair == original


def test_halftime_difference_is_a_genuine_discrepancy(pair):
    right = copy.deepcopy(pair['titan'])
    right['history'][0]['halftime_home_score'] += 1
    finding = census.compare_pair(pair['nowscore'], right)[0]
    assert finding['field'].startswith('h_data:')
    assert finding['disposition'] == 'UNRESOLVED'


def test_duplicate_history_identity_is_not_source_agreement(pair):
    left = copy.deepcopy(pair['nowscore'])
    right = copy.deepcopy(pair['titan'])
    history_id = left['history'][0]['history_id']
    for record in (left, right):
        duplicate = copy.deepcopy(next(row for row in record['history'] if row['history_id'] == history_id))
        duplicate['home_score'] += 1
        record['history'].append(duplicate)
    finding = next(row for row in census.compare_pair(left, right)
                   if row['field'].endswith(f':{history_id}'))
    assert finding['disposition'] == 'UNRESOLVED'


@pytest.mark.parametrize('source', ['nowscore', 'titan'])
def test_missing_standings_side_keeps_team_identity_and_is_not_agreement(pages, source):
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(pages[source].decode(), 'html.parser')
    for table in soup.find_all('table'):
        if table.find('a', href=lambda value: value and re.search(r'/team/(?:Summary/)?1356\.html?$', value, re.I)):
            table.decompose()
            break
    parsed = census.analysis_record(str(soup).encode(), source=source, provider_id='1870517')
    assert parsed['season_tables'][0] == {
        'side': 'home', 'team_id': '1356', 'state': 'ABSENT', 'values': None}
    assert parsed['season_tables'][1]['team_id'] == '376'
    findings = census.compare_pair(parsed, copy.deepcopy(parsed))
    assert findings[0]['field'] == 'season_tables'
    assert findings[0]['disposition'] == 'COVERAGE_DIFFERENCE'


@pytest.mark.parametrize('source', ['nowscore', 'titan'])
def test_halftime_cannot_exceed_fulltime(pages, source):
    raw = pages[source].replace(b"'0-0'", b"'99-99'", 1)
    with pytest.raises(ValueError, match='halftime score exceeds full-time'):
        census.analysis_record(raw, source=source, provider_id='1870517')


def test_transport_receipt_integrity(corpus):
    path = corpus / 'raw-browser/nowscore-1870517.json'
    meta, raw = census.read_response(path)
    assert meta['sha256'] == hashlib.sha256(raw).hexdigest()
    assert 'body_base64' not in meta
    record = json.loads(path.read_text())
    record['sha256'] = '0' * 64
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        census.read_response(path)
    record['sha256'] = meta['sha256']
    record['byte_count'] += 1
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='size mismatch'):
        census.read_response(path)
    record['byte_count'] -= 1
    record.pop('sha256')
    path.write_text(json.dumps(record))
    assert census.read_response(path)[0]['sha256'] == meta['sha256']


@pytest.mark.parametrize('field,value', [('status',True), ('url','file:///tmp/x'),
    ('received_at_utc','2026-09-05T09:00:00Z'), ('started_at_utc','2026-09-05T10:00:00'),
    ('body_base64','%%%')])
def test_invalid_receipts(corpus, field, value):
    path = corpus / 'raw-browser/nowscore-1870517.json'
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        census.read_response(path)


def test_panel_denominators_and_repeatability():
    rows = [dict(issue='001', slot=i, provider_id=str(i), league='A' if i < 4 else 'B',
                 kickoff_utc='2026-09-06T00:00:00+00:00') for i in range(6)]
    rows += [{**rows[0], 'slot': 10}, {**rows[1], 'slot': 11, 'league':'excluded'}]
    kwargs = dict(at_utc='2026-09-05T00:00:00Z', leagues=['A','B'], quotas={'001':4}, upcoming_issues=['001'])
    panel, denominator = census.select_panel(rows, **kwargs)
    assert len(panel) == 4 and len(denominator) == 8
    assert [r['league'] for r in panel] == ['A','B','A','B']
    assert denominator[-2]['reason'] == 'duplicate_provider_candidate'
    assert denominator[-1]['reason'] == 'outside_competition_scope'
    assert census.select_panel(rows, **kwargs) == (panel, denominator)
    with pytest.raises(ValueError, match='insufficient'):
        census.select_panel(rows, **{**kwargs, 'quotas':{'001':7}})
    with pytest.raises(ValueError, match='invalid sampling'):
        census.select_panel(rows, **{**kwargs, 'at_utc':'2026-09-05'})


def test_csv_missing_zero_ids_and_empty(tmp_path):
    path = tmp_path / 'table.csv'
    census.write_rows(path, [dict(id='001', value=None), dict(id='002', value=0)], ['id','value'])
    with path.open() as stream:
        assert list(csv.DictReader(stream)) == [{'id':'001','value':''},{'id':'002','value':'0'}]
    census.write_rows(path, [], ['id','value'])
    assert path.read_text() == 'id,value\n'
    with pytest.raises(ValueError):
        census.write_rows(path, [{'extra':1}], ['id'])


def test_build_replay_and_no_overwrite(corpus, tmp_path):
    stamp = '2026-09-05T12:00:00Z'
    first = census.build_outputs(corpus, tmp_path/'first', generated_at_utc=stamp)
    second = census.build_outputs(corpus, tmp_path/'second', generated_at_utc=stamp)
    assert first == second
    assert first['panel_rows'] == 1 and first['response_rows'] == 2
    assert first['historical_learning'] == 'NONE'
    assert first['finding_rows'] == 0
    for name, expected in first['output_hashes'].items():
        assert hashlib.sha256((tmp_path/'first'/name).read_bytes()).hexdigest() == expected
    with pytest.raises(FileExistsError):
        census.build_outputs(corpus, tmp_path/'first', generated_at_utc=stamp)


def test_panel_provider_identity_must_match_denominator(corpus, tmp_path):
    path = corpus / 'denominator.json'
    rows = json.loads(path.read_text())
    rows[0]['provider_id'] = '999999'
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='panel to denominator'):
        census.build_outputs(corpus, tmp_path / 'mismatch', generated_at_utc='2026-09-05T12:00:00Z')
    assert not (tmp_path / 'mismatch').exists()


def test_roster_team_or_orientation_conflict_quarantines_fixture(corpus, tmp_path):
    for name in ('panel', 'denominator'):
        path = corpus / f'{name}.json'
        rows = json.loads(path.read_text())
        rows[0]['roster_home'], rows[0]['roster_away'] = rows[0]['roster_away'], rows[0]['roster_home']
        path.write_text(json.dumps(rows))
    output = tmp_path / 'roster-conflict'
    census.build_outputs(corpus, output, generated_at_utc='2026-09-05T12:00:00Z')
    with (output / 'findings.csv').open() as stream:
        findings = list(csv.DictReader(stream))
    assert {(row['field'], row['disposition']) for row in findings} == {
        ('panel_roster_home', 'IDENTITY_AMBIGUOUS'),
        ('panel_roster_away', 'IDENTITY_AMBIGUOUS'),
    }
    from src.fundamentals_pipeline import derive_release_tables, read_normalized_release
    tables = derive_release_tables('roster-conflict', {'main': read_normalized_release(output)}, [])
    assert tables['canonical_identity'][0]['identity_status'] == 'QUARANTINED'
    assert tables['facts'] == []


def test_analysis_sources_agreeing_on_wrong_team_ids_are_quarantined(corpus, pair, tmp_path, monkeypatch):
    wrong = copy.deepcopy(pair)
    for record in wrong.values():
        record['home_id'], record['away_id'] = '999', '998'
    monkeypatch.setattr(census, 'analysis_record',
                        lambda raw, *, source, provider_id, auxiliary_raw=None: wrong[source])
    output = tmp_path / 'wrong-analysis-teams'
    census.build_outputs(corpus, output, generated_at_utc='2026-09-05T12:00:00Z')
    with (output / 'findings.csv').open() as stream:
        findings = list(csv.DictReader(stream))
    assert {(row['field'], row['disposition']) for row in findings
            if row['field'].startswith('roster_')} == {
        ('roster_home_id:nowscore', 'IDENTITY_AMBIGUOUS'),
        ('roster_away_id:nowscore', 'IDENTITY_AMBIGUOUS'),
        ('roster_home_id:titan', 'IDENTITY_AMBIGUOUS'),
        ('roster_away_id:titan', 'IDENTITY_AMBIGUOUS'),
    }
    from src.fundamentals_pipeline import derive_release_tables, read_normalized_release
    tables = derive_release_tables('wrong-analysis-teams', {'main': read_normalized_release(output)}, [])
    assert tables['canonical_identity'][0]['identity_status'] == 'QUARANTINED'
    assert tables['facts'] == []


def test_panel_requires_roster_team_identity(corpus, tmp_path):
    path = corpus / 'panel.json'
    rows = json.loads(path.read_text())
    del rows[0]['roster_home']
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='incomplete'):
        census.build_outputs(corpus, tmp_path / 'missing-roster', generated_at_utc='2026-09-05T12:00:00Z')


def test_build_explicit_missing_and_http_failure(corpus, tmp_path):
    (corpus/'raw-browser/nowscore-1870517.json').unlink()
    path = corpus/'raw-browser/titan-1870517.json'
    record = json.loads(path.read_text())
    record['status'] = 442
    path.write_text(json.dumps(record))
    census.build_outputs(corpus, tmp_path/'result', generated_at_utc='2026-09-05T12:00:00Z')
    with (tmp_path/'result/responses.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert [r['capture_state'] for r in rows] == ['NOT_ATTEMPTED','HTTP_FAILURE']
    assert all(r['parse_state']=='NOT_PARSED' for r in rows)


def test_absent_schedule_and_lineup_sections_are_not_published_empty(corpus, tmp_path):
    panel = json.loads((corpus / 'panel.json').read_text())[0]
    kickoff = panel['kickoff_utc']
    local = __import__('datetime').datetime.fromisoformat(kickoff).astimezone(
        __import__('zoneinfo').ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    raw = (f'<html><title>分析</title><input id="hide_scheduleId" value="1870517">'
           f'<input id="hide_matchTime" value="{local}"><script>'
           'var scheduleID=1870517;'
           'var hometeam="埃克塞特城";var guestteam="科切斯特联";'
           'var h2h_home=1356;var h2h_away=376;var h_data=[];var a_data=[];var v_data=[];'
           '</script></html>').encode()
    for source in ('nowscore', 'titan'):
        path = corpus / 'raw-browser' / f'{source}-1870517.json'
        receipt = json.loads(path.read_text())
        receipt.update(byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                       body_base64=base64.b64encode(raw).decode())
        path.write_text(json.dumps(receipt))
    output = tmp_path / 'absent-sections'
    census.build_outputs(corpus, output, generated_at_utc='2026-09-05T12:00:00Z')
    with (output / 'fields.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    states = {(row['source'], row['field']): row['field_state'] for row in rows}
    assert all(states[(source, field)] == 'ABSENT'
               for source in ('nowscore', 'titan')
               for field in ('previous_lineup', 'schedules'))


def test_build_rollback(corpus, tmp_path, monkeypatch):
    def fail_publish(*args):
        raise OSError('injected publish failure')
    monkeypatch.setattr(census.os, 'rename', fail_publish)
    with pytest.raises(OSError, match='injected'):
        census.build_outputs(corpus, tmp_path/'result', generated_at_utc='2026-09-05T12:00:00Z')
    assert not (tmp_path/'result').exists()
    assert not list(tmp_path.glob('.census-build-*'))


def test_external_data_script_required_and_parsed():
    raw = gzip.decompress((FIXTURES/'nowscore-2910880.gz').read_bytes())
    auxiliary = gzip.decompress((FIXTURES/'nowscore-js-2910880.gz').read_bytes())
    with pytest.raises(ValueError, match='required analysis JS'):
        census.analysis_record(raw, source='nowscore', provider_id='2910880')
    data = census.analysis_record(raw, source='nowscore', provider_id='2910880', auxiliary_raw=auxiliary)
    first = next(r for r in data['history'] if r['block']=='h_data')
    assert first['history_id'] == '2910874'
    assert first['event_date'] == '2026-09-01'
    assert (first['home_score'],first['away_score']) == (2,3)
    assert first['home_id']=='1964' and first['away_id']=='350'


def test_standings_difference_is_unresolved(pair):
    right = copy.deepcopy(pair['titan'])
    right['season_tables'][0]['values'][1] += 1
    findings = census.compare_pair(pair['nowscore'],right)
    assert findings[0]['field']=='season_tables'
    assert findings[0]['disposition']=='UNRESOLVED'


def test_schedule_difference_is_queued_and_missing_schedule_is_coverage(pair):
    left = copy.deepcopy(pair['nowscore'])
    right = copy.deepcopy(pair['titan'])
    left['schedules'] = [['09-06', '甲-丙']]
    right['schedules'] = [['09-07', '甲-丁']]
    finding = census.compare_pair(left, right)[0]
    assert finding['field'] == 'schedules'
    assert finding['disposition'] == 'UNRESOLVED'
    right['schedules'] = []
    assert census.compare_pair(left, right)[0]['disposition'] == 'COVERAGE_DIFFERENCE'


def test_source_schedule_layouts_normalize_to_same_typed_facts_and_reject_bad_rows():
    fixture_date = datetime.date(2025, 5, 17)
    nowscore = census.normalize_schedule_rows(
        [['日职联', '2025-05-21', '川崎前锋 VS 浦和红钻', '4 天']],
        source='nowscore', fixture_local_date=fixture_date)
    titan = census.normalize_schedule_rows(
        [['05-21', '日职联', '川崎前锋 - 浦和红钻', '分析', '', '4 天']],
        source='titan', fixture_local_date=fixture_date)
    assert nowscore == titan == [{
        'event_date': '2025-05-21', 'competition': '日职联',
        'home': '川崎前锋', 'away': '浦和红钻', 'published_lead_days': 4}]
    assert census.normalize_schedule_rows(
        [['02-29', '联赛', '甲 - 乙', '', '', '60 天']],
        source='titan', fixture_local_date=datetime.date(2023, 12, 31))[0]['event_date'] == '2024-02-29'
    with pytest.raises(ValueError, match='Titan schedule row'):
        census.normalize_schedule_rows(
            [['05-21', '日职联', '川崎前锋 - 浦和红钻', '', 'unexpected', '4 天']],
            source='titan', fixture_local_date=fixture_date)


def test_roster_uses_authoritative_parser(corpus, monkeypatch):
    path = corpus/'raw-browser/nowscore-1870517.json'
    record = json.loads(path.read_text())
    record['final_url']='https://cp.nowscore.com/buy/DanChang.aspx'
    path.write_text(json.dumps(record))
    parsed = dict(schedule_date='2026-09-05',kickoff_time='20:00',slot=1,
                  native_match_id='00123',league='英乙',home='甲',away='乙',home_id='11',away_id='22',status='未',
                  cutoff_text='截止时间：2026-09-05 19:55')
    with monkeypatch.context() as patch:
        patch.setattr(census,'parse_page',lambda raw,issue,kind:[parsed])
        rows=census.roster_records(path,'001')
        assert rows[0]['provider_id']=='00123'
        assert rows[0]['kickoff_utc']=='2026-09-05T12:00:00+00:00'
        assert rows[0]['issue']=='001'
        assert (rows[0]['roster_home_id'], rows[0]['roster_away_id']) == ('11', '22')
        patch.setattr(census,'parse_page',lambda raw,issue,kind:[parsed,parsed])
        with pytest.raises(ValueError,match='duplicate'):
            census.roster_records(path,'001')
    record['status']=442
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError,match='roster capture'):
        census.roster_records(path,'001')


def test_external_asset_provenance_and_latest_availability(corpus, tmp_path):
    identity='2910880'
    for name in ('nowscore','nowscore-js','titan'):
        raw=gzip.decompress((FIXTURES/f'{name}-{identity}.gz').read_bytes())
        record=json.loads((FIXTURES/f'{name}-{identity}.provenance.json').read_text())
        record['body_base64']=base64.b64encode(raw).decode()
        record['started_at_utc']='2026-09-05T10:00:00Z'
        # Offset strings cannot be compared lexicographically for chronology.
        record['received_at_utc']='2026-09-05T13:00:00+02:00' if name=='nowscore-js' else '2026-09-05T10:00:01Z'
        (corpus/'raw-browser'/f'{name}-{identity}.json').write_text(json.dumps(record))
    row=dict(issue='00001',slot=1,provider_id=identity,league='英甲',period='upcoming',
             panel_kind='stratified',roster_home='科里蒂巴',roster_away='米拉索',
             kickoff_utc='2026-09-05T10:30:00Z')
    write_roster_capture(corpus, row, home_id='350', away_id='7429')
    for name in ('panel','denominator'):
        (corpus/f'{name}.json').write_text(json.dumps([row]))
    census.build_outputs(corpus,tmp_path/'asset-result',generated_at_utc='2026-09-05T12:00:00Z')
    with (tmp_path/'asset-result/responses.csv').open() as stream:
        response=next(r for r in csv.DictReader(stream) if r['source']=='nowscore')
    assert response['parse_state']=='PARSED'
    assert response['evidence_class']=='HISTORICAL_PROXY'
    assert response['received_at_utc']=='2026-09-05T13:00:00+02:00'
    with (tmp_path/'asset-result/fields.csv').open() as stream:
        fields={r['field']:r for r in csv.DictReader(stream) if r['source']=='nowscore'}
    assert fields['h_data']['raw_sha256']==response['auxiliary_sha256']
    assert fields['venue']['raw_sha256']==response['sha256']
    assert response['auxiliary_status']=='200'


def test_inline_history_ignores_unreferenced_auxiliary_provenance(corpus, tmp_path):
    url = 'https://live.nowscore.com/analysisJs/data1870517.js'
    (corpus / 'raw-browser' / 'nowscore-js-1870517.json').write_text(json.dumps({
        'started_at_utc': '2026-09-05T11:00:00Z', 'received_at_utc': '2026-09-05T11:00:01Z',
        'url': url, 'attempts': 3, 'error': 'Timeout: auxiliary URL unavailable',
    }))
    census.build_outputs(corpus, tmp_path / 'inline-result', generated_at_utc='2026-09-05T12:00:00Z')
    with (tmp_path / 'inline-result' / 'responses.csv').open() as stream:
        response = next(row for row in csv.DictReader(stream) if row['source'] == 'nowscore')
    with (tmp_path / 'inline-result' / 'fields.csv').open() as stream:
        history = next(row for row in csv.DictReader(stream)
                       if row['source'] == 'nowscore' and row['field'] == 'h_data')
    assert history['record_count'] == '30'
    assert history['raw_sha256'] == response['sha256']
    assert history['received_at_utc'] == '2026-09-05T10:00:01+00:00'
    assert response['received_at_utc'] == '2026-09-05T10:00:01+00:00'
    assert response['parse_state'] == 'PARSED'
    assert response['auxiliary_sha256'] == ''


def test_auxiliary_transport_failure_is_explicit_parser_failure(corpus, tmp_path):
    identity = '2910880'
    raw = gzip.decompress((FIXTURES / f'nowscore-{identity}.gz').read_bytes())
    receipt = json.loads((FIXTURES / f'nowscore-{identity}.provenance.json').read_text())
    receipt['body_base64'] = base64.b64encode(raw).decode()
    (corpus / 'raw-browser' / f'nowscore-{identity}.json').write_text(json.dumps(receipt))
    (corpus / 'raw-browser' / f'nowscore-js-{identity}.json').write_text(json.dumps({
        'url': f'https://live.nowscore.com/analysisJs/data{identity}.js',
        'started_at_utc': '2026-09-05T10:00:00Z', 'received_at_utc': '2026-09-05T10:00:01Z',
        'attempts': 3, 'error': 'Timeout: bounded timeout'}))
    titan_raw = gzip.decompress((FIXTURES / f'titan-{identity}.gz').read_bytes())
    titan_receipt = json.loads((FIXTURES / f'titan-{identity}.provenance.json').read_text())
    titan_receipt['body_base64'] = base64.b64encode(titan_raw).decode()
    (corpus / 'raw-browser' / f'titan-{identity}.json').write_text(json.dumps(titan_receipt))
    row = dict(issue='00001', slot=1, provider_id=identity, league='英甲', period='historical',
               panel_kind='regression', roster_home='科里蒂巴', roster_away='米拉索',
               kickoff_utc='2026-09-05T10:30:00+00:00')
    write_roster_capture(corpus, row, home_id='350', away_id='7429')
    for name in ('panel', 'denominator'):
        (corpus / f'{name}.json').write_text(json.dumps([row]))
    census.build_outputs(corpus, tmp_path / 'aux-failure', generated_at_utc='2026-09-05T12:00:00Z')
    with (tmp_path / 'aux-failure' / 'responses.csv').open() as stream:
        response = next(row for row in csv.DictReader(stream) if row['source'] == 'nowscore')
    assert response['capture_state'] == 'HTTP_OK'
    assert response['parse_state'] == 'PARSER_FAILURE'
    assert response['error'] == 'auxiliary transport failure: Timeout: bounded timeout'


def test_cli_materialization_and_replay(tmp_path):
    import subprocess
    import sys
    repo=Path(__file__).resolve().parents[1]
    root=tmp_path/'cli-input'
    output=tmp_path/'cli-output'
    subprocess.run([sys.executable,str(repo/'scripts/materialize_fundamentals_census_fixture.py'),
                    '--output-dir',str(root)],check=True,capture_output=True,text=True)
    result=subprocess.run([sys.executable,str(repo/'scripts/replay_fundamentals_census.py'),
                    '--input-dir',str(root),'--output-dir',str(output),
                    '--generated-at-utc','2026-09-05T12:00:00Z'],check=True,capture_output=True,text=True)
    receipt=json.loads(result.stdout)
    assert receipt['panel_rows']==1 and receipt['finding_rows']==0
    assert json.loads((root/'panel.json').read_text())[0]['slot']==293
    assert 'multimarket_p0.py' in receipt['implementation_hashes']


def test_native_lottery_group_date_is_not_kickoff_calendar_day(tmp_path):
    raw=gzip.decompress((FIXTURES/'roster-20064.gz').read_bytes())
    receipt=json.loads((FIXTURES/'roster-20064.provenance.json').read_text())
    receipt['body_base64']=base64.b64encode(raw).decode()
    path=tmp_path/'roster.json';path.write_text(json.dumps(receipt))
    records=census.roster_records(path,'20064')
    row=next(r for r in records if r['slot']==293)
    assert row['roster_group_date']=='2020-06-22'
    assert row['roster_clock']=='00:15'
    assert row['roster_deadline_utc']=='2020-06-22T16:10:00+00:00'
    assert row['kickoff_utc']=='2020-06-22T16:15:00+00:00'
    assert row['provider_id']=='1870517'


def test_archived_visible_kickoff_profile():
    raw=gzip.decompress((FIXTURES/'nowscore-1326813.gz').read_bytes())
    record=census.analysis_record(raw,source='nowscore',provider_id='1326813')
    assert record['kickoff_utc']=='2016-11-12T13:00:00+00:00'
    assert record['home_id']=='803' and record['away_id']=='815'
    assert len(record['history'])==65
    duplicate=b'<table><tr><td class="team_info"><strong>\xe6\xaf\x94\xe8\xb5\x9b\xe6\x97\xb6\xe9\x97\xb4\xef\xbc\x9a2016-11-12 21:00:00</strong></td></tr></table>'
    with pytest.raises(ValueError,match='ambiguous visible'):
        census.analysis_record(raw+duplicate,source='nowscore',provider_id='1326813')


def test_same_name_different_native_team_is_quarantined(pair):
    right=copy.deepcopy(pair['titan']);right['home_id']='999'
    findings=census.compare_pair(pair['nowscore'],right)
    assert findings[0]['field']=='home_id'
    assert findings[0]['disposition']=='IDENTITY_AMBIGUOUS'


def test_redirect_to_another_fixture_is_not_parsed(corpus,tmp_path):
    p=corpus/'raw-browser/titan-1870517.json';r=json.loads(p.read_text())
    r['final_url']='https://zq.titan007.com/analysis/999cn.htm';p.write_text(json.dumps(r))
    census.build_outputs(corpus,tmp_path/'redirect',generated_at_utc='2026-09-05T12:00:00Z')
    with (tmp_path/'redirect/responses.csv').open() as stream:
        titan=next(r for r in csv.DictReader(stream) if r['source']=='titan')
    assert titan['capture_state']=='HTTP_FAILURE' and titan['parse_state']=='NOT_PARSED'


def test_sampling_revision_hash_is_required_to_match(corpus,tmp_path):
    (corpus/'sampling-revision.json').write_text(json.dumps({'new_panel_sha256':'wrong'}))
    with pytest.raises(ValueError,match='revision panel hash'):
        census.build_outputs(corpus,tmp_path/'revision',generated_at_utc='2026-09-05T12:00:00Z')
    assert not (tmp_path/'revision').exists()


def test_actual_future_schedule_and_separate_lineup_tables():
    for source,expected_lineup in [('nowscore',40),('titan',32)]:
        raw=gzip.decompress((FIXTURES/f'{source}-2701744.gz').read_bytes())
        auxiliary=gzip.decompress((FIXTURES/'nowscore-js-2701744.gz').read_bytes()) if source=='nowscore' else None
        data=census.analysis_record(raw,source=source,provider_id='2701744',auxiliary_raw=auxiliary)
        assert len(data['schedules'])==10
        assert len(data['schedule_source_rows'])==10
        assert len(data['previous_lineup'])==expected_lineup
        assert len(data['injuries'])==3
        assert data['previous_lineup'][0]=='16 牲川步见'
    findings = census.compare_pair(
        census.analysis_record(
            gzip.decompress((FIXTURES/'nowscore-2701744.gz').read_bytes()), source='nowscore',
            provider_id='2701744', auxiliary_raw=gzip.decompress((FIXTURES/'nowscore-js-2701744.gz').read_bytes())),
        census.analysis_record(
            gzip.decompress((FIXTURES/'titan-2701744.gz').read_bytes()), source='titan',
            provider_id='2701744'))
    assert not any(finding['field'] == 'schedules' for finding in findings)


def test_implementation_change_aborts_publish(corpus,tmp_path,monkeypatch):
    original=Path.read_bytes
    calls=0
    def changing_bytes(path):
        nonlocal calls
        raw=original(path)
        if path==Path(census.__file__):
            calls+=1
            if calls>1:return raw+b'\n# changed'
        return raw
    monkeypatch.setattr(Path,'read_bytes',changing_bytes)
    with pytest.raises(ValueError,match='implementation changed'):
        census.build_outputs(corpus,tmp_path/'changed-code',generated_at_utc='2026-09-05T12:00:00Z')
    assert not (tmp_path/'changed-code').exists()
    assert not list(tmp_path.glob('.census-build-*'))
