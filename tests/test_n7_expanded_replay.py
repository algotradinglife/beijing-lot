import pytest
from src.n7_expanded_replay import replay_open_first


@pytest.mark.parametrize('objective',['any_hit','coverage_sum','expected_net'])
def test_open_first_replay(objective):
    cut={'1':'2011-01-01T00:00:00Z'}
    options=[dict(sleeve_id=1,stake=2,expected_gross=3,coverage=.6,unit_copies=1,role='CORE',depth=1),
             dict(sleeve_id=1,stake=4,expected_gross=5,coverage=.9,unit_copies=1,role='CORE',depth=2),
             dict(sleeve_id=2,stake=2,expected_gross=2,coverage=.4,unit_copies=1,role='CORE',depth=1)]
    x=dict(cutoffs=cut,mode='BREADTH',options=options,opening_options=[1,3],opportunity_options=[],
           train=dict(cutoffs=cut,hits=[[1,1,0],[0,1,1]]))
    assert replay_open_first(x,cut,6,objective)==[1,3]
    x['mode']='DEPTH'
    assert replay_open_first(x,cut,6,objective)==[3,2]
    assert replay_open_first(x,cut,0,objective)==[]
    with pytest.raises(ValueError):replay_open_first(x,{},6,objective)
    with pytest.raises(ValueError):replay_open_first(x,cut,3,objective)
    x['train']['hits']=[[2,1,0]]
    with pytest.raises(ValueError):replay_open_first(x,cut,6,objective)


def test_empty_and_invalid_options():
    c={'1':'2011-01-01T00:00:00Z'}
    x=dict(cutoffs=c,mode='BREADTH',options=[],opening_options=[],opportunity_options=[],
           train=dict(cutoffs=c,hits=[[],[]]))
    assert replay_open_first(x,c,1024,'any_hit')==[]
    x['opening_options']=[1]
    with pytest.raises(ValueError):replay_open_first(x,c,1024,'any_hit')
