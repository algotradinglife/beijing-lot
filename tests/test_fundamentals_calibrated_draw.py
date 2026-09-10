import hashlib
import json
import pickle
import io
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.fundamentals_calibrated_draw import freeze_calibrated_draw_release, load_calibrated_draw, predict_calibrated_draw
from src.fundamentals_retrained_experts import fit_experts, save_frozen_experts
from src.fundamentals_signal_rates import fit_signal_rates, predict_signal_rates
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure


@pytest.fixture
def frozen(tmp_path):
    root=Path(__file__).resolve().parents[1]
    history=pd.DataFrame(dict(issue_code='100101',slot=range(30),provider_id=[str(i) for i in range(30)],
        issue_year=2010,data_available_ts='2010-01-01T00:00:00Z',predictor_clock_ts='2009-12-31T00:00:00Z',
        label_available_ts='2010-01-02T00:00:00Z',handicap=-1,x=range(30),
        draw_signal=['POSITIVE']*10+['NEGATIVE']*10+['ABSTAIN']*10,
        draw_target=[1]*7+[0]*3+[1]*2+[0]*8+[1]*3+[0]*7))
    cutoff=Cutoff.decision_epoch('100102','2010-01-03T00:00:00Z')
    policy=dict(blend_weight=.5,abstain_boost=.05)
    source=tmp_path/'source.json';source.write_text('[]')
    receipt=dict(selected=policy,oof_sha256=stable_json_hash([]),
        implementation=implementation_closure(root,['src.fundamentals_signal_rate_cv']),
        source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()})
    cv=dict(receipt=receipt,seal=stable_json_hash(receipt),selected=policy,oof=[])
    (tmp_path/'rate-cv.json').write_text(json.dumps(cv))
    sources={str(tmp_path/'rate-cv.json'):hashlib.sha256((tmp_path/'rate-cv.json').read_bytes()).hexdigest()}
    expert=fit_experts(history,cutoff,features={'draw':['x']},training_issues=['100101'],
        source_hashes=sources,repository_root=root,depths={'draw':1},minimum_leaf=5,minimum_ess=10,
        bounds=[.2,.6],seed=417)
    save_frozen_experts(expert,tmp_path/'draw-expert')
    rates=fit_signal_rates(history,cutoff,shrinkage_n=20,minimum_ess=10,
        source_hashes=sources,repository_root=root)
    raw=pickle.dumps(rates,protocol=5)
    (tmp_path/'signal-rates.pkl').write_bytes(raw)
    (tmp_path/'signal-rates.json').write_text(json.dumps(dict(receipt=rates['receipt'],seal=rates['seal'],
        selected=policy,model_sha256=hashlib.sha256(raw).hexdigest())))
    freeze_calibrated_draw_release(tmp_path,version="1.1.0",repository_root=root)
    frame=pd.DataFrame(dict(issue_code='100102',slot=[1,2,3],provider_id=['a','b','c'],
        handicap=[-1,2,-1],x=[5.,25.,np.nan],baseline_draw=.2,predictor_clock_ts='2010-01-02T23:00:00Z'))
    return tmp_path,root,frame,cutoff


def test_loaded_api_matches_calibration_and_preserves_missing_status(frozen):
    path,root,frame,cutoff=frozen
    artifact=load_calibrated_draw(path,expected_version="1.1.0",repository_root=root)
    result=predict_calibrated_draw(artifact,frame,cutoff)
    expected=predict_signal_rates(artifact['rates'],frame.assign(draw_signal=result.draw_signal),
        cutoff,**artifact['receipt']['policy'])
    np.testing.assert_allclose(result.draw_target_probability,expected.draw_probability)
    assert result.calibration_status.tolist()==['CALIBRATED','NO_PRIOR_HANDICAP_BAND','INSUFFICIENT_FEATURES']
    assert result.draw_target_probability.iloc[1:].tolist()==[.2,.2]
    assert 'draw_probability' not in result  # legacy fusion must not silently blend twice
    assert result.attrs['prediction_receipt']['probability_semantics']=='FINAL_HANDICAP_DRAW_MASS'
    assert result.attrs['prediction_receipt']['deployable'] is False
    assert result.expert_version.eq('1.1.0').all()
    assert result.attrs['prediction_receipt']['version']=='1.1.0'
    changed=predict_calibrated_draw(artifact,frame.assign(baseline_draw=.25),cutoff)
    assert changed.attrs['prediction_receipt']['input_sha256']!=result.attrs['prediction_receipt']['input_sha256']
    observed=frame.assign(draw_target=1,actual_home=99)
    pd.testing.assert_frame_equal(predict_calibrated_draw(artifact,observed,cutoff),result)
    empty=predict_calibrated_draw(artifact,frame.iloc[:0],cutoff)
    assert empty.empty and 'draw_target_probability' in empty
    with pytest.raises(ValueError):
        predict_calibrated_draw(artifact,frame.assign(predictor_clock_ts=cutoff.cutoff_ts),cutoff)
    with pytest.raises(ValueError):
        predict_calibrated_draw(artifact,pd.concat([frame,frame]),cutoff)
    with pytest.raises(ValueError):
        predict_calibrated_draw(artifact,frame,Cutoff.decision_epoch('100102','2010-01-02T00:00:00Z'))
    bad=deepcopy(artifact);bad['receipt']['policy']['blend_weight']=1.
    with pytest.raises(ValueError,match='binding'):
        predict_calibrated_draw(bad,frame,cutoff)


def test_loader_rejects_changed_frozen_bytes_and_sources(frozen):
    path,root,_,_=frozen
    original=(path/'signal-rates.pkl').read_bytes()
    (path/'signal-rates.pkl').write_bytes(b'invalid pickle')
    with pytest.raises(ValueError,match='model/receipt'):
        load_calibrated_draw(path,expected_version="1.1.0",repository_root=root)
    (path/'signal-rates.pkl').write_bytes(original)
    (path/'source.json').write_text('[1]')
    with pytest.raises(ValueError,match='CV source changed'):
        load_calibrated_draw(path,expected_version="1.1.0",repository_root=root)


def test_loader_rejects_selector_code_drift_before_deserializing(frozen,monkeypatch):
    path,root,_,_=frozen
    original_open=Path.open
    selector=root/'src/fundamentals_signal_rate_cv.py'
    def changed_open(file,mode='r',*args,**kwargs):
        if file.resolve()==selector and mode=='rb':
            with original_open(file,mode,*args,**kwargs) as handle:
                return io.BytesIO(handle.read()+b'\n# changed selector\n')
        return original_open(file,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',changed_open)
    def forbidden_loads(raw):
        pytest.fail('Deserialization must follow CV provenance validation')
    monkeypatch.setattr(pickle,'loads',forbidden_loads)
    with pytest.raises(ValueError,match='implementation closure differs'):
        load_calibrated_draw(path,expected_version="1.1.0",repository_root=root)


def test_exact_version_is_mandatory_and_release_cannot_be_overwritten(frozen):
    path,root,frame,cutoff=frozen
    with pytest.raises(TypeError,match='expected_version'):
        load_calibrated_draw(path,repository_root=root)
    for version in ['latest','1','1.0','1.0.0',None]:
        with pytest.raises(ValueError,match='version'):
            load_calibrated_draw(path,expected_version=version,repository_root=root)
    with pytest.raises(FileExistsError,match='already frozen'):
        freeze_calibrated_draw_release(path,version='1.1.0',repository_root=root)
    with pytest.raises(ValueError,match='version'):
        freeze_calibrated_draw_release(path,version='2.0.0',repository_root=root)
    artifact=load_calibrated_draw(path,expected_version='1.1.0',repository_root=root)
    artifact['receipt']['version']='9.0.0'
    artifact['seal']=stable_json_hash(artifact['receipt'])
    with pytest.raises(ValueError,match='binding'):
        predict_calibrated_draw(artifact,frame,cutoff)
    release=path/'calibrated-draw-release.json';data=json.loads(release.read_text())
    data['receipt']['version']='9.0.0';data['seal']=stable_json_hash(data['receipt'])
    release.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='version/seal'):
        load_calibrated_draw(path,expected_version='1.1.0',repository_root=root)
    release.unlink()
    with pytest.raises(FileNotFoundError):
        load_calibrated_draw(path,expected_version='1.1.0',repository_root=root)


def test_preserved_training_runtime_is_verified_separately(frozen,tmp_path):
    import shutil
    path,root,frame,cutoff=frozen
    archive=path/'training-runtime'
    modules=['src.fundamentals_calibrated_draw','src.fundamentals_signal_rate_cv']
    files=implementation_closure(root,modules)['files']
    for name in files:
        target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,target)
    candidate=path/'new-release';candidate.mkdir()
    for name in ['rate-cv.json','signal-rates.json','signal-rates.pkl','draw-expert/model.json','draw-expert/model.pkl']:
        target=candidate/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path/name,target)
    freeze_calibrated_draw_release(candidate,version='1.1.0',repository_root=root,provenance_root=archive)
    artifact=load_calibrated_draw(candidate,expected_version='1.1.0',repository_root=root)
    assert artifact['receipt']['provenance_root']==str(archive)
    assert predict_calibrated_draw(artifact,frame,cutoff).expert_version.eq('1.1.0').all()
    target=archive/'src/fundamentals_signal_rates.py'
    target.write_text(target.read_text()+'\n# altered old implementation\n')
    with pytest.raises(ValueError,match='implementation closure differs'):
        load_calibrated_draw(candidate,expected_version='1.1.0',repository_root=root)
