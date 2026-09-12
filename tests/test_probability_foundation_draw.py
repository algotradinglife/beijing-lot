from pathlib import Path
import copy
import numpy as np
import pandas as pd
import pytest
from src.probability_foundation_draw import draw_cells,fit_draw_foundation,predict_draw_foundation
from src.temporal_learning import Cutoff,TemporalContractError

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('variant',['strength','balance'])
def test_cutoff_fit_replay_and_future_mutation(tmp_path,variant):
    cutoff=Cutoff.decision_epoch('next','2010-02-01T00:00:00Z')
    history=pd.DataFrame(dict(issue_code=['old']*120,issue_year=[2010]*120,slot=range(120),
        provider_id=[str(i) for i in range(120)],fixture_decision_ts=['2010-01-01T00:00:00Z']*120,
        label_available_ts=['2010-01-01T06:00:00Z']*120,p_D=[.25]*120,q_D=[.2]*120,
        q_W=[.5]*120,q_L=[.3]*120,actual=['D']*60+['W']*60))
    kwargs=dict(repository_root=ROOT,source_hashes={'fixture':'a'*64},market_edges=[0,.2,.25,1],
        secondary_edges=[0,.2,.3,1],prior_strength=100,epsilon=1e-6,version=f'market-{variant}-draw-1.0.0-diagnostic')
    artifact=fit_draw_foundation(history,cutoff,**kwargs)
    assert artifact['cells'][0]['observed_draw_rate']==pytest.approx(.5)
    assert artifact==fit_draw_foundation(history,cutoff,**kwargs)
    future=history.iloc[:1].copy();future.issue_code='next';future.actual='L'
    # Even a bad early target label is excluded by exact identity.
    changed=fit_draw_foundation(pd.concat([history,future],ignore_index=True),cutoff,**kwargs)
    assert changed['cells']==artifact['cells']
    future.issue_code='later';future.label_available_ts='2010-03-01T00:00:00Z'
    assert fit_draw_foundation(pd.concat([history,future],ignore_index=True),cutoff,**kwargs)['cells']==artifact['cells']
    target=pd.DataFrame(dict(issue=['next'],slot=[1],provider_id=['1'],fixture_decision_ts=['2010-02-01T01:00:00Z'],
        p_D=[.25],q_D=[.2],q_W=[.5],q_L=[.3]))
    prediction=predict_draw_foundation(artifact,target,cutoff,repository_root=ROOT)
    import shutil
    for relative in artifact['receipt']['implementation']['files']:
        destination=tmp_path/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/relative,destination)
    clock=tmp_path/'src/temporal_learning/diagnostic_labels.py'
    assert clock.exists()
    clock.write_text(clock.read_text()+'\n# changed clock implementation\n')
    with pytest.raises(TemporalContractError,match='closure differs'):
        predict_draw_foundation(artifact,target,cutoff,repository_root=tmp_path)
    assert prediction.new_D.iloc[0]==pytest.approx(.2+36/220)
    varied=target.copy();varied.q_D=.22;varied.q_W=.51;varied.q_L=.27
    assert predict_draw_foundation(artifact,varied,cutoff,repository_root=ROOT).new_D.iloc[0]==pytest.approx((60+100*.22)/220)
    assert prediction.new_W.iloc[0]/prediction.new_L.iloc[0]==pytest.approx(5/3)
    assert prediction[['new_W','new_D','new_L']].sum(axis=1).iloc[0]==pytest.approx(1)
    unseen=target.copy();unseen.p_D=.1
    if variant=='balance':
        unseen.q_W=.7;unseen.q_L=.1
        without_strength=target.drop(columns='p_D')
        assert predict_draw_foundation(artifact,without_strength,cutoff,repository_root=ROOT).new_D.equals(prediction.new_D)
        changed_prediction=predict_draw_foundation(changed,target,cutoff,repository_root=ROOT)
        assert changed_prediction[['new_W','new_D','new_L']].equals(prediction[['new_W','new_D','new_L']])
    assert predict_draw_foundation(artifact,unseen,cutoff,repository_root=ROOT).new_D.iloc[0]==.2
    with pytest.raises(TemporalContractError):predict_draw_foundation(artifact,target.assign(actual='D'),cutoff,repository_root=ROOT)
    broken=copy.deepcopy(artifact);broken['cells'][0]['correction']=.9
    with pytest.raises(TemporalContractError):predict_draw_foundation(broken,target,cutoff,repository_root=ROOT)
    with pytest.raises(TemporalContractError):predict_draw_foundation(artifact,target,Cutoff.decision_epoch('later','2010-03-01'),repository_root=ROOT)
    with pytest.raises(TemporalContractError):fit_draw_foundation(history.iloc[:1],cutoff,**kwargs)
    with pytest.raises(TemporalContractError):draw_cells(target.assign(q_D=np.nan),cutoff,market_edges=[0,1],secondary_edges=[0,1],version=kwargs['version'])
    bins=draw_cells(pd.DataFrame({'p_D':[0,.2,1],'q_D':[0,.2,1],'q_W':[1,.8,0],'q_L':[0,0,0]}),cutoff,market_edges=[0,.2,1],secondary_edges=[0,.2,1],version=kwargs['version'])
    assert bins.market_bin.tolist()==[0,1,1]
    if variant=='balance':
        assert bins.secondary_bin.tolist()==[1,1,0]
