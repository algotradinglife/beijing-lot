from copy import deepcopy
import pytest
from src.temporal_learning.core import stable_json_hash
from src.n7_residual_check import check_locked_groups


def test_original_groups_cannot_be_displaced_or_resized():
    rows=[dict(issue='001',arm='OLD',seed=1,sleeve_id='0',depth=2,copies=1,stake=4)]
    cuts={'a':'epoch'}
    p=dict(issue='001',original_arm='OLD',seed=1,cutoffs=cuts,locked_sleeve_ids=[0],
      sleeve_keys=[dict(sleeve_id=0,depth=2,stake=4),dict(sleeve_id=9,depth=1,stake=2)],
      stake=6,cash_cny=2,budget_cny=8)
    p['seal']=stable_json_hash(p)
    assert check_locked_groups(p,rows,new_group_ids=[9],cutoffs=cuts)['added_stake']==2
    bad=deepcopy(p);bad.pop('seal');bad['sleeve_keys'][0]['depth']=1;bad['seal']=stable_json_hash(bad)
    with pytest.raises(ValueError,match='resized'):check_locked_groups(bad,rows,new_group_ids=[9],cutoffs=cuts)
    with pytest.raises(ValueError,match='new refill'):check_locked_groups(p,rows,new_group_ids=[],cutoffs=cuts)
    with pytest.raises(ValueError):check_locked_groups(p,rows,new_group_ids=[9],cutoffs={})
