import hashlib
import json
import sys
import shutil
from pathlib import Path
import pytest
from tests.test_fundamentals_calibrated_draw import frozen
from src.fundamentals_draw_versions import read_draw_version,predict_draw_version
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def catalog(frozen):
    path,root,frame,cutoff=frozen
    worker='scripts/predict_draw_version_worker.py'
    files={worker:hashlib.sha256((root/worker).read_bytes()).hexdigest()}
    versions={}
    for version in ['0.1.0','0.2.0','1.0.0','1.0.1','1.1.0']:
        raw=version=='0.1.0'
        versions[version]=dict(version=version,backend='RAW_TREE' if raw else 'CALIBRATED',
            probability_semantics='RAW_EXPERT_PROBABILITY' if raw else 'FINAL_HANDICAP_DRAW_MASS',
            runtime_root=str(root),models={'100102':str(path/'draw-expert/model.pkl')},
            supports_draw_weight=version=='1.1.0',model_dir=str(path),implementation_version='1.1.0',files=files)
    receipt=dict(versions=versions)
    target=path/'catalog.json';target.write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
    return target,root,frame,cutoff


def test_numbered_versions_execute_and_preserve_probability_semantics(catalog):
    path,root,frame,cutoff=catalog
    outputs={}
    for version in ['0.1.0','0.2.0','1.0.0','1.0.1','1.1.0']:
        result=predict_draw_version(version,frame,cutoffs=[cutoff]*len(frame),catalog_path=path,
            repository_root=root,python=sys.executable)
        assert result.expert_version.eq(version).all()
        assert result.attrs['prediction_receipt']['version']==version
        outputs[version]=result
    assert 'draw_probability' in outputs['0.1.0']
    assert 'draw_target_probability' not in outputs['0.1.0']
    assert 'draw_probability' not in outputs['1.0.0']
    assert outputs['0.2.0'].draw_target_probability.equals(outputs['1.0.0'].draw_target_probability)
    assert outputs['0.1.0'].draw_signal.equals(outputs['1.0.0'].draw_signal)
    irrelevant=predict_draw_version('0.1.0',frame.assign(actual_home=99,draw_target=1),
        cutoffs=[cutoff]*len(frame),catalog_path=path,repository_root=root,python=sys.executable)
    assert irrelevant.attrs['prediction_receipt']['input_sha256']==outputs['0.1.0'].attrs['prediction_receipt']['input_sha256']


def test_unknown_mutated_and_bad_cutoff_fail_closed(catalog):
    path,root,frame,cutoff=catalog
    with pytest.raises(ValueError,match='exact draw version'):
        read_draw_version(path,'latest',repository_root=root)
    kwargs=dict(catalog_path=path,repository_root=root,python=sys.executable)
    with pytest.raises(ValueError,match='cutoffs'):
        predict_draw_version('0.1.0',frame,cutoffs=[],**kwargs)
    with pytest.raises(ValueError,match='identity'):
        predict_draw_version('0.1.0',frame,cutoffs=[Cutoff.decision_epoch('100103','2010-01-03T00:00:00Z')]*3,**kwargs)
    with pytest.raises(ValueError):
        predict_draw_version('1.0.0',frame.assign(predictor_clock_ts=cutoff.cutoff_ts),cutoffs=[cutoff]*3,**kwargs)
    bad=json.loads(path.read_text());bad['receipt']['versions']['0.1.0']['files']['scripts/predict_draw_version_worker.py']='changed'
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='catalog changed'):
        read_draw_version(path,'0.1.0',repository_root=root)
    bad['seal']=stable_json_hash(bad['receipt']);path.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='file changed'):
        read_draw_version(path,'0.1.0',repository_root=root)


def test_inherited_pythonpath_cannot_override_archived_runtime(catalog,monkeypatch):
    path,root,frame,cutoff=catalog
    archive=path.parent/'archive';(archive/'src').mkdir(parents=True)
    (archive/'src/__init__.py').write_text('"""Isolated test runtime."""\n')
    metadata=json.loads((path.parent/'draw-expert/model.json').read_text())
    files=metadata['receipt']['draw']['implementation']['files']
    for name in files:
        destination=archive/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,destination)
    catalog_data=json.loads(path.read_text())
    catalog_data['receipt']['versions']['0.1.0']['runtime_root']=str(archive)
    catalog_data['seal']=stable_json_hash(catalog_data['receipt']);path.write_text(json.dumps(catalog_data))
    monkeypatch.setenv('PYTHONPATH',str(root))
    result=predict_draw_version('0.1.0',frame,cutoffs=[cutoff]*len(frame),catalog_path=path,
        repository_root=root,python=sys.executable)
    receipt=result.attrs['prediction_receipt']
    assert receipt['runtime_root']==str(archive)
    assert all(Path(p).is_relative_to(archive/'src') for p in receipt['imported_sources'])
    assert str(archive/'src/fundamentals_retrained_experts.py') in receipt['imported_sources']
