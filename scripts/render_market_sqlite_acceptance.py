"""Render a real batch QMD and bind successful output to inputs and implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_batch import verified_market_json
from src.market_sqlite_acceptance import market_storage_implementation
from src.market_storage import _publish_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('contract','batch-id','quarto'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project=Path(__file__).resolve().parents[1]
    batch=args.batch_id
    if Path(batch).name!=batch or batch in ('.','..'):raise ValueError('unsafe batch id')
    audit=root/'audits/market-sqlite'/batch
    names={'import':'import-receipt.json','inventory':'source-inventories.json','publication':'publication-staging-receipt.json'}
    inputs={role:dict(path=str((audit/name).relative_to(root)),sha256=hashlib.sha256((audit/name).read_bytes()).hexdigest())
            for role,name in names.items()}
    imported=verified_market_json(root/inputs['import']['path'],inputs['import']['sha256'])
    code=market_storage_implementation(project)
    report=root/'reports/market-sqlite'/batch/'verified-render'
    report.mkdir(parents=True,exist_ok=True)
    source=report/'report.qmd';source.write_bytes((project/'quarto/market_sqlite_migration.qmd').read_bytes())
    params=dict(repository_root=str(project),database=imported['database'],issue=imported['issues'][0],
                batch_id=batch,python=sys.executable)
    _publish_json(report/'params.json',params)
    with (report/'render.log').open('w') as log:
        subprocess.run([args.quarto,'render',str(source),'--execute-params',str(report/'params.json'),
                        '--execute','--no-cache'],check=True,stdout=log,stderr=subprocess.STDOUT)
    if market_storage_implementation(project)!=code:raise ValueError('implementation changed during render')
    for ref in inputs.values():verified_market_json(root/ref['path'],ref['sha256'])
    html=report/'report.html'
    receipt=dict(state='QMD_RENDER_VERIFIED',batch_id=batch,issues=imported['issues'],database=imported['database'],
        implementation_hashes=code,input_evidence=inputs,html=str(html),html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),
        qmd_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),params=params)
    _publish_json(audit/'report-receipt.json',receipt)
    print(json.dumps(dict(state=receipt['state'],html=str(html))))
