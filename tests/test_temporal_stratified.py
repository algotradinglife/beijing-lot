import json
import pandas as pd
import pytest
from pathlib import Path
from src.n7_risk_context import n7_risk_context
from src.temporal_learning.core import Cutoff
from src.temporal_learning.stratified import stratified_context_json, stratified_contexts_json


def test_sparse_cell_support_and_component_mass_are_independent_of_global_ess():
    history=pd.DataFrame([dict(issue_code=str(i),last_fixture_cutoff=t.isoformat(),
        hit_residual=0,depth_residual=0) for i,t in enumerate(pd.date_range('2010-01-01',periods=100,tz='UTC'))])
    cutoff=Cutoff.decision_epoch('target','2011-01-01')
    ctx=n7_risk_context(history,cutoff,repository_root=Path(__file__).resolve().parents[1],
        source_hashes={'input':'a'*64},delay_hours=48,window_issues=20,recent_blend=.5,minimum_ess=20)
    membership=[dict(issue_code=str(i),cell='sparse') for i in [*range(29),99]]
    membership += [dict(issue_code=str(i),cell='dense') for i in range(100)]
    result=json.loads(stratified_context_json(json.dumps(ctx),json.dumps(membership),minimum_ess=20,minimum_recent_ess=5))
    rows={s['cell']:s for s in result['strata']}
    assert rows['sparse']['status']=='UNKNOWN'
    assert rows['dense']['status']=='READY'
    for row in rows.values():
        assert row['alpha']==pytest.approx(.5)
        assert sum(r['long_weight'] for r in row['rows'])==pytest.approx(1)
        assert sum(r['recent_weight'] for r in row['rows'])==pytest.approx(1)
    changed=membership+[dict(issue_code='target',cell='dense'),dict(issue_code='future',cell='dense')]
    mutated=json.loads(stratified_context_json(json.dumps(ctx),json.dumps(changed),minimum_ess=20,minimum_recent_ess=5))
    assert result['strata']==mutated['strata']
    batch=json.loads(stratified_contexts_json(json.dumps([ctx]),json.dumps(membership),
        minimum_ess=20,minimum_recent_ess=5))
    assert batch==[result]
    with pytest.raises(ValueError):
        stratified_contexts_json(json.dumps(ctx),json.dumps(membership),minimum_ess=20,minimum_recent_ess=5)
    ctx['receipt']['cutoff_identity']='wrong'
    with pytest.raises(ValueError):
        stratified_context_json(json.dumps(ctx),json.dumps(membership),minimum_ess=20,minimum_recent_ess=5)
