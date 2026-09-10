"""Training replay warns automatically; frozen inputs and numerical rules stay intact."""
import warnings
import pandas as pd
import pytest
from tests.test_fundamentals_calibrated_draw import frozen
from tests.test_fundamentals_draw_versions import catalog
from src.fundamentals_calibrated_draw import load_calibrated_draw, predict_calibrated_draw
from src.fundamentals_draw_versions import predict_draw_version
from src.fundamentals_signal_rates import predict_signal_rates
from src.temporal_learning import Cutoff
from src.temporal_learning.replay import prediction_scope, HistoricalReplayWarning
import sys


@pytest.mark.parametrize('issue,time,scope',[
    ('100101','2010-01-02T00:00:00Z','IN_SAMPLE_REPLAY'),
    ('100101','2010-02-01T00:00:00Z','IN_SAMPLE_REPLAY'),
    ('100100','2010-01-02T00:00:00Z','RETROSPECTIVE_REPLAY'),
    ('100102','2010-01-03T00:00:00Z','OUT_OF_SAMPLE'),
])
def test_shared_scope(issue,time,scope):
    cutoff=Cutoff.decision_epoch(issue,time)
    model=Cutoff.decision_epoch('100102','2010-01-03T00:00:00Z')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        assert prediction_scope(cutoff,['100101'],model)==scope
    assert len(caught)==int(scope!='OUT_OF_SAMPLE')
    with pytest.raises(ValueError,match='cutoffs'):
        prediction_scope(None,['100101'],model)


def test_training_and_earlier_replay_without_switch(frozen):
    path,root,frame,cutoff=frozen
    artifact=load_calibrated_draw(path,expected_version='1.1.0',repository_root=root)
    baseline=predict_calibrated_draw(artifact,frame,cutoff)
    for issue,scope in [('100101','IN_SAMPLE_REPLAY'),('100100','RETROSPECTIVE_REPLAY')]:
        target=frame.assign(issue_code=issue,predictor_clock_ts='2010-01-01T23:00:00Z')
        epoch=Cutoff.decision_epoch(issue,'2010-01-02T00:00:00Z')
        with pytest.warns(HistoricalReplayWarning) as caught:
            output=predict_calibrated_draw(artifact,target,epoch)
        assert len(caught)==1
        assert output.evaluation_scope.eq(scope).all()
        assert output.draw_target_probability.equals(baseline.draw_target_probability)
        receipt=output.attrs['prediction_receipt']
        assert receipt['evaluation_scope']==scope and receipt['deployable'] is False
        assert receipt['cutoff_ts']==epoch.cutoff_ts.isoformat()
        assert receipt['model_cutoff_ts']==artifact['expert']['cutoff'].cutoff_ts.isoformat()
        with pytest.warns(HistoricalReplayWarning):
            changed=predict_calibrated_draw(artifact,target.assign(draw_target=999,actual_home=99),epoch)
        pd.testing.assert_frame_equal(changed,output)
        assert changed.attrs==output.attrs
        with pytest.warns(HistoricalReplayWarning):
            rates=predict_signal_rates(artifact['rates'],target.assign(draw_signal=output.draw_signal),epoch,
                                       **artifact['receipt']['policy'])
        assert rates.draw_probability.equals(output.draw_target_probability)
        with pytest.raises(ValueError), pytest.warns(HistoricalReplayWarning):
            predict_calibrated_draw(artifact,target.assign(predictor_clock_ts=epoch.cutoff_ts),epoch)
        with pytest.raises(ValueError), pytest.warns(HistoricalReplayWarning):
            predict_calibrated_draw(artifact,pd.concat([target,target]),epoch)


def test_router_propagates_training_warning(catalog):
    path,root,frame,_=catalog
    target=frame.assign(issue_code='100101',predictor_clock_ts='2010-01-01T23:00:00Z')
    cutoff=Cutoff.decision_epoch('100101','2010-01-02T00:00:00Z')
    with pytest.warns(HistoricalReplayWarning):
        result=predict_draw_version('1.1.0',target,cutoffs=[cutoff]*len(target),
            catalog_path=path,repository_root=root,python=sys.executable)
    assert result.evaluation_scope.eq('IN_SAMPLE_REPLAY').all()
    assert result.expert_version.eq('1.1.0').all()
