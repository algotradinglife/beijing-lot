import copy
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_single_guard import guard_single_positions
from src.temporal_learning.core import stable_json_hash


def test_single_guard_keeps_control_and_enforces_conflict_and_cap():
 f=pd.DataFrame([dict(issue='001',slot=i,provider_id=f'{i:03}',handicap=0,p_W=.6,p_D=.25,p_L=.15,q_W=.5,q_D=.3,q_L=.2) for i in range(1,29)])
 cuts={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
 p=n7_single_plan(f,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
 old=copy.deepcopy(p)
 base=guard_single_positions(p,cutoffs=cuts,protect_conflict=False,minimum_tv=.15,single_cap=None)
 assert base['tickets']==p['tickets'] and base['stake']==p['stake'] and p==old
 for cap in [2,3]:
  z=guard_single_positions(p,cutoffs=cuts,protect_conflict=True,minimum_tv=.15,single_cap=cap)
  assert max(Counter((r['slot'],r['support']) for r in z['legs'] if len(r['support'])==1).values())<=cap
  assert all(sum(len(r['support'])==1 for r in z['legs'] if r['group']==g)==2 for g in range(1,z['groups']+1))
 bad=copy.deepcopy(p);bad.pop('seal')
 for r in bad['legs']:r.update(q_W=.1,q_D=.8,q_L=.1)
 bad['seal']=stable_json_hash(bad)
 z=guard_single_positions(bad,cutoffs=cuts,protect_conflict=True,minimum_tv=.15,single_cap=2)
 assert z['groups']==0 and z['stake']==0 and z['cash_cny']==1024
 assert all(r['conflict'] and not r['funded'] for r in z['guard_ledger'])
 with pytest.raises(ValueError):guard_single_positions(p,cutoffs=cuts,protect_conflict=True,minimum_tv=.15,single_cap=0)
 with pytest.raises(ValueError):guard_single_positions(dict(p,seal='bad'),cutoffs=cuts,protect_conflict=True,minimum_tv=.15,single_cap=2)


def test_cap_relocates_singles_after_two_uses():
 f=pd.DataFrame([dict(issue='001',slot=i,provider_id=f'{i:03}',handicap=0,p_W=.7-i*.002,p_D=.2+i*.001,p_L=.1+i*.001,q_W=.5,q_D=.3,q_L=.2) for i in range(1,15)])
 cuts={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
 p=n7_single_plan(f,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
 ls=[r for r in p['legs'] if r['group']==1];ts=[t for t in p['tickets'] if t['group']==1]
 p.pop('seal');p.update(groups=6,legs=[dict(r,group=g) for g in range(1,7) for r in ls],tickets=[dict(t,group=g) for g in range(1,7) for t in ts],stake=384,cash_cny=640);p['seal']=stable_json_hash(p)
 z=guard_single_positions(p,cutoffs=cuts,protect_conflict=False,minimum_tv=.15,single_cap=2)
 first={r['slot'] for r in z['legs'] if r['group']==1 and len(r['support'])==1}
 third={r['slot'] for r in z['legs'] if r['group']==3 and len(r['support'])==1}
 assert first.isdisjoint(third) and z['groups']==6
 assert max(Counter(r['slot'] for r in z['legs'] if len(r['support'])==1).values())==2
 assert any(r['capped'] for r in z['guard_ledger'])
