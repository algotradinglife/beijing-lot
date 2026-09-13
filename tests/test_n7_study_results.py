"""Batch joins retain every period, arm and seed without inventing outcomes."""
from copy import deepcopy
import pytest
from src.n7_study_results import combine_n7_study_results
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def parts():
    output=[]
    for issue in ['002','001']:
        for arm in ['control','core']:
            receipt=dict(issues=[issue],parameters=dict(seeds=[1],arms=[arm]),historical_admission=False)
            seal=stable_json_hash(receipt)
            row=dict(issue=issue,seed=1,arm=arm,status='COMPLETE',stake=2,gross=4,net=2,roi=1,hits=1)
            if issue=='002':
                row.update(status='NOT_EVALUABLE',reason='NOT_PUBLISHED',stake=None,gross=None,net=None,roi=None,hits=None)
            output.append(dict(freeze=dict(receipt=receipt,seal=seal),result=dict(rows=[row],
                issue_order=[issue],freeze_seal=seal,historical_admission=False)))
    return output


def test_combine_exact_grid_preserves_unavailable_and_financial_rows(parts):
    before=deepcopy(parts)
    result=combine_n7_study_results(parts,issue_order=['001','002'],seeds=[1],arms=['control','core'])
    assert [r['issue'] for r in result['rows']]==['001','001','002','002']
    assert result['rows'][0]['net']==2
    assert result['rows'][2]['net'] is None and result['rows'][2]['reason']=='NOT_PUBLISHED'
    assert parts==before


def test_combine_rejects_missing_duplicate_changed_or_zero_filled_results(parts):
    kwargs=dict(issue_order=['001','002'],seeds=[1],arms=['control','core'])
    with pytest.raises(ValueError,match='exact requested'):combine_n7_study_results(parts[:-1],**kwargs)
    with pytest.raises(ValueError,match='Duplicate'):combine_n7_study_results(parts+[parts[0]],**kwargs)
    changed=deepcopy(parts);changed[0]['result']['freeze_seal']='wrong'
    with pytest.raises(ValueError,match='identity'):combine_n7_study_results(changed,**kwargs)
    changed=deepcopy(parts);changed[0]['result']['rows'][0]['net']=0
    with pytest.raises(ValueError,match='null financial'):combine_n7_study_results(changed,**kwargs)
    changed=deepcopy(parts);changed[0]['result']['rows']=[]
    with pytest.raises(ValueError,match='Incomplete'):combine_n7_study_results(changed,**kwargs)
