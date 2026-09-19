"""One-issue saved-response regression, source choice and field contracts."""
import copy
import gzip
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from src.fundamentals_census import analysis_record, read_response
from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import competition_context, weather_context, field_choice, history_observations, pilot_tables


@pytest.fixture
def sample(tmp_path):
    paths = {}
    for p in Path('tests/fixtures/fundamentals_pilot').glob('*.json.gz'):
        target = tmp_path / p.name.removesuffix('.gz')
        target.write_bytes(gzip.decompress(p.read_bytes())); paths[target.stem] = str(target)
    report = issue_capture_report(paths['roster'], [paths['nowscore-358101'], paths['titan-358101']], issue='100101', expected_fixture_count=78)
    cutoffs = {str(f['slot']): datetime.strptime(f['deadline_text'].split('：')[-1], '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Shanghai')).isoformat() for f in report['fixtures']}
    return report, cutoffs, paths


def test_archived_identity_clock_and_negative_proof(sample):
    report, _, paths = sample
    assert all(r['parse_state'] == 'PARSED' for r in report['observations'][:2])
    _, raw = read_response(Path(paths['titan-358101']))
    assert analysis_record(raw, source='titan', provider_id='358101')['kickoff_utc'] == '2010-01-01T05:00:00+00:00'
    with pytest.raises(ValueError, match='fixture ID'):
        analysis_record(raw, source='titan', provider_id='999')
    with pytest.raises(ValueError, match='fixture ID'):
        analysis_record(raw.replace(b'oddslist/358101.htm', b'oddslist/999.htm'), source='titan', provider_id='358101')
    with pytest.raises(ValueError, match='kickoff disagrees'):
        analysis_record(raw.replace(b'matchTime=2010-1-1 13:00:00', b'matchTime=2010-1-1 14:00:00'), source='titan', provider_id='358101')


def test_competition_context_has_no_global_navigation_guess():
    links = [dict(text='日皇杯 资料库', url='https://zq.titan007.com/cup_match/2009-2010/cupmatch_vs/cupmatch_162.htm'), dict(text='英超', url='https://x/League/36')]
    assert competition_context(links)['competition_category'] == 'CUP'
    assert competition_context(links)['season'] == '2009-2010'
    assert competition_context([dict(text='西甲资料', url='javascript:')])['competition_id'] is None
    assert competition_context([dict(text='西乙 资料', url='https://info.nowscore.com/cn/SubLeague.aspx?SclassID=33')])['competition_category'] == 'LEAGUE'
    assert competition_context(links + [dict(text='其他资料',url='https://x/cn/League.aspx?SclassID=99')])['competition_id'] is None


@pytest.mark.parametrize('text,description,lo,hi', [
    ('天气： 大雨 , -1~3℃ , 倒计时', '大雨', -1., 3.),
    ('天气： ℃ 距开赛时间', None, None, None),
    ('天气： , -3℃ , 倒计时', None, -3., -3.),
    ('天气：多雲 0 ℃ 距开赛时间', '多雲', 0., 0.),
    ('没有天气字段', None, None, None)])
def test_weather_blank_zero_and_ranges(text, description, lo, hi):
    row = weather_context(text)
    assert (row['weather_description'],row['temperature_min_c'],row['temperature_max_c']) == (description,lo,hi)
    assert row['weather_availability'] == 'UNKNOWN'
    if description == '多雲': assert row['weather_normalized'] == '多云'


def test_bad_temperature_and_source_choice():
    with pytest.raises(ValueError, match='Reversed'): weather_context('天气：晴 3~-1℃ 倒计时')
    assert field_choice(None,None)['status']=='MISSING'
    assert field_choice(None,0)==dict(value=0,source='nowscore',status='NOWSCORE_FILL')
    assert field_choice('a','a')['source']=='titan'
    assert field_choice('a',None)['status']=='TITAN_ONLY'
    assert field_choice('a','b')==dict(value='a',source='titan',status='TITAN_PRIMARY_CROSSCHECK_DIFFERENCE')
    value=[1]; picked=field_choice(value,None); picked['value'].append(2);assert value==[1]


def test_history_preserves_errors_dates_categories_and_half(sample):
    report, _, _ = sample
    raw=copy.deepcopy(report['page_fields'][1]['raw_fields'])
    row=raw['home_history_raw'][0]
    raw={ 'home_history_raw':[row,copy.deepcopy(row),[],copy.deepcopy(row)]}
    raw['home_history_raw'][1][0]='2010-01-01'
    raw['home_history_raw'][3][10]='9-9'
    args=dict(issue='100101',slot=1,source='titan',provider_id='358101',body_sha256='a'*64,
              cutoff=datetime(2010,1,1,tzinfo=ZoneInfo('Asia/Shanghai')),categories={('titan','162'):'CUP'})
    result=history_observations(raw,**args)
    assert result[0]['competition_category']=='CUP' and result[0]['chronology']=='BEFORE_DATE_PROXY'
    assert result[1]['chronology']=='SAME_DAY_UNKNOWN'
    assert not result[2]['valid']
    assert result[3]['valid'] and result[3]['halftime_home_goals'] is None
    assert result[3]['home_goals']==row[8]
    raw['home_history_raw'][0][0]='2030-01-01'
    assert history_observations(raw,**args)[0]['chronology']=='POST_CUTOFF'
    assert history_observations({'home_history_raw':42},**args)==[]


def test_pilot_full_denominator_identity_cutoff_and_no_mutation(sample):
    report,cutoffs,_=sample;original=copy.deepcopy(report)
    output=pilot_tables(report,cutoffs=cutoffs)
    assert report==original
    assert len(output['source_fixtures'])==156 and len(output['integrated_fixtures'])==78
    first=output['integrated_fixtures'][0]
    assert first['identity_source']=='titan' and first['competition_category']=='CUP'
    assert not first['historical_admission'] and first['temperature_min_c'] is None
    hist=output['integrated_history']
    assert hist and all(r['source']=='titan' for r in hist if 'titan' in r['observed_sources'])
    assert all(r['selection']=='NOWSCORE_FILL' for r in hist if r['source']=='nowscore')
    assert len({(r['slot'],r['history_id']) for r in hist})==len(hist)
    assert all(r['chronology']=='BEFORE_DATE_PROXY' and not r['historical_admission'] for r in hist)
    with pytest.raises(ValueError, match='every fixture'):pilot_tables(report,cutoffs={})
    bad=cutoffs|{'1':'2010-01-01T12:00:00'}
    with pytest.raises(ValueError,match='timezone'):pilot_tables(report,cutoffs=bad)
    with pytest.raises(ValueError,match='exceeds'):pilot_tables(report,cutoffs=cutoffs|{'1':'2030-01-01T00:00:00Z'})
    report['observations'][0]['home_id']='999'
    assert not pilot_tables(report,cutoffs=cutoffs)['source_fixtures'][0]['identity_valid']


def test_nowscore_difference_does_not_veto_valid_titan(sample):
    report,cutoffs,_=sample
    raw=report['page_fields'][0]['raw_fields']['home_history_raw'][0]
    history_id=str(raw[20]);raw[8]+=1
    output=pilot_tables(report,cutoffs=cutoffs)
    selected=next(r for r in output['integrated_history'] if r['history_id']==history_id)
    assert selected['source']=='titan' and selected['home_goals']==raw[8]-1
    assert any(r['history_id']==history_id and 'home_goals' in r['fields'] for r in output['crosscheck_differences'])
    assert not any(r.get('history_id')==history_id for r in output['exclusions'])


def test_titan_parser_failure_allows_flagged_nowscore_supplement(sample):
    report,cutoffs,_=sample
    report['observations'][1].update(parse_state='PARSE_FAILURE',home_id=None,away_id=None,kickoff_utc=None)
    output=pilot_tables(report,cutoffs=cutoffs)
    assert output['source_fixtures'][0]['identity_valid']
    assert output['integrated_fixtures'][0]['identity_source'] == 'nowscore'
    assert output['integrated_history']


def test_review_regressions_blank_weather_target_id_half_fill_and_receipt(sample):
    report,cutoffs,_=sample
    assert weather_context('天气：\xa0 ℃ 距开赛时间')['weather_normalized'] is None
    trow=report['page_fields'][1]['raw_fields']['home_history_raw'][0]
    history_id=str(trow[15]);trow[10]=''
    result=pilot_tables(report,cutoffs=cutoffs)
    selected=next(r for r in result['integrated_history'] if r['history_id']==history_id)
    assert selected['halftime_home_goals']==1 and selected['halftime_home_goals_source']=='nowscore'
    assert result['implementation_hashes']['fundamentals_pilot.py']
    assert datetime.fromisoformat(result['generated_at_utc']).utcoffset() is not None
    trow[15]=358101;trow[0]='2009-01-01'
    result=pilot_tables(report,cutoffs=cutoffs)
    assert not any(r['history_id']=='358101' for r in result['integrated_history'])


def test_nowscore_competition_difference_retains_titan_dependent_attributes(sample):
    report,cutoffs,_=sample
    for link in report['page_fields'][0]['raw_fields']['page_links']:
        if 'SclassID=162' in link['url'] and '资料' in link['text']:
            link['url']=link['url'].replace('SclassID=162','SclassID=999')
    result=pilot_tables(report,cutoffs=cutoffs)
    first=result['integrated_fixtures'][0]
    assert first['competition_id_status']=='TITAN_PRIMARY_CROSSCHECK_DIFFERENCE'
    assert first['competition_id']=='162' and first['competition_category']=='CUP'
    assert first['competition_name'] is not None and first['season']=='2009-2010'
    case=next(c for c in result['crosscheck_differences'] if c['history_id'] is None and c['fields']==['competition_id'])
    assert {o['value'] for o in case['observations']}=={'162','999'}
    assert all(o['url'] and o['raw_sha256'] for o in case['observations'])


def test_internal_titan_contradiction_is_quarantined_without_nowscore_override(sample):
    report,cutoffs,_=sample
    rows=report['page_fields'][1]['raw_fields']['home_history_raw']
    added=copy.deepcopy(rows[0]);added[8]+=1;rows.append(added)
    history_id=str(added[15]);out=pilot_tables(report,cutoffs=cutoffs)
    assert not any(h['history_id']==history_id for h in out['integrated_history'])
    assert any(e.get('history_id')==history_id and e['reason']=='TITAN_INTERNAL_HISTORY_CONFLICT' for e in out['exclusions'])


def test_halftime_titan_primary_and_no_fill_across_conflicting_identity(sample):
    report,cutoffs,_=sample
    t=report['page_fields'][1]['raw_fields']['home_history_raw'][0]
    n=report['page_fields'][0]['raw_fields']['home_history_raw'][0]
    history_id=str(t[15]);n[10]='0-0'
    out=pilot_tables(report,cutoffs=cutoffs)
    h=next(h for h in out['integrated_history'] if h['history_id']==history_id)
    assert h['halftime_home_goals']==1 and h['halftime_home_goals_source']=='titan'
    t[10]='';n[4]=999999
    out=pilot_tables(report,cutoffs=cutoffs)
    h=next(h for h in out['integrated_history'] if h['history_id']==history_id)
    assert h['halftime_home_goals'] is None


def test_internally_inconsistent_nowscore_cannot_fill_titan_halftime(sample):
    report,cutoffs,_=sample
    t=report['page_fields'][1]['raw_fields']['home_history_raw'][0];t[10]=''
    n=report['page_fields'][0]['raw_fields']['home_history_raw']
    bad=copy.deepcopy(n[0]);bad[8]+=1;bad[10]='0-0';n.append(bad)
    history_id=str(t[15]);result=pilot_tables(report,cutoffs=cutoffs)
    chosen=next(h for h in result['integrated_history'] if h['history_id']==history_id)
    assert chosen['source']=='titan' and chosen['home_goals']==t[8]
    assert chosen['halftime_home_goals'] is None and chosen['halftime_home_goals_source'] is None
    assert chosen['halftime_home_goals_status']=='NOWSCORE_FILL_INTERNAL_CONFLICT'
    assert any(e.get('history_id')==history_id and e['reason']=='NOWSCORE_INTERNAL_HISTORY_CONFLICT_HALFTIME_FILL' for e in result['exclusions'])


def test_bad_nowscore_weather_is_local_and_does_not_abort_titan(sample):
    report,cutoffs,_=sample
    baseline=pilot_tables(report,cutoffs=cutoffs)
    raw=report['page_fields'][0]['raw_fields']
    assert '天气：' in raw['page_text']
    raw['page_text']=raw['page_text'].replace('天气：','天气：3~-1℃',1)
    assert '3~-1℃' in raw['page_text']
    result=pilot_tables(report,cutoffs=cutoffs)
    assert result['integrated_fixtures']==baseline['integrated_fixtures']
    assert result['integrated_history']==baseline['integrated_history']
    n=result['source_fixtures'][0]
    assert n['weather_parse_error']=='Reversed source temperature range'
    assert '3~-1℃' in n['weather_raw'] and n['temperature_min_c'] is None
    assert any(e['reason']=='INVALID_SOURCE_WEATHER' and e['source']=='nowscore' for e in result['exclusions'])


def test_bad_nowscore_competition_url_does_not_abort_titan(sample):
    report,cutoffs,_=sample
    baseline=pilot_tables(report,cutoffs=cutoffs)
    report['page_fields'][0]['raw_fields']['page_links']=[dict(text='资料',url='http://[bad')]
    result=pilot_tables(report,cutoffs=cutoffs)
    assert result['integrated_fixtures'][0]['competition_id']=='162'
    assert result['integrated_fixtures'][0]['identity_source']=='titan'
    assert result['source_fixtures'][0]['competition_parse_error']
    assert any(e['reason']=='INVALID_SOURCE_COMPETITION' for e in result['exclusions'])


def test_ambiguous_nowscore_category_mapping_remains_source_local(sample):
    report,cutoffs,_=sample
    report['page_fields'][2]['raw_fields']={'page_links':[
        dict(text='赛事资料',url='https://info.nowscore.com/cn/League.aspx?SclassID=162')]}
    result=pilot_tables(report,cutoffs=cutoffs)
    assert result['integrated_fixtures'][0]['competition_category']=='CUP'
    assert any(e['reason']=='AMBIGUOUS_SOURCE_CATEGORY_MAPPING' and e['source']=='nowscore' for e in result['exclusions'])
    relevant=[h for h in result['source_history'] if h['source']=='nowscore' and h['competition_id']=='162']
    assert relevant and all(h['competition_category']=='UNKNOWN' for h in relevant)

@pytest.mark.parametrize("source", ["nowscore", "titan"])
@pytest.mark.parametrize("bad_kind", ["same_ids", "short_row", "half_above_full"])
def test_history_partial_preserves_identity_and_valid_rows(source, bad_kind):
    import hashlib
    from src.fundamentals_census import AnalysisFieldError, analysis_record, canonical
    from src.fundamentals_issue_report import parsed_page_observation
    index = 20 if source == "nowscore" else 15
    good = [""] * (index + 1)
    good[0:4] = ["26-08-01", 36, "联赛", "#000000"]
    good[4:11] = [1, "甲", 3, "丙", 2, 0, "1-0"]
    good[index] = 99
    bad = copy.deepcopy(good)
    bad[index] = 100
    if bad_kind == "same_ids":
        bad[6] = 1
    elif bad_kind == "short_row":
        bad = []
    else:
        bad[10] = "3-0"
    embedded = ('<input id="hide_scheduleId" value="123">' if source == "nowscore"
                else "<script>var scheduleID=123;</script>")
    raw = (f'<html><meta charset="utf-8"><title>分析</title>{embedded}'
        '<input id="hide_matchTime" value="2026-09-05 20:00">'
        '<script>var hometeam="甲";var guestteam="乙";var h2h_home=1;var h2h_away=2;'
        f'var h_data={canonical([good,bad])};var a_data=[];var v_data=[];</script></html>').encode()
    original = bytes(raw)
    with pytest.raises(AnalysisFieldError) as caught:
        analysis_record(raw, source=source, provider_id="123")
    assert caught.value.field == "history"
    assert caught.value.partial_record["home_id"] == "1"
    assert caught.value.partial_record["history"] is None
    assert caught.value.partial_record["blocks"]["h_data"] == [good,bad]
    fixture = dict(issue="260901", slot=1, provider_id="123", home_id="1", away_id="2",
        clock="20:00", deadline_text="截止时间：2026-09-05 19:30")
    observations=[]; fields=[]
    for selected in ("nowscore","titan"):
        url = (f"https://live.nowscore.com/analysis/123cn.html" if selected=="nowscore"
               else "https://zq.titan007.com/analysis/123cn.htm")
        obs = dict(issue="260901",slot=1,provider_id="123",source=selected,url=url,raw_sha256=None,
            parse_state="NOT_ATTEMPTED",home=None,away=None,home_id=None,away_id=None,kickoff_utc=None)
        field=dict(issue="260901",slot=1,source=selected,raw_fields=None)
        if selected == source:
            parsed=parsed_page_observation(raw,source=source,provider_id="123",url=url)
            obs.update(parsed["row"]);obs["raw_sha256"]=hashlib.sha256(raw).hexdigest()
            field.update(parsed["fields"])
            assert obs["parse_state"]=="PARTIAL_FIELD_FAILURE"
        observations.append(obs);fields.append(field)
    report=dict(issue="260901",fixtures=[fixture],observations=observations,page_fields=fields,
        input_file_hashes={},implementation_hashes={},runtime={})
    result=pilot_tables(report,cutoffs={"1":"2026-09-05T19:30:00+08:00"})
    assert next(r for r in result["source_fixtures"] if r["source"]==source)["identity_valid"]
    selected={r["history_id"]:r for r in result["integrated_history"]}
    assert selected["99"]["home_goals"]==2
    if bad_kind=="half_above_full":
        assert selected["100"]["home_goals"]==2
        assert selected["100"]["halftime_home_goals"] is None
    else:
        assert "100" not in selected
        assert any(not r["valid"] for r in result["source_history"])
    assert raw==original


def test_shared_roster_clock_allows_minutes_but_rejects_day_or_identity(sample):
    from datetime import timedelta
    report,cutoffs,_=sample
    original=copy.deepcopy(report)
    base=datetime.fromisoformat(report["observations"][0]["kickoff_utc"])
    for changes, expected in (
        ({"kickoff_utc":(base+timedelta(minutes=5)).isoformat()},True),
        ({"kickoff_utc":(base+timedelta(days=1)).isoformat()},False),
        ({"home_id":"999"},False),
        ({"provider_id":"999"},False),
    ):
        changed=copy.deepcopy(report)
        changed["observations"][0].update(changes)
        result=pilot_tables(changed,cutoffs=cutoffs)
        assert result["source_fixtures"][0]["identity_valid"] is expected
        assert result["source_fixtures"][0]["clock_alignment"]["cutoff_identity"]
    assert report==original


def test_unavailable_primary_fill_does_not_bypass_partial_or_identity_conflict(sample):
    report,cutoffs,_=sample
    titan=next(o for o in report["observations"] if o["source"]=="titan" and o["slot"]==1)
    original=copy.deepcopy(titan)
    for state in ("PARSE_FAILURE","HTTP_FAILURE","NOT_CAPTURED"):
        titan.update(parse_state=state,home_id=None,away_id=None,kickoff_utc=None)
        result=pilot_tables(report,cutoffs=cutoffs)
        assert result["integrated_fixtures"][0]["identity_source"]=="nowscore"
        assert any(r["reason"]=="UNAVAILABLE_PRIMARY_NOWSCORE_FILL_NOT_INDEPENDENTLY_VERIFIED" for r in result["exclusions"])
    titan["parse_state"]="PARTIAL_FIELD_FAILURE"
    assert pilot_tables(report,cutoffs=cutoffs)["integrated_fixtures"][0]["identity_source"] is None
    titan.update(original);titan["home_id"]="WRONG"
    assert pilot_tables(report,cutoffs=cutoffs)["integrated_fixtures"][0]["identity_source"] is None
    titan["parse_state"]="PARSE_FAILURE"
    assert pilot_tables(report,cutoffs=cutoffs)["integrated_fixtures"][0]["identity_source"] is None


def test_independent_date_substitution_exact_scope_and_source_contract(sample,tmp_path):
    import hashlib
    report,cutoffs,_=sample
    titan=next(o for o in report["observations"] if o["slot"]==1 and o["source"]=="titan")
    titan["kickoff_utc"]="2009-12-30T05:00:00+00:00"
    original=copy.deepcopy(report)
    f=report["fixtures"][0]
    evidence=tmp_path/"verified.json";evidence.write_text("independent exact date")
    d=dict(issue=f["issue"],slot=1,provider_id=f["provider_id"],roster_ids=[f["home_id"],f["away_id"]],cutoff_utc=cutoffs["1"],action="INDEPENDENTLY_VERIFIED_NOWSCORE_DATE_SUBSTITUTION",independent_evidence_path="verified.json",evidence_files={"verified.json":hashlib.sha256(evidence.read_bytes()).hexdigest()},analysis_sources={o["source"]:{k:o.get(k) for k in ("raw_sha256","home_id","away_id","kickoff_utc","provider_id")} for o in report["observations"] if o["slot"]==1})
    before=pilot_tables(report,cutoffs=cutoffs)
    after=pilot_tables(report,cutoffs=cutoffs,source_substitutions=[d],repository_root=tmp_path)
    assert before["integrated_fixtures"][0]["identity_source"] is None
    assert after["integrated_fixtures"][0]["identity_source"]=="nowscore"
    assert before["integrated_fixtures"][1:]==after["integrated_fixtures"][1:]
    assert report==original
    for key,value in (("slot",2),("cutoff_utc","2000-01-01T00:00:00+00:00"),("provider_id","wrong"),("action","WRONG"),("roster_ids",["x","y"]),("independent_evidence_path","missing")):
        bad=copy.deepcopy(d);bad[key]=value
        with pytest.raises(ValueError):pilot_tables(report,cutoffs=cutoffs,source_substitutions=[bad],repository_root=tmp_path)
    bad=copy.deepcopy(d);bad["analysis_sources"]["nowscore"]["raw_sha256"]="wrong"
    with pytest.raises(ValueError):pilot_tables(report,cutoffs=cutoffs,source_substitutions=[bad],repository_root=tmp_path)
    with pytest.raises(ValueError):pilot_tables(report,cutoffs=cutoffs,source_substitutions=[d,d],repository_root=tmp_path)
    with pytest.raises(ValueError):pilot_tables(report,cutoffs=cutoffs,source_substitutions=[d])
    evidence.write_text("changed")
    with pytest.raises(ValueError):pilot_tables(report,cutoffs=cutoffs,source_substitutions=[d],repository_root=tmp_path)
