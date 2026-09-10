import hashlib,json,sys
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_active_experts import predict_active_experts


def test_paired_selection_pins_manifest_and_only_weights_draw(tmp_path,monkeypatch):
    import src.fundamentals_active_experts as module
    manifest=tmp_path/'manifest.json';manifest.write_text('{}')
    r=dict(format='PORTABLE_EXPERT_SELECTION_V1',experts={e:dict(version='2.0.0') for e in ['draw','high']},manifest_path='manifest.json',manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),model_root='models',source_root='.',provenance_root='.')
    p=tmp_path/'active.json';p.write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    calls=[]
    monkeypatch.setattr(module,'load_portable_experts',lambda *a,**kw:dict(release_seal='frozen'))
    def predict(artifact,expert,frame,**kw):
        calls.append((expert,kw));return frame.copy()
    monkeypatch.setattr(module,'predict_portable_expert',predict)
    f=pd.DataFrame([dict(issue_code='001',slot=1,provider_id='a',predictor_clock_ts='2009-12-31T00:00:00Z')]);cuts=[Cutoff.decision_epoch('001','2010-01-01T00:00:00Z')]
    args=dict(cutoffs=cuts,selection_path=p,repository_root=tmp_path,python=sys.executable)
    result=predict_active_experts(f,draw_weight=.7,**args)
    assert set(result)=={'draw','high'} and len(calls)==2
    assert calls[0][1]['draw_weight']==.7 and 'draw_weight' not in calls[1][1]
    assert calls[0][1]['cutoff'] is cuts[0]
    calls.clear();manifest.write_text('changed')
    with pytest.raises(ValueError,match='manifest changed'):predict_active_experts(f,**args)
    assert not calls
    with pytest.raises(ValueError,match='Python'):predict_active_experts(f,**{**args,'python':'/wrong/python'})
    with pytest.raises(ValueError,match='fixtures'):predict_active_experts(f.iloc[:0],**args)
    r['experts'].pop('high');p.write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    with pytest.raises(ValueError,match='selection'):predict_active_experts(f,**args)
