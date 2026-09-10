import hashlib,json
from copy import deepcopy
from pathlib import Path
import pandas as pd
import pytest
from src.fundamentals_expert_refresh import read_refresh_features,attach_refresh_labels,calibration_rows
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def test_attach_labels_identity_completion_clocks_and_empty():
    features=pd.DataFrame(dict(issue_code=['100101','100102','100103'],slot=1,provider_id=['a','b','c'],
        handicap=[-1,0,-2],data_available_ts=['2010-01-01T00:00:00Z','2010-01-02T00:00:00Z','2010-01-03T00:00:00Z']))
    labels=pd.DataFrame(dict(issue_code=features.issue_code,slot=1,provider_id=['a','wrong','c'],
        actual_home=[2,1,3],actual_away=[1,1,0],label_status='COMPLETED'))
    cutoff=Cutoff.decision_epoch('100104','2010-01-03T01:00:00Z')
    rows,excluded=attach_refresh_labels(features,labels,cutoff=cutoff,label_delay_hours=6)
    assert len(rows)==1 and bool(rows.iloc[0].draw_target) and not bool(rows.iloc[0].cover_target)
    assert rows.iloc[0].label_available_ts=='2010-01-01T06:00:00+00:00'
    assert set(excluded.reason)=={'NO_MATCHING_LABEL_IDENTITY','LABEL_NOT_AVAILABLE_BEFORE_FIT_CUTOFF'}
    rows,excluded=attach_refresh_labels(features.iloc[:0],labels,cutoff=cutoff,label_delay_hours=6)
    assert rows.empty and 'draw_target' in rows
    with pytest.raises(ValueError,match='Duplicate'):
        attach_refresh_labels(pd.concat([features,features]),labels,cutoff=cutoff,label_delay_hours=6)
    with pytest.raises(ValueError,match='completed score'):
        attach_refresh_labels(features,labels.assign(actual_home=-1),cutoff=cutoff,label_delay_hours=6)
    rows,excluded=attach_refresh_labels(features,labels.assign(label_status='NON_COMPLETED_STATUS'),cutoff=cutoff,label_delay_hours=6)
    assert rows.empty and 'NON_COMPLETED_STATUS' in set(excluded.reason)
    with pytest.raises(ValueError):attach_refresh_labels(features,labels,cutoff=None,label_delay_hours=6)


def test_calibration_requires_preselected_policy_and_exact_join():
    cutoff=Cutoff.decision_epoch('100104','2010-01-04T00:00:00Z')
    rows=[dict(issue_code='100103',slot=i,provider_id=str(i),draw_signal=s,draw_probability=p) for i,s,p in [(1,'ABSTAIN',.3),(2,'INSUFFICIENT_FEATURES',None)]]
    receipt=dict(cutoff_identity=cutoff.identity,cutoff_ts=cutoff.cutoff_ts.isoformat(),candidates=[{}],oof_sha256=stable_json_hash(rows))
    cv=dict(receipt=receipt,seal=stable_json_hash(receipt),oof=rows)
    history=pd.DataFrame(rows).assign(issue_year=2010,data_available_ts='2010-01-03T00:00:00Z',label_available_ts='2010-01-03T06:00:00Z',baseline_draw=.2,handicap=0)
    ready,excluded=calibration_rows(cv,history,cutoff=cutoff)
    assert len(ready)==len(excluded)==1
    with pytest.raises(ValueError,match='identities'):
        calibration_rows(cv,history.iloc[:1],cutoff=cutoff)
    bad=deepcopy(cv);bad['receipt']['candidates']=[{},{}];bad['seal']=stable_json_hash(bad['receipt'])
    with pytest.raises(ValueError,match='preselected'):
        calibration_rows(bad,history,cutoff=cutoff)


def test_snapshot_split_is_label_free_and_hash_bound(tmp_path):
    prior=tmp_path/'prior';exp=tmp_path/'experiment';clean=tmp_path/'clean'
    for p in [prior,exp,clean/'projected']:p.mkdir(parents=True)
    base=dict(slot=1,provider_id='a',handicap=0,baseline_draw=.2,baseline_cover=.3,x=1,predictor_clock_ts='2009-12-31T00:00:00Z')
    old=dict(data=[dict(base,issue_code='100101',data_available_ts='2010-01-01T00:00:00Z',draw_target=999)],
        training_issues=['100101'],features={'draw':['x'],'high':['x']},validation_cutoffs={})
    (prior/'training.json').write_text(json.dumps(old))
    prediction=dict(features=[dict(base,issue='100102',provider_id='b')],selected={'cutoffs':{'100102':{'1':'2010-01-02T00:00:00Z'}}})
    (prior/'predictions.json').write_text(json.dumps(prediction))
    receipt=dict(clocks=[dict(issue='100102',slot=1,provider_id='b',predictor_clock_ts='2010-01-01T23:00:00Z')],predictions_sha256=stable_json_hash([]),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in prior.glob('*.json')})
    (exp/'predictions.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt),predictions=[])))
    cuts={f'10010{n}':{'1':f'2010-01-0{n}T00:00:00Z'} for n in [3,4]}
    prepared=dict(contract={'issues':list(cuts)},cutoffs=cuts,source_hashes={},files={})
    (clean/'prepared.json').write_text(json.dumps(dict(receipt=prepared,seal=stable_json_hash(prepared),readiness=[])))
    files={}
    for issue in cuts:
        p=clean/'projected'/f'{issue}.json';p.write_text(json.dumps(dict(features=[dict(base,issue=issue,provider_id=issue)],cutoffs={issue:cuts[issue]})))
        files[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    (clean/'projected/receipt.json').write_text(json.dumps(dict(files=files,implementation={},prepared_sha256=hashlib.sha256((clean/'prepared.json').read_bytes()).hexdigest())))
    result=read_refresh_features(prior,exp,clean,train_count=3,test_count=1,initial_issues=1)
    assert len(result['train'])==3 and len(result['test'])==1 and 'draw_target' not in result['train']
    assert result['contract']['test_issues']==['100104']
    with pytest.raises(ValueError,match='counts'):
        read_refresh_features(prior,exp,clean,train_count=4,test_count=1,initial_issues=1)
    p.write_text('{}')
    with pytest.raises(ValueError,match='source changed'):
        read_refresh_features(prior,exp,clean,train_count=3,test_count=1,initial_issues=1)
