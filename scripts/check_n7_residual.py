#!/usr/bin/env python3
"""Read-only replay and independent accounting checks for the fixed five arms."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.temporal_learning import verify_implementation_closure

p=argparse.ArgumentParser()
for name in ['study','predictions','replay','reference','repository']:
    p.add_argument('--'+name,required=True,type=Path)
a=p.parse_args()
receipt=json.loads((a.study/'evaluation-receipt.json').read_text())
for file,field in [('plans-frozen.json','freeze_sha256'),('results.csv','results_sha256')]:
    if hashlib.sha256((a.study/file).read_bytes()).hexdigest()!=receipt[field]:raise ValueError('Evaluation output changed')
verify_implementation_closure(a.repository,receipt['implementation'])
for path,sha in receipt['input_hashes'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Settlement input changed')
freeze=json.loads((a.predictions/'prediction-freeze.json').read_text())
verify_implementation_closure(a.repository,freeze['python_implementation'])
for name,sha in freeze['implementation'].items():
    if hashlib.sha256((a.repository/name).read_bytes()).hexdigest()!=sha:raise ValueError('R implementation changed')
for name,sha in freeze['files'].items():
    if hashlib.sha256((a.predictions/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen prediction changed')
replays=0
for path in sorted(a.predictions.glob('*-plans.json')):
    plans=json.loads(path.read_text())
    if plans!=json.loads((a.replay/path.name).read_text()):raise ValueError('Residual replay changed')
    replays+=len(plans)
rows=pd.read_csv(a.study/'results.csv',dtype={'issue':str})
reference=pd.read_csv(a.reference/'results.csv',dtype={'issue':str})
keys=['issue','arm','seed']
controls=reference[reference.variant.isin(['FILTER_ONLY','REFILL'])]
actual=rows[rows.variant.isin(['FILTER_ONLY','REFILL'])]
pd.testing.assert_frame_equal(controls.sort_values(keys).reset_index(drop=True),
    actual[controls.columns].sort_values(keys).reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-9)
unchanged_rows=0
for variant in ['STANDALONE','INCREMENTAL','EFFICIENCY_GATE']:
    expected=reference[(reference.variant=='FILTER_ONLY')&~reference.issue.isin(['100608','100711'])].copy()
    expected['variant']=variant;expected['arm']=expected.arm.str.replace('_SP130_',f'_{variant}_',regex=False)
    actual=rows[(rows.variant==variant)&~rows.issue.isin(['100608','100711'])]
    unchanged_rows+=len(actual)
    pd.testing.assert_frame_equal(expected.sort_values(keys).reset_index(drop=True),
        actual[expected.columns].sort_values(keys).reset_index(drop=True),check_dtype=False,rtol=1e-12,atol=1e-9)
summary=pd.read_csv(a.study/'report-summary.csv')
if len(summary)!=405 or len(rows)!=81000 or replays!=486:raise ValueError('Experiment grid mismatch')
for row in summary.to_dict('records'):
    x=rows[(rows.arm==row['arm'])&(rows.seed==row['seed'])].sort_values('issue')
    if len(x)!=200 or x.issue.nunique()!=200:raise ValueError('Issue grid mismatch')
    net=x.net.to_numpy();stake=x.stake.sum();equity=np.r_[100000,100000+net.cumsum()]
    streak=longest=0
    for n in net:streak=streak+1 if n<0 else 0;longest=max(longest,streak)
    expected=dict(net=net.sum(),stake=stake,cash=x.cash.sum(),roi=net.sum()/stake,
      hit_issues=(x.hits>0).sum(),profit_issues=(net>0).sum(),
      max_drawdown=(np.maximum.accumulate(equity)-equity).max(),longest_loss_streak=longest,
      net_without_best=net.sum()-np.sort(net)[-1],net_without_best3=net.sum()-np.sort(net)[-3:].sum(),
      net_without_best5=net.sum()-np.sort(net)[-5:].sum())
    for k,v in expected.items():
        if not np.isclose(row[k],v,rtol=1e-10,atol=1e-6):raise ValueError('Summary mismatch: '+k)
efficiency=pd.read_csv(a.study/'report-efficiency.csv')
if len(efficiency)!=243:raise ValueError('Efficiency grid mismatch')
for row in efficiency.to_dict('records'):
    x=rows[(rows.arm==row['arm'])&(rows.seed==row['seed'])]
    stake=x.added_stake.sum();gain=x.added_eval_union.sum()
    status='NO_ADDITION' if stake==0 else ('SPENT_WITHOUT_EVAL_GAIN' if gain==0 else 'POSITIVE_EVAL_GAIN')
    if status!=row['efficiency_status']:raise ValueError('Efficiency status mismatch')
    expected=dict(added_stake=stake,added_expected_hit_periods=gain,
      added_issues=(x.added_stake>0).sum(),
      spent_zero_gain_issues=((x.added_stake>0)&(x.added_eval_union==0)).sum(),
      cny_per_expected_extra_hit_period=stake/gain if gain>0 else np.nan,
      cny_per_summed_coverage_pp=stake/(100*gain) if gain>0 else np.nan)
    for k,v in expected.items():
        if not np.isclose(row[k],v,rtol=1e-10,atol=1e-6,equal_nan=True):raise ValueError('Efficiency mismatch: '+k)
out=dict(status='PASS',rows=len(rows),summaries=len(summary),allocation_replays=replays,
    paired_efficiency_checks=len(efficiency),
    control_rows=len(controls),unchanged_rows=unchanged_rows,
    results_sha256=receipt['results_sha256'],summary_sha256=hashlib.sha256((a.study/'report-summary.csv').read_bytes()).hexdigest())
(a.study/'independent-check.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out))
