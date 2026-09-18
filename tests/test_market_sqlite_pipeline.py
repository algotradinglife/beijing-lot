import subprocess
import sys
import pytest
from src.market_sqlite_pipeline import prepare_market_batch


def test_sequential_preparation_stops_and_replays(tmp_path):
    plan=tmp_path/'audits/market-sqlite/b/audit-retention-plan.json'
    plan.parent.mkdir(parents=True);plan.write_text('{}')
    calls=[]
    def execute(cmd,**kwargs):
        calls.append((cmd,kwargs))
        if len(calls)==3:raise subprocess.CalledProcessError(1,cmd)
    args=dict(python=sys.executable,data_root=tmp_path,batch_id='b',quarto=sys.executable)
    with pytest.raises(subprocess.CalledProcessError):
        prepare_market_batch(tmp_path,run=execute,**args)
    assert len(calls)==3
    assert all(k==dict(cwd=tmp_path,check=True) for _,k in calls)
    calls.clear()
    result=prepare_market_batch(tmp_path,run=lambda cmd,**kw:calls.append(cmd),**args)
    assert result==['import','audit','inventory','publication','report']
    assert len(calls)==5
    assert calls[0][1].endswith('/scripts/migrate_market_sqlite_batch.py')
    assert calls[0][0]==sys.executable
    assert all('retire' not in arg and 'activate' not in arg for cmd in calls for arg in cmd)


@pytest.mark.parametrize('batch',['','..','../b','/b'])
def test_unsafe_batch_rejected_before_execution(tmp_path,batch):
    with pytest.raises(ValueError,match='unsafe'):
        prepare_market_batch(tmp_path,python=sys.executable,data_root=tmp_path,
                             batch_id=batch,quarto=sys.executable)


def test_missing_plan_rejected_before_execution(tmp_path):
    with pytest.raises(ValueError,match='retention plan'):
        prepare_market_batch(tmp_path,python=sys.executable,data_root=tmp_path,
                             batch_id='b',quarto=sys.executable)
