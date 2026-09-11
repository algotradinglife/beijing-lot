import copy
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_missed_portfolio import drop_weak_leg,fixed_n67_wallets,settle_missed_portfolio


def test_drop_and_wallets_use_prematch_support_and_complete_units():
 f=pd.DataFrame([dict(issue='001',slot=i,provider_id=f'{i:03}',handicap=0,p_W=.6,p_D=.25,p_L=.15,q_W=.5,q_D=.3,q_L=.2) for i in range(1,29)])
 c={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
 p=n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
 before=copy.deepcopy(p);d=drop_weak_leg(p,cutoffs=c)
 assert p==before and all(len(r['support'])==1 for r in d['removed'])
 assert all(sum(len(r['support'])==1 for r in d['legs'] if r['group']==g)==1 for g in range(1,d['groups']+1))
 for wallets in [dict(N7=512,N6=512),dict(N7=1024,N6=0),dict(N7=0,N6=1024)]:
  q=fixed_n67_wallets(dict(N7=p,N6=d),cutoffs=c,wallets=wallets,budget_cny=1024,unit_cny=2,payout_factor=.65)
  assert q['stake']+q['cash_cny']==1024
  for name in wallets:assert sum(x['plan']['stake'] for x in q['components'] if x['source']==name)<=wallets[name]
  a=f[['issue','slot','provider_id','handicap']].assign(status='READY',actual_direction='W',spf_sp=2.)
  r=settle_missed_portfolio(q,a)
  assert r['gross']==pytest.approx(sum(2*.65*2**x['n'] for x in q['components']))
  assert r['hits']==len(q['components'])
  bad=copy.deepcopy(q);bad['stake']+=2
  with pytest.raises(ValueError):settle_missed_portfolio(bad,a)
  with pytest.raises(ValueError):settle_missed_portfolio(q,a.iloc[:0])
 with pytest.raises(ValueError):fixed_n67_wallets(dict(N7=p),cutoffs=c,wallets=dict(N7=512),budget_cny=1024,unit_cny=2,payout_factor=.65)
 bad=copy.deepcopy(p);bad['seal']='bad'
 with pytest.raises(ValueError):drop_weak_leg(bad,cutoffs=c)
