"""Bounded local acceptance orchestration, no model fit or target selection.
Waits for completed build receipt; repeats pinned intake and scoring in fresh R
processes, executes the new test file, then the repository's complete R entry.
"""
from pathlib import Path
import json,os,subprocess,time,hashlib,shutil,tempfile,sys
root=Path.cwd();out=root/'results/fm171-26103-draw-20261017'
env={**os.environ,**json.loads((out/'test-environment.json').read_text())}
rs='/opt/R/4.6.1/bin/Rscript';commands=[];started=time.monotonic()
while not (out/'build-commands.json').exists():
    assert time.monotonic()-started<14400,'Bounded build wait expired; inspect build and worker logs'
    time.sleep(5)
b=json.loads((out/'build-commands.json').read_text());assert b['status']=='EVALUATED'
backup=Path(tempfile.mkdtemp(prefix='fm171-26103-verification-'))
files=['fundamentals.rds','fixtures.csv','inputs.json','euro-contexts.rds','euro-selected.rds','exclusion-rosters.json']
before={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in files}
for n in files:shutil.copy2(out/n,backup/n)
cmd=[rs,'r/fm171_26103_intake.R',str(root)]
with (out/'intake-replay.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
commands.append(dict(command=cmd,exit_code=code));assert code==0,cmd
after={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in files}
assert before==after,('Intake bytes changed: preserve recovery at',str(backup))
(out/'intake-replay.json').write_text(json.dumps({'status':'ALL_PINNED_INPUTS_BYTE_IDENTICAL','files':before,'backup':str(backup)},indent=2)+'\n')
evaluation=json.loads((out/'evaluation.json').read_text())
score_files=[r['path'] for r in evaluation['outputs']]+['labels.csv','label-exclusions.csv']
score_before={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in score_files}
for n in score_files:shutil.copy2(out/n,backup/n)
cmd=[rs,'r/fm171_26103_evaluate.R',str(root)]
with (out/'evaluation-replay.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
commands.append(dict(command=cmd,exit_code=code));assert code==0,cmd
score_after={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in score_files}
assert score_before==score_after,('Scoring replay differs: preserve recovery at',str(backup))
(out/'evaluation-replay.json').write_text(json.dumps({'status':'ALL_SCORING_CSV_BYTE_IDENTICAL','files':score_after,'backup':str(backup)},indent=2)+'\n')
expr='library(testthat);library(beidan);beidan::python_backend(Sys.getenv("BEIDAN_TEST_PYTHON"));x<-test_file("tests/testthat/test-fm171-26103-draw.R",package="beidan",load_helpers=FALSE,reporter="summary",stop_on_failure=FALSE);d<-as.data.frame(x);totals<-list(tests=nrow(d),passed=sum(d$passed),failed=sum(d$failed),errors=sum(d$error),warnings=sum(d$warning),skipped=sum(d$skipped));jsonlite::write_json(totals,"results/fm171-26103-draw-20261017/targeted-tests.json",auto_unbox=TRUE,pretty=TRUE);stopifnot(totals$failed==0,totals$errors==0,totals$warnings==0,totals$skipped==0)'
cmd=[rs,'-e',expr]
with (out/'targeted-tests.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
commands.append(dict(command=cmd,exit_code=code));assert code==0,'Targeted tests failed; fix before full suite'
print('TARGETED_PASSED',flush=True)
cmd=[rs,'tests/testthat.R']
with (out/'full-R-tests.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
commands.append(dict(command=cmd,exit_code=code));assert code==0,'Complete R entry failed; inspect full log'
(out/'verification-commands.json').write_text(json.dumps({'status':'COMPLETE_R_ENTRY_PASSED','commands':commands,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'wall_seconds':time.monotonic()-started},indent=2)+'\n')
print('COMPLETE_R_ENTRY_PASSED',flush=True)
