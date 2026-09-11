import collections
import itertools
import pandas as pd
from src.temporal_learning import Cutoff
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio


def test_budget_bound_reuse_is_nonbinding_and_fills_32_groups():
    rows=[]
    for s in range(1,11):
        p,q=([.7,.2,.1],[.7,.2,.1]) if s<3 else ([.4,.35,.25],[.4,.35,.25])
        if s==10:p,q=[.6,.3,.1],[.4,.2,.4]
        rows.append(dict(issue='001',slot=s,provider_id=str(s),handicap=1,
            **dict(zip(['p_W','p_D','p_L'],p)),**dict(zip(['q_W','q_D','q_L'],q))))
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for s in range(1,11)}
    plan=independent_consensus_portfolio(pd.DataFrame(rows),cutoffs=cuts,
        conversion_budget_fraction=0,budget_cny=1024,minimum_anchor_market=.5,
        max_uses=1024//32,max_pair_overlap=5,unit_cny=2,payout_factor=.65,seed=0,group_size=6)
    assert len(plan['components'])==32 and plan['stake']==1024 and plan['cash_cny']==0
    holdings=collections.Counter(r['slot'] for c in plan['components'] for r in c['legs'])
    assert holdings[1]==32 and holdings[2]==32
    sets=[set(r['slot'] for r in c['legs']) for c in plan['components']]
    assert all(len(a&b)<=5 for a,b in itertools.combinations(sets,2))
    assert all(len(c['tickets'])==16 and c['stake']==32 for c in plan['components'])
