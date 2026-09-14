"""Bounded batch dispatcher with immutable-receipt resumption; no labels.

CLI: project-python scripts/run_n7_expanded_allocation_batches.py PIPELINE TEMPLATE [BATCH]
Without BATCH, launch at most allocation_workers separate batch processes.
Completed batches are verified/replayed, never overwritten. A declared external
in-flight batch may finish before resumption; other partial outputs fail closed.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

entry_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
cfg=json.loads(Path(sys.argv[1]).read_text());template=json.loads(Path(sys.argv[2]).read_text())
study=Path(cfg['study']);root=Path(cfg['repository_root'])
receipt=json.loads((study/'inputs/input-receipt.json').read_text())
if len(sys.argv)==4:
    k=int(sys.argv[3]);assert 0<=k<len(receipt['batches'])
    path=study/f'batch-{k:03d}';deadline=time.monotonic()+7200
    while not (path/'batch-receipt.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('Missing prediction batch '+str(k))
        time.sleep(10)
    catalog=path/'catalog.json';allocation=path/'allocations'
    if not catalog.exists():
        subprocess.run([cfg['python'],str(root/'scripts/catalog_n7_expanded_batch.py'),str(path),str(root)],check=True,cwd=root)
    config={**template,'catalog':str(catalog),'catalog_sha256':hashlib.sha256(catalog.read_bytes()).hexdigest(),
            'output_dir':str(allocation)}
    config_path=path/'allocation-config.json'
    if allocation.exists():
        if json.loads(config_path.read_text())!=config:raise ValueError('Existing batch parameters differ')
        while not (allocation/'plans-frozen.json').exists():
            if k not in cfg.get('externally_running_batches',[]) or time.monotonic()>deadline:
                raise ValueError('Partial allocation requires investigation: '+str(k))
            time.sleep(10)
    else:
        config_path.write_text(json.dumps(config,indent=2))
        with (path/'allocation.log').open('w') as log:
            subprocess.run([cfg['rscript'],str(root/'scripts/run_n7_expanded_allocations.R'),str(config_path)],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    proof=allocation/'prediction-replay.json'
    if not proof.exists():
        subprocess.run([cfg['python'],str(root/'scripts/check_n7_expanded_allocations.py'),str(allocation)],check=True,cwd=root)
    verified=json.loads(proof.read_text())
    if verified['status']!='PASS' or verified['freeze_sha256']!=hashlib.sha256((allocation/'plans-frozen.json').read_bytes()).hexdigest():
        raise ValueError('Completed replay binding differs')
    frozen=json.loads((allocation/'plans-frozen.json').read_text())
    for name,sha in frozen['files'].items():
        if hashlib.sha256((allocation/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen allocation changed')
    for path,sha in frozen['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen source changed')
    for name,sha in {**frozen['implementation'],**verified['implementation']}.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:raise ValueError('Replay implementation changed')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=entry_sha:raise ValueError('Dispatcher changed while running')
    print('Frozen and independently replayed batch',k,flush=True)
else:
    assert len(sys.argv)==3 and 1<=cfg['allocation_workers']<=3
    with ThreadPoolExecutor(max_workers=cfg['allocation_workers']) as workers:
        jobs=[workers.submit(subprocess.run,[cfg['python'],str(Path(__file__).resolve()),
              str(Path(sys.argv[1]).resolve()),str(Path(sys.argv[2]).resolve()),str(k)],cwd=root,check=True)
              for k in range(len(receipt['batches']))]
        for job in as_completed(jobs):job.result()
    all_freezes={}
    for k in range(len(receipt['batches'])):
        for name in ('plans-frozen.json','prediction-replay.json'):
            p=study/f'batch-{k:03d}/allocations'/name
            all_freezes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    out=study/'all-plans-frozen.json'
    if out.exists():raise ValueError('Complete freeze exists')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=entry_sha:raise ValueError('Dispatcher changed while running')
    out.write_text(json.dumps(dict(status='ALL_PREDICTIONS_FROZEN_BEFORE_TARGET_SETTLEMENT',
        requested_issues=json.loads((study/'inputs/scope.json').read_text())['issues'],files=all_freezes,
        source_receipt_sha256=hashlib.sha256((study/'inputs/input-receipt.json').read_bytes()).hexdigest(),
        implementation_sha256=entry_sha,historical_admission=False),indent=2))
    print('ALL new issue plans frozen and replayed; target settlement may now be opened',flush=True)
