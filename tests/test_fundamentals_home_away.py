import copy
import gzip
from pathlib import Path
import pytest
from src.temporal_learning import Cutoff, TemporalContractError
from src.temporal_learning.diagnostic_window import diagnostic_date_window
from src.fundamentals_home_away import home_away_windows, roster_observed_results
from src import fundamentals_home_away as module


def test_window_cutoff_target_and_mutation_invariance():
    rows = [dict(history_id=str(i), event_date=f'2009-12-{i:02d}') for i in range(1,21)]
    args = dict(cutoff=Cutoff.decision_epoch('100101','2010-01-01T12:00:00+08:00'),
        window=10,minimum=10,timezone='Asia/Shanghai',excluded_ids={'20'},source_hashes={'raw':'abc'},implementation_hashes={'code':'def'})
    original = copy.deepcopy(rows)
    result = diagnostic_date_window(rows,**args)
    assert result['receipt']['selected_ids'] == [str(i) for i in range(19,9,-1)]
    assert result['receipt']['ess'] == 10
    assert not result['receipt']['historical_admission']
    assert rows == original
    mutated = rows + [dict(history_id='future',event_date='2010-01-02'),dict(history_id='same',event_date='2010-01-01')]
    assert diagnostic_date_window(mutated,**args)['rows'] == result['rows']
    changed = {**args,'cutoff':Cutoff.decision_epoch('100101','2009-12-15T12:00:00+08:00')}
    assert diagnostic_date_window(rows,**changed)['receipt']['identity'] != result['receipt']['identity']
    assert diagnostic_date_window(rows[:3],**args)['receipt']['status'] == 'INSUFFICIENT_HISTORY'
    assert diagnostic_date_window([],**args)['rows'] == []
    with pytest.raises(TemporalContractError): diagnostic_date_window(rows,**{**args,'minimum':0})
    with pytest.raises(TemporalContractError): diagnostic_date_window(rows+rows,**args)
    with pytest.raises(ValueError): diagnostic_date_window([dict(history_id='bad',event_date='no date')],**args)
    with pytest.raises(TemporalContractError): diagnostic_date_window(rows,**{**args,'cutoff':None})


def test_domain_windows_preserve_unavailable_and_exclude_neutral():
    root = Path(__file__).resolve().parents[1]
    fixture = dict(issue='100101',slot=11,provider_id='target',home='H',away='A',competition='cup',home_id='H',away_id='A')
    history = [dict(slot=11,history_id=str(i),event_date=f'2009-12-{i:02d}',home_id='H',away_id='A',
                    home='H',away='A',home_goals=2,away_goals=1) for i in range(1,12)]
    history[-1]['home'] = 'H(中)'
    pilot = dict(integrated_fixtures=[dict(slot=11,neutral_venue=None,identity_source='titan')],
                 integrated_history=history,input_file_hashes={'raw':'abc'},implementation_hashes={'parser':'def'})
    args = dict(cutoffs={'11':'2010-01-01T12:00:00+08:00'},window=10,minimum=10,repository_root=root)
    result = home_away_windows(pilot,[fixture],**args)[0]
    assert result['status'] == 'OK_DIAGNOSTIC'
    assert len(result['home_window']) == len(result['away_window']) == 10
    assert result['home_neutral_excluded'] == 1
    pilot['integrated_fixtures'][0]['neutral_venue'] = True
    assert home_away_windows(pilot,[fixture],**args)[0]['status'] == 'NEUTRAL_TARGET'
    pilot['integrated_fixtures'][0]['identity_source'] = None
    assert home_away_windows(pilot,[fixture],**args)[0]['status'] == 'IDENTITY_UNAVAILABLE'
    with pytest.raises(ValueError): home_away_windows(pilot,[fixture],**{**args,'cutoffs':{}})


def test_saved_roster_labels_postponement_identity_and_bad_score(tmp_path,monkeypatch):
    path = tmp_path/'roster.json'
    path.write_bytes(gzip.decompress(Path('tests/fixtures/fundamentals_pilot/roster.json.gz').read_bytes()))
    result = roster_observed_results(path,issue='100101',slots=[1,2,3,11])
    assert [(r['actual_home'],r['actual_away']) for r in result] == [(4,1),(None,None),(4,0),(3,1)]
    assert result[1]['result_state'] == '推迟'
    with pytest.raises(ValueError): roster_observed_results(path,issue='100102',slots=[1])
    meta,raw = module.read_response(path)
    monkeypatch.setattr(module,'read_response',lambda _: (meta,raw.replace(b'4-1',b'x-x',1)))
    with pytest.raises(ValueError,match='Malformed'): roster_observed_results(path,issue='100101',slots=[1])
