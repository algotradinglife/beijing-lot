import json
import pytest
from src.temporal_learning import Cutoff
from src.joint_grid_rotation_replay import replay_rotation_json


def test_replay_priorities_and_cutoff():
    c=Cutoff.decision_epoch('001','2020-01-01T00:00:00+00:00')
    x=dict(issue='001',cutoff_ts='2020-01-01T00:00:00+00:00',cutoff_identity=c.identity,
        tickets=[dict(issue='001',ticket_id=str(i),sleeve_id=i//2,cell='good',prob=1-i/10,payout_hat=200,base_copies=int(i<2)) for i in range(6)],
        members=[dict(sleeve_id=i//2,fixture=str(i)) for i in range(6)],
        signals=[dict(cell='good',state='GOOD')],parameters=dict(mode='EXPAND',cut_fraction=.5,unit_cny=2,fixture_cap_cny=8,payout_floor=128,probability_only=False,target_units=4,max_overlap=1))
    assert replay_rotation_json(json.dumps(x),c)==[1,1,1,0,1,0]
    x['parameters']['target_units']=8
    assert replay_rotation_json(json.dumps(x),c)==[2,2,1,1,1,1]
    with pytest.raises(ValueError):replay_rotation_json(json.dumps(x),Cutoff.decision_epoch('002',x['cutoff_ts']))
    x['tickets'][0]['issue']='002'
    with pytest.raises(ValueError):replay_rotation_json(json.dumps(x),c)
