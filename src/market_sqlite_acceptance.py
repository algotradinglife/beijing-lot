"""Validate content acceptance prerequisites; never authorize raw retirement."""
import hashlib
from contextlib import closing
from pathlib import Path
from src.market_sqlite import open_market_database, verify_market_batch_backup
from src.market_sqlite_batch import verified_market_json
from src.market_sqlite_query import query_market_batch_source_inventories


def prepare_market_storage_acceptance(data_root, *, evidence, implementation_hashes):
    """Build a read-eligible storage receipt from hash-bound batch evidence.

    evidence maps import/inventory/publication/review/report to path and SHA256.
    Review must bind the exact caller-supplied implementation closure and passed
    report receipt must bind its rendered HTML. Caller validates current code
    closure, publishes immutably under the migration lock and performs cutover.
    Raw deletion requires a separate verified cutover/reference gate.
    """
    root=Path(data_root).resolve(strict=True)
    required={'import','inventory','publication','review','report'}
    if set(evidence)!=required or not implementation_hashes:
        raise ValueError('complete acceptance evidence required')
    documents={}
    for name,ref in evidence.items():
        path=(root/ref['path']).resolve(strict=True);path.relative_to(root)
        documents[name]=verified_market_json(path,ref['sha256'])
    imported=documents['import'];batch=imported['batch_id'];issues=imported['issues']
    if len(issues)!=50 or len(set(issues))!=50:
        raise ValueError('exact fifty-issue acceptance required')
    states={'import':'REPLAYED_BACKED_UP_PENDING_CUTOVER_REVIEW',
            'inventory':'SOURCE_INVENTORIES_BACKUP_VERIFIED_NOT_ACCEPTED',
            'publication':'PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED',
            'review':'CODEX_REVIEW_PASSED','report':'QMD_RENDER_VERIFIED'}
    for name,doc in documents.items():
        if doc.get('state')!=states[name] or doc.get('batch_id')!=batch:
            raise ValueError('acceptance evidence state/batch mismatch: '+name)
    inventory=documents['inventory'];publication=documents['publication']
    if set(publication['issues'])!=set(issues) or not inventory['source_inventories']:
        raise ValueError('acceptance scope mismatch')
    if {key.split('/',1)[0] for key in inventory['source_inventories']}!=set(issues):
        raise ValueError('source inventory must cover exact batch scope')
    if any(not key.endswith('/response') or proof.get('records',0)<1 or
           not isinstance(proof.get('sha256'),str) or len(proof['sha256'])!=64
           for key,proof in inventory['source_inventories'].items()):
        raise ValueError('invalid source inventory proof')
    if Path(inventory['database']).resolve()!=Path(imported['database']).resolve():
        raise ValueError('acceptance database mismatch')
    review=documents['review'];report=documents['report']
    if (set(report.get('issues',[]))!=set(issues) or
            Path(report.get('database','')).resolve()!=Path(imported['database']).resolve()):
        raise ValueError('report database/scope mismatch')
    if report.get('input_evidence')!={name:evidence[name] for name in ('import','inventory','publication')}:
        raise ValueError('report input evidence mismatch')
    database=Path(imported['database']).resolve(strict=True);database.relative_to(root)
    if query_market_batch_source_inventories(database,batch_id=batch)!=inventory['source_inventories']:
        raise ValueError('live source inventories differ from frozen proof')
    backup=Path(inventory['backup']).resolve(strict=True);backup.relative_to(root)
    with closing(open_market_database(database)) as connection:
        if verify_market_batch_backup(connection,backup,batch_id=batch)!=inventory['backup_sha256']:
            raise ValueError('complete batch backup hash mismatch')
    if review.get('implementation_hashes')!=implementation_hashes or review.get('findings')!=[]:
        raise ValueError('current implementation review required')
    for doc,field in ((report,'html'),(review,'review_output'),(publication,'publication')):
        artifact=(root/doc[field]).resolve(strict=True);artifact.relative_to(root)
        expected=doc['sha256'] if field=='publication' else doc[field+'_sha256']
        with artifact.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:
                raise ValueError('acceptance artifact changed: '+field)
    if report.get('implementation_hashes')!=implementation_hashes:
        raise ValueError('current implementation report required')
    return dict(state='SQLITE_BATCH_ACCEPTED',batch_id=batch,issues=issues,database=imported['database'],
                source_inventories=inventory['source_inventories'],evidence=evidence,
                implementation_hashes=implementation_hashes,raw_deletion_authorized=False,
                consumer_cutover_complete=False)


def market_storage_implementation(project_root):
    """Return one authoritative transitive code identity for report/review/acceptance.

    Includes migration modules, consumer implementations, command entry points,
    R reporting and QMD. Reads source only; no data or network effects.
    """
    from src.temporal_learning.provenance import implementation_closure
    project=Path(project_root).resolve(strict=True)
    modules=tuple('src.'+p.stem for p in sorted((project/'src').glob('market_sqlite*.py')))+(
        'src.fundamentals_scope_market','src.market_cleaning_batch','src.fundamentals_market_history',
        'src.market_capture_epoch','src.n7_published_markets')
    files=list((project/'scripts').glob('*market_sqlite*.py'))+[
        project/'scripts/prepare_market_capture_epoch.py',project/'r/market_sqlite_report.R',
        project/'quarto/market_sqlite_migration.qmd']
    entry_modules=tuple('scripts.'+file.stem for file in files if file.suffix=='.py')
    code=implementation_closure(project,modules+entry_modules+('src',))['files']
    for file in files:code[str(file.relative_to(project))]=hashlib.sha256(file.read_bytes()).hexdigest()
    return code
