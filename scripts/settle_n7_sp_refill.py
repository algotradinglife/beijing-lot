#!/usr/bin/env python3
"""Assemble the fixed three-arm freeze, then evaluate rebuilt physical tickets."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning import implementation_closure, verify_implementation_closure
from src.n7_rank_diagnostic import load_rank_issue
from src.n7_sp_refill_settlement import settle_refill_plans

parser=argparse.ArgumentParser()
parser.add_argument('--refill',required=True,type=Path)
parser.add_argument('--control',required=True,type=Path)
parser.add_argument('--audit-study',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
repository=Path(__file__).resolve().parents[1]
settlement_implementation=implementation_closure(repository,
    ['scripts.settle_n7_sp_refill','src.n7_sp_refill_settlement'],distributions=['numpy','pandas'])
if args.output.exists():raise ValueError('Output already exists')
bindings={}
for root,freeze_name in [(args.refill,'prediction-freeze.json'),(args.control,'plans-frozen.json')]:
    freeze=json.loads((root/freeze_name).read_text())
    bindings[str(root/freeze_name)]=hashlib.sha256((root/freeze_name).read_bytes()).hexdigest()
    for name,expected in freeze['files'].items():
        path=root/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('Prediction binding changed')
        bindings[str(path)]=expected
refill_freeze=json.loads((args.refill/'prediction-freeze.json').read_text())
control=pd.read_csv(args.control/'predictions.csv',dtype={'issue':str})
control=control[control.minimum_sp.isin([1.,1.3])].copy()
refill=pd.read_csv(args.refill/'predictions.csv',dtype={'issue':str})
affected=sorted(refill.issue.unique())
gate=control[control.minimum_sp==1.3]
observed=sorted(gate.loc[gate.eligible_groups<gate.total_groups,'issue'].unique())
if affected!=observed:raise ValueError('Rebuilt issue set does not match frozen fixture gate')
reused=gate[~gate.issue.isin(affected)].copy()
reused['arm']=reused.arm.str.replace('_SP130_','_REFILL_',regex=False)
reused['variant']='REFILL'
control['variant']=control.minimum_sp.map({1.:'NO_FILTER',1.3:'FILTER_ONLY'})
refill['variant']='REFILL'
predictions=pd.concat([control,reused,refill],ignore_index=True)
if predictions.duplicated(['issue','arm','seed']).any() or len(predictions)!=48600:
    raise ValueError('Three-arm 200-issue scope mismatch')
plans=[]
for path in sorted(args.refill.glob('*-plans.json')):
    for plan in json.loads(path.read_text()):
        plan['seal']=stable_json_hash(plan)
        plans.append(plan)
if len(plans)!=len(refill):raise ValueError('Rebuilt plan grid incomplete')
args.output.mkdir(parents=True)
predictions.to_csv(args.output/'predictions.csv',index=False)
(args.output/'refill-plans.json').write_text(json.dumps(plans,allow_nan=False))
frozen_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [args.output/'predictions.csv',args.output/'refill-plans.json']}
freeze=dict(input_bindings=bindings,files=frozen_files,affected_issues=affected,
    reused_issues=sorted(reused.issue.unique()),rows=len(predictions),refill_plans=len(plans),
    cutoffs=refill_freeze['metadata'],historical_admission=False,labels_loaded=False)
freeze['seal']=stable_json_hash(freeze)
(args.output/'plans-frozen.json').write_text(json.dumps(freeze,indent=2,allow_nan=False))
# Actual audits/results become visible only after the complete three-arm freeze.
settlement_inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
    [args.audit_study/'plans-frozen.json',args.audit_study/'audit-snapshot.json',
     args.audit_study/'evaluation-receipt.json',args.control/'results.csv',
     args.control/'evaluation-receipt.json']}
settled=[]
for issue in affected:
    audit=json.loads(load_rank_issue(args.audit_study,issue))['audit']
    settled.extend(settle_refill_plans([p for p in plans if p['issue']==issue],audit))
actual=pd.DataFrame(settled)
new=refill.merge(actual[['issue','arm','seed','gross','net','hits','physical_tickets']],
                 on=['issue','arm','seed'],validate='one_to_one')
prior_receipt=json.loads((args.control/'evaluation-receipt.json').read_text())
if hashlib.sha256((args.control/'results.csv').read_bytes()).hexdigest()!=prior_receipt['results_sha256']:
    raise ValueError('Control settlement binding changed')
prior=pd.read_csv(args.control/'results.csv',dtype={'issue':str})
controls=prior[prior.minimum_sp.isin([1.,1.3])].copy()
controls['variant']=controls.minimum_sp.map({1.:'NO_FILTER',1.3:'FILTER_ONLY'})
unchanged=prior[(prior.minimum_sp==1.3)&~prior.issue.isin(affected)].copy()
unchanged['arm']=unchanged.arm.str.replace('_SP130_','_REFILL_',regex=False)
unchanged['variant']='REFILL'
results=pd.concat([controls,unchanged,new],ignore_index=True)
if len(results)!=len(predictions) or results[['gross','net','hits']].isna().any().any():
    raise ValueError('Incomplete settlement')
results.to_csv(args.output/'results.csv',index=False)
verify_implementation_closure(repository,settlement_implementation)
for path,sha in settlement_inputs.items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Settlement input changed during evaluation')
receipt=dict(status='PASS',plans=len(results),independently_settled_refill_plans=len(plans),
    reused_control_rows=len(controls)+len(unchanged),
    freeze_sha256=hashlib.sha256((args.output/'plans-frozen.json').read_bytes()).hexdigest(),
    results_sha256=hashlib.sha256((args.output/'results.csv').read_bytes()).hexdigest(),
    audit_study=str(args.audit_study),historical_admission=False,
    settlement_implementation=settlement_implementation,settlement_inputs=settlement_inputs)
(args.output/'evaluation-receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
