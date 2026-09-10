import copy
from pathlib import Path
import pytest
from src.fundamentals_draw_context import draw_form_summary, draw_context_inputs
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_window import diagnostic_date_window


def test_summary_orientation_cutoff_empty_and_tamper():
    cutoff = Cutoff.decision_epoch('100101', '2010-01-01T12:00:00+08:00')
    rows = [dict(history_id='1',event_date='2009-12-01',home_id='H',away_id='A',home_goals=2,away_goals=0),
            dict(history_id='2',event_date='2009-12-02',home_id='A',away_id='H',home_goals=1,away_goals=1)]
    args = dict(cutoff=cutoff, window=10, minimum=1, timezone='Asia/Shanghai',excluded_ids={'target'},source_hashes={'raw':'a'},implementation_hashes={'code':'b'})
    selected = diagnostic_date_window(rows, **args)
    result = draw_form_summary(selected, team_id='H', target_net=2, cutoff=cutoff)
    assert result == dict(n=2,wins=1,draws=1,losses=0,goals_for_pg=1.5,goals_against_pg=.5,net_pg=1.,points_pg=2.,exact_margin_rate=.5,total_pg=2.)
    assert draw_form_summary(selected,team_id='A',target_net=-2,cutoff=cutoff)['exact_margin_rate'] == .5
    assert draw_form_summary(diagnostic_date_window([],**args),team_id='H',target_net=0,cutoff=cutoff)['n'] == 0
    other = Cutoff.decision_epoch('100102','2010-01-02T00:00:00Z')
    forged = copy.deepcopy(selected);forged['receipt']['cutoff_identity']=other.identity
    with pytest.raises(ValueError,match='integrity'): draw_form_summary(forged,team_id='H',target_net=0,cutoff=other)
    changed = copy.deepcopy(selected); changed['rows'][0]['home_goals']=9
    with pytest.raises(ValueError,match='changed'): draw_form_summary(changed,team_id='H',target_net=0,cutoff=cutoff)
    with pytest.raises(ValueError,match='cutoff'): draw_form_summary(selected,team_id='H',target_net=0,cutoff=Cutoff.decision_epoch('100102','2010-01-02T00:00:00Z'))
    with pytest.raises(ValueError,match='orientation'): draw_form_summary(selected,team_id='missing',target_net=0,cutoff=cutoff)
    bad=copy.deepcopy(rows);bad[0]['home_goals']=-1
    with pytest.raises(ValueError,match='Integer'): draw_form_summary(diagnostic_date_window(bad,**args),team_id='H',target_net=0,cutoff=cutoff)


def test_context_targets_fail_explicitly(tmp_path):
    args=dict(repository_root=Path(__file__).resolve().parents[1],cache_dir=str(tmp_path),window=10,minimum=10)
    with pytest.raises(ValueError,match='Unique'): draw_context_inputs([],[],**args)
    with pytest.raises(ValueError,match='Unmatched'): draw_context_inputs([],[dict(issue='100101',slot=1,provider_id='x',handicap=0)],**args)


def test_context_weather_assumption_and_four_windows(monkeypatch,tmp_path):
    from src import fundamentals_draw_context as module
    cutoff='2010-01-01T12:00:00+08:00'
    fixture=dict(issue='100101',slot=1,provider_id='target',home_id='H',away_id='A',home='H',away='A',competition='cup')
    rows=[dict(slot=1,history_id=str(i),event_date=f'2009-12-{i:02d}',home_id='H',away_id='A',home='H',away='A',home_goals=2,away_goals=1) for i in range(1,11)]
    base=dict(slot=1,neutral_venue=False,identity_source='titan',competition_name='杯赛',competition_category='cup',weather_normalized='雨',weather_normalized_source='titan',temperature_min_c=0,temperature_max_c=2)
    pilot=dict(integrated_fixtures=[base],integrated_history=rows,input_file_hashes={'raw':'a'},implementation_hashes={'code':'b'})
    monkeypatch.setattr(module,'issue_capture_report',lambda *a,**k: dict(fixtures=[fixture]))
    monkeypatch.setattr(module,'pilot_tables',lambda *a,**k: pilot)
    inv=[dict(issue='100101',roster_path='raw',response_paths=[],fixture_count=1,cutoffs={'1':cutoff})]
    targets=[dict(issue='100101',slot=1,provider_id='target',handicap=-1)]
    args=dict(repository_root=Path(__file__).resolve().parents[1],cache_dir=str(tmp_path),window=10,minimum=10)
    x=draw_context_inputs(inv,targets,**args)
    r=x['rows'][0]
    assert r['home_team_id']=='H' and r['away_team_id']=='A'
    assert r['weather_used'] and r['weather_availability']=='UNKNOWN'
    assert r['weather_assumption']=='ASSUMED_PREMATCH_BY_OWNER'
    assert r['home_overall_goals_for_pg']==2 and r['away_venue_goals_for_pg']==1
    assert len(x['receipts'][0]['views'])==4
    assert r['home_overall_exact_margin_rate']==r['away_overall_exact_margin_rate']==1
    rows.append(dict(slot=1,history_id='future',event_date='2010-01-02',home_id='H',away_id='A',home='H',away='A',home_goals=9,away_goals=0))
    assert draw_context_inputs(inv,targets,**args)['rows']==x['rows']
    base.update(weather_normalized=None,temperature_min_c=None,temperature_max_c=None)
    assert not draw_context_inputs(inv,targets,**args)['rows'][0]['weather_used']
    with pytest.raises(ValueError,match='identity'): draw_context_inputs(inv,[dict(targets[0],provider_id='wrong')],**args)


def test_context_cli_starts_without_pythonpath(tmp_path):
    import os
    import subprocess
    import sys
    environment=dict(os.environ)
    environment.pop('PYTHONPATH',None)
    script=Path(__file__).resolve().parents[1]/'scripts/build_expert_context.py'
    result=subprocess.run([sys.executable,str(script),'--help'],cwd=tmp_path,
        env=environment,capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stderr
    assert '--inventories' in result.stdout and '--output' in result.stdout
