from pathlib import Path

import pandas as pd
import pytest

from src.fundamentals_signal_rate_cv import cross_validate_signal_rates
from src.temporal_learning import Cutoff


def test_second_stage_cv_and_post_cutoff_invariance():
    rows=[]
    for day in range(1,4):
        for slot in range(30):
            rows.append(dict(issue_code=f'10010{day}',slot=slot,provider_id=f'{day}-{slot}',
                issue_year=2010,data_available_ts=f'2010-01-0{day}T00:01:00Z',
                predictor_clock_ts=f'2010-01-0{day}T00:00:00Z',
                label_available_ts=f'2010-01-0{day}T12:00:00Z',handicap=-1,
                draw_signal='ABSTAIN',draw_target=slot%3==0,baseline_draw=.2))
    frame=pd.DataFrame(rows)
    cutoff=Cutoff.decision_epoch('100104','2010-01-04T00:00:00Z')
    kwargs=dict(issue_order=['100101','100102','100103'],initial_issues=1,
        validation_cutoffs={'100102':'2010-01-02T00:01:00Z','100103':'2010-01-03T00:01:00Z'},
        source_hashes={'fixture':'test'},repository_root=Path(__file__).resolve().parents[1],
        shrinkage_n=20,minimum_ess=10)
    result=cross_validate_signal_rates(frame,cutoff,**kwargs)
    assert len(result['oof'])==360
    assert all(m['n']==60 for m in result['metrics'])
    assert result['selected']==dict(blend_weight=1.,abstain_boost=0.)
    future=frame.iloc[:2].assign(issue_code='100104',draw_target=True,
        label_available_ts='2010-01-05T00:00:00Z')
    other=cross_validate_signal_rates(pd.concat([frame,future],ignore_index=True),cutoff,**kwargs)
    assert result['selected']==other['selected']
    assert result['oof']==other['oof']
    with pytest.raises(ValueError,match='scope'):
        cross_validate_signal_rates(frame,cutoff,**{**kwargs,'validation_cutoffs':{}})
