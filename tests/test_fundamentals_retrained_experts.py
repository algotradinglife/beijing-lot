from copy import deepcopy
from pathlib import Path
import json
import hashlib
import pickle

import numpy as np
import pandas as pd
import pytest

from src.fundamentals_retrained_experts import fit_experts, predict_experts, predict_frozen_file
from src.temporal_learning import Cutoff


@pytest.fixture
def experiment():
    n = 40
    history = pd.DataFrame({"issue_code": ["100101"] * n, "slot": range(1, n + 1),
        "provider_id": [str(i) for i in range(n)], "issue_year": [2010] * n,
        "label_available_ts": ["2010-01-02T12:00:00Z"] * n,
        "data_available_ts": ["2010-01-02T00:00:00Z"] * n,
        "predictor_clock_ts": ["2010-01-01T00:00:00Z"] * n,
        "handicap": [-2] * n, "x": list(range(n)),
        "draw_target": [i < 10 for i in range(n)], "cover_target": [i >= 20 for i in range(n)]})
    kwargs = dict(cutoff=Cutoff.decision_epoch("100105", "2010-01-12T00:00:00Z"),
        features={"draw": ["x"], "high": ["x"]}, training_issues=["100101"],
        source_hashes={"fixture": "test"}, repository_root=Path(__file__).resolve().parents[1],
        depths={"draw": 1, "high": 2}, minimum_leaf=5, minimum_ess=10, bounds=[.2, .6], seed=17)
    return history, kwargs


def test_train_predict_missing_scope_mutation_and_replay(experiment):
    history, kwargs = experiment
    artifact = fit_experts(history, **kwargs)
    assert artifact["receipt"]["draw"]["partition"]["tune_rows"] == 0
    target = history.drop(columns=["draw_target", "cover_target"]).copy()
    target["issue_code"] = "100105"
    p = predict_experts(artifact, target, kwargs["cutoff"])
    assert p.draw_signal.iloc[0] == "POSITIVE"
    assert p.high_signal.iloc[-1] == "POSITIVE"
    target.loc[0, "x"] = np.nan
    target.loc[1, "handicap"] = 0
    q = predict_experts(artifact, target, kwargs["cutoff"])
    assert q.draw_signal.iloc[0] == "INSUFFICIENT_FEATURES"
    assert q.high_signal.iloc[1] == "NOT_APPLICABLE"
    future = history.iloc[:2].copy()
    future["issue_code"] = "100105"
    future["x"] = 99999
    replay = fit_experts(pd.concat([history, future], ignore_index=True), **kwargs)
    assert artifact["seal"] == replay["seal"]
    pd.testing.assert_frame_equal(q, predict_experts(replay, target, kwargs["cutoff"]))
    with pytest.warns(UserWarning, match="训练内回放"):
        predict_experts(artifact, history, Cutoff.decision_epoch("100101", "2010-01-01T00:00:00Z"))
    assert len(predict_experts(artifact, history, Cutoff.decision_epoch("100101", "2010-01-01T00:00:00Z"))) == 40
    broken = deepcopy(artifact)
    broken["models"]["draw"].tree_.threshold[0] = -100
    with pytest.raises(ValueError, match="Frozen model changed"):
        predict_experts(broken, target, kwargs["cutoff"])


def test_invalid_inputs_fail(experiment):
    history, kwargs = experiment
    with pytest.raises(ValueError, match="Unique complete"):
        fit_experts(pd.concat([history, history]), **kwargs)
    with pytest.raises(ValueError, match="label-free"):
        fit_experts(history, **{**kwargs, "features": {"draw": ["draw_target"], "high": ["x"]}})
    with pytest.raises(ValueError, match="effective sample size"):
        fit_experts(history.iloc[:6], **kwargs)
    with pytest.raises(ValueError, match="prior training"):
        fit_experts(history, **{**kwargs, "training_issues": ["100105"]})


def test_frozen_file_checks_and_independent_reload(experiment, tmp_path):
    history, kwargs = experiment
    source = tmp_path / 'source.json'
    source.write_text('[]')
    kwargs['source_hashes'] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    artifact = fit_experts(history, **kwargs)
    model = tmp_path / 'frozen.pkl'
    raw = pickle.dumps(artifact, protocol=5)
    model.write_bytes(raw)
    model.with_suffix('.json').write_text(json.dumps({'receipt': artifact['receipt'],
        'seal': artifact['seal'], 'model_sha256': hashlib.sha256(raw).hexdigest()}))
    target = history.copy();target['issue_code'] = '100105'
    expected = predict_experts(artifact, target, kwargs['cutoff'])
    actual = predict_frozen_file(model, target, kwargs['cutoff'], repository_root=kwargs['repository_root'])
    pd.testing.assert_frame_equal(expected, actual)
    source.write_text('[1]')
    with pytest.raises(ValueError, match='training source changed'):
        predict_frozen_file(model, target, kwargs['cutoff'], repository_root=kwargs['repository_root'])
    model.write_bytes(b'bad')
    with pytest.raises(ValueError, match='Frozen file changed'):
        predict_frozen_file(model, target, kwargs['cutoff'], repository_root=kwargs['repository_root'])


def test_independent_experts_save_reload_combine_and_isolation(experiment, tmp_path):
    from src.fundamentals_retrained_experts import save_frozen_experts, combine_expert_predictions
    history, kwargs = experiment
    source = tmp_path / 'input.json'; source.write_text('fixture')
    kwargs['source_hashes'] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    target = history.copy(); target['issue_code'] = '100105'
    outputs = {}
    for name, other in [('draw','cover_target'), ('high','draw_target')]:
        options = {**kwargs, 'features':{name:['x']}, 'depths':{name:1}}
        single = fit_experts(history.drop(columns=other), **options)
        assert set(single['models']) == {name}
        path = save_frozen_experts(single, tmp_path/name)
        outputs[name] = predict_frozen_file(path, target, kwargs['cutoff'], repository_root=kwargs['repository_root'])
        with pytest.raises(FileExistsError):
            save_frozen_experts(single, tmp_path/name)
        changed = deepcopy(single); changed['bounds'] = [.1,.8]
        with pytest.raises(ValueError, match='policy changed'):
            save_frozen_experts(changed, tmp_path/'bad')
    result = combine_expert_predictions(outputs, kwargs['cutoff'])
    assert len(result) == len(target)
    assert set(result.columns) == {'issue_code','slot','provider_id','draw_probability','draw_signal','high_probability','high_signal'}
    with pytest.raises(ValueError, match='binding mismatch|scopes differ'):
        combine_expert_predictions({**outputs,'high':outputs['high'].iloc[1:]},kwargs['cutoff'])
    with pytest.raises(ValueError, match='identities'):
        combine_expert_predictions({**outputs,'draw':pd.concat([outputs['draw']]*2)},kwargs['cutoff'])
    with pytest.raises(ValueError, match='Both'):
        combine_expert_predictions({'draw':outputs['draw']},kwargs['cutoff'])
    invalid = outputs['draw'].copy();invalid.loc[0,'draw_probability'] = 2
    with pytest.raises(ValueError, match='contract'):
        combine_expert_predictions({**outputs,'draw':invalid},kwargs['cutoff'])
    later = Cutoff.decision_epoch('100105', '2010-01-12T12:00:00Z')
    high_model = fit_experts(history, **{**kwargs,'features':{'high':['x']},'depths':{'high':1}})
    later_high = predict_experts(high_model,target,later)
    with pytest.raises(ValueError, match='cutoff/model binding'):
        combine_expert_predictions({**outputs,'high':later_high},kwargs['cutoff'])
    # Altering high-only labels cannot alter a separately trained draw expert.
    options = {**kwargs,'features':{'draw':['x']},'depths':{'draw':1}}
    before = fit_experts(history, **options)
    history['cover_target'] = ~history.cover_target
    assert fit_experts(history, **options)['receipt']['draw']['model_sha256'] == before['receipt']['draw']['model_sha256']


def test_model_publish_rolls_back_failed_serialization(experiment, tmp_path, monkeypatch):
    from src.fundamentals_retrained_experts import save_frozen_experts
    history, kwargs = experiment
    artifact = fit_experts(history, **kwargs)
    def fail(*args, **kwargs):
        raise OSError('simulated write failure')
    monkeypatch.setattr(pickle, 'dumps', fail)
    with pytest.raises(OSError, match='simulated'):
        save_frozen_experts(artifact, tmp_path/'run')
    assert list(tmp_path.iterdir()) == []


def test_training_clocks_and_replay_metadata_fail_closed(experiment,tmp_path):
    from src.fundamentals_retrained_experts import save_frozen_experts
    history,kwargs=experiment
    for bad in [None,'2026-01-01T00:00:00Z','2010-01-02T00:00:00Z']:
        with pytest.raises(ValueError,match='clock'):fit_experts(history.assign(predictor_clock_ts=bad),**kwargs)
    with pytest.raises(ValueError,match='clock'):fit_experts(history.drop(columns='predictor_clock_ts'),**kwargs)
    model=fit_experts(history,**kwargs)
    assert model['receipt']['draw']['maximum_predictor_clock']=='2010-01-01T00:00:00+00:00'
    target=history.assign(issue_code='100105')
    for key,value in [('training_issues',[]),('cutoff',Cutoff.decision_epoch('100105','2009-01-01T00:00:00Z'))]:
        broken=deepcopy(model);broken[key]=value
        with pytest.raises(ValueError,match='chronology|membership'):predict_experts(broken,target,kwargs['cutoff'])
        with pytest.raises(ValueError,match='chronology|membership'):save_frozen_experts(broken,tmp_path/'broken')
