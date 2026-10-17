"""Declared offline research orchestration; no statistical functions or clock admission.
Run from repository root with .venv/bin/python. Waits for the four already-started
fixed shards, assembles the cache-bound batch, then independently recomputes every
fixture in four shards. Only after replay acceptance does calibration/scoring run.
"""
from pathlib import Path
import subprocess,os,json,time,sys,hashlib
root=Path.cwd();out=root/'results/fm171-26103-draw-20261017'
env={**os.environ,**json.loads((root/'results/fm171-draw-calibration-20261017/test-environment.json').read_text())}
env.update(TZ='UTC',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',XDG_CACHE_HOME='/tmp/fm171-26103-quarto-cache')
(out/'test-environment.json').write_text(json.dumps({k:env[k] for k in json.loads((root/'results/fm171-draw-calibration-20261017/test-environment.json').read_text())}|{'TZ':env['TZ'],'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','XDG_CACHE_HOME':env['XDG_CACHE_HOME']},indent=2)+'\n')
rs='/opt/R/4.6.1/bin/Rscript';commands=[]
start=time.monotonic()
while not all((out/f'native-shard-{i}of4.rds').exists() for i in range(1,5)):
    assert time.monotonic()-start<7200,'Native shards incomplete after bounded2hour orchestration timeout; inspect worker errors'
    time.sleep(5)
cmd=[rs,'r/fm171_26103_native_freeze.R',str(root)]
with (out/'native-merge.log').open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
commands.append(dict(command=cmd,exit_code=code));assert code==0,cmd
print('native merged',flush=True)
processes=[]
for i in range(1,5):
    cmd=[rs,'r/fm171_26103_native_freeze.R',str(root),'replay-shard',str(i),'4']
    log=(out/f'native-replay-{i}of4.log').open('w')
    processes.append((cmd,subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT),log))
for cmd,p,log in processes:
    code=p.wait();log.close();commands.append(dict(command=cmd,exit_code=code))
assert all(c['exit_code']==0 for c in commands),'Independent replay failed; inspect four logs'
for filename,extra,logfile in [
 ('r/fm171_26103_native_replay_accept.R',[],'native-replay-accept.log'),
 ('r/fm171_26103_calibrate.R',[],'calibration-freeze.log'),
 ('r/fm171_26103_calibrate.R',['replay'],'calibration-replay.log'),
 ('r/fm171_26103_evaluate.R',[],'evaluate.log')]:
    cmd=[rs,filename,str(root),*extra]
    with (out/logfile).open('w') as log:code=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    commands.append(dict(command=cmd,exit_code=code));assert code==0,cmd
    print('completed',filename,extra,flush=True)
(out/'build-commands.json').write_text(json.dumps({'status':'EVALUATED','commands':commands,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'wall_seconds':time.monotonic()-start},indent=2)+'\n')
print('EVALUATED',flush=True)
