import copy,itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_rescue_shapes import MODES,rescue_shape_plan

@pytest.fixture
def source():
 f=pd.DataFrame([dict(issue='001',slot=i,provider_id=f'{i:03}',handicap=0,p_W=.65-i*.002,p_D=.25,p_L=.1+i*.002,q_W=.2,q_D=.3,q_L=.5) for i in range(1,29)])
 cuts={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
 p=n7_single_plan(f,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
 return p,cuts

@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('weight',[0,.5,1])
def test_shapes_complete_budget_and_decision_mass(source,mode,weight):
 p,cuts=source;old=copy.deepcopy(p)
 z=rescue_shape_plan(p,cutoffs=cuts,market_weight=weight,mode=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
 assert p==old and z['stake']<=1024 and z['stake']+z['cash_cny']==1024
 assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
 for g in range(1,z['groups']+1):
  ls=[r for r in z['legs'] if r['group']==g];ts=[t for t in z['tickets'] if t['group']==g]
  assert len(ls)==(6 if mode.startswith('N6') else 7)
  assert {t['code'] for t in ts}=={''.join(c) for c in itertools.product(*(r['support'] for r in ls))}
  for r in ls:
   assert r['decision_probabilities']==[(1-weight)*r['p_'+d]+weight*r['q_'+d] for d in 'WDL']
   if weight==1:assert '0' in r['support']
 if mode=='N7_C2_TOP1' and weight==0:assert z['tickets']==p['tickets']
 if mode=='N7_C0':assert all(len(r['support'])==2 for r in z['legs'])
 if mode=='N7_C2_RETENTION_CAP2':assert max(Counter((r['slot'],r['support']) for r in z['legs'] if len(r['support'])==1).values())<=2


def test_retention_transfers_compression_and_rejects_bad_inputs(source):
 p,cuts=source;p=copy.deepcopy(p);p.pop('seal')
 first=[r['slot'] for r in p['legs'] if r['group']==1]
 for r in p['legs']:
  if r['slot']==first[0]:r.update(p_W=.7,p_D=.29,p_L=.01)
  if r['slot']==first[-1]:r.update(p_W=.6,p_D=.21,p_L=.19)
 p['seal']=stable_json_hash(p)
 args=dict(cutoffs=cuts,market_weight=0,budget_cny=1024,unit_cny=2,payout_factor=.65)
 a=rescue_shape_plan(p,mode='N7_C2_TOP1',**args);b=rescue_shape_plan(p,mode='N7_C2_RETENTION',**args)
 assert a['ledger'][0]['single_slots']!=b['ledger'][0]['single_slots']
 for bad in [dict(mode='BAD'),dict(mode='N7_C0',market_weight=.1),dict(mode='N7_C0',budget_cny=1025),dict(mode='N7_C0',cutoffs={})]:
  with pytest.raises(ValueError):rescue_shape_plan(p,**{**args,**bad})
 with pytest.raises(ValueError):rescue_shape_plan(dict(p,seal='bad'),mode='N7_C0',**args)


def test_caps_transfer_funded_singles_and_budget_skips(source):
 p,cuts=source;unique={r['slot']:r for r in p['legs']};p=copy.deepcopy(p);p.pop('seal');legs=[];tickets=[]
 for g in range(1,5):
  group=[1,2]+list(range(3+(g-1)*5,8+(g-1)*5));current=[]
  for i in group:
   r=dict(unique[i],group=g,p_W=.8 if i<=2 else .6,p_D=.15 if i<=2 else .25,p_L=.05 if i<=2 else .15)
   r['support']='3' if i<=2 else '31';current.append(r)
  legs.extend(current);tickets.extend(dict(group=g,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in current)))
 p.update(groups=4,legs=legs,tickets=tickets,stake=256,cash_cny=768);p['seal']=stable_json_hash(p)
 z=rescue_shape_plan(p,cutoffs=cuts,market_weight=0,mode='N7_C2_RETENTION_CAP2',budget_cny=1024,unit_cny=2,payout_factor=.65)
 assert z['groups']==4 and z['ledger'][0]['single_slots']==[1,2] and set(z['ledger'][2]['single_slots']).isdisjoint({1,2})
 assert max(Counter((r['slot'],r['support']) for r in z['legs'] if len(r['support'])==1).values())==2
 # An additional distinct all-double group must be held as cash, not partly funded.
 p.pop('seal');p['groups']=5;p['legs'].extend(dict(unique[i],group=5,p_W=.8 if i<=2 else .6,p_D=.15 if i<=2 else .25,p_L=.05 if i<=2 else .15) for i in [1,2,23,24,25,26,27]);p['tickets'].extend(dict(t,group=5) for t in tickets[-32:]);p['stake']=320;p['cash_cny']=704;p['seal']=stable_json_hash(p)
 z=rescue_shape_plan(p,cutoffs=cuts,market_weight=0,mode='N7_C0',budget_cny=1024,unit_cny=2,payout_factor=.65)
 assert z['groups']==4 and z['stake']==1024 and z['ledger'][-1]['reason']=='BUDGET'
