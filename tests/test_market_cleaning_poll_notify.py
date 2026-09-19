import json
from types import SimpleNamespace
import pytest
from src.market_cleaning_notify import notify_cleaning_poll

@pytest.mark.parametrize('state,expected',[('STARTED','尚未表示批次已冻结'),('BUSY','上一轮仍在运行')])
def test_poll_notification(tmp_path,state,expected):
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(thread='thread-id',codex='/bin/codex')))
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='queued',stderr='')
    assert notify_cleaning_poll(config,state,run=run)['state']==state
    assert len(calls)==1
    assert calls[0][0][:5]==['/bin/codex','queue','--thread','thread-id','--message']
    assert expected in calls[0][0][5]
    assert calls[0][1]['timeout']==15

def test_poll_failure_and_invalid_state(tmp_path):
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(thread='t',codex='/bin/codex')))
    with pytest.raises(ValueError):
        notify_cleaning_poll(config,'BAD')
    with pytest.raises(RuntimeError,match='failed'):
        notify_cleaning_poll(config,'STARTED',run=lambda *a,**k: SimpleNamespace(returncode=1,stderr='failed'))
    config.write_text(json.dumps(dict(thread='t',codex='relative')))
    with pytest.raises(ValueError):
        notify_cleaning_poll(config,'STARTED')

def test_scheduler_continues_when_notification_and_logger_fail(tmp_path):
    from pathlib import Path
    import subprocess
    source=Path('scripts/poll_market_cleaning.sh').read_text()
    line=next(line for line in source.splitlines() if '--poll-state' in line)
    # Stub only external commands; execute the scheduler's actual error guards.
    command=line.replace(line.split(' || ')[0], 'false', 1)
    command=command.replace("/usr/bin/logger -t beijing-lot-market-cleaning 'Scheduler notification failed; inspect queue delivery'", 'false')
    result=subprocess.run(['bash','-c','set -e\n'+command+'\necho continued'],capture_output=True,text=True)
    assert result.returncode==0
    assert result.stdout.strip()=='continued'
