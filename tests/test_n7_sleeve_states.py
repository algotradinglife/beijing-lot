import numpy as np
import pandas as pd
import pytest
import gzip
import json
from pathlib import Path
from src.n7_sleeve_states import enumerate_sleeve,select_sleeve_states
from src.temporal_learning import Cutoff


def test_solver_coverage_tolerance_real_regression():
    case=json.loads(gzip.decompress(Path('tests/fixtures/n7_sleeve_numerical.json.gz').read_bytes()))
    e=case['enumeration'];cuts={s:Cutoff.decision_epoch(e['issue'],t) for s,t in e['cutoffs'].items()}
    settings={**case['parameters'],'solver_seconds':10.,'solver_relative_gap':.001,'solver_feasibility_tolerance':1e-9}
    selected=select_sleeve_states(e,cutoffs=cuts,**settings)
    assert selected['status']=='COMPLETE'
    assert len(selected['state_ids'])==64
    assert selected['coverage']>=settings['minimum_coverage']-1e-8
    assert selected['expected_roi']>=settings['minimum_roi']-1e-8


def test_full_state_cardinality_probability_value_and_constraints():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for i in range(7)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    e=enumerate_sleeve(f,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    assert len(e['states'])==len(set(map(tuple,e['states'])))==2187
    assert sum(e['probability'])==pytest.approx(1)
    assert e['probability'][0]==pytest.approx(.6**7)
    assert e['estimated_payout'][0]==pytest.approx(2*.65/.5**7)
    args=dict(cutoffs=cuts,ticket_count=64,minimum_coverage=None,minimum_roi=None,seed=1,hamming_minimum=2,solver_seconds=10.,solver_relative_gap=.001,solver_feasibility_tolerance=1e-9)
    prob=select_sleeve_states(e,kind='TOP64_PROB',**args)
    value=select_sleeve_states(e,kind='TOP64_VALUE',**args)
    for kind in ('TOP64_PROB','TOP64_VALUE','RANDOM64','DIVERSITY'):
        a=select_sleeve_states(e,kind=kind,**args)
        assert len(set(a['state_ids']))==64 and a['coverage']<=prob['coverage']+1e-10
        assert a['expected_gross']<=value['expected_gross']+1e-8
        if kind=='DIVERSITY':assert a['minimum_hamming']>=2
    frontier=select_sleeve_states(e,kind='FRONTIER',**{**args,'minimum_coverage':prob['coverage']*.8,'minimum_roi':-.35})
    assert frontier['status']=='COMPLETE' and frontier['coverage']>=prob['coverage']*.8-1e-8
    assert frontier['expected_roi']>=-.35-1e-8
    impossible=select_sleeve_states(e,kind='FRONTIER',**{**args,'minimum_coverage':1.,'minimum_roi':0.})
    assert impossible['status']=='INFEASIBLE' and impossible['state_ids']==[]
    with pytest.raises(ValueError):enumerate_sleeve(f.iloc[:6],cutoffs=cuts,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):select_sleeve_states(e,kind='TOP64_PROB',**{**args,'minimum_roi':0.})
    with pytest.raises(ValueError):select_sleeve_states(e,kind='TOP64_PROB',**{**args,'cutoffs':{}})
