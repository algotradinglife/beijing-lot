import hashlib,json
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_active_experts import predict_active_experts


def test_paired_selection_pins_versions_and_only_weights_draw(tmp_path,monkeypatch):
    import src.fundamentals_active_experts as module
    entries={}
    for e,backend in [('draw','CALIBRATED'),('high','RAW_TREE')]:
        rc=dict(versions={'2.0.0':dict(version='2.0.0',backend=backend,files={})})
        p=tmp_path/f'{e}.json';p.write_text(json.dumps(dict(receipt=rc,seal=stable_json_hash(rc))))
        entries[e]=dict(version='2.0.0',catalog_path=str(p),catalog_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    r=dict(experts=entries);p=tmp_path/'active.json';p.write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    calls=[]
    def predict(version,frame,**kw):
        calls.append((version,kw));return frame.copy()
    monkeypatch.setattr(module,'predict_draw_version',predict)
    f=pd.DataFrame([dict(issue_code='001',slot=1,provider_id='a')]);cuts=[Cutoff.decision_epoch('001','2010-01-01T00:00:00Z')]
    args=dict(cutoffs=cuts,selection_path=p,repository_root=tmp_path,python='/explicit/python')
    result=predict_active_experts(f,draw_weight=.7,**args)
    assert set(result)=={'draw','high'} and len(calls)==2
    assert calls[0][0]==calls[1][0]=='2.0.0'
    assert calls[0][1]['draw_weight']==.7 and 'draw_weight' not in calls[1][1]
    assert calls[0][1]['cutoffs'] is cuts
    (tmp_path/'high.json').write_text('changed');calls.clear()
    with pytest.raises(ValueError,match='catalog changed'):predict_active_experts(f,**args)
    assert not calls
    r['experts'].pop('high');p.write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    with pytest.raises(ValueError,match='selection'):predict_active_experts(f,**args)

    r=dict(experts=entries)
    bad=dict(versions={'2.0.0':dict(version='2.0.0',backend='CALIBRATED',files={})})
    catalog=tmp_path/'high.json';catalog.write_text(json.dumps(dict(receipt=bad,seal=stable_json_hash(bad))))
    entries['high']=dict(version='2.0.0',catalog_path=str(catalog),catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest())
    p.write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    with pytest.raises(ValueError,match='backend'):predict_active_experts(f,**args)
    assert not calls
