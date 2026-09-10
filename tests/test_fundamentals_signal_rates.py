from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.fundamentals_signal_rates import fit_signal_rates, predict_signal_rates
from src.temporal_learning import Cutoff


def test_conditional_rates_shrinkage_boost_and_missing_support():
    history = pd.DataFrame(dict(issue_code=['100101']*30,slot=range(30),
        provider_id=[str(i) for i in range(30)],issue_year=2010,
        data_available_ts='2010-01-01T00:00:00Z',label_available_ts='2010-01-02T00:00:00Z',
        handicap=-1,draw_signal=['POSITIVE']*10+['NEGATIVE']*10+['ABSTAIN']*10,
        draw_target=[1]*7+[0]*3+[1]*2+[0]*8+[1]*3+[0]*7))
    cutoff = Cutoff.decision_epoch('100102','2010-01-03T00:00:00Z')
    kwargs = dict(shrinkage_n=10,minimum_ess=10,source_hashes={'fixture':'test'},
                  repository_root=Path(__file__).resolve().parents[1])
    artifact = fit_signal_rates(history,cutoff,**kwargs)
    target = pd.DataFrame(dict(issue_code='100102',slot=range(5),provider_id=list('abcde'),
        handicap=[-1,-1,1,2,-1],draw_signal=['POSITIVE','NEGATIVE','ABSTAIN','ABSTAIN','INSUFFICIENT_FEATURES'],
        baseline_draw=.2,predictor_clock_ts='2010-01-02T23:00:00Z'))
    for weight in [.5,1.]:
        for boost in [0.,.02,.05]:
            result = predict_signal_rates(artifact,target,cutoff,blend_weight=weight,abstain_boost=boost)
            expected = np.array([(7+10*12.5/31)/20,(2+10*12.5/31)/20,(3+10*12.5/31)/20])
            np.testing.assert_allclose(result.reference_probability.iloc[:3],expected)
            expected[2] += boost
            np.testing.assert_allclose(result.draw_probability.iloc[:3],(1-weight)*.2+weight*expected)
            assert result.draw_probability.iloc[3:].tolist() == [.2,.2]
            assert result.calibration_status.iloc[3:].tolist()==['NO_PRIOR_HANDICAP_BAND','INSUFFICIENT_FEATURES']
    future = history.iloc[:2].assign(issue_code='100102',draw_target=1,label_available_ts='2010-01-04T00:00:00Z')
    replay = fit_signal_rates(pd.concat([history,future],ignore_index=True),cutoff,**kwargs)
    assert replay['receipt']['estimates']==artifact['receipt']['estimates']
    assert artifact['receipt']['weight_receipt']['effective_sample_size']==pytest.approx(30)
    bad=deepcopy(artifact);bad['receipt']['estimates'][0]['probability']=.9
    with pytest.raises(ValueError,match='changed'):
        predict_signal_rates(bad,target,cutoff,blend_weight=1.,abstain_boost=0.)
    with pytest.raises(ValueError,match='identities'):
        fit_signal_rates(pd.concat([history,history]),cutoff,**kwargs)
    with pytest.raises(ValueError,match='Valid OOF'):
        fit_signal_rates(history.assign(draw_signal='INVALID'),cutoff,**kwargs)
    with pytest.raises(ValueError):
        predict_signal_rates(artifact,target.assign(predictor_clock_ts=cutoff.cutoff_ts),cutoff,blend_weight=1.,abstain_boost=0.)
    with pytest.raises(ValueError,match='draw_weight'):
        predict_signal_rates(artifact,target,cutoff,blend_weight=1.3,abstain_boost=0.)
