"""Freeze label-free three-arm top-probability N7 stake multiplier before querying settlement."""
import argparse
import json
from pathlib import Path
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_n7_baseline import archive_n7_inputs
from src.fundamentals_n7_topstake import n7_topstake_plan

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);args=cli.parse_args()
    root=Path.cwd();out=Path(args.output)
    if out.exists():raise FileExistsError('New immutable directory required')
    base=Path('data/derived/fundamentals_417')
    studies=[base/s for s in ['retrain-four-v1','train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1']]
    inputs=archive_n7_inputs(studies,root)
    inputs['implementation']=implementation_closure(root,['src.fundamentals_n7_topstake','src.fundamentals_n7_twocover'],distributions=['numpy','pandas'])
    import hashlib
    for f in ['scripts/run_fundamentals_n7_topstake.py','scripts/settle_fundamentals_n7_topstake.R','r/fundamentals_n7_topstake.R']:
        inputs['source_hashes'][f]=hashlib.sha256(Path(f).read_bytes()).hexdigest()
    plans=[]
    for issue,g in pd.DataFrame(inputs['rows']).groupby('issue',sort=True):
        cuts={s:Cutoff.decision_epoch(issue,t) for s,t in inputs['cutoffs'][issue].items()}
        for top_multiplier in [1,2,3]:
            plans.append(n7_topstake_plan(g,cutoffs=cuts,top_multiplier=top_multiplier,max_groups=6,
                unit_cny=2,payout_factor=.65,allocation_seed=417))
        print('FROZEN',issue,flush=True)
    contract=dict(training_issues=json.loads((base/'cv-thirtytwo-test-sixteen-v1/contract.json').read_text())['training_issues'],
        issues=sorted(inputs['cutoffs']),cohort_rows=len(inputs['rows']),exclusions=len(inputs['exclusions']),
        strategies=['BASE','TOP2','TOP3'],funding=['UNIT'],max_groups=6,
        unit_cny=2,payout_factor=.65,allocation_seed=417,fitted=False,protection=False,settlement_opened=False,
        mode='EXPOSED_FIXTURE_RELATIVE_RETROSPECTIVE',historical_admission=False)
    out.mkdir(parents=True)
    for name,value in [('inputs',inputs),('plans',plans),('contract',contract)]:
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
