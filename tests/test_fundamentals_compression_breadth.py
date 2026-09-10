import copy
import itertools
import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_compression_breadth import breadth_candidates,compression_surface,breadth_scenarios,compression_breadth_plan,breadth_metrics
from src.fundamentals_n7_single import settle_n7_single


@pytest.fixture(scope='module')
def source():
 f=pd.DataFrame([dict(issue='100101',slot=i,provider_id=str(i),handicap=0,p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for i in range(1,15)])
 c={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in f.slot};pool=breadth_candidates(f,cutoffs=c,seed=0,pool_size=128)
 return f,c,pool


@pytest.mark.parametrize('depth',[0,1,2,3])
@pytest.mark.parametrize('rule',['TOP1','RETENTION','ABS_LOSS','VALUE_RETENTION','RANDOM'])
def test_full_depth_rules_and_breadth(source,depth,rule):
 f,c,pool=source;surface=compression_surface(f,pool,cutoffs=c,depth=depth,rule=rule,seed=0);design=breadth_scenarios(f,surface,cutoffs=c,seed=101,draws=256);evaluation=breadth_scenarios(f,surface,cutoffs=c,seed=102,draws=4096)
 for breadth in ['REPEAT','QUALITY','UNION','RANDOM']:
  plan=compression_breadth_plan(f,surface,design,cutoffs=c,breadth=breadth,seed=0,budget_cny=512,quality_pool_size=64,unit_cny=2,payout_factor=.65)
  assert plan['stake']==512 and plan['paid_ticket_units']==256 and plan['cash_cny']==0
  assert plan['unique_tickets']==256//2**depth if breadth=='REPEAT' else plan['unique_tickets']==256
  identities=set()
  for g in range(1,plan['groups']+1):
   legs=[r for r in plan['legs'] if r['group']==g];ts=[t for t in plan['tickets'] if t['group']==g]
   assert sum(len(r['support'])==1 for r in legs)==depth
   assert len(ts)==2**(7-depth)
   assert {t['code'] for t in ts}=={''.join(z) for z in itertools.product(*(r['support'] for r in legs))}
   for t in ts:
    key=tuple((r['slot'],z) for r,z in zip(legs,t['code']));assert key not in identities;identities.add(key)
  m=breadth_metrics(plan,evaluation,cutoffs=c);assert 0<=m['model_union']<=1 and 0<m['fixture_hhi']<=1
  if breadth=='REPEAT':
   mass=.6**depth*.9**(7-depth);exact=1-(1-mass)**2
   assert abs(m['model_union']-exact)<.04
  audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY');r=settle_n7_single(plan,audit)
  assert r['gross']==pytest.approx(2*.65*2**7*2*2**depth)
  audit['spf_sp']=999;assert compression_breadth_plan(f,surface,design,cutoffs=c,breadth=breadth,seed=0,budget_cny=512,quality_pool_size=64,unit_cny=2,payout_factor=.65)==plan


def test_probability_rules_and_invalid_inputs(source):
 f,c,pool=source;s=compression_surface(f,pool,cutoffs=c,depth=2,rule='RETENTION',seed=0)
 assert s['mass'][0]==pytest.approx(.6**2*.9**5)
 assert s['ledger'][0][0]['retention']==pytest.approx(2/3)
 d=breadth_scenarios(f,s,cutoffs=c,seed=1,draws=256)
 kw=dict(cutoffs=c,breadth='UNION',seed=0,budget_cny=512,quality_pool_size=64,unit_cny=2,payout_factor=.65)
 p=compression_breadth_plan(f,s,d,**kw)
 with pytest.raises(ValueError):breadth_metrics(p,d,cutoffs=c)
 bad=copy.deepcopy(s);bad['mass'][0]=1
 with pytest.raises(ValueError):breadth_scenarios(f,bad,cutoffs=c,seed=2,draws=256)
 with pytest.raises(ValueError):compression_breadth_plan(f,s,d,**dict(kw,budget_cny=1024))
 with pytest.raises(ValueError):compression_breadth_plan(f,s,d,**dict(kw,quality_pool_size=1))
 with pytest.raises(ValueError):compression_surface(f,pool,cutoffs=c,depth=4,rule='RETENTION',seed=0)
 with pytest.raises(ValueError):breadth_candidates(f,cutoffs={},seed=0,pool_size=128)
 with pytest.raises(ValueError):breadth_candidates(f,cutoffs=c,seed=0,pool_size=1)
 with pytest.raises(ValueError):breadth_scenarios(f,s,cutoffs=c,seed=0,draws=0)


def test_report_fixture_restore_and_tamper(tmp_path):
 import base64,gzip,hashlib,json,subprocess,sys
 from pathlib import Path
 # Small synthetic archive exercises the storage contract without full research.
 files={n:b'{}' for n in ['plans-frozen.json','results.json','report-inputs.json']};files['legs.json.gz']=gzip.compress(b'[]',mtime=0)
 obj=dict(files={n:base64.b64encode(b).decode() for n,b in files.items()},hashes={n:hashlib.sha256(b).hexdigest() for n,b in files.items()});archive=tmp_path/'fixture.gz';archive.write_bytes(gzip.compress(json.dumps(obj).encode()))
 cmd=[sys.executable,'scripts/restore_compression_breadth_fixture.py','--fixture',str(archive),'--output',str(tmp_path/'restored')]
 subprocess.run(cmd,check=True)
 for n,b in files.items():assert (tmp_path/'restored'/n).read_bytes()==b
 assert subprocess.run(cmd,capture_output=True).returncode!=0
 obj['hashes']['results.json']='0'*64;archive.write_bytes(gzip.compress(json.dumps(obj).encode()));cmd[-1]=str(tmp_path/'tampered');assert subprocess.run(cmd,capture_output=True).returncode!=0
 assert not (tmp_path/'tampered').exists()


def test_cutoff_and_scenario_metadata_are_immutable(source):
 from src.temporal_learning.core import stable_json_hash
 f,c,pool=source;s=compression_surface(f,pool,cutoffs=c,depth=2,rule='TOP1',seed=0)
 d=breadth_scenarios(f,s,cutoffs=c,seed=101,draws=256);e=breadth_scenarios(f,s,cutoffs=c,seed=102,draws=256)
 kw=dict(cutoffs=c,breadth='UNION',seed=0,budget_cny=512,quality_pool_size=64,unit_cny=2,payout_factor=.65)
 p=compression_breadth_plan(f,s,d,**kw)
 old={slot:Cutoff.decision_epoch('100101','2009-01-01T00:00:00Z') for slot in c}
 with pytest.raises(ValueError,match='cutoff'):compression_surface(f,pool,cutoffs=old,depth=2,rule='TOP1',seed=0)
 with pytest.raises(ValueError,match='cutoff'):breadth_scenarios(f,s,cutoffs=old,seed=102,draws=256)
 with pytest.raises(ValueError,match='cutoff'):compression_breadth_plan(f,s,d,**dict(kw,cutoffs=old))
 for field,value in [('seed',102),('draws',128),('shape',[128,128])]:
  fake=dict(d,**{field:value})
  with pytest.raises(ValueError,match='metadata'):breadth_metrics(p,fake,cutoffs=c)
  with pytest.raises(ValueError,match='metadata'):compression_breadth_plan(f,s,fake,**kw)
 fake=dict(e,draws=128);fake['seal']=stable_json_hash({k:v for k,v in fake.items() if k not in {'hits','seal'}})
 with pytest.raises(ValueError,match='dimensions'):breadth_metrics(p,fake,cutoffs=c)
 fake=copy.deepcopy(e);fake['hits'][0,0]=not fake['hits'][0,0]
 with pytest.raises(ValueError,match='bytes'):breadth_metrics(p,fake,cutoffs=c)


def test_batch_settlement_is_equivalent_and_audit_local(source):
 from src.fundamentals_compression_breadth import settle_breadth_bundle
 f,c,pool=source;s=compression_surface(f,pool,cutoffs=c,depth=2,rule='TOP1',seed=0);d=breadth_scenarios(f,s,cutoffs=c,seed=101,draws=256)
 bundle={b:dict(plan=compression_breadth_plan(f,s,d,cutoffs=c,breadth=b,seed=0,budget_cny=512,quality_pool_size=64,unit_cny=2,payout_factor=.65)) for b in ['REPEAT','QUALITY','UNION','RANDOM']}
 original=copy.deepcopy(bundle);audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
 result=settle_breadth_bundle(bundle,audit)
 for k,v in bundle.items():assert result[k]==settle_n7_single(v['plan'],audit)
 audit.loc[0,'spf_sp']=np.nan;pending=settle_breadth_bundle(bundle,audit)
 for k,v in bundle.items():assert pending[k]==settle_n7_single(v['plan'],audit)
 audit['actual_direction']='L';loss=settle_breadth_bundle(bundle,audit)
 assert all(v['net']==-512 for v in loss.values());assert original==bundle
 bad=copy.deepcopy(bundle);bad['REPEAT']['plan']['stake']+=2
 with pytest.raises(ValueError,match='changed'):settle_breadth_bundle(bad,audit)
