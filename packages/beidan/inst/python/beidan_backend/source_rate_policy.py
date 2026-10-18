"""Explicit administration of an existing shared capture cadence; no import I/O."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import sqlite3
import time

from . import extraction_cache


def set_source_interval(cache, source, interval_seconds, *, expected_interval_seconds, reason):
    """Change one registered source interval under the capture store's writer lock.

    ``cache`` is an explicit ExtractionCache. Intervals are finite seconds,
    minimum1 for Titan/Nowscore and2.1 for Nova. ``expected_interval_seconds``
    must match the existing policy; a stale/missing policy fails closed.
    ``reason`` records the explicit authorization, not an inferred permission.
    Subsequent raw acquisitions must explicitly request this interval; conservative
    callers such as SourceClient.request may raise it again via their defaults.
    No HTTP, raw capture mutation, ledger deletion, or last-attempt reset occurs.
    Repeating an already-applied value is a state no-op with a fresh receipt.
    Transaction failures roll back and release both connection and file lock.
    This is operational administration, not a historical-learning artifact.
    """
    if not isinstance(cache, extraction_cache.ExtractionCache):
        raise TypeError('Explicit ExtractionCache required')
    if source not in {'titan', 'nowscore', 'novaapi'}:
        raise ValueError('Unknown capture source')
    floor = 2.1 if source == 'novaapi' else 1
    for value in (interval_seconds, expected_interval_seconds):
        if type(value) not in (int, float) or not math.isfinite(value) or value < floor:
            raise ValueError('Finite source interval at or above its minimum required')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Explicit nonempty authorization reason required')
    with cache.lock, closing(sqlite3.connect(cache.path)) as con:
        try:
            con.execute('BEGIN IMMEDIATE')
            before = con.execute('SELECT last_attempt,interval_sec FROM rate WHERE source=?', (source,)).fetchone()
            if before is None or before[1] != expected_interval_seconds:
                raise ValueError('Registered source interval differs from expected value')
            if not math.isfinite(before[0]) or not 0 <= before[0] <= time.time():
                raise extraction_cache.CaptureIntegrityError('Invalid last-attempt chronology')
            changed = before[1] != interval_seconds
            if changed:
                con.execute('UPDATE rate SET interval_sec=? WHERE source=?', (interval_seconds, source))
            after = con.execute('SELECT last_attempt,interval_sec FROM rate WHERE source=?', (source,)).fetchone()
            if after != (before[0], interval_seconds):
                raise extraction_cache.CaptureIntegrityError('Cadence update changed request history')
            con.commit()
        except BaseException:
            con.rollback()
            raise
    return dict(source=source,previous_interval_seconds=before[1],interval_seconds=after[1],
        last_attempt=after[0],last_attempt_preserved=True,changed=changed,reason=reason,
        observed_at=datetime.now(timezone.utc).isoformat(),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cache_implementation_sha256=hashlib.sha256(Path(extraction_cache.__file__).read_bytes()).hexdigest())
