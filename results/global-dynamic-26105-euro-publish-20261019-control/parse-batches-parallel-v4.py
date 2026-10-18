import os,signal,sys,json,time,hashlib,subprocess
from pathlib import Path
p=Path(__file__).resolve().parent;out=p/'parsed-batches-v1';worker=p/'parse-batches-v1.py'
expected_worker_sha='8340e5cb0f1b58cfae85a904c5e95b96a963a4dfa7b1e80f70cb963445879cae'
assert hashlib.sha256(worker.read_bytes()).hexdigest()==expected_worker_sha
import gc,pickle
from datetime import datetime,timezone
from beidan_backend.source_market_publication import validate_market_tables
inherited=[{'pid': 849088, 'first': 31, 'start': '166305547'}, {'pid': 849089, 'first': 41, 'start': '166305547'}, {'pid': 849090, 'first': 51, 'start': '166305547'}]
observations=[]
for observed in inherited:
    proc=Path(f"/proc/{observed['pid']}/stat")
    observed_exit=None
    while proc.exists():
        try:
            raw_stat=proc.read_text()
        except OSError as error:
            if error.errno in (2,3):break
            raise
        fields=raw_stat.split(') ',1)[1].split()
        assert fields[19]==observed['start'], 'Inherited PID reused;inspect'
        if fields[0]=='Z':
            observed_exit=os.waitstatus_to_exitcode(int(fields[49]));break
        time.sleep(5)
    observations.append(dict(observed,exit_status=observed_exit,
        availability='observed zombie wait status' if observed_exit is not None else 'reaped by init;exit status unavailable'))
    if observed_exit is not None:assert observed_exit==0,'Inherited worker failed;inspect'
# Independently replay actual existing SDK validation for all preserved data.
recovery=[]
for first in range(1,61,10):
    checkpoint=out/f'{first:03d}.pickle';receipt=out/f'{first:03d}.json'
    record=json.loads(receipt.read_bytes())
    assert record['slots']==list(range(first,first+10)) and record['network_attempts']==0
    assert record['script_sha256']==expected_worker_sha
    assert hashlib.sha256(checkpoint.read_bytes()).hexdigest()==record['pickle_sha256']
    with checkpoint.open('rb') as stream:part=pickle.load(stream)
    assert record['receipt']==part['receipt']
    validate_market_tables(part)
    assert len(part['tables']['status'])==10 and len(part['tables']['resources'])==20
    assert all(r['state'] in {'VERIFIED','EMPTY'} for r in part['tables']['resources'])
    recovery.append(dict(first_slot=first,pickle_sha256=record['pickle_sha256'],validation='SDK_CONTRACT_REPLAY_PASSED'))
    del part;gc.collect()
with (p/'scheduler-recovery-validation-v4.json').open('x') as stream:
    json.dump(dict(observations=observations,independent_validation=recovery,
        original_exit_status_inferred=False,generated_at=datetime.now(timezone.utc).isoformat()),stream,indent=2)
print('INHERITED_CHECKPOINTS_VALIDATED;original status gaps explicit;normal supervised scheduling resumes',flush=True)
pending=[]
for first in range(1,366,10):
    receipt=out/f'{first:03d}.json';checkpoint=out/f'{first:03d}.pickle'
    if receipt.exists():
        record=json.loads(receipt.read_bytes())
        assert record['slots']==list(range(first,min(first+10,366)))
        assert record['script_sha256']==expected_worker_sha and record['network_attempts']==0
        assert record['roster_input_sha256']=='bb6355e04281cb3b980bdf19477a89b309b1380fcfc37fd31b0c0716acc8feed'
        assert hashlib.sha256(checkpoint.read_bytes()).hexdigest()==record['pickle_sha256']
        print('VERIFIED_REUSE '+str(first),flush=True)
    else:
        assert not checkpoint.exists(), 'Partial checkpoint requires explicit investigation'
        pending.append(first)
active=[];failed=[]
while pending or active:
    while pending and len(active)<3 and not failed:
        first=pending.pop(0)
        assert hashlib.sha256(worker.read_bytes()).hexdigest()==expected_worker_sha
        stream=(p/f'parallel-v4-batch-{first:03d}.log').open('x')
        child=subprocess.Popen([sys.executable,str(worker),str(first)],stdout=stream,stderr=subprocess.STDOUT)
        active.append((first,child,stream))
        print('START '+str(first)+' PID '+str(child.pid),flush=True)
    remaining=[]
    for first,child,stream in active:
        status=child.poll()
        if status is None:remaining.append((first,child,stream));continue
        stream.close()
        print('EXIT '+str(first)+' '+str(status),flush=True)
        if status!=0:failed.append((first,status))
    active=remaining
    if failed and not active:raise RuntimeError('Batch failure;preserve all evidence: '+repr(failed))
    if pending or active:time.sleep(5)
assert hashlib.sha256(worker.read_bytes()).hexdigest()==expected_worker_sha
assert len(list(out.glob('*.json')))==37
print('ALL37_BATCHES_TERMINAL_SUCCESS;no target labels or model admission',flush=True)
