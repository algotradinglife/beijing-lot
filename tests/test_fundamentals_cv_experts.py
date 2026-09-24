import copy
from pathlib import Path
import pandas as pd
import pytest
from src.fundamentals_cv_experts import cross_validate_experts
from beidan_backend.temporal_learning import Cutoff


@pytest.mark.parametrize("expert_names", [("draw", "high"), ("draw",), ("high",)])
def test_cv_prior_windows_identity_purge_and_future_mutation(expert_names):
    issues = ['090101', '090102', '090103', '090104']
    rows = []
    for day, issue in enumerate(issues, 1):
        for slot in range(24):
            rows.append(dict(issue_code=issue, issue_year=2009, slot=slot,
                provider_id='repeat' if slot == 0 else f'{issue}{slot}', handicap=-2,
                data_available_ts=f'2009-01-{day:02d}T00:00:00Z',
                predictor_clock_ts='2008-12-31T00:00:00Z',
                label_available_ts=f'2009-01-{day:02d}T06:00:00Z',
                x=slot % 3, draw_target=slot % 3 == 1, cover_target=slot % 3 == 2))
    frame = pd.DataFrame(rows)
    if len(expert_names) == 1:
        frame = frame.drop(columns='cover_target' if expert_names[0] == 'draw' else 'draw_target')
    candidates = [dict(depths={e:d for e in expert_names}, minimum_leaf=3, bounds=[.2,.6]) for d in [1,2]]
    kwargs = dict(features={e:['x'] for e in expert_names}, issue_order=issues,
        initial_issues=2, candidates=candidates, source_hashes={'synthetic':'v1'},
        repository_root=Path(__file__).resolve().parents[1], minimum_ess=6, seed=417,
        validation_cutoffs={'090103':'2009-01-03T00:00:00Z','090104':'2009-01-04T00:00:00Z'})
    cutoff = Cutoff.decision_epoch('090105', '2009-01-05T00:00:00Z')
    result = cross_validate_experts(frame, cutoff, **kwargs)
    from src.fundamentals_retrained_experts import fit_experts
    fit_kwargs = dict(features=kwargs['features'], training_issues=issues,
        source_hashes=kwargs['source_hashes'], repository_root=kwargs['repository_root'],
        minimum_ess=6, seed=417, **result['selected'])
    fitted = fit_experts(frame, cutoff, selection=result, **fit_kwargs)
    for receipt in fitted['receipt'].values():
        assert receipt['tuning'] == 'CUTOFF_BOUND_CV'
        assert receipt['selection']['seal'] == result['seal']
    bad = copy.deepcopy(result); bad['oof'][0]['candidate'] = 999
    with pytest.raises(ValueError, match='CV selection binding'):
        fit_experts(frame, cutoff, selection=bad, **fit_kwargs)
    assert len(result['oof']) == 96
    assert len(result['receipt']['fold_receipts']) == 4
    for fold in result['receipt']['fold_receipts']:
        assert fold['repeated_identity_purged'] >= 2
        for receipt in fold['receipt'].values():
            assert receipt['maximum_training_label_timestamp'] < receipt['cutoff_ts']
            assert fold['issue'] not in receipt['training_issues']
    future = dict(rows[-1], issue_code='090105', provider_id='target', x=999,
                  data_available_ts='2008-01-01T00:00:00Z', label_available_ts='2008-01-01T00:00:00Z')
    mutated = cross_validate_experts(pd.concat([frame, pd.DataFrame([future])], ignore_index=True), cutoff, **kwargs)
    assert mutated['selected'] == result['selected']
    assert mutated['oof'] == result['oof']
    assert cross_validate_experts(frame, cutoff, **kwargs)['seal'] == result['seal']
    with pytest.raises(ValueError):
        cross_validate_experts(frame, cutoff, **{**kwargs, 'initial_issues':4})
    with pytest.raises(ValueError):
        cross_validate_experts(frame, cutoff, **{**kwargs, 'issue_order':issues+['090105']})
    late = frame.copy()
    late.loc[late.issue_code.eq('090103'), 'predictor_clock_ts'] = '2009-01-04T00:00:00Z'
    with pytest.raises(ValueError, match='Predictor clock'):
        cross_validate_experts(late, cutoff, **kwargs)


def test_diagnostic_predictor_clocks_are_strict_and_not_availability():
    from beidan_backend.temporal_learning.predictor_clock import diagnostic_predictor_clock, require_prior_predictor_clock
    cutoff = Cutoff.decision_epoch('100101','2010-01-02T12:00:00Z')
    x = diagnostic_predictor_clock(['2010-01-01'], ['2010-01-02T11:00:00Z'],
        cutoff=cutoff, timezone='Asia/Shanghai', source_hashes={'saved':'sha'})
    assert x['receipt']['maximum_predictor_clock'] == '2010-01-02T11:00:00+00:00'
    assert not x['receipt']['historical_admission']
    require_prior_predictor_clock(x['receipt']['maximum_predictor_clock'], cutoff)
    with pytest.raises(ValueError):
        require_prior_predictor_clock(cutoff.cutoff_ts, cutoff)
    with pytest.raises(ValueError):
        diagnostic_predictor_clock(['2010-01-02'], [], cutoff=cutoff,
            timezone='Asia/Shanghai', source_hashes={'saved':'sha'})
    for missing in [None, '', 'NaT']:
        with pytest.raises(ValueError):
            require_prior_predictor_clock(missing, cutoff)
        with pytest.raises(ValueError):
            diagnostic_predictor_clock(['2010-01-01'], [missing], cutoff=cutoff,
                timezone='Asia/Shanghai', source_hashes={'saved':'sha'})
