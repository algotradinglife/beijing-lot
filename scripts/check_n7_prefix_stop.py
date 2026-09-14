#!/usr/bin/env python3
"""Independent byte, prefix, actual-state, and accounting replay for #451."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.n7_union_inputs import verify_union_binding
from src.n7_prefix_validation import verify_summary_grid

p=argparse.ArgumentParser()
for name in ('predictions','study','repository'):
    p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
freeze=json.loads((a.predictions/'prediction-freeze.json').read_text())
evaluation=json.loads((a.study/'evaluation-receipt.json').read_text())
cfg=freeze['config']
for directory,receipt in ((a.predictions,freeze),(a.study,evaluation)):
    for name,sha in receipt['files'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==sha,('file drift',name)
    for path,sha in receipt['input_hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,('input drift',path)
    for path,sha in receipt['implementation'].items():
        assert hashlib.sha256((a.repository/path).read_bytes()).hexdigest()==sha,('code drift',path)
verify_union_binding(freeze['input_binding'],cfg['catalog'],cfg['rank_dir'],a.repository)
rank_receipt=json.loads((Path(cfg['rank_dir'])/'receipt.json').read_text())
audits={}
for source in rank_receipt['sources']:
    root=Path(source['study'])
    raw=(root/'plans-frozen.json').read_bytes();eraw=(root/'evaluation-receipt.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==source['freeze_sha256']
    assert hashlib.sha256(eraw).hexdigest()==source['evaluation_sha256']
    e=json.loads(eraw);araw=(root/'audit-snapshot.json').read_bytes()
    assert hashlib.sha256(araw).hexdigest()==e['audit_sha256']
    owned_issues=set(json.loads(raw)['receipt']['issues'])
    for row in json.loads(araw)['rows']:
        if str(row['issue']) not in owned_issues:
            continue
        key=str(row['issue']),str(row['slot']),str(row['provider_id'])
        assert key not in audits
        audits[key]=row
original=pd.read_csv(Path(cfg['control_dir'])/'funded.csv',dtype={'issue':str,'sleeve_id':str})
original=original[original.arm.str.contains('_SP130_')]
plans=pd.read_csv(a.predictions/'funded.csv',dtype={'issue':str,'sleeve_id':str})
curves={};actual={}
for item in json.loads(Path(cfg['catalog']).read_text())['issues']:
    raw=Path(item['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
    b=json.loads(gzip.decompress(raw));issue=item['issue']
    assert b['cutoffs']==freeze['cutoffs'][issue]
    for g in b['sleeves']:
        key=issue,str(g['id']);en=g['enumeration']
        prob=np.asarray(en['probability']);value=np.asarray(en['expected_contribution'])
        order=np.lexsort((np.arange(2187),-value,-prob))
        mass=np.r_[0,prob[order].cumsum()];gross=np.r_[0,value[order].cumsum()]
        curves[key]=mass,gross
        state=0;payout=1.3
        for f in en['fixtures']:
            audit=audits[(issue,str(f['slot']),str(f['provider_id']))]
            assert f['handicap']==audit['handicap'] and audit['spf_sp']>0
            state=3*state+('W','D','L').index(audit['actual_direction'])
            payout*=audit['spf_sp']
        actual[key]=(int(np.flatnonzero(order==state)[0])+1,payout)
assert len(curves)==4800
expected=[]
for row in original.to_dict('records'):
    mass,gross=curves[(row['issue'],row['sleeve_id'])]
    assert np.isclose(row['coverage'],mass[row['depth']],atol=1e-10)
    assert np.isclose(row['expected_gross'],gross[row['depth']]*row['copies'],atol=1e-7)
    for rule in cfg['rules']:
        mode=rule['mode'];v=rule['value'];old=row['depth']
        target=old if mode=='original' else v if mode=='cap' else max(1,int(np.floor(old*v))) if mode=='fraction' else int(np.flatnonzero(mass>=v-1e-12)[0])
        depth=min(old,target)
        expected.append(dict(issue=row['issue'],arm=row['arm'],seed=row['seed'],sleeve_id=row['sleeve_id'],
          variant=rule['variant'],depth=depth,stake=depth*2*row['copies'],coverage=mass[depth],
          expected_gross=gross[depth]*row['copies']))
expected=pd.DataFrame(expected);keys=['issue','arm','seed','sleeve_id','variant']
pd.testing.assert_frame_equal(expected.sort_values(keys).reset_index(drop=True),
  plans[expected.columns].sort_values(keys).reset_index(drop=True),check_dtype=False,atol=1e-7,rtol=1e-10)
groups=pd.read_csv(a.study/'groups.csv',dtype={'issue':str,'sleeve_id':str})
rank=np.array([actual[(r.issue,r.sleeve_id)][0] for r in groups.itertuples()])
payout=np.array([actual[(r.issue,r.sleeve_id)][1] for r in groups.itertuples()])
assert np.array_equal(rank,groups.actual_rank)
assert np.allclose(payout,groups.actual_gross_cny,rtol=1e-10,atol=1e-6)
assert np.allclose(np.where(rank<=groups.depth,payout*groups.copies,0),groups.gross,rtol=1e-10,atol=1e-6)
bands=pd.read_csv(a.study/'bands.csv',dtype={'issue':str,'sleeve_id':str})
band_totals=bands.groupby(['issue','arm','seed','sleeve_id']).agg(stake=('band_stake','sum'),gross=('band_gross','sum'),expected_gross=('band_expected_gross','sum'),coverage=('band_coverage','sum')).reset_index()
base=groups[groups.variant=='FILTER_ONLY']
joined_bands=base.merge(band_totals,on=['issue','arm','seed','sleeve_id'],validate='one_to_one',suffixes=('','_bands'))
assert len(joined_bands)==len(base)
for name in ('stake','gross','coverage','expected_gross'):
    assert np.allclose(joined_bands[name],joined_bands[name+'_bands'],rtol=1e-10,atol=1e-6)
for row in bands.itertuples():
    mass,gross=curves[(row.issue,row.sleeve_id)];rank,payout=actual[(row.issue,row.sleeve_id)]
    assert np.isclose(row.band_stake,2*(row.depth-row.lower_depth)*row.copies)
    assert np.isclose(row.band_coverage,mass[row.depth]-mass[row.lower_depth],atol=1e-10)
    assert np.isclose(row.band_expected_gross,(gross[row.depth]-gross[row.lower_depth])*row.copies,atol=1e-6)
    assert np.isclose(row.band_gross,payout*row.copies if row.lower_depth<rank<=row.depth else 0,atol=1e-6)
rows=pd.read_csv(a.study/'results.csv',dtype={'issue':str})
totals=groups.groupby(['issue','arm','seed','variant']).agg(stake=('stake','sum'),gross=('gross','sum'),hits=('hit','sum')).reset_index().rename(columns={'arm':'original_arm'})
joined=rows.merge(totals,on=['issue','original_arm','seed','variant'],how='left',validate='one_to_one',suffixes=('','_check'))
for name in ('stake','gross','hits'):
    assert np.allclose(joined[name],joined[name+'_check'].fillna(0),rtol=1e-10,atol=1e-6)
assert np.allclose(rows.net,rows.gross-rows.stake) and np.allclose(rows.cash,rows.budget_cny-rows.stake)
assert len(rows)==129600
summary=pd.read_csv(a.study/'report-summary.csv')
assert len(rows[['arm','seed']].drop_duplicates())==648
verify_summary_grid(rows,summary)
for row in summary.to_dict('records'):
    x=rows[(rows.arm==row['arm'])&(rows.seed==row['seed'])].sort_values('issue')
    assert x.issue.nunique()==200
    net=x.net.to_numpy();equity=np.r_[100000,100000+net.cumsum()]
    expected=dict(stake=x.stake.sum(),net=net.sum(),roi=net.sum()/x.stake.sum(),
      hit_issues=(x.hits>0).sum(),profit_issues=(net>0).sum(),cash=x.cash.sum(),
      max_drawdown=(np.maximum.accumulate(equity)-equity).max(),
      net_without_best=net.sum()-np.sort(net)[-1],net_without_best3=net.sum()-np.sort(net)[-3:].sum(),
      net_without_best5=net.sum()-np.sort(net)[-5:].sum())
    for name,value in expected.items():assert np.isclose(row[name],value,rtol=1e-10,atol=1e-6),name
out=dict(status='PASS',candidate_states_checked=len(curves),prefixes=len(plans),rows=len(rows),summaries=len(summary),
  results_sha256=hashlib.sha256((a.study/'results.csv').read_bytes()).hexdigest())
(a.study/'independent-check.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
