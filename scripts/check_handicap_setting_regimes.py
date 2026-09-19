"""Independent read-only arithmetic replay of descriptive regime tables."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

receipt_path = Path(sys.argv[1])
r = json.loads(receipt_path.read_text())
c = r['config']; out = receipt_path.parent; root = Path(c['repository_root'])
for name, sha in r['files'].items():
    assert hashlib.sha256((out/name).read_bytes()).hexdigest() == sha
for name, sha in r['code'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == sha
assert hashlib.sha256(Path(c['input']).read_bytes()).hexdigest() == c['input_sha256']
assert hashlib.sha256(Path(c['manifest']).read_bytes()).hexdigest() == c['manifest_sha256']
x = pd.read_csv(out/'regime-fixtures.csv', dtype={'issue':str,'provider_id':str,'year':str})
assert len(x) == r['fixtures'] and x.issue.nunique() == r['issues']
assert not x.duplicated(['issue','slot','provider_id']).any()
assert (np.select([x.actual_home-x.actual_away+x.handicap>0,x.actual_home-x.actual_away+x.handicap==0],['W','D'],default='L') == x.actual_direction).all()
raw = pd.DataFrame(json.loads(Path(c['input']).read_text())['rows'])
keys=['issue','slot','provider_id']; raw=raw.set_index(keys).sort_index(); ordered=x.set_index(keys).sort_index()
assert raw.index.equals(ordered.index)
for col in ['handicap','p_W','p_D','p_L','q_W','q_D','q_L','odds_W','odds_D','odds_L','lambda_home','lambda_away']:
    assert np.allclose(raw[col].astype(float), ordered[col].astype(float),equal_nan=True)
labels=[]
m=json.loads(Path(c['manifest']).read_text())
for source in m['labels']:
    p=Path(source['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==source['sha256']
    labels.append(pd.read_csv(p,dtype={'issue':str,'provider_id':str}))
l=pd.concat(labels).set_index(keys);assert not l.index.duplicated().any();l=l.loc[ordered.index]
for col in ['handicap','actual_home','actual_away','spf_sp']:
    assert np.allclose(l[col],ordered[col])
assert (l.actual_direction==ordered.actual_direction).all()
for source,sha in r['sources'].items():
    assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==sha
annual=pd.read_csv(out/'regime-annual.csv',dtype={'year':str})
for a in annual.itertuples():
    z=x[x.year==a.year];assert len(z)==a.fixtures and z.issue.nunique()==a.issues
    assert abs((z.handicap==0).mean()-a.zero_share)<1e-12
standard=pd.read_csv(out/'regime-standardized.csv',dtype={'year':str})
# Rebuild bins, common support and weights independently from raw numbers.
inv=1/x[['odds_W','odds_D','odds_L']].to_numpy();euro=inv/inv.sum(axis=1,keepdims=True)
for j,d in enumerate('WDL'):assert np.allclose(x['euro_'+d],euro[:,j])
strength_bin=pd.cut(euro[:,0]-euro[:,2],c['strength_breaks'],include_lowest=True,labels=False)
total_bin=pd.cut(x.lambda_home+x.lambda_away,c['total_breaks']+[np.inf],include_lowest=True,labels=False)
x['replay_cell']=pd.Series(strength_bin).astype(str)+'/'+total_bin.astype(str)
complete=x[x.year.isin(c['complete_years']) & total_bin.notna()]
n=complete.groupby(['replay_cell','year']).size().unstack(fill_value=0)
common=n.index[(n>=c['minimum_support']).all(axis=1)]
common_rows=complete[complete.replay_cell.isin(common)]
w=common_rows.groupby('replay_cell').size();w=w/w.sum()
for a in standard.itertuples():
    z=common_rows[common_rows.year==a.year];rates=z.assign(zero=(z.handicap==0).astype(float)).groupby('replay_cell').zero.mean()
    assert len(rates)==a.common_cells and abs(float((rates*w).sum())-a.standard_zero)<1e-12
strong=pd.read_csv(out/'regime-strength-standardized.csv',dtype={'year':str})
xx=x[x.year.isin(['2010','2011','2012','2013','2014'])].copy()
xx['sb']=pd.cut(xx.euro_W-xx.euro_L,c['strength_breaks'],include_lowest=True,labels=False)
counts=xx.groupby(['sb','year']).size().unstack(fill_value=0)
valid=counts.index[(counts>=c['minimum_support']).all(axis=1)]
xx=xx[xx.sb.isin(valid)];weights=xx.groupby('sb').size();weights=weights/weights.sum()
for a in strong.itertuples():
    rates=xx[xx.year==a.year].assign(zero=lambda t:(t.handicap==0).astype(float)).groupby('sb').zero.mean()
    assert abs(float((weights*rates).sum())-a.standard_zero)<1e-12
scores=pd.read_csv(out/'regime-scores.csv',dtype={'year':str})
for a in scores.itertuples():
    z=x[(x.year==a.year)&(x.handicap==a.handicap)];p=z[['p_W','p_D','p_L']].to_numpy()
    if a.model=='RAW_MAPPING':p=z[['q_W','q_D','q_L']].to_numpy()
    elif a.model=='ZERO_EURO' and a.handicap==0:p=z[['euro_W','euro_D','euro_L']].to_numpy()
    y=(z.actual_direction.to_numpy()[:,None]==np.array(list('WDL'))).astype(float)
    assert abs(((p-y)**2).sum(axis=1).mean()-a.brier)<1e-12
    assert abs(-np.log((p*y).sum(axis=1)).mean()-a.log_loss)<1e-12
print(f'PASS: {len(x)} records / {x.issue.nunique()} issues; identities, labels, sources, common-support weights and all Brier/log-loss cells independently replayed')
