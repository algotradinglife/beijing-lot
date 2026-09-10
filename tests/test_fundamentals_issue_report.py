"""Full denominator, explicit revisions and failure classification."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from src.fundamentals_issue_report import issue_capture_report

FIXTURES = Path(__file__).parent / 'fixtures/fundamentals_census'


def write_receipt(path, raw, url, status=200):
    path.write_text(json.dumps(dict(url=url, final_url=url, status=status,
        started_at_utc='2026-09-06T00:00:00+00:00', received_at_utc='2026-09-06T00:00:01+00:00',
        byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        body_base64=base64.b64encode(raw).decode())))
    return str(path)


@pytest.fixture
def roster(tmp_path):
    return write_receipt(tmp_path/'roster.json',
        gzip.decompress((FIXTURES/'roster-130511-type8.html.gz').read_bytes()),
        'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511')


def test_full_denominator_with_no_captures(roster):
    report = issue_capture_report(roster, [], issue='130511')
    assert report['fixture_count'] == 83
    assert report['expected_pages'] == len(report['observations']) == 166
    assert all(row['capture_state'] == 'NOT_CAPTURED' for row in report['observations'])
    assert report['identity_acceptance'] == 'NOT_PERFORMED'


def test_two_sources_do_not_automatically_accept_identity(roster, tmp_path):
    paths=[]
    for source, host, ext in [('nowscore','live.nowscore.com','html'),('titan','zq.titan007.com','htm')]:
        paths.append(write_receipt(tmp_path/f'{source}.json',
            gzip.decompress((FIXTURES/f'{source}-844632.html.gz').read_bytes()),
            f'https://{host}/analysis/844632cn.{ext}'))
    report = issue_capture_report(roster, paths, issue='130511')
    rows = [r for r in report['observations'] if r['slot'] == 1]
    assert all(r['parse_state'] == 'PARSED' for r in rows)
    assert all(r['pairing_status'] == 'PENDING_IDENTITY_REVIEW' for r in rows)
    assert rows[0]['away'] != rows[1]['away']
    assert len(report['input_file_hashes']) == 3
    assert len(report['implementation_hashes']) == 5
    assert 'fundamentals_jina.py' in report['implementation_hashes']


@pytest.mark.parametrize('status,parse', [(404,'NOT_ATTEMPTED'), (200,'PARSE_FAILURE')])
def test_failure_is_not_empty_content(roster,tmp_path,status,parse):
    path=write_receipt(tmp_path/'failed.json',b'not a match',
                       'https://live.nowscore.com/analysis/844632cn.html',status)
    row=issue_capture_report(roster,[path],issue='130511')['observations'][0]
    assert row['parse_state'] == parse
    assert row['status'] == status
    assert row['home'] is None


@pytest.mark.parametrize('change',['duplicate','unknown','redirect','tamper'])
def test_receipt_selection_is_explicit(roster,tmp_path,change):
    path=write_receipt(tmp_path/'page.json',b'x','https://live.nowscore.com/analysis/844632cn.html')
    record=json.loads(Path(path).read_text())
    paths=[path]
    if change=='duplicate': paths.append(path)
    if change=='unknown': record['url']=record['final_url']='https://live.nowscore.com/analysis/999cn.html'
    if change=='redirect': record['final_url']='https://example.org/'
    if change=='tamper': record['sha256']='0'*64
    Path(path).write_text(json.dumps(record))
    with pytest.raises(ValueError): issue_capture_report(roster,paths,issue='130511')


def test_missing_designated_slot_is_not_a_smaller_success(roster):
    from bs4 import BeautifulSoup
    record=json.loads(Path(roster).read_text())
    soup=BeautifulSoup(base64.b64decode(record['body_base64']).decode('utf-8-sig'),'html.parser')
    soup.select_one('#row_83').decompose()
    raw=str(soup).encode()
    write_receipt(Path(roster),raw,record['url'])
    with pytest.raises(ValueError,match='slot set mismatch'):
        issue_capture_report(roster,[],issue='130511')


def test_malformed_clock_keeps_all_rows_and_raw_value(roster,tmp_path):
    raw=b'<meta charset="utf-8"><title>\xe5\x88\x86\xe6\x9e\x90</title><script>var hometeam="Home";var guestteam="Away";var h2h_home=1;var h2h_away=2;var strTime=123;</script><input id="hide_scheduleId" value="844632">'
    path=write_receipt(tmp_path/'bad-clock.json',raw,'https://live.nowscore.com/analysis/844632cn.html')
    report=issue_capture_report(roster,[path],issue='130511')
    assert len(report['observations'])==166
    assert report['observations'][0]['parse_state']=='PARSE_FAILURE'
    assert report['page_fields'][0]['raw_fields']['javascript_literals']['strTime']==123


def test_schedule_failure_is_isolated_without_accepting_the_field(roster,tmp_path):
    from src.fundamentals_census import AnalysisFieldError, analysis_record
    raw=gzip.decompress((FIXTURES/'nowscore-725219.html.gz').read_bytes())
    with pytest.raises(AnalysisFieldError) as caught:
        analysis_record(raw,source='nowscore',provider_id='725219')
    error=caught.value
    assert error.field=='schedules'
    assert isinstance(error,ValueError)
    assert error.partial_record['schedules'] is None
    assert error.partial_record['quarantined_fields']==['schedules']
    assert any('2015-07-11' in row for row in error.partial_record['schedule_source_rows'])
    assert error.partial_record['history']
    path=write_receipt(tmp_path/'schedule.json',raw,'https://live.nowscore.com/analysis/725219cn.html')
    report=issue_capture_report(roster,[path],issue='130511')
    row=next(r for r in report['observations'] if r['slot']==7 and r['source']=='nowscore')
    fields=next(r for r in report['page_fields'] if r['slot']==7 and r['source']=='nowscore')
    assert row['parse_state']=='PARTIAL_FIELD_FAILURE'
    assert row['home_id']=='4400'
    assert fields['normalized_fields'] is None
    assert fields['partial_fields']['schedules'] is None
    assert fields['partial_fields']['quarantined_fields']==['schedules']
    assert len(report['observations'])==166


def test_explicit_slot_gaps_are_preserved_without_renumbering(roster, tmp_path):
    from bs4 import BeautifulSoup
    raw = gzip.decompress((FIXTURES/'roster-130511-type8.html.gz').read_bytes())
    soup = BeautifulSoup(raw, 'html.parser')
    for row in soup.select('tr[id^="row_"]'):
        if row['matchid'] not in ('1', '3'):
            row.decompose()
    receipt = write_receipt(tmp_path / 'gap.json', str(soup).encode(),
        'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511')
    with pytest.raises(ValueError, match='slot set'):
        issue_capture_report(receipt, [], issue='130511', expected_fixture_count=2)
    result = issue_capture_report(receipt, [], issue='130511', expected_fixture_count=2, expected_slots=[3, 1])
    assert result['expected_slots'] == [1, 3] and result['slot_gaps'] == [2]
    assert [row['slot'] for row in result['observations']] == [1, 1, 3, 3]
    for bad in ([1, 1], [1, True], [1, 2], [1], '1,3'):
        with pytest.raises(ValueError, match='slot set'):
            issue_capture_report(receipt, [], issue='130511', expected_fixture_count=2, expected_slots=bad)


def test_auxiliary_receipt_binding_and_raw_arrays(tmp_path, monkeypatch):
    import src.fundamentals_issue_report as module
    identity = '2910880'
    page_url = f'https://live.nowscore.com/analysis/{identity}cn.html'
    raw = gzip.decompress((FIXTURES / f'nowscore-{identity}.gz').read_bytes())
    asset = gzip.decompress((FIXTURES / f'nowscore-js-{identity}.gz').read_bytes())
    roster_url = 'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    roster = write_receipt(tmp_path / 'roster.json', b'roster', roster_url)
    monkeypatch.setattr(module, 'issue_analysis_pages', lambda *a, **k: [dict(slot=1, provider_id=identity,
        nowscore_url=page_url, titan_candidate_url=f'https://zq.titan007.com/analysis/{identity}cn.htm')])
    page = write_receipt(tmp_path / 'page.json', raw, page_url)
    asset_url = f'https://live.nowscore.com/analysisJs/data{identity}.js'
    receipt = write_receipt(tmp_path / 'asset.json', asset, asset_url)
    args = dict(issue='130511', expected_fixture_count=1)
    missing = module.issue_capture_report(roster, [page], **args)
    assert 'required analysis JS' in missing['observations'][0]['error']
    result = module.issue_capture_report(roster, [page], auxiliary_response_paths={page_url: receipt}, **args)
    assert result['observations'][0]['parse_state'] == 'PARSED'
    assert receipt in result['input_file_hashes']
    assert result['page_fields'][0]['raw_fields']['home_history_raw']
    assert result['page_fields'][0]['raw_fields']['auxiliary_sha256'] == hashlib.sha256(asset).hexdigest()
    write_receipt(Path(receipt), asset, asset_url, status=403)
    with pytest.raises(ValueError, match='auxiliary response'):
        module.issue_capture_report(roster, [page], auxiliary_response_paths={page_url: receipt}, **args)
    with pytest.raises(ValueError, match='captured inventory'):
        module.issue_capture_report(roster, [page], auxiliary_response_paths={'unknown': receipt}, **args)


def test_auxiliary_cache_invalidation_and_reference_validation(tmp_path):
    from src.fundamentals_issue_report import parsed_page_observation
    identity = '2910880'
    raw = gzip.decompress((FIXTURES / f'nowscore-{identity}.gz').read_bytes())
    asset = gzip.decompress((FIXTURES / f'nowscore-js-{identity}.gz').read_bytes())
    args = dict(source='nowscore', provider_id=identity, url=f'https://live.nowscore.com/analysis/{identity}cn.html', cache_dir=str(tmp_path))
    first = parsed_page_observation(raw, auxiliary_raw=asset, **args)
    assert parsed_page_observation(raw, auxiliary_raw=asset, **args) == first
    assert len(list(tmp_path.glob('*.json'))) == 1
    changed = parsed_page_observation(raw, auxiliary_raw=asset + b'\n// new snapshot', **args)
    assert len(list(tmp_path.glob('*.json'))) == 2
    assert changed['fields']['raw_fields']['auxiliary_sha256'] != first['fields']['raw_fields']['auxiliary_sha256']
    with pytest.raises(ValueError, match='unreferenced'):
        parsed_page_observation(b'<html></html>', auxiliary_raw=asset, **args)
    with pytest.raises(ValueError, match='unreferenced'):
        parsed_page_observation(raw, auxiliary_raw=asset, **(args | {'source': 'titan'}))


def test_jina_html_is_parsed_with_bound_transport_provenance(roster, tmp_path):
    from src.fundamentals_census import decode_analysis_text
    original = gzip.decompress((FIXTURES/'titan-844632.html.gz').read_bytes())
    body = decode_analysis_text(original)[0].encode('utf-8')
    url = 'https://r.jina.ai/https://zq.titan007.com/analysis/844632cn.htm'
    path = write_receipt(tmp_path/'jina.json', body, url)
    report = issue_capture_report(roster, [path], issue='130511')
    row = next(r for r in report['observations'] if r['slot']==1 and r['source']=='titan')
    assert row['parse_state']=='PARSED'
    assert row['pairing_status']=='PENDING_IDENTITY_REVIEW'
    assert row['transport_url']==url
    assert row['raw_sha256']==row['transport_sha256']==hashlib.sha256(body).hexdigest()
    assert path in report['input_file_hashes']


def test_malformed_jina_utf8_is_a_page_failure(roster, tmp_path):
    url='https://r.jina.ai/https://zq.titan007.com/analysis/844632cn.htm'
    path=write_receipt(tmp_path/'bad-jina.json', b'\xff', url)
    report=issue_capture_report(roster,[path],issue='130511')
    assert len(report['observations'])==166
    row=next(r for r in report['observations'] if r['slot']==1 and r['source']=='titan')
    assert row['parse_state']=='PARSE_FAILURE'
    assert row['transport_url']==url
    assert row['raw_sha256']==hashlib.sha256(b'\xff').hexdigest()
