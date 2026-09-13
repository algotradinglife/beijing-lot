import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest

from src.probability_foundation_draw import fit_draw_foundation, predict_draw_foundation
from src.n7_frozen_foundation import bind_frozen_draw_foundation, read_frozen_draw_history
from src.temporal_learning import Cutoff, TemporalContractError

ROOT=Path(__file__).resolve().parents[1]


def test_reference_history_reader_preserves_keys_and_shared_clocks(tmp_path):
    factors=dict(rows=[dict(issue='001',slot=1,provider_id='002',q_D=.2)],
                 cutoffs={'001':{'1':'2010-01-01T00:00:00Z'}})
    audit=dict(rows=[dict(issue='001',slot=1,provider_id='002',actual_direction='D')])
    fp=tmp_path/'factors.json';ap=tmp_path/'audit.json'
    fp.write_text(json.dumps(factors));ap.write_text(json.dumps(audit))
    args=dict(factors_path=fp,factors_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),
        audit_path=ap,audit_sha256=hashlib.sha256(ap.read_bytes()).hexdigest(),
        cutoff=Cutoff.decision_epoch('target','2010-02-01T00:00:00Z'),label_delay_hours=6)
    result=read_frozen_draw_history(**args)
    assert result.provider_id.tolist()==['002']
    assert result.label_available_ts.tolist()==['2010-01-01T06:00:00+00:00']
    assert result.actual.tolist()==['D']
    with pytest.raises(TemporalContractError,match='precede cutoff'):
        read_frozen_draw_history(**{**args,'cutoff':Cutoff.decision_epoch('target','2010-01-01T01:00:00Z')})
    with pytest.raises(TemporalContractError,match='file changed'):
        read_frozen_draw_history(**{**args,'audit_sha256':'0'*64})
    audit['rows']*=2;ap.write_text(json.dumps(audit))
    with pytest.raises(pd.errors.MergeError):
        read_frozen_draw_history(**{**args,'audit_sha256':hashlib.sha256(ap.read_bytes()).hexdigest()})


def test_frozen_cells_rebind_without_fit_and_reject_changed_history(tmp_path,monkeypatch):
    history=pd.DataFrame(dict(issue_code=['old']*120,issue_year=[2010]*120,slot=range(120),
        provider_id=[str(i) for i in range(120)],fixture_decision_ts=['2010-01-01T00:00:00Z']*120,
        label_available_ts=['2010-01-01T06:00:00Z']*120,q_D=[.2]*120,
        q_W=[.5]*120,q_L=[.3]*120,actual=['D']*60+['W']*60))
    first=Cutoff.decision_epoch('first','2010-02-01T00:00:00Z')
    artifact=fit_draw_foundation(history,first,repository_root=ROOT,source_hashes={'fixture':'a'*64},
        market_edges=[0,.2,.25,1],secondary_edges=[0,.2,.3,1],prior_strength=100,epsilon=1e-6,
        version='market-balance-draw-1.0.0-diagnostic')
    path=tmp_path/'model.json';path.write_text(json.dumps(artifact))
    kwargs=dict(model_path=path,model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                reference_repository_root=ROOT,repository_root=ROOT,source_hashes={'fixture':'a'*64})
    from src import probability_foundation_draw as module
    def forbidden(*args,**kwargs):
        pytest.fail('Frozen continuation must never fit')
    monkeypatch.setattr(module,'fit_draw_foundation',forbidden)
    target=Cutoff.decision_epoch('target','2010-03-01T00:00:00Z')
    bound=bind_frozen_draw_foundation(history,target,**kwargs)
    assert bound['cells']==artifact['cells'] and bound['parameters']==artifact['parameters']
    assert bound['receipt']['cache_key']!=artifact['receipt']['cache_key']
    assert bound['receipt']['cutoff_identity']==target.identity
    assert bound==bind_frozen_draw_foundation(history,target,**kwargs)
    frame=pd.DataFrame(dict(issue=['target'],slot=[1],provider_id=['1'],
        fixture_decision_ts=['2010-03-01T01:00:00Z'],q_D=[.2],q_W=[.5],q_L=[.3]))
    prediction=predict_draw_foundation(bound,frame,target,repository_root=ROOT)
    assert prediction.new_D.iloc[0]==pytest.approx((60+100*.2)/220)
    changed=history.copy();changed.loc[0,'actual']='L'
    with pytest.raises(TemporalContractError,match='training evidence differs'):
        bind_frozen_draw_foundation(changed,target,**kwargs)
    future=history.iloc[:1].copy();future.issue_code='future';future.label_available_ts='2011-01-01T00:00:00Z'
    extended=bind_frozen_draw_foundation(pd.concat([history,future],ignore_index=True),target,**kwargs)
    assert extended['cells']==bound['cells']
    with pytest.raises(TemporalContractError,match='follow reference'):
        bind_frozen_draw_foundation(history,first,**kwargs)
    with pytest.raises(TemporalContractError,match='file changed'):
        bind_frozen_draw_foundation(history,target,**{**kwargs,'model_sha256':'0'*64})
