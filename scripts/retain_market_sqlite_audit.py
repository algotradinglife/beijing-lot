"""Retain explicitly selected cleaning evidence for an imported SQLite batch."""
import argparse
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.market_sqlite import open_market_database,backup_market_batch,verify_market_batch_backup
from src.market_sqlite_audit import collect_market_audit_evidence,collect_archived_market_audit,store_market_audit_evidence
from src.market_sqlite_query import query_market_audit_evidence
from src.market_storage import _publish_json
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',required=True)
    parser.add_argument('--plan',required=True,help='Explicit JSON plan under persistent data root')
    args=parser.parse_args()
    project=Path(__file__).resolve().parents[1]
    root=Path(args.data_root).resolve(strict=True)
    contract=project/'config/persistent_data_layout.json'
    if root!=Path(json.loads(contract.read_text())['data_root']).resolve(strict=True):
        raise ValueError('data root differs from contract')
    subprocess.run([sys.executable,str(project/'scripts/check_persistent_data_layout.py'),'--contract',str(contract)],check=True)
    plan_path=(root/args.plan).resolve(strict=True)
    plan_path.relative_to(root)
    plan_bytes=plan_path.read_bytes()
    plan=json.loads(plan_bytes)
    code=implementation_closure(project,('src.market_sqlite_audit','src.market_sqlite','src.market_sqlite_query'))['files']
    code[str(Path(__file__).relative_to(project))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    batch=plan['batch_id']
    if not batch or Path(batch).name!=batch or batch in ('.','..'):
        raise ValueError('unsafe batch identity')
    audit=root/'audits/market-sqlite'/batch
    evidence=collect_market_audit_evidence(root,plan['acceptance_paths'],issues=plan['issues'])
    for archived in plan.get('archived_evidence',[]):
        evidence.append(collect_archived_market_audit(root,**archived))
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if plan_path.read_bytes()!=plan_bytes:
            raise ValueError('audit retention plan changed during verification')
        with closing(open_market_database(root/'markets/releases/market-history-v1.sqlite')) as db:
            store_market_audit_evidence(db,batch_id=batch,evidence=evidence)
            loaded=query_market_audit_evidence(root/'markets/releases/market-history-v1.sqlite',batch_id=batch)
            if loaded!=sorted(evidence,key=lambda e:e['acceptance_path']):
                raise ValueError('audit readback mismatch')
            backup=audit/'market-history-with-audits.sqlite'
            if backup.exists():
                digest=verify_market_batch_backup(db,backup,batch_id=batch)
            else:
                digest=backup_market_batch(db,backup,batch_id=batch)
            if query_market_audit_evidence(backup,batch_id=batch)!=loaded:
                raise ValueError('audit backup readback mismatch')
            _publish_json(audit/'audit-retention-receipt.json',dict(
                state='AUDIT_RETAINED_BACKED_UP_PENDING_CUTOVER',batch_id=batch,
                plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),implementation_hashes=code,
                evidence_documents=len(loaded),backup=str(backup),backup_sha256=digest))
