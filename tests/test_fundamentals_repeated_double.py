import copy,itertools,math
import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,settle_breadth_bundle
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_n7_diversity import replace_repeated_double_tail,evaluate_fixed_supports


@pytest.fixture(scope='module')
def source():
 f=pd.DataFrame([dict(issue='100101',slot=i,provider_id=str(i),handicap=0,p_W=.57+.006*i,p_D=.28-.003*i,p_L=.15-.003*i,q_W=.5,q_D=.3,q_L=.2) for i in range(1,22)])
 c={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in f.slot}
 refs={d:n7_single_plan(f,cutoffs=c,budget_cny=512,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in (1,2)}
 pool=breadth_candidates(f,cutoffs=c,seed=41900,pool_size=128);plans={}
 for d in (1,2):
  s=bridge_surface(f,pool,refs,cutoffs=c,depth=d);design=breadth_scenarios(f,s,cutoffs=c,seed=41901,draws=128)
  plans[d]=bridge_plan(f,s,design,refs[d],cutoffs=c,preserve_prefix=True,quality='COMPRESSED',overlap='FREE',cash_policy='HOLD',budget_cny=512,unit_cny=2,payout_factor=.65)
 return f,c,plans


@pytest.mark.parametrize('depth',[1,2])
def test_repeated_double_semantics_and_actual_scenarios(source,depth):
 f,c,plans=source;b=plans[depth];original=copy.deepcopy(b);p=replace_repeated_double_tail(b,cutoffs=c)
 assert b==original
 for k in ['stake','budget_cny','cash_cny','groups','group_units','single_count','cutoffs','input_sha256']:assert p[k]==b[k]
 assert 'surface_seal' not in p and 'selected_candidates' not in p
 seen={};changed=0;third=0
 for g in range(1,p['groups']+1):
  before=sorted([l for l in b['legs'] if l['group']==g],key=lambda r:r['slot']);after=sorted([l for l in p['legs'] if l['group']==g],key=lambda r:r['slot'])
  for a,z in zip(before,after):
   prior=seen.get(a['slot'],0);expected='30' if prior and len(a['support'])==2 else a['support']
   assert z==dict(a,support=expected);changed+=a['support']!=expected;third+=prior>=2 and len(a['support'])==2;seen[a['slot']]=prior+1
  codes={''.join(z) for z in itertools.product(*(l['support'] for l in after))};ts=[t for t in p['tickets'] if t['group']==g]
  assert len(codes)==len(ts)==2**(7-depth) and codes=={t['code'] for t in ts}
 assert changed>0 and sum(l['changed'] for l in p['diversity_ledger'])==changed
 if depth==2:assert third>0
 assert all(new<=old+1e-14 for new,old in zip(p['group_probability'],b['group_probability']))
 e=evaluate_fixed_supports(f,p,cutoffs=c,seed=41902,draws=4096)
 # Independent direct Monte Carlo on actual digits, shared fixture per draw.
 probs=f[['p_W','p_D','p_L']].to_numpy();u=np.random.default_rng(41902).random((len(f),4096));direction=(u>=probs[:,0,None]).astype(int)+(u>=(probs[:,0]+probs[:,1])[:,None]).astype(int);codes=np.array(list('310'))[direction];hits=[]
 for g in range(1,p['groups']+1):
  legs=[l for l in p['legs'] if l['group']==g];hits.append(np.all([np.isin(codes[l['slot']-1],list(l['support'])) for l in legs],axis=0))
 assert e['metrics']['model_union']==np.any(hits,axis=0).mean()
 assert e['receipt']['plan_seal']==p['seal']
 audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
 settled=settle_breadth_bundle({'p':{'plan':p}},audit)['p'];assert settled['gross']==pytest.approx(p['groups']*2*.65*2**7)
 audit.actual_direction='L';assert settle_breadth_bundle({'p':{'plan':p}},audit)['p']['gross']==0
 assert replace_repeated_double_tail(b,cutoffs=c)==p


def test_units_ties_and_failure_contracts(source):
 f,c,plans=source;b=copy.deepcopy(plans[2])
 for t in b['tickets']:
  if t['group']==1:t['units']=3
 b['stake']=sum(t['units']*2 for t in b['tickets']);b['budget_cny']=b['stake']+b['cash_cny'];b['seal']=stable_json_hash({k:v for k,v in b.items() if k!='seal'})
 p=replace_repeated_double_tail(b,cutoffs=c);assert [t['units'] for t in p['tickets']]==[t['units'] for t in b['tickets']]
 assert p['group_units'][0]==3
 with pytest.raises(ValueError):replace_repeated_double_tail(p,cutoffs=c)
 early={k:Cutoff.decision_epoch('100101','2009-01-01T00:00:00Z') for k in c}
 with pytest.raises(ValueError):replace_repeated_double_tail(b,cutoffs=early)
 with pytest.raises(ValueError):evaluate_fixed_supports(f,p,cutoffs=early,seed=41902,draws=128)
 with pytest.raises(ValueError):evaluate_fixed_supports(f,p,cutoffs=c,seed=41901,draws=128)
 bad=copy.deepcopy(b);bad['tickets'][0]['units']=0;bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
 with pytest.raises(ValueError):replace_repeated_double_tail(bad,cutoffs=c)
 bad=copy.deepcopy(b);bad['budget_cny']+=2;bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
 with pytest.raises(ValueError):replace_repeated_double_tail(bad,cutoffs=c)
 bad=copy.deepcopy(b);bad['legs'][0]['p_W']=float('nan');bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
 with pytest.raises(ValueError):replace_repeated_double_tail(bad,cutoffs=c)
 changed=f.copy();changed['p_W']+=.01;changed['p_D']-=.01
 with pytest.raises(ValueError):evaluate_fixed_supports(changed,p,cutoffs=c,seed=41902,draws=128)
 # Equal probabilities keep W on singles, W+D first use, W+L later doubles.
 tied=copy.deepcopy(plans[2])
 for r in tied['legs']:r.update(p_W=1/3,p_D=1/3,p_L=1/3)
 tied['seal']=stable_json_hash({k:v for k,v in tied.items() if k!='seal'})
 q=replace_repeated_double_tail(tied,cutoffs=c)
 assert all(l['selected_support']=='30' for l in q['diversity_ledger'] if l['changed'])


@pytest.mark.parametrize('depth',[1,2])
def test_conditional_gap_filter_and_boundaries(source,depth):
 f,c,plans=source;b=copy.deepcopy(plans[depth])
 for r in b['legs']:
  r.update(p_W=.6,p_D=.2+.003*r['slot'],p_L=.2-.003*r['slot'])
 b['seal']=stable_json_hash({k:v for k,v in b.items() if k!='seal'})
 changed=[]
 for threshold in [0,.02,.05,.10,1]:
  p=replace_repeated_double_tail(b,cutoffs=c,max_gap=threshold)
  keys=set()
  for l in p['diversity_ledger']:
   eligible=l['prior_appearances']>0 and len(l['source_support'])==2 and l['second_third_gap']<=threshold+1e-12
   assert l['changed']==eligible
   if eligible:keys.add((l['group'],l['slot']))
  changed.append(keys)
  assert p['max_gap']==threshold
  for k in ['stake','cash_cny','budget_cny','groups','single_count','group_units']:assert p[k]==b[k]
 assert not changed[0] and changed[-1]
 assert all(a<=z for a,z in zip(changed,changed[1:]))
 assert any(a<z for a,z in zip(changed,changed[1:]))
 # Original fixture probabilities have a 13-point second/third gap.
 original=plans[depth]
 boundary=replace_repeated_double_tail(original,cutoffs=c,max_gap=.13)
 assert boundary['tickets']==replace_repeated_double_tail(original,cutoffs=c)['tickets']
 below=replace_repeated_double_tail(original,cutoffs=c,max_gap=.13-1e-9)
 assert below['tickets']==original['tickets']
 assert evaluate_fixed_supports(f,below,cutoffs=c,seed=41902,draws=128)['metrics']==evaluate_fixed_supports(f,original,cutoffs=c,seed=41902,draws=128)['metrics']
 tied=copy.deepcopy(original)
 for r in tied['legs']:r.update(p_W=.6,p_D=.2,p_L=.2)
 tied['seal']=stable_json_hash({k:v for k,v in tied.items() if k!='seal'})
 assert any(l['changed'] for l in replace_repeated_double_tail(tied,cutoffs=c,max_gap=0)['diversity_ledger'])
 for invalid in [-.1,1.1,float('nan'),float('inf'),True,None,'0.05']:
  with pytest.raises(ValueError):replace_repeated_double_tail(original,cutoffs=c,max_gap=invalid)
