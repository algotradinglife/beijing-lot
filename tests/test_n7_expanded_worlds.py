"""R sampler integration: counts, probabilities, distinct seeds and cutoffs."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize('bad_cutoff',[False,True])
def test_expanded_seed_world_replay(tmp_path,bad_cutoff):
    cuts={'001:1':'2020-01-01T00:00:00Z'}
    fixtures=[dict(p_W=1.,p_D=0.,p_L=0.),dict(p_W=.3,p_D=.4,p_L=.3)]
    bundle=tmp_path/'bundle.json.gz'
    bundle.write_bytes(gzip.compress(json.dumps(dict(cutoffs=cuts,expanded_pool=dict(fixtures=fixtures))).encode()))
    request=dict(bundle=str(bundle),cutoffs={} if bad_cutoff else cuts,seeds=[42501,42502],
                 allocation_worlds=256,evaluation_worlds=5000,evaluation_seed_offset=1000000)
    command=[shutil.which('Rscript'),'scripts/replay_n7_expanded_worlds.R',str(Path.cwd())]
    result=subprocess.run(command,input=json.dumps(request),text=True,capture_output=True)
    if bad_cutoff:
        assert result.returncode!=0
        return
    assert result.returncode==0,result.stderr
    x=json.loads(result.stdout)
    assert len(x['42501']['train'])==256 and len(x['42501']['evaluation'])==5000
    assert all(row[0]==0 and len(row)==2 and row[1] in (0,1,2) for row in x['42501']['evaluation'])
    assert x['42501']['train']!=x['42502']['train']
    assert x['42501']['train']!=x['42501']['evaluation'][:256]
    again=subprocess.run(command,input=json.dumps(request),text=True,capture_output=True,check=True)
    assert result.stdout==again.stdout
