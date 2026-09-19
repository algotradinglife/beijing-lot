"""Bounded unique-page workers. Only the caller publishes shared checkpoints."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil

from src.fundamentals_bulk_capture import atomic_json
from src.fundamentals_capture import TRANSIENT_STATUSES
from src.fundamentals_history_capture import capture_history_batch, CaptureCircuitOpen


def capture_market_key(key, output, *, ledger_path, budget_id, request_budget,
                       min_free_bytes, min_interval_seconds, sleeper,
                       wall_clock=None, fetch=None, disk_free=None, stop_event=None, on_attempt=None):
    """Capture/replay one unique market key, at most two durable attempts.

    Returns selected receipt, newly committed manifests and optional stop reason.
    Caller must own output/worker.lock and dispatch each key only once at a time.
    Each call owns its HTTP session; input/output are explicit persistent paths.
    No shared progress or in-memory cache is mutated here.
    """
    # Local import avoids an import-time cycle with the coordinating runner.
    from src.fundamentals_market_history import market_document, index_market_captures
    document = market_document(key)
    directory = Path(output) / 'responses' / key.replace(':', '-')
    committed = []
    interrupted = []
    for attempt in (1, 2):
        if stop_event is not None and stop_event.is_set():
            return dict(indexed=None, committed=committed, stop="CIRCUIT_OPEN")
        target = directory / f'attempt-{attempt:02d}'
        manifest = target / 'capture-manifest.json'
        reservation = directory / f'attempt-{attempt:02d}.json'
        if reservation.exists() and not manifest.exists():
            interrupted.append(dict(path=str(reservation),
                sha256=hashlib.sha256(reservation.read_bytes()).hexdigest(),
                state='INTERRUPTED', status=None,
                received_at_utc=json.loads(reservation.read_text())['received_at_utc']))
            continue
        if not manifest.exists():
            if (disk_free(output) if disk_free else shutil.disk_usage(output).free) < min_free_bytes:
                return dict(indexed=None, committed=committed, stop='DISK_SPACE_LOW')
            while True:
                if stop_event is not None and stop_event.is_set():
                    return dict(indexed=None, committed=committed, stop="CIRCUIT_OPEN")
                atomic_json(reservation, dict(url=document['url'], error='INTERRUPTED_OR_RESERVED',
                    received_at_utc=datetime.now(timezone.utc).isoformat()))
                try:
                    capture_history_batch([document], target, ledger_path=ledger_path,
                        budget_id=budget_id, request_budget=request_budget,
                        min_interval_seconds=min_interval_seconds, wall_clock=wall_clock,
                        sleeper=sleeper, fetch=fetch, cancel_event=stop_event)
                    committed.append(str(manifest))
                    break
                except CaptureCircuitOpen:
                    reservation.unlink()
                    return dict(indexed=None, committed=committed, stop="CIRCUIT_OPEN")
                except BlockingIOError:
                    reservation.unlink()
                    sleeper(0.1)
                except ValueError as exc:
                    if 'budget exhausted' not in str(exc):
                        raise
                    reservation.unlink()
                    return dict(indexed=None, committed=committed, stop='BUDGET_EXHAUSTED')
        indexed = index_market_captures([manifest])[key]
        chosen = indexed['selected']
        if str(manifest) in committed and on_attempt is not None:
            on_attempt(key, manifest, chosen)
        if chosen['status'] not in TRANSIENT_STATUSES and chosen['state'] != 'TRANSPORT_FAILURE':
            return dict(indexed=indexed, committed=committed, stop=None)
        if attempt == 2:
            return dict(indexed=indexed, committed=committed, stop=None)
    return dict(indexed=dict(attempts=interrupted, selected=interrupted[-1]),
                committed=committed, stop=None)
