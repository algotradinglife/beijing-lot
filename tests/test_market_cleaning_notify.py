import hashlib
import json
import subprocess
from types import SimpleNamespace
import pytest
from src.market_cleaning_notify import cleaning_events, notify_cleaning_events


@pytest.fixture
def batch(tmp_path):
    directory=tmp_path/'audits/market-cleaning/batches/001-002';directory.mkdir(parents=True)
    manifest=directory/'manifest.json';manifest.write_text(json.dumps(dict(issues=['001','002'])))
    state=tmp_path/'runtime/state/market-cleaning';state.mkdir(parents=True)
    (state/'status.json').write_text(json.dumps(dict(status='PROCESSING_BATCH',active_batch=str(directory))))
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(thread='test-thread',codex='/bin/codex')))
    return tmp_path,directory,config


def test_start_once_then_verified_complete_once(batch):
    root,directory,config=batch; calls=[]
    def run(command,**kwargs):
        calls.append(command);return SimpleNamespace(returncode=0,stdout='queued',stderr='')
    notify_cleaning_events(root,config,run=run)
    notify_cleaning_events(root,config,run=run)
    assert len(calls)==1 and calls[0][1:4]==['queue','--thread','test-thread']
    summary=directory/'summary.json';summary.write_text('{}')
    receipt=dict(status='ACCEPTED_DIAGNOSTIC_BATCH',issues=['001','002'])
    for key,path in [('manifest',directory/'manifest.json'),('market_summary',summary)]:
        receipt[key]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (directory/'final-acceptance.json').write_text(json.dumps(receipt))
    notify_cleaning_events(root,config,run=run);notify_cleaning_events(root,config,run=run)
    assert len(calls)==2 and '验收完成' in calls[-1][-1]
    summary.write_text('changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        cleaning_events(root,{},[str(directory)])


def test_failure_retry_but_timeout_is_not_duplicated(batch):
    root,directory,config=batch
    states=notify_cleaning_events(root,config,run=lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr='offline'))
    assert set(states.values())=={'PENDING'}
    def timeout(*args,**kwargs):
        raise subprocess.TimeoutExpired('codex queue',45)
    assert set(notify_cleaning_events(root,config,run=timeout).values())=={'UNKNOWN'}
    def forbidden(*args,**kwargs):
        pytest.fail('ambiguous delivery must not be duplicated')
    notify_cleaning_events(root,config,run=forbidden)


def test_idle_does_not_notify_old_batches_and_rejects_escape(batch):
    root,directory,config=batch
    assert cleaning_events(root,{'status':'WAITING_FOR_50_ISSUES'},[])==[]
    with pytest.raises(ValueError,match='outside'):
        cleaning_events(root,{},[str(root.parent)])


def test_accepted_batch_detected_when_setup_finishes_after_batch(batch):
    root,directory,config=batch
    events=cleaning_events(root,dict(status='BATCH_ACCEPTED',active_batch=str(directory)),[])
    assert events[0]['kind']=='started' and '补发' in events[0]['message']
