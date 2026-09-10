import hashlib,json,shutil
from pathlib import Path
import pandas as pd
import pytest
from tests.test_fundamentals_calibrated_draw import frozen
from src.fundamentals_portable_experts import freeze_portable_experts,load_portable_experts,predict_portable_expert,_portable_path
from src.fundamentals_retrained_experts import fit_experts,save_frozen_experts
from src.temporal_learning.provenance import implementation_closure
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def portable(frozen):
    source,root,frame,cutoff=frozen
    bundle=source/'bundle';(bundle/'draw').mkdir(parents=True)
    shutil.copytree(source/'draw-expert',bundle/'draw/draw-expert')
    for name in ['signal-rates.json','signal-rates.pkl','rate-cv.json']:shutil.copyfile(source/name,bundle/'draw'/name)
    history=pd.DataFrame(dict(issue_code='100101',slot=range(30),provider_id=[str(i) for i in range(30)],issue_year=2010,data_available_ts='2010-01-01T00:00:00Z',predictor_clock_ts='2009-12-31T00:00:00Z',label_available_ts='2010-01-02T00:00:00Z',handicap=-2,x=range(30),cover_target=[0,1]*15))
    source_file=source/'source.json'
    high=fit_experts(history,cutoff,features={'high':['x']},training_issues=['100101'],source_hashes={str(source_file):hashlib.sha256(source_file.read_bytes()).hexdigest()},repository_root=root,depths={'high':1},minimum_leaf=5,minimum_ess=10,bounds=[.2,.6],seed=417)
    save_frozen_experts(high,bundle/'high/high-expert')
    archive=source/'runtime'
    files=implementation_closure(root,['src.fundamentals_portable_experts','src.fundamentals_signal_rate_cv'])['files']
    for name in files:
        target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
    manifest=source/'portable.json'
    freeze_portable_experts(bundle,output_path=manifest,source_root=source,provenance_root=archive,repository_root=root,version='2.0.0')
    return source,root,frame.assign(handicap=-2),cutoff


def test_move_all_model_sources_and_training_runtime_preserves_predictions(portable):
    source,root,frame,cutoff=portable
    args=dict(expected_version='2.0.0',model_root=source/'bundle',source_root=source,provenance_root=source/'runtime',repository_root=root)
    before=load_portable_experts(source/'portable.json',**args)
    predicted={e:predict_portable_expert(before,e,frame,cutoff=cutoff) for e in ['draw','high']}
    moved=source.parent/(source.name+'-moved');shutil.move(str(source),moved)
    assert not source.exists()
    after=load_portable_experts(moved/'portable.json',expected_version='2.0.0',model_root=moved/'bundle',source_root=moved,provenance_root=moved/'runtime',repository_root=moved/'runtime')
    assert before['seal']==after['seal']
    for e in predicted:pd.testing.assert_frame_equal(predicted[e],predict_portable_expert(after,e,frame,cutoff=cutoff))
    (moved/'source.json').write_text('changed')
    with pytest.raises(ValueError,match='source changed'):load_portable_experts(moved/'portable.json',expected_version='2.0.0',model_root=moved/'bundle',source_root=moved,provenance_root=moved/'runtime',repository_root=moved/'runtime')


def test_portable_preflights_before_pickle_and_rejects_tampering(portable,monkeypatch):
    source,root,frame,cutoff=portable
    args=dict(expected_version='2.0.0',model_root=source/'bundle',source_root=source,provenance_root=source/'runtime',repository_root=root)
    manifest=source/'portable.json'
    with pytest.raises(FileExistsError):freeze_portable_experts(source/'bundle',output_path=manifest,source_root=source,provenance_root=source/'runtime',repository_root=root,version='2.0.0')
    a=load_portable_experts(manifest,**args)
    with pytest.raises(ValueError,match='only to draw'):predict_portable_expert(a,'high',frame,cutoff=cutoff,draw_weight=.5)
    for bad in [None,cutoff.cutoff_ts.isoformat()]:
        with pytest.raises(ValueError,match='clock'):
            predict_portable_expert(a,'high',frame.assign(predictor_clock_ts=bad),cutoff=cutoff)
    with pytest.raises(ValueError,match='clock'):
        predict_portable_expert(a,'high',frame.drop(columns='predictor_clock_ts'),cutoff=cutoff)
    a['release_seal']='wrong'
    with pytest.raises(ValueError,match='binding'):predict_portable_expert(a,'draw',frame,cutoff=cutoff)
    for path in ['../outside','/absolute']:
        with pytest.raises(ValueError,match='relative'): _portable_path(source,path)
    assert _portable_path(source,'.')==source
    raw=manifest.read_text();changed=json.loads(raw);changed['receipt']['sources']={};changed['seal']=stable_json_hash(changed['receipt']);manifest.write_text(json.dumps(changed))
    import src.fundamentals_portable_experts as module
    def forbidden(*args):raise AssertionError('unpickle before source checks')
    monkeypatch.setattr(module.pickle,'loads',forbidden)
    with pytest.raises(ValueError,match='bindings incomplete'):load_portable_experts(manifest,**args)
    manifest.write_text(raw);(source/'runtime/src/temporal_learning/core.py').write_text('changed')
    with pytest.raises(ValueError,match='implementation'):load_portable_experts(manifest,**args)
