"""Independent descriptive support and category-table check; no learning."""
import json,math,sys,hashlib
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 root=Path('data/derived/fundamentals_417/category-diagnostics-v1')
 seal=json.loads((root/'plans-frozen.json').read_text());assert hashlib.sha256(seal['canonical_json'].encode()).hexdigest()==seal['seal'];receipt=json.loads(seal['canonical_json'])
 verify_clean_file_bindings({**receipt['source_hashes'],**receipt['report_files']},repository_root=Path.cwd());verify_implementation_closure(Path.cwd(),receipt['implementation'])
 assert hashlib.sha256((root/'results.json').read_bytes()).hexdigest()==receipt['result_sha256']
 data=json.loads((root/'results.json').read_text());assert data['upstream_freeze_seal']==receipt['plan_freeze_seal']
 factors={(r['issue'],r['slot'],r['provider_id']):r for r in data['factors']};audit={(r['issue'],r['slot'],r['provider_id']):r for r in data['audit']}
 features={(r['issue'],r['slot'],r['provider_id']):r for r in data['features']};states={r['issue']:r['hits'] for r in data['rows']}
 hypothetical=[];held=[];group_errors={}
 for key,f in factors.items():
  order=sorted(range(3),key=lambda j:(-f['p_'+'WDL'[j]],j))
  for n in [1,2]:hypothetical.append(dict(**f,support=''.join('310'[j] for j in range(3) if j in order[:n]),one_away_blocker=False))
 for leg in data['legs']:
  key=tuple(leg[k] for k in ['issue','slot','provider_id']);f=factors[key]
  assert all(leg[c]==f[c] for c in ['handicap','p_W','p_D','p_L','q_W','q_D','q_L'])
  hit=dict(W='3',D='1',L='0')[audit[key]['actual_direction']] in leg['support'];g=(leg['issue'],leg['group'])
  group_errors[g]=group_errors.get(g,0)+int(not hit);held.append(dict(**leg,hit=hit))
 for r in held:r['one_away_blocker']=not r['hit'] and group_errors[r['issue'],r['group']]==1
 unique={}
 for r in held:unique.setdefault((r['issue'],r['slot'],r['provider_id'],r['support']),dict(r,one_away_blocker=False))
 records=[]
 for view,rows in [('ALL_AVAILABLE',hypothetical),('SELECTED_UNIQUE',list(unique.values())),('HOLDINGS',held)]:
  for row in rows:
   key=tuple(row[k] for k in ['issue','slot','provider_id']);f=factors[key];a=audit[key];feature=features[key];p=[f['p_'+d] for d in 'WDL'];q=[f['q_'+d] for d in 'WDL']
   assert a['status']=='READY' and a['handicap']==f['handicap']
   competition=feature['competition'];family='FRIENDLY' if '友谊' in competition else 'PLAYOFF' if '附' in competition else 'OTHER_CUP_FLAG' if feature['cup']==1 else 'OTHER_CUP_ZERO'
   conflict='AGREE' if np.argmax(p)==np.argmax(q) else 'STRONG_DIFF' if sum(abs(x-y) for x,y in zip(p,q))/2>=.15 else 'MILD_DIFF'
   item=dict(issue=row['issue'],view=view,role='SINGLE' if len(row['support'])==1 else 'DOUBLE',conflict=conflict,depth=str(min(abs(f['handicap']),2)),league=competition.strip(),family=family,history_n=str(min(feature['home_venue_n'],feature['away_venue_n'])),
    hit=dict(W='3',D='1',L='0')[a['actual_direction']] in row['support'],predicted=sum(p['310'.index(c)] for c in row['support']),market=sum(q['310'.index(c)] for c in row['support']),one_away_blocker=row['one_away_blocker'])
   for period in ['ALL48','MISS25' if states[row['issue']]==0 else 'HIT23']:records.append(dict(item,slice=period))
 x=pd.DataFrame(records);saved=pd.read_csv(root/'summary.csv',dtype={'stratum':str})
 checked=0
 for dim in ['conflict','depth','league','family','history_n']:
  groups=x.groupby(['view','slice','role',dim])
  expected=groups.agg(n=('hit','size'),issues=('issue','nunique'),hits=('hit','sum'),actual_percent=('hit','mean'),predicted_percent=('predicted','mean'),market_percent=('market','mean'),one_away_blockers=('one_away_blocker','sum'))
  expected[['actual_percent','predicted_percent','market_percent']]*=100
  actual=saved[saved.dimension==dim].set_index(['view','slice','role','stratum'])
  assert set(actual.index)==set(expected.index)
  for key,row in expected.iterrows():
   for col,v in row.items():assert math.isclose(v,actual.loc[key,col],abs_tol=1e-8),(dim,key,col)
   checked+=1
 print('PASS',checked,'independent strata: all/unique/holdings,48/25/23,roles,probability means,one-away attribution')
