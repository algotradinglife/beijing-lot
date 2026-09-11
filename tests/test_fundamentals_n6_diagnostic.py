import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_compression_breadth import breadth_candidates,settle_breadth_bundle
from src.fundamentals_n6_diagnostic import n6_diagnostic_plan


def test_n6_whole_tickets_reuse_and_authoritative_payout():
 f=pd.DataFrame([dict(issue='001',slot=i,provider_id=f'{i:03}',handicap=0,p_W=.6,p_D=.25,p_L=.15,q_W=.5,q_D=.3,q_L=.2) for i in range(1,37)])
 c={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
 pool=breadth_candidates(f,cutoffs=c,seed=41900,pool_size=128)
 for depth in [1,2]:
  kw=dict(cutoffs=c,depth=depth,budget_cny=1024,unit_cny=2,payout_factor=.65,max_uses=6,max_pair_overlap=5)
  p=n6_diagnostic_plan(f,pool,**kw)
  assert p==n6_diagnostic_plan(f,pool,**kw)
  assert p['stake']+p['cash_cny']==1024 and p['stake']==p['groups']*2*2**(6-depth)
  counts=Counter(r['slot'] for r in p['legs']);assert max(counts.values())<=6
  sets=[]
  for i in range(1,p['groups']+1):
   ls=[r for r in p['legs'] if r['group']==i];sets.append({r['slot'] for r in ls})
   assert len(ls)==6 and sum(len(r['support'])==1 for r in ls)==depth
  assert all(len(a&b)<=5 for a,b in itertools.combinations(sets,2))
  audit=f[['issue','slot','provider_id','handicap']].assign(status='READY',actual_direction='W',spf_sp=2.)
  settled=settle_breadth_bundle({'n6':{'plan':p}},audit)['n6']
  assert settled['gross']==pytest.approx(p['groups']*2*.65*2**6)
  with pytest.raises(ValueError):n6_diagnostic_plan(f,pool,**dict(kw,budget_cny=2048))
  with pytest.raises(ValueError):n6_diagnostic_plan(f,pool,**dict(kw,max_pair_overlap=6))
  bad=dict(pool,seal='bad')
  with pytest.raises(ValueError):n6_diagnostic_plan(f,bad,**kw)
