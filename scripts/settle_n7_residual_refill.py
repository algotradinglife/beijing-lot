#!/usr/bin/env python3
"""Freeze the five-arm comparison, then independently settle residual additions."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.temporal_learning import implementation_closure, verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.n7_residual_comparison import assemble_residual_predictions
from src.n7_residual_check import check_locked_groups
from src.n7_sp_refill_check import check_refill_prefixes
from src.n7_sp_refill_settlement import settle_refill_plans
from src.n7_rank_diagnostic import load_rank_issue
from src.n7_residual_sources import verify_refill_sources,verify_paired_audit

p=argparse.ArgumentParser()
for name in ['residual','reference','audit-study','output']:
    p.add_argument('--'+name,required=True,type=Path)
a=p.parse_args();root=Path(__file__).resolve().parents[1]
if a.output.exists():raise ValueError('Output already exists')
res=json.loads((a.residual/'prediction-freeze.json').read_text())
ref=json.loads((a.reference/'plans-frozen.json').read_text())
for name,sha in res['files'].items():
    if hashlib.sha256((a.residual/name).read_bytes()).hexdigest()!=sha:raise ValueError('Residual input changed')
for path,sha in res['input_hashes'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Original funded source changed')
for path,sha in ref['files'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Reference prediction changed')
reference=pd.read_csv(a.reference/'predictions.csv',dtype={'issue':str})
additions=pd.read_csv(a.residual/'predictions.csv',dtype={'issue':str})
affected=sorted(additions.issue.unique());issues=sorted(reference.issue.unique())
predictions=assemble_residual_predictions(reference,additions,issue_order=issues,affected_issues=affected)
if len(predictions)!=81000 or len(issues)!=200:raise ValueError('Fixed experiment scope mismatch')
plans=[]
refill_directory=Path(res['config']['refill_dir'])
verify_refill_sources(refill_directory,res['input_hashes'][str(refill_directory/'prediction-freeze.json')])
funded=pd.read_csv(Path(res['config']['control_dir'])/'funded.csv',dtype={'issue':str,'sleeve_id':str}).to_dict('records')
for path in sorted(a.residual.glob('*-plans.json')):
    key=path.name.removesuffix('-plans.json')
    bundle=json.loads((Path(res['config']['refill_dir'])/(key+'-bundle.json')).read_text())
    ledger=json.loads((Path(res['config']['refill_dir'])/(key+'-candidates.json')).read_text())
    ids=[g['sleeve_id'] for g in ledger['groups'] if g['origin']=='REFILL_TOP2']
    for plan in json.loads(path.read_text()):
        plan['seal']=stable_json_hash(plan)
        check_locked_groups(plan,funded,new_group_ids=ids,cutoffs=bundle['cutoffs'])
        check_refill_prefixes(plan,bundle,minimum_sp=1.3,unit_cny=2,payout_factor=.65)
        plans.append(plan)
closure=implementation_closure(root,['scripts.settle_n7_residual_refill'],distributions=['numpy','pandas'])
a.output.mkdir(parents=True)
predictions.to_csv(a.output/'predictions.csv',index=False)
(a.output/'residual-plans.json').write_text(json.dumps(plans,allow_nan=False))
source_paths=[a.residual/'prediction-freeze.json',a.reference/'plans-frozen.json']
freeze=dict(affected_issues=affected,issues=issues,historical_admission=False,labels_loaded=False,
    implementation=closure,
    input_hashes={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in source_paths},
    files={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in
      [a.output/'predictions.csv',a.output/'residual-plans.json']})
(a.output/'plans-frozen.json').write_text(json.dumps(freeze,indent=2))
# Outcomes are read only after all five arms and 200 issues are frozen.
inputs=[a.reference/'results.csv',a.reference/'evaluation-receipt.json',
 a.audit_study/'audit-snapshot.json',a.audit_study/'plans-frozen.json',a.audit_study/'evaluation-receipt.json']
input_hashes={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in inputs}
receipt=json.loads((a.reference/'evaluation-receipt.json').read_text())
verify_paired_audit(a.audit_study,receipt)
if (receipt['results_sha256']!=input_hashes[str(a.reference/'results.csv')] or
 receipt['freeze_sha256']!=freeze['input_hashes'][str(a.reference/'plans-frozen.json')]):
    raise ValueError('Reference settlement/freeze mismatch')
results=pd.read_csv(a.reference/'results.csv',dtype={'issue':str})
settled=[]
for issue in affected:
    audit=json.loads(load_rank_issue(a.audit_study,issue))['audit']
    settled.extend(settle_refill_plans([plan for plan in plans if plan['issue']==issue],audit))
actual=pd.DataFrame(settled)
new=additions.merge(actual[['issue','arm','seed','gross','net','hits']],on=['issue','arm','seed'],validate='one_to_one')
combined=assemble_residual_predictions(results,new,issue_order=issues,affected_issues=affected)
if combined[['gross','net','hits']].isna().any().any():raise ValueError('Unsettled comparison')
combined.to_csv(a.output/'results.csv',index=False)
verify_implementation_closure(root,closure)
verify_refill_sources(refill_directory,res['input_hashes'][str(refill_directory/'prediction-freeze.json')])
for path,sha in input_hashes.items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Settlement input changed')
receipt=dict(status='PASS',rows=len(combined),independent_locked_prefix_settlement_checks=len(plans),
    input_hashes=input_hashes,implementation=closure,
    freeze_sha256=hashlib.sha256((a.output/'plans-frozen.json').read_bytes()).hexdigest(),
    results_sha256=hashlib.sha256((a.output/'results.csv').read_bytes()).hexdigest())
(a.output/'evaluation-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:receipt[k] for k in ['status','rows','independent_locked_prefix_settlement_checks','results_sha256']}))
