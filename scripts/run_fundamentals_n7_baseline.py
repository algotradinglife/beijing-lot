"""Thin freeze-only entry: no settlement prices or model fitting."""
import argparse
import json
from pathlib import Path
import pandas as pd
from src.temporal_learning import Cutoff
from src.fundamentals_n7_baseline import archive_n7_inputs,n7_baseline_plan

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path.cwd();out=Path(args.output)
    if out.exists(): raise FileExistsError('New immutable experiment directory required')
    base=Path('data/derived/fundamentals_417')
    studies=[base/s for s in ['retrain-four-v1','train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1']]
    inputs=archive_n7_inputs(studies,root)
    frame=pd.DataFrame(inputs['rows']);plans=[]
    for issue,g in frame.groupby('issue',sort=True):
        epochs={s:Cutoff.decision_epoch(issue,t) for s,t in inputs['cutoffs'][issue].items()}
        for selector in ['COVERAGE','VALUE']:
            for shape in ['C0E0','C1E2','C1E3']:
                for funding in ['UNIT','MATCHED']:
                    plans.append(n7_baseline_plan(g,cutoffs=epochs,selector=selector,shape=shape,funding=funding,
                        max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417))
        print('FROZEN',issue,flush=True)
    out.mkdir(parents=True)
    (out/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,allow_nan=False))
    (out/'plans.json').write_text(json.dumps(plans,ensure_ascii=False,allow_nan=False))
    contract=dict(issues=sorted(frame.issue.unique()),cohort_rows=len(frame),exclusions=len(inputs['exclusions']),
        selectors=['COVERAGE','VALUE'],shapes=['C0E0','C1E2','C1E3'],funding=['UNIT','MATCHED'],
        max_groups=6,n=7,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417,
        fitted=False,protection=False,scope='48_EXPOSED_ISSUES',mode='FIXTURE_RELATIVE_RETROSPECTIVE',
        historical_admission=False,settlement_opened=False,implementation=inputs['implementation'])
    (out/'contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2))
