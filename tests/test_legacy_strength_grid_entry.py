"""Archive-to-plan-to-settlement integration, missing-factor and tamper behavior."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from src.temporal_learning.core import stable_json_hash


def test_archived_strength_entry(tmp_path):
    root=Path(__file__).resolve().parents[1]
    rows=[dict(issue='001',slot=s,provider_id=str(s),handicap=1,p_W=.6,p_D=.25,p_L=.15,
               q_W=.6,q_D=.25 if s<7 else .1,q_L=.15 if s<7 else .3) for s in range(1,9)]
    factors=dict(rows=rows,issues=['001','002'],cutoffs={'001':{str(s):'2010-01-01T12:00:00+00:00' for s in range(1,9)}})
    audit=dict(rows=[dict(issue='001',slot=s,provider_id=str(s),handicap=1,actual_home=1,
                         actual_away=1,actual_direction='W',status='READY',spf_sp=2) for s in range(1,9)])
    archive=tmp_path/'input.tar';prepared=dict(receipt={},seal=stable_json_hash({}))
    with tarfile.open(archive,'w') as tar:
        for name,obj in [('factors.json',factors),('prepared.json',prepared),('settlement-audit.json',audit)]:
            raw=json.dumps(obj).encode();info=tarfile.TarInfo('updated100-strategies-v1/'+name);info.size=len(raw);tar.addfile(info,io.BytesIO(raw))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest();out=tmp_path/'study'
    env=dict(os.environ,PYTHONPATH=str(root));base=[sys.executable,str(root/'scripts/replay_legacy_strength_grid.py')]
    args=['--archive',str(archive),'--archive-sha256',digest,'--output',str(out)]
    for phase in ['freeze','settle']:
        subprocess.run(base+[phase]+args,cwd=root,env=env,check=True,capture_output=True)
    results=json.loads((out/'results.json').read_text())
    assert results['unavailable']==[dict(issue='002',reason='NO_READY_FACTORS')]
    assert len(results['rows'])==6 and all(x['hits']==1 for x in results['rows'])
    ap=tmp_path/'audit.json';ap.write_text(json.dumps(audit));proof=tmp_path/'proof.json'
    command=[sys.executable,str(root/'scripts/check_legacy_grid_settlement.py'),'--study',str(out),
             '--audit',str(ap),'--audit-sha256',hashlib.sha256(ap.read_bytes()).hexdigest(),'--output',str(proof)]
    subprocess.run(command,cwd=root,env=env,check=True,capture_output=True)
    assert json.loads(proof.read_text())['plans']==6
    # Chronology is part of drawdown, not just a presentation choice.
    original_order=results['issue_order'];results['issue_order']=['002','001']
    (out/'results.json').write_text(json.dumps(results))
    assert subprocess.run(command,cwd=root,env=env,capture_output=True).returncode!=0
    results['issue_order']=original_order
    results['rows'][0]['gross']+=1;(out/'results.json').write_text(json.dumps(results))
    assert subprocess.run(command,cwd=root,env=env,capture_output=True).returncode!=0
    assert subprocess.run(base+['settle']+args,cwd=root,env=env,capture_output=True).returncode!=0
