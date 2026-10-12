"""Independent replay in read-only R processes; no fitting or cutoff selection."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,json,sys,hashlib
root=Path(sys.argv[1]).resolve();out=root/'results/fm16-three-issues-20261012'
# Three CPU processes read the same frozen inputs and stable installed package.
with ThreadPoolExecutor(max_workers=3) as pool:
    tasks=[]
    for shard in range(1,4):
        log=open(out/f'replay-{shard}.log','w')
        tasks.append((shard,log,pool.submit(subprocess.run,['/opt/R/4.6.1/bin/Rscript',str(root/'r/fm16_three_issue_freeze.R'),str(root),'replay',str(shard),'3'],stdout=log,stderr=subprocess.STDOUT)))
    for shard,log,task in tasks:
        result=task.result();log.close()
        assert result.returncode==0,f'Replay shard {shard} failed; inspect log'
receipts=[json.loads((out/f'replay-{i}.json').read_text()) for i in range(1,4)]
ids=sum([x['fixture_ids']for x in receipts],[])
assert len(ids)==len(set(ids))==346
assert all(x['status']=='FULL_IDENTICAL_REPLAY' and x['sha256']==hashlib.sha256((out/'forecasts.rds').read_bytes()).hexdigest() for x in receipts)
(out/'replay.json').write_text(json.dumps({'status':'FULL_IDENTICAL_REPLAY','fixtures':len(ids),'sha256':receipts[0]['sha256'],'shard_receipts':[f'replay-{i}.json'for i in range(1,4)],'scheduler_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'client_sha256':hashlib.sha256((root/'r/fm16_three_issue_freeze.R').read_bytes()).hexdigest()},indent=2)+'\n')
print('Identical replay:',len(ids))
