import copy
import numpy as np
import pytest
from src.n7_expanded_pool_check import verify_expanded_pool


@pytest.mark.parametrize('mode',['BREADTH','DEPTH'])
def test_complete_pool_and_low_sp_exclusion(mode):
    c={'1':'2011-01-01T00:00:00Z'}
    fixtures=[dict(p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for _ in range(7)]
    bundle=dict(cutoffs=c,expanded_pool=dict(fixtures=fixtures),sleeves=[dict(id=0)])
    surface={0:dict(mass=np.r_[0,.3,.6,.9,np.ones(2184)],f=np.arange(7))}
    cfg=dict(targets=.25,cap_cny=256,max_copies=1,depth_reference_targets=[.25,.30],depths=[2,4])
    policy=dict(mode=mode,minimum_sp=1.3)
    depths=[1] if mode=='BREADTH' else [1,2,4]
    snap=dict(cutoffs=c,mode=mode,opening_options=[1],opportunity_options=[],
              options=[dict(sleeve_id=0,depth=d,role='CORE',rule='PROB_PREFIX',unit_copies=1) for d in depths])
    assert verify_expanded_pool(snap,bundle,surface,c,cfg,policy)
    missing=copy.deepcopy(snap);missing['options'].pop()
    with pytest.raises(ValueError,match='option pool'):verify_expanded_pool(missing,bundle,surface,c,cfg,policy)
    for f in fixtures:f.update(q_W=.9,q_D=.05,q_L=.05)
    with pytest.raises(ValueError,match='option pool'):verify_expanded_pool(snap,bundle,surface,c,cfg,policy)
    snap.update(options=[],opening_options=[])
    assert verify_expanded_pool(snap,bundle,surface,c,cfg,policy)
    with pytest.raises(ValueError):verify_expanded_pool(snap,bundle,surface,{},cfg,policy)


def test_no_affordable_coverage_does_not_open_group():
    c={'1':'2011-01-01T00:00:00Z'}
    bundle=dict(cutoffs=c,expanded_pool=dict(fixtures=[dict(p_W=.4,p_D=.3,p_L=.3,q_W=.4,q_D=.3,q_L=.3)]*7),sleeves=[dict(id=0)])
    surface={0:dict(mass=np.linspace(0,1,2188),f=np.arange(7))}
    cfg=dict(targets=.25,cap_cny=256,max_copies=1,depth_reference_targets=[.25,.30],depths=[15,32,64,128])
    snap=dict(cutoffs=c,mode='BREADTH',options=[],opening_options=[],opportunity_options=[])
    assert verify_expanded_pool(snap,bundle,surface,c,cfg,dict(mode='BREADTH',minimum_sp=1.3))
