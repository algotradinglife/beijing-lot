"""Publish content acceptance for SQLite reader cutover, never raw deletion."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_acceptance import prepare_market_storage_acceptance,market_storage_implementation
from src.market_storage import _publish_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--evidence',required=True,help='Hash-bound five-role evidence manifest under data root')
    args=parser.parse_args()
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project=Path(__file__).resolve().parents[1]
    path=(root/args.evidence).resolve(strict=True);path.relative_to(root)
    raw=path.read_bytes();evidence=json.loads(raw)
    code=market_storage_implementation(project)
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=prepare_market_storage_acceptance(root,evidence=evidence,implementation_hashes=code)
        database=Path(result['database']).resolve(strict=True);database.relative_to(root)
        if path.read_bytes()!=raw:raise ValueError('acceptance inputs changed')
        for name,digest in code.items():
            if hashlib.sha256((project/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('implementation changed during acceptance')
        batch=result['batch_id']
        if Path(batch).name!=batch or batch in ('.','..'):raise ValueError('unsafe batch id')
        output=root/'audits/market-sqlite'/batch/'storage-acceptance.json'
        if output.exists() and json.loads(output.read_text())!=result:
            raise ValueError('immutable storage acceptance already differs')
        _publish_json(output,result)
        print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                              state=result['state'],raw_deletion_authorized=False)))
