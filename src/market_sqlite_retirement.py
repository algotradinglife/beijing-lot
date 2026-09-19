"""Prepare exact raw-file retirement candidates; no deletion or approval."""
import hashlib
from pathlib import Path


def verify_retirement_capture_bindings(data_root, plan, captures, *, batch_id):
    """Require each candidate path/hash to belong to the specified stored batch.

    Captures come from the verified SQLite query API. This gate prevents a
    reviewed candidate list from retiring unrelated raw files. It performs no
    writes and does not replace backup, review or consumer-reference checks.
    Unknown candidates, conflicting aliases or another batch raise ValueError.
    """
    import os
    import re
    root = Path(data_root).resolve(strict=True)
    if not batch_id or plan.get('batch_id') != batch_id:
        raise ValueError('retirement batch mismatch')
    identities = {}
    for capture in captures:
        if capture.get('kind') != 'capture' or capture.get('batch_id') != batch_id:
            raise ValueError('capture batch mismatch')
        aliases = capture['data'].get('path_aliases', [capture['data']['path']])
        if (not isinstance(aliases, list) or capture['data']['path'] not in aliases or
                any(not isinstance(name, str) or not name for name in aliases)):
            raise ValueError('invalid capture aliases')
        for name in aliases:
            path = os.path.abspath(root / name)
            digest = capture['source_sha256']
            if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
                raise ValueError('invalid capture source hash')
            if path in identities and identities[path] != digest:
                raise ValueError('conflicting capture aliases')
            identities[path] = digest
    for candidate in plan['candidates']:
        path = os.path.abspath(root / candidate['path'])
        if path not in identities or identities[path] != candidate['sha256']:
            raise ValueError('candidate not bound to stored capture')
    return dict(state='RETIREMENT_CAPTURE_BINDINGS_VERIFIED', batch_id=batch_id,
                candidates=len(plan['candidates']), raw_deletion_authorized=False)


def market_followup_reference_paths(documents, captures):
    """Protect source aliases mentioned by follow-up or decision documents.

    Caller supplies the complete frozen follow-up/decision documents, not all
    provenance ledgers. Any matching source hash or path protects every alias of
    that capture, including relocated copies. This conservative read-only rule
    may retain extra files; it never establishes that document coverage is full.
    Returns sorted paths. Invalid capture identities raise ValueError.
    """
    strings = set()
    pending = list(documents)
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            pending.extend(value)
        elif isinstance(value, str):
            strings.add(value)
    protected = set()
    for capture in captures:
        if capture.get('kind') != 'capture':
            raise ValueError('capture records required')
        aliases = capture['data'].get('path_aliases', [capture['data']['path']])
        if (not isinstance(aliases, list) or not aliases or capture['data']['path'] not in aliases or
                any(not isinstance(path, str) or not path for path in aliases)):
            raise ValueError('invalid capture aliases')
        if capture['source_sha256'] in strings or strings.intersection(aliases):
            protected.update(aliases)
    return sorted(protected)


def plan_market_raw_retirement(data_root, captures, *, protected_paths):
    """Inventory imported raw JSONs excluding all known active/shared references.

    captures: iterable of SQLite capture records, including original response
    hash, URL and data.path. protected_paths: explicit paths still required by
    other issues/consumers. Only files under markets/raw are candidates; archived
    historical names and other data domains remain untouched. Every candidate's
    current bytes must match the imported source hash. Returns candidate and
    excluded lists plus allocated bytes. This does not authorize deletion.
    """
    root=Path(data_root).resolve(strict=True)
    raw=(root/'markets/raw').resolve(strict=True)
    protected={str((root/p).resolve()) for p in protected_paths}
    seen={};candidates=[];excluded=[]
    for record in captures:
        if record.get('kind')!='capture':
            raise ValueError('capture records required')
        aliases=record['data'].get('path_aliases',[record['data']['path']])
        if not isinstance(aliases,list) or any(not isinstance(name,str) or not name for name in aliases):
            raise ValueError('invalid capture aliases')
        if record['data']['path'] not in aliases:
            raise ValueError('primary path missing from aliases')
        for name in aliases:
            path=(root/name).resolve()
            digest=record['source_sha256']
            if str(path) in seen:
                if seen[str(path)]!=digest:
                    raise ValueError('conflicting retirement source hashes')
                continue
            seen[str(path)]=digest
            if not path.is_relative_to(raw) or path.suffix!='.json':
                excluded.append(dict(path=name,reason='OUTSIDE_RAW_JSON_SCOPE'));continue
            if str(path) in protected:
                excluded.append(dict(path=name,reason='ACTIVE_OR_SHARED_REFERENCE'));continue
            if not path.is_file():
                raise ValueError(f'candidate source missing: {name}')
            with path.open('rb') as source:
                if hashlib.file_digest(source,'sha256').hexdigest()!=digest:
                    raise ValueError('retirement source hash mismatch')
            stat=path.stat()
            candidates.append(dict(path=str(path.relative_to(root)),sha256=digest,
                                   source_url=record['source_url'],bytes=stat.st_size,
                                   allocated_bytes=stat.st_blocks*512))
    return dict(state='PLAN_ONLY_NOT_AUTHORIZED',candidates=candidates,excluded=excluded,
                allocated_bytes=sum(r['allocated_bytes'] for r in candidates))


def market_reference_paths(capture_indexes, unconverted_issue_rows, *, replay_decisions=()):
    """Collect exact paths still needed by collection and unconverted issues.

    Inputs are already verified decoded indexes and audit rows, not directory
    guesses. Include selected responses AND every retry. Missing path fields
    fail instead of weakening protection. Returns sorted unique path strings.
    Accepted SQLite references are verified before their raw path is released.
    Caller must bind input hashes and revalidate them before any deletion.
    replay_decisions supplies frozen decisions whose replay still consumes raw
    evidence; all their bound files stay protected even with a SQLite capture.
    """
    paths=set()
    for index in capture_indexes:
        if not isinstance(index,dict):
            raise ValueError('capture index must be an object')
        for key, entry in index.items():
            references=list(entry.get('attempts',[]))
            if entry.get('selected') is not None:
                references.append(entry['selected'])
            for reference in references:
                path=reference.get('path')
                if not isinstance(path,str) or not path:
                    raise ValueError('capture reference path missing')
                if 'storage' in reference:
                    from src.fundamentals_market_history import verify_selected_market_receipt
                    # A storage marker alone is not proof of cutover: verify the
                    # accepted batch, exact source and database record binding.
                    verify_selected_market_receipt(reference, key)
                else:
                    paths.add(path)
    for row in unconverted_issue_rows:
        hashes=row.get('source_hashes')
        if not isinstance(hashes,dict) or not hashes:
            raise ValueError('unconverted source references missing')
        capture=row.get('capture_path')
        if capture and capture not in hashes:
            raise ValueError('unconverted capture missing from source bindings')
        storage=row.get('storage')
        if storage is not None:
            if not capture:
                raise ValueError('stored audit capture path missing')
            from src.fundamentals_market_history import verify_selected_market_receipt
            verify_selected_market_receipt(dict(path=capture,sha256=hashes[capture],storage=storage),
                                           row['market']+':'+row['provider_id'])
        paths.update(name for name in hashes if storage is None or name!=capture)
    for decision in replay_decisions:
        files=decision.get('files')
        required=[decision.get('capture_path'),decision.get('roster_path')]
        required.extend(decision[k] for k in ('peer_path','independent_evidence_path') if k in decision)
        if not isinstance(files,dict) or any(not name or name not in files for name in required):
            raise ValueError('decision replay source bindings missing')
        paths.update(files)
    return sorted(paths)


def execute_market_raw_retirement(data_root, plan, *, journal_path, verify_acceptance):
    """Retire exact planned JSON files after caller verifies all acceptance gates.

    verify_acceptance(plan) must validate the frozen review/backup/cutover and
    current reference inventory, raising on failure. Called under an exclusive
    migration lock before any mutation. Journal binds the entire plan and records
    intent durably before unlink, allowing restart after interruption. Missing
    files without prior intent, changed bytes and symlinks fail closed.
    This low-level function does not itself establish batch acceptance.
    """
    import fcntl
    import json
    import os
    from src.market_storage import _publish_json
    root=Path(data_root).resolve(strict=True)
    raw=(root/'markets/raw').resolve(strict=True)
    journal_path=Path(journal_path).absolute()
    if not journal_path.parent.resolve(strict=True).is_relative_to(root/'audits/market-sqlite'):
        raise ValueError('retirement journal outside audit scope')
    if journal_path.is_symlink():
        raise ValueError('retirement journal symlink')
    encoded=json.dumps(plan,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest=hashlib.sha256(encoded).hexdigest()
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify_acceptance(plan)
        journal=json.loads(journal_path.read_text()) if journal_path.exists() else {
            'plan_sha256':digest,'entries':{}}
        if journal.get('plan_sha256')!=digest:
            raise ValueError('retirement journal plan mismatch')
        candidates=plan['candidates']
        names=[item['path'] for item in candidates]
        if len(set(names))!=len(names) or set(journal['entries'])-set(names):
            raise ValueError('retirement inventory mismatch')
        # Preflight the whole batch before the first unlink.
        for item in candidates:
            path=root/item['path']
            if (path.is_symlink() or path.absolute()!=path.resolve() or
                    not path.resolve().is_relative_to(raw) or path.suffix!='.json'):
                raise ValueError('unsafe retirement path')
            previous=journal['entries'].get(item['path'])
            if previous and previous not in ('DELETE_INTENT','REMOVED'):
                raise ValueError('invalid retirement journal state')
            if not path.exists():
                if not previous:raise ValueError('source missing without retirement intent')
                continue
            if previous=='REMOVED':raise ValueError('retired source reappeared')
            with path.open('rb') as source:
                if hashlib.file_digest(source,'sha256').hexdigest()!=item['sha256']:
                    raise ValueError('retirement source hash mismatch')
        for item in candidates:
            name=item['path'];path=root/name
            if journal['entries'].get(name)=='REMOVED':continue
            journal['entries'][name]='DELETE_INTENT'
            _publish_json(journal_path,journal)
            if path.exists():
                with path.open('rb') as source:
                    if hashlib.file_digest(source,'sha256').hexdigest()!=item['sha256']:
                        raise ValueError('retirement source changed before deletion')
                path.unlink()
                descriptor=os.open(path.parent,os.O_RDONLY)
                try:os.fsync(descriptor)
                finally:os.close(descriptor)
            journal['entries'][name]='REMOVED'
            _publish_json(journal_path,journal)
        return dict(state='RAW_RETIREMENT_COMPLETE',plan_sha256=digest,
                    removed_files=len(journal['entries']))


def verify_retirement_reference_exclusion(data_root, plan, *, snapshots, protected_paths):
    """Check frozen consumer inputs and exclude every still-required raw path.

    snapshots maps persistent input paths to SHA256 digests (registry, indexes,
    publication and decision inventories). Caller establishes inventory coverage
    and holds writer locks. This read-only check is one retirement gate, not
    content acceptance or deletion authorization. Missing inputs raise
    FileNotFoundError; changed inputs, unsafe candidate names and protected
    candidates raise ValueError.
    """
    root = Path(data_root).resolve(strict=True)
    if not isinstance(snapshots, dict) or not snapshots:
        raise ValueError('reference snapshots required')
    for name, expected in snapshots.items():
        path = root / name
        if path.is_symlink() or path.absolute() != path.resolve() or not path.resolve().is_relative_to(root):
            raise ValueError('unsafe reference snapshot path')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('reference snapshot changed: ' + str(name))
    protected = {str((root / name).resolve()) for name in protected_paths}
    names = set()
    for candidate in plan['candidates']:
        name = candidate['path']
        path = root / name
        if (Path(name).is_absolute() or '..' in Path(name).parts or
                path.is_symlink() or path.absolute() != path.resolve() or
                not path.resolve().is_relative_to(root / 'markets/raw') or path.suffix != '.json'):
            raise ValueError('unsafe retirement candidate')
        if name in names:
            raise ValueError('duplicate retirement candidate')
        names.add(name)
        if str(path.resolve()) in protected:
            raise ValueError('retirement candidate still referenced: ' + name)
    return dict(state='REFERENCE_EXCLUSION_VERIFIED', candidates=len(names),
                snapshots=len(snapshots), protected_paths=len(protected),
                raw_deletion_authorized=False)
