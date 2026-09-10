import copy
import pytest
from src.fundamentals_score_review import score_review_context


def test_review_uses_selected_history_and_keeps_unknown_participation(monkeypatch):
    fixture=dict(issue='x',slot=1,provider_id='001')
    report=dict(issue='x',fixtures=[fixture],observations=[])
    pilot=dict(integrated_fixtures=[dict(slot=1,competition_category='CUP')],
        integrated_history=[dict(history_id='future',slot=1)],crosscheck_differences=[
            dict(slot=1,history_id='used',fields=['home_goals']),
            dict(slot=1,history_id='future',fields=['home_goals'])])
    h=dict(slot=1,history_id='used',source='nowscore')
    window=dict(fixture,home_window=[h],away_window=[h],cutoff_utc='2009-01-01T04:00:00+00:00',
        history_mode='SAME_ROLE',identity_source='titan',adjudication={})
    args=dict(cutoffs={'1':'2009-01-01T12:00:00+08:00'})
    observed=[]
    evidence=[dict(slot=1,role='home',competition_categories=['LEAGUE'],competition_id='A',competition_names=['League A']),
        dict(slot=1,role='away',competition_categories=['LEAGUE'],competition_id='B',competition_names=['League B'])]
    def context(r,p,**kwargs):
        observed.append(p['integrated_history']);return dict(participation=evidence)
    monkeypatch.setattr('src.fundamentals_score_review.league_context_tables',context)
    original=copy.deepcopy((report,pilot,window))
    result=score_review_context(report,pilot,[window],**args)
    row=result['fixtures'][0]
    assert observed==[[h]]
    assert row['selected_nowscore_histories']==row['selected_history_crosschecks']==1
    assert row['league_relation']=='DIFFERENT_OBSERVED_LEAGUES'
    assert len(result['pending_queue'])==1
    assert (report,pilot,window)==original
    evidence[1]['competition_id']='A'
    assert score_review_context(report,pilot,[window],**args)['fixtures'][0]['league_relation']=='SAME_OBSERVED_LEAGUE'
    evidence.append(dict(evidence[0],competition_id='C'))
    assert score_review_context(report,pilot,[window],**args)['fixtures'][0]['league_relation']=='UNKNOWN'
    evidence.clear()
    empty=score_review_context(report,pilot,[dict(window,home_window=[],away_window=[])],**args)
    assert empty['fixtures'][0]['league_relation']=='UNKNOWN'
    assert empty['fixtures'][0]['home_league_evidence'] is None
    assert empty['pending_queue']==[]
    report['observations']=[dict(slot=1,source='nowscore',error='schedules parse failure')]
    result=score_review_context(report,pilot,[window],**args)
    assert len(result['pending_queue'])==2 and result['pending_queue'][-1]['kind']=='SOURCE_PARSER_ERROR'
    assert 'source_errors' not in result['fixtures'][0]
    assert 'schedules parse failure' not in str(result['fixtures'])
    with pytest.raises(ValueError,match='identity'):score_review_context(report,pilot,[dict(window,provider_id='wrong')],**args)
    with pytest.raises(ValueError,match='identity'):score_review_context(report,pilot,[window,window],**args)
    with pytest.raises(ValueError,match='cutoff'):score_review_context(report,pilot,[dict(window,cutoff_utc='2010-01-01T00:00:00+00:00')],**args)
