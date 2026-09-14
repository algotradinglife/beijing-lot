#!/usr/bin/env python3
"""Check refill replay/prefixes and independently recompute report summaries."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.temporal_learning import verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.n7_sp_refill_check import check_refill_prefixes

p=argparse.ArgumentParser()
p.add_argument('--refill',required=True,type=Path)
p.add_argument('--replay',required=True,type=Path)
p.add_argument('--comparison',required=True,type=Path)
p.add_argument('--repository',required=True,type=Path)
a=p.parse_args()
evaluation=json.loads((a.comparison/'evaluation-receipt.json').read_text())
for name,field in [('results.csv','results_sha256'),('plans-frozen.json','freeze_sha256')]:
    if hashlib.sha256((a.comparison/name).read_bytes()).hexdigest()!=evaluation[field]:
        raise ValueError('Comparison output binding changed: '+name)
verify_implementation_closure(a.repository,evaluation['settlement_implementation'])
for path,sha in evaluation['settlement_inputs'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Settlement input changed')
freeze=json.loads((a.refill/'prediction-freeze.json').read_text())
verify_implementation_closure(a.repository,freeze['python_implementation'])
for name,sha in freeze['files'].items():
    if hashlib.sha256((a.refill/name).read_bytes()).hexdigest()!=sha:raise ValueError('Refill artifact changed')
for name,sha in freeze['implementation'].items():
    if hashlib.sha256((a.repository/name).read_bytes()).hexdigest()!=sha:raise ValueError('R implementation changed')
count=0
for path in sorted(a.refill.glob('*-plans.json')):
    plans=json.loads(path.read_text())
    if plans!=json.loads((a.replay/path.name).read_text()):raise ValueError('Allocation replay differs')
    bundle=json.loads(path.with_name(path.name.replace('-plans.json','-bundle.json')).read_text())
    for plan in plans:
        plan['seal']=stable_json_hash(plan)
        check_refill_prefixes(plan,bundle,minimum_sp=1.3,unit_cny=2,payout_factor=.65)
        count+=1
rows=pd.read_csv(a.comparison/'results.csv',dtype={'issue':str})
summary=pd.read_csv(a.comparison/'report-summary.csv')
if len(rows)!=48600 or len(summary)!=243 or count!=162:raise ValueError('Incomplete comparison')
for row in summary.to_dict('records'):
    frame=rows[(rows.arm==row['arm'])&(rows.seed==row['seed'])].sort_values('issue')
    if len(frame)!=200 or frame.issue.nunique()!=200:raise ValueError('Incomplete issue grid')
    net=frame.net.to_numpy();stake=frame.stake.sum();equity=np.r_[100000,100000+net.cumsum()]
    streak=best=0
    for value in net:
        streak=streak+1 if value<0 else 0;best=max(best,streak)
    expected=dict(stake=stake,net=net.sum(),roi=net.sum()/stake,hit_issues=(frame.hits>0).sum(),
      profit_issues=(net>0).sum(),cash=frame.cash.sum(),max_drawdown=(np.maximum.accumulate(equity)-equity).max(),
      longest_loss_streak=best,net_without_best=net.sum()-np.sort(net)[-1],
      net_without_best3=net.sum()-np.sort(net)[-3:].sum(),net_without_best5=net.sum()-np.sort(net)[-5:].sum())
    for field,value in expected.items():
        if not np.isclose(row[field],value,rtol=1e-10,atol=1e-6):raise ValueError(f'Summary mismatch {field}')
receipt=dict(status='PASS',allocation_replays=count,independent_prefix_checks=count,
    report_summaries=len(summary),result_rows=len(rows),
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    source_files={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in
      [a.refill/'prediction-freeze.json',a.replay/'prediction-freeze.json',
       a.comparison/'results.csv',a.comparison/'report-summary.csv']})
(a.comparison/'independent-check.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
