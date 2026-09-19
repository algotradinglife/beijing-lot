"""Durable cleaning lifecycle notifications to an explicitly configured Codex thread."""
import fcntl
import hashlib
import json
import subprocess
from pathlib import Path

from src.fundamentals_bulk_capture import atomic_json


def cleaning_events(root, status, tracked):
    """Return verified start/completion events for active or previously tracked batches.

    Root is the mounted persistent data root. Completion requires the accepted
    receipt, exact issue list and matching manifest/summary hashes. Read-only;
    missing acceptance means still running, integrity conflicts raise ValueError.
    """
    root = Path(root).resolve()
    batches = set(tracked)
    if status.get('status') in ('PROCESSING_BATCH', 'BATCH_ACCEPTED') and status.get('active_batch'):
        batches.add(status['active_batch'])
    events = []
    for name in sorted(batches):
        batch = Path(name).resolve()
        if not batch.is_relative_to(root/'audits/market-cleaning/batches'):
            raise ValueError('batch outside cleaning root')
        manifest = batch/'manifest.json'
        data = manifest.read_bytes()
        issues = json.loads(data)['issues']
        if not issues or len(issues) != len(set(issues)):
            raise ValueError('invalid batch issues')
        digest = hashlib.sha256(data).hexdigest()
        identity = str(batch)+':'+digest
        start_label = '盘口清洗启动记录（补发）' if status.get('status') == 'BATCH_ACCEPTED' and name not in tracked else '盘口清洗启动'
        events.append(dict(id=identity+':started', batch=str(batch), kind='started',
            message=f'【{start_label}】{batch.name}，共 {len(issues)} 期。范围已冻结，开始清洗核验。此消息为自动进度通知，请简要转告用户，不要据此重复启动任务。'))
        acceptance = batch/'final-acceptance.json'
        if not acceptance.exists():
            continue
        result = json.loads(acceptance.read_text())
        if result.get('status') != 'ACCEPTED_DIAGNOSTIC_BATCH':
            continue
        if result.get('issues') != issues:
            raise ValueError('acceptance issue mismatch')
        for key, expected in [('manifest', manifest), ('market_summary', None)]:
            bound = result[key]
            path = Path(bound['path']).resolve()
            if not path.is_relative_to(root) or (expected is not None and path != expected):
                raise ValueError('acceptance path mismatch')
            if hashlib.sha256(path.read_bytes()).hexdigest() != bound['sha256']:
                raise ValueError('acceptance hash mismatch')
        events.append(dict(id=identity+':completed', batch=str(batch), kind='completed',
            message=f'【盘口清洗验收完成】{batch.name}，共 {len(issues)} 期，验收状态 {result["status"]}。仍属历史诊断数据，异常保留隔离，不代表报价全部无缺口。验收凭证：{acceptance}。此消息为自动进度通知，请简要转告用户，不要据此重复启动任务。'))
    return events


def notify_cleaning_events(root, config, *, run=subprocess.run):
    """Poll lifecycle state and queue each event once after confirmed CLI success.

    Config explicitly supplies thread and absolute Codex binary. Caller checks
    storage contract before invocation. Separate flock/outbox makes cron and
    direct lifecycle hooks mutually exclusive. Known CLI failure retries next
    poll; an interrupted/timeout send stays IN_FLIGHT/UNKNOWN for reconciliation
    because Codex queue exposes no idempotency key. Never silently duplicate it.
    """
    root = Path(root).resolve()
    settings = json.loads(Path(config).read_text())
    if not settings.get('thread') or not Path(settings['codex']).is_absolute():
        raise ValueError('explicit thread and Codex binary required')
    directory = root/'runtime/state/market-cleaning/notifications'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'notify.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = directory/'outbox.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else dict(thread=settings['thread'],tracked=[],events={})
        if state['thread'] != settings['thread']:
            raise ValueError('notification thread changed')
        status = json.loads((root/'runtime/state/market-cleaning/status.json').read_text())
        events = cleaning_events(root, status, state['tracked'])
        for event in events:
            if event['batch'] not in state['tracked']:
                state['tracked'].append(event['batch'])
            item = state['events'].setdefault(event['id'],dict(**event,state='PENDING'))
            if item['state'] in ('SENT','IN_FLIGHT','UNKNOWN'):
                continue
            item['state'] = 'IN_FLIGHT'
            atomic_json(state_path,state)
            try:
                result = run([settings['codex'],'queue','--thread',settings['thread'],'--message',item['message']],
                             capture_output=True,text=True,timeout=45)
            except subprocess.TimeoutExpired:
                item.update(state='UNKNOWN', error='queue timed out; reconcile before retry')
            except OSError as exc:
                item.update(state='PENDING', error=str(exc))
            else:
                item.update(state='SENT' if result.returncode == 0 else 'PENDING',
                            returncode=result.returncode, response=(result.stdout+result.stderr)[-2000:])
            atomic_json(state_path,state)
        atomic_json(state_path,state)
        return {key:item['state'] for key,item in state['events'].items()}


def notify_cleaning_poll(config, state, *, run=subprocess.run):
    """Queue scheduler-entry status immediately, before expensive data scans.

    Config supplies the thread and CLI. State is STARTED or BUSY. No data writes
    or retries: ambiguous delivery must not generate duplicate notifications.
    CLI errors propagate to the caller, which logs them without stopping work.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    if state not in ('STARTED', 'BUSY'):
        raise ValueError('invalid poll state')
    settings = json.loads(Path(config).read_text())
    if not settings.get('thread') or not Path(settings['codex']).is_absolute():
        raise ValueError('explicit thread and Codex binary required')
    timestamp = datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d %H:%M:%S')
    detail = ('已进入自动检查，将核验待清洗期次并按50期推进；尚未表示批次已冻结。'
              if state == 'STARTED' else '定时检查已触发，上一轮仍在运行，本轮不重复启动。')
    message = f'【盘口定时检查】北京时间 {timestamp}。{detail}此消息为自动进度通知，请简要转告用户，不要据此重复启动任务。'
    result = run([settings['codex'], 'queue', '--thread', settings['thread'], '--message', message],
                 capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr or 'Codex queue failed')
    return dict(state=state, timestamp=timestamp, output=result.stdout)
