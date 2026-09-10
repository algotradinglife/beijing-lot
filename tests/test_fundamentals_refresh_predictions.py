import json,hashlib
from pathlib import Path
import pandas as pd
import pytest
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_refresh_predictions import save_refresh_prediction,verify_refresh_predictions,refresh_input_hash,validate_refresh_candidate,freeze_refresh_report_inputs


def test_compact_receipts_reject_probability_version_input_and_cutoff_mutations(tmp_path,monkeypatch):
    root=tmp_path;study=root/'study';study.mkdir();(study/'evaluation').mkdir()
    monkeypatch.setattr('src.fundamentals_refresh_predictions.validate_refresh_candidate',lambda *args: None)
    f=[dict(issue_code='002',slot=1,provider_id='id',handicap=-2,predictor_clock_ts='2009-12-31T00:00:00Z',baseline_draw=.2)]
    (root/'meta.json').write_text(json.dumps(dict(receipt={'high':dict(features=['baseline_draw'])})))
    for name,x in [('test-features.json',f),('contract.json',dict(cutoffs={'002':{'1':'2010-01-01T00:00:00Z'}})),('models-frozen.json',dict(files={}))]:
        (study/name).write_text(json.dumps(x))
    (study/'test-labels.json').write_text('{}')
    (study/'training-data.json').write_text('[]')
    versions={v:dict(version=v,backend='RAW_TREE',files={},models={'002':str(root/'meta.pkl')}) for v in ['2.0.0','1.1.0','0.1.0']}
    rc=dict(versions=versions);catalog=root/'catalog.json';catalog.write_text(json.dumps(dict(receipt=rc,seal=stable_json_hash(rc))))
    for name,v in [('new_draw','2.0.0'),('new_high','2.0.0'),('old_draw','1.1.0'),('old_high','0.1.0')]:
        result=pd.DataFrame([dict(**f[0],expert_version=v,probability=.3)])
        r=dict(input_sha256=refresh_input_hash(study,versions[v],repository_root=root),version=v,prediction_sha256=stable_json_hash(result.to_json(orient='records')),catalog_seal=stable_json_hash(rc),model_receipts={'x':{'hash':'a'}},cutoffs=['2010-01-01T00:00:00+00:00'])
        result.attrs=dict(prediction_receipt=r,prediction_seal=stable_json_hash(r))
        path=study/'evaluation'/f'{name}.json'
        save_refresh_prediction(result,path,version=v,catalog_path=catalog,study=study,repository_root=root)
        with pytest.raises(FileExistsError):save_refresh_prediction(result,path,version=v,catalog_path=catalog,study=study,repository_root=root)
        with pytest.raises(ValueError,match='mismatch'):save_refresh_prediction(result,path,version='bad',catalog_path=catalog,study=study,repository_root=root)
    freeze_refresh_report_inputs(study)
    freeze_refresh_report_inputs(study)
    (study/'test-labels.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='snapshot changed'):verify_refresh_predictions(study,repository_root=root)
    with pytest.raises(ValueError,match='snapshot changed'):freeze_refresh_report_inputs(study)
    (study/'test-labels.json').write_text('{}')
    assert verify_refresh_predictions(study,repository_root=root)==dict(new_draw=1,new_high=1,old_draw=1,old_high=1)
    path=study/'evaluation/new_draw.json';raw=path.read_text();x=json.loads(raw);x['rows'][0]['probability']=.8;path.write_text(json.dumps(x))
    with pytest.raises(ValueError,match='seal'):verify_refresh_predictions(study,repository_root=root)
    path.write_text(raw);x=json.loads(raw);x['receipt']['cutoffs']=['bad'];x['seal']=stable_json_hash(x['receipt']);path.write_text(json.dumps(x))
    with pytest.raises(ValueError,match='cutoffs'):verify_refresh_predictions(study,repository_root=root)
    path.write_text(raw);(study/'test-features.json').write_text(json.dumps(f)+' ')
    with pytest.raises(ValueError,match='input'):verify_refresh_predictions(study,repository_root=root)
    f[0]['baseline_draw']=.9
    (study/'test-features.json').write_text(json.dumps(f))
    for output in (study/'evaluation').glob('*.json'):
        changed=json.loads(output.read_text())
        changed['receipt']['snapshot_hashes']['test-features.json']=hashlib.sha256((study/'test-features.json').read_bytes()).hexdigest()
        changed['seal']=stable_json_hash(changed['receipt']);output.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='Router input hash'):verify_refresh_predictions(study,repository_root=root)



def test_fit_binds_and_rejects_changed_upstream_provenance(tmp_path,monkeypatch):
    import runpy,sys,shutil
    import src.fundamentals_cv_experts as cv
    study=tmp_path/'study';study.mkdir();raw=tmp_path/'raw.json';raw.write_text('raw')
    c=dict(cutoff_issue='003',cutoff_ts='2010-01-03T00:00:00Z',train_issues=['001','002'],
        features={'high':['baseline_cover']},initial_issues=1,validation_cutoffs={'002':'2010-01-02T00:00:00Z'})
    policy=dict(candidates=[dict(depth=1,minimum_leaf=5)],bounds=[.2,.6],minimum_ess=1,seed=1)
    receipt=dict(contract=c,source_hashes={str(raw):hashlib.sha256(raw.read_bytes()).hexdigest()})
    for name,x in [('contract.json',c),('fit-policy.json',policy),('training-data.json',[]),('train-labels.json',[]),('train-features.json',[]),('input-receipt.json',dict(receipt=receipt,seal=stable_json_hash(receipt)))]:
        (study/name).write_text(json.dumps(x))
    def selected(*args,**kwargs):
        assert str(study/'input-receipt.json') in kwargs['source_hashes']
        assert kwargs['source_hashes'][str(raw)]==receipt['source_hashes'][str(raw)]
        raise RuntimeError('CV_REACHED')
    monkeypatch.setattr(cv,'cross_validate_experts',selected)
    monkeypatch.setattr(sys,'argv',['fit','--study',str(study),'--expert','high'])
    with pytest.raises(RuntimeError,match='CV_REACHED'):runpy.run_path('scripts/fit_expert_refresh.py',run_name='__main__')
    (study/'high').rmdir();raw.write_text('changed')
    with pytest.raises(ValueError,match='Upstream input changed'):runpy.run_path('scripts/fit_expert_refresh.py',run_name='__main__')


def test_catalog_must_name_frozen_candidate(tmp_path):
    model=str(tmp_path/'draw/draw-expert/model.json')
    frozen=dict(files={model:'sha'})
    entry=dict(backend='CALIBRATED',model_dir=str(tmp_path/'draw'),files={model:'sha'})
    validate_refresh_candidate(entry,'draw',tmp_path,frozen)
    with pytest.raises(ValueError,match='candidate'):validate_refresh_candidate({**entry,'model_dir':'wrong'},'draw',tmp_path,frozen)
    with pytest.raises(ValueError,match='binding'):validate_refresh_candidate({**entry,'files':{}},'draw',tmp_path,frozen)
    model=str(tmp_path/'high/high-expert/model.pkl');frozen=dict(files={model:'sha'})
    entry=dict(backend='RAW_TREE',models={'002':model},files={model:'sha'})
    validate_refresh_candidate(entry,'high',tmp_path,frozen)
    with pytest.raises(ValueError,match='candidate'):validate_refresh_candidate({**entry,'models':{'002':'other'}},'high',tmp_path,frozen)


def test_legacy_catalog_roots_are_explicit_and_preserve_worker_pin(tmp_path):
    from src.fundamentals_refresh_predictions import bind_legacy_catalog_roots
    receipt=dict(versions={'old':dict(runtime_root='runtime',model_dir='model',models={'001':'model.pkl'},files={'source':'sha','scripts/predict_draw_version_worker.py':'worker'})})
    original=dict(receipt=receipt,seal=stable_json_hash(receipt))
    bound=bind_legacy_catalog_roots(original,tmp_path)
    entry=bound['receipt']['versions']['old']
    assert entry['model_dir']==str(tmp_path/'model')
    assert entry['models']['001']==str(tmp_path/'model.pkl')
    assert entry['files']=={str(tmp_path/'source'):'sha','scripts/predict_draw_version_worker.py':'worker'}
    assert original['receipt']['versions']['old']['model_dir']=='model'
    assert bound['seal']==stable_json_hash(bound['receipt'])
    with pytest.raises(ValueError,match='seal'):bind_legacy_catalog_roots({**original,'seal':'bad'},tmp_path)


def test_relative_freeze_catalog_candidate_roundtrip(tmp_path,monkeypatch):
    import runpy,sys
    from src.fundamentals_refresh_predictions import frozen_candidate_files
    script=Path('scripts/freeze_expert_refresh.py').resolve()
    study=tmp_path/'study';(study/'draw').mkdir(parents=True);(study/'high/high-expert').mkdir(parents=True)
    (study/'contract.json').write_text(json.dumps(dict(api_version='1.1.0',model_version='2.0.0')))
    (study/'draw/fixture').write_bytes(b'draw')
    raw=b'high';(study/'high/high-expert/model.pkl').write_bytes(raw);rc={'high':{}}
    (study/'high/high-expert/model.json').write_text(json.dumps(dict(receipt=rc,seal=stable_json_hash(rc),model_sha256=hashlib.sha256(raw).hexdigest())))
    monkeypatch.setattr('src.fundamentals_calibrated_draw.load_calibrated_draw',lambda *args,**kwargs:None)
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(sys,'argv',['freeze','--study','study'])
    runpy.run_path(str(script),run_name='__main__')
    frozen=json.loads((study/'models-frozen.json').read_text())
    assert all(Path(k).is_absolute() for k in frozen['files'])
    files=frozen_candidate_files('study','high',frozen)
    entry=dict(backend='RAW_TREE',models={'002':str(study/'high/high-expert/model.pkl')},files=files)
    validate_refresh_candidate(entry,'high',study,frozen)
    relative=dict(files={str(Path(k).relative_to(tmp_path)):v for k,v in frozen['files'].items()})
    assert frozen_candidate_files(study,'high',relative)==files
    validate_refresh_candidate(entry,'high','study',relative)
    with pytest.raises(ValueError,match='Missing frozen'):frozen_candidate_files('absent','high',frozen)
    with pytest.raises(ValueError,match='Unknown'):frozen_candidate_files(study,'bad',frozen)
