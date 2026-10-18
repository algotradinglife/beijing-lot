"""Exact receipt-driven sequencing for the currently confirmed Titan process."""
from pathlib import Path
import json,subprocess,time,shlex
from datetime import datetime,timezone
root=Path('/home/drwho1985/workspace/algotradinglife/beijing-lot')
out=root/'results/global-dynamic-source-rate-20261018'
titan=root/'results/global-dynamic-26105-readiness-20261018-control'
runner=root/'results/global-dynamic-walkforward-20261018/run-local-check.py'
terminal=titan/'titan-gap-capture-exit.json'
while not terminal.is_file():
    proc=Path('/proc/3856830')
    if not proc.is_dir():
        time.sleep(2)
        if not terminal.is_file():raise RuntimeError('Actual Titan handle absent without terminal receipt; inspect before resuming')
        break
    cmd=(proc/'cmdline').read_bytes().decode().replace('\0',' ')
    if 'src/global_dynamic_26105_capture_missing_20261018.py' not in cmd:
        raise RuntimeError('Titan PID identity changed; no automatic restart')
    time.sleep(5)
first=json.loads(terminal.read_text())
if first['exit_status'] not in (0,2):raise RuntimeError('Titan failed outside bounded request statuses; inspect real terminal state')
if first['exit_status']==2:
    name='titan-gap-retry';spec=json.loads((titan/'titan-gap-capture-job.json').read_text())
    spec['log']=str(out/(name+'.log'));spec['receipt']=str(out/(name+'-exit.json'))
    p=out/(name+'-job.json');assert not p.exists();p.write_text(json.dumps(spec,indent=2)+'\n')
    code=subprocess.run([str(root/'.venv/bin/python'),str(runner),str(p)]).returncode
    if code not in (0,2):raise RuntimeError('Bounded Titan retry failed; inspect receipt')
name='nowscore-gap-capture'
args=[str(root/'.venv/bin/python'),'src/global_dynamic_nowscore_capture_20261018.py','--input',str(out/'nowscore-missing.csv'),'--output','hot:global-dynamic-26105-nowscore-gaps-20261018','--policy-receipt',str(out/'applied-policy.json'),'--min-interval-seconds','5']
script='. config/source-extraction.env\nexport PYTHONPATH='+shlex.quote(str(out/'library-final/beidan/python'))+'\nexec '+shlex.join(args)
spec=dict(command=['/bin/zsh','-c',script],cwd=str(root),log=str(out/(name+'.log')),receipt=str(out/(name+'-exit.json')))
p=out/(name+'-job.json');assert not p.exists();p.write_text(json.dumps(spec,indent=2)+'\n')
job=subprocess.Popen([str(root/'.venv/bin/python'),str(runner),str(p)],start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(out/'nowscore-capture-launch.json').write_text(json.dumps(dict(wrapper_pid=job.pid,job=str(p),started_at_utc=datetime.now(timezone.utc).isoformat(),scope=730,goal_complete=False),indent=2)+'\n')
print('NOWSCORE_STARTED',job.pid,flush=True)
