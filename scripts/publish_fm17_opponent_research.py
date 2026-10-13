"""Thin explicit staging-to-catalog client, with verified local input hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pyarrow.parquet as pq
from beidan_backend.opponent_publication import publish_opponent_research
from beidan_backend.versioning import write_json_atomically
from beidan_backend.temporal_learning.provenance import implementation_closure


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--staging',required=True)
    parser.add_argument('--label',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();staging=Path(args.staging)
    manifest=json.loads((staging/'manifest.json').read_bytes())
    if hashlib.sha256((staging/'receipt.json').read_bytes()).hexdigest()!=manifest['receipt_sha256']:
        raise ValueError('Staging receipt digest differs')
    tables={}
    for name,sha in manifest['tables'].items():
        p=staging/(name+'.parquet')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Staging table digest differs')
        tables[name]=pq.read_table(p)  # Declared local NVMe staging, never NAS reads.
    receipt=json.loads((staging/'receipt.json').read_bytes())
    receipt['publication_implementation']=implementation_closure(Path.cwd(),('beidan_backend.opponent_publication',),
        distributions=('pyarrow','pandas','numpy','filelock'))
    receipt['publication_client_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result=publish_opponent_research(tables,receipt,args.label,environ=dict(os.environ),repository_root=Path.cwd())
    write_json_atomically(result,Path(args.output));print(json.dumps(result))
