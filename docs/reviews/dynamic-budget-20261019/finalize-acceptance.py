"""One-shot local receipt assembly after the required standard repository phase."""
import hashlib
import json
import pathlib
import re
root = pathlib.Path.cwd()
out = root / 'results/dynamic-budget-20261019'
exit_receipt = json.loads((out/'repository-tests-exit.json').read_text())
assert exit_receipt['exit_status'] == 0
log = (out/'repository-tests.log').read_text()
match = re.search(r'repository: tests=(\d+) passed=(\d+) failed=(\d+) errors=(\d+) warnings=(\d+) skipped=(\d+)',log)
assert match, 'missing complete standard phase totals'
names=['blocks','passed','failed','errors','warnings','skipped']
counts=dict(zip(names,map(int,match.groups())))
assert counts['failed']==counts['errors']==counts['warnings']==counts['skipped']==0
assert 'dynamic-budget-study:' in log
inventory=json.loads((out/'snapshot-source-inventory.json').read_text())
snapshot=pathlib.Path(inventory['root'])
for item in inventory['files']:
 assert hashlib.sha256((snapshot/item['path']).read_bytes()).hexdigest()==item['sha256'], item['path']
runtime0=json.loads((out/'runtime-0.json').read_text());runtime1=json.loads((out/'runtime-1.json').read_text())
for key in ['selector','settlement','kernel']:
 assert runtime0[key]==runtime1[key],key
sources=['r/dynamic_budget_freeze_20261019.R','r/dynamic_budget_evaluate_20261019.R','tests/testthat/test-dynamic-budget-study.R','quarto/dynamic_budget_20261019.qmd']
source_files=[]
for p in sources:
 a=hashlib.sha256((root/p).read_bytes()).hexdigest()
 assert a==hashlib.sha256((snapshot/p).read_bytes()).hexdigest(),p
 source_files.append({'path':p,'sha256':a})
assert 'NO_BLOCKING_FINDINGS' in (out/'review-results.log').read_text()
x={'status':'ACCEPTED','repository_tests':dict(counts,exit_status=0,command='Rscript tests/testthat.R --phase=repository'),
 'standard_entry_receipt':exit_receipt,'snapshot_root':str(snapshot),'snapshot_source_inventory_sha256':hashlib.sha256((out/'snapshot-source-inventory.json').read_bytes()).hexdigest(),
 'source_files':source_files,'runtime_calculation':runtime0,'runtime_verification':runtime1,
 'package_changed':False,'python_changed':False,'baseline_2000_parity_issues':['26103','26104','26105'],
 'review_results':'NO_BLOCKING_FINDINGS; final accepted-render artifact follow-up recorded separately',
 'scope':'All repository tests on last accepted isolated base plus budget clients/tests/current standard entry. Unrelated dirty package work in shared checkout is excluded; no claim of testing all current WIP.',
 'setup_recovery':'Initial private full-copy exceeded tmpfs quota; only that failed task copy was removed, baseline files hard-linked into a new isolated tree; changed source files detached before copying. Tests TMPDIR uses NVMe. No unrelated work removed.'}
(out/'acceptance.json').write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps(counts))
