from pathlib import Path
import os,json,subprocess
root=Path.cwd();out=root/'results/fm171-margin-shape-20261017'
env=json.loads((root/'results/fm-lambda-integration-20261017/test-environment.json').read_text())
assert all(Path(env[k]).exists() for k in ['BEIDAN_TEST_PYTHON','BEIDAN_PARQUET_ROOT'])
(out/'test-environment.json').write_text(json.dumps(env,indent=2)+'\n')
args=['/opt/R/4.6.1/bin/Rscript']
if os.environ.get('SHAPE_TARGETED')=='1':
 args+=['-e','library(testthat);library(beidan);beidan::python_backend(Sys.getenv("BEIDAN_TEST_PYTHON")); x<-test_file("tests/testthat/test-fm171-margin-shape.R",package="beidan",load_helpers=FALSE,stop_on_failure=TRUE);d<-as.data.frame(x);jsonlite::write_json(list(tests=nrow(d),passed=sum(d$passed),failed=sum(d$failed),errors=sum(d$error),skipped=sum(d$skipped)),"results/fm171-margin-shape-20261017/targeted-tests.json",auto_unbox=TRUE,pretty=TRUE)']
else:args+=['tests/testthat.R']
raise SystemExit(subprocess.run(args,env={**os.environ,**env}).returncode)
