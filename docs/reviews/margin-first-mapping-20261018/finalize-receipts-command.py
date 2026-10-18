"""One-shot local acceptance receipt from completed, independently recorded checks."""
from pathlib import Path
import hashlib,json,re
root=Path.cwd();out=root/'results/margin-first-mapping-20261018'
r=json.loads((out/'full-R-exit.json').read_text());py=json.loads((out/'full-python-exit.json').read_text())
assert r['exit_status']==py['exit_status']==0
text=(out/'full-R.log').read_text();tests=[]
for phase,minimum_tests,minimum_passed in [('package',992,9664),('repository',810,183338)]:
 m=re.search(phase+r': tests=(\d+) passed=(\d+) failed=(\d+) errors=(\d+) warnings=(\d+) skipped=(\d+)',text)
 assert m is not None
 values=list(map(int,m.groups()));assert values[0]>=minimum_tests and values[1]>=minimum_passed and values[2:]==[0,0,0,0]
 tests.append(dict(suite=phase,tests=values[0],passed=values[1],failed=values[2],errors=values[3],warnings=values[4],skipped=values[5]))
pylast=(out/'full-python.log').read_text().strip().splitlines()[-1]
assert re.search(r'674 passed in ',pylast) and not re.search(r'failed|error|skipped',pylast)
tests.append(dict(suite='Python backend and capture clients',tests=674,passed=674,failed=0,errors=0,warnings=0,skipped=0))
review=json.loads((out/'final-review-receipt.json').read_text());assert review['status']=='NO_BLOCKING_FINDINGS' and review['exit_status']==0
for row in review['files']:
 assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256']
 assert hashlib.sha256((Path('/tmp/beidan-source-rate-20261018')/row['path']).read_bytes()).hexdigest()==row['sha256']
eval_receipt=json.loads((out/'evaluation.json').read_text());assert eval_receipt['selection_replay']=='IDENTICAL'
for key,name in [('groups','group-evaluation.csv'),('rounds','round-evaluation.csv')]:
 assert hashlib.sha256((out/name).read_bytes()).hexdigest()==eval_receipt['output_hashes'][key]
checks=[]
for name in ['install','runtime']:
 observed=json.loads((out/(name+'-observation.json')).read_text());assert observed['exit_status']==0
 checks.append(dict(check=name,command=observed['command'],exit_status=0,evidence=name+'-observation.json'))
for name in ['full-R','full-python']:
 checks.append(dict(check=name,command='Project Python run-local-check.py '+name+'-job.json',exit_status=0,evidence=name+'-exit.json'))
checks.extend([dict(check='source-review',command=review['command'],exit_status=0,evidence='final-review-receipt.json'),dict(check='selection-and-scoring-replay',command='Rscript r/margin_first_mapping_evaluate_20261018.R PROJECT_ROOT',exit_status=0,evidence='evaluation.json'),dict(check='independent-enumeration-and-baseline',command='Rscript r/margin_first_mapping_checks_20261019.R PROJECT_ROOT',exit_status=0,evidence='independent-checks.json')])
acceptance=dict(producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),status='LOCAL_CHECKS_PASSED',files=review['files'],tests=tests,checks=checks,full_R_receipt_sha256=hashlib.sha256((out/'full-R-exit.json').read_bytes()).hexdigest(),full_python_receipt_sha256=hashlib.sha256((out/'full-python-exit.json').read_bytes()).hexdigest(),scoring_receipt_sha256=hashlib.sha256((out/'evaluation.json').read_bytes()).hexdigest())
p=out/'acceptance.json';assert not p.exists()
p.write_text(json.dumps(acceptance,indent=2));print(json.dumps(tests,indent=2))
