"""Verify a completed prediction batch and bind its allocation-only catalog.

CLI: project-python scripts/catalog_n7_expanded_batch.py BATCH REPOSITORY_ROOT
No labels, fitting or writes to input artifacts. Existing catalogs fail closed.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

from src.temporal_learning import verify_implementation_closure
from src.temporal_learning.core import stable_json_hash

batch,root=map(Path,sys.argv[1:]);out=batch/'catalog.json'
if out.exists():raise ValueError('Catalog already exists')
receipt_path=batch/'batch-receipt.json';raw=receipt_path.read_bytes();receipt=json.loads(raw)
sources={str(receipt_path):hashlib.sha256(raw).hexdigest()}
for name,identity in receipt['files'].items():
    path=batch/name
    if hashlib.sha256(path.read_bytes()).hexdigest()!=identity:raise ValueError('Batch changed: '+name)
    sources[str(path)]=identity
candidate=json.loads((batch/'candidates/candidate-manifest.json').read_text())
c=candidate['receipt']
if candidate['seal']!=stable_json_hash(c) or c['historical_admission'] is not False:
    raise ValueError('Invalid candidate seal/admission')
if c['requested_issues']!=receipt['issues']:raise ValueError('Batch issue scope differs')
verify_implementation_closure(root,c['implementation'])
issues=[]
for path,identity in {**c['source_hashes'],**c['pool_hashes'],**c['bundle_hashes']}.items():
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=identity:raise ValueError('Candidate source changed: '+path)
    sources[path]=identity
    if path in c['bundle_hashes']:
        bundle=json.loads(gzip.decompress(raw))
        if bundle['issue'] not in c['issues']:raise ValueError('Unexpected bundle issue')
        issues.append(dict(issue=bundle['issue'],path=path,sha256=identity))
if len(issues)!=len(c['issues']) or {i['issue'] for i in issues}!=set(c['issues']):
    raise ValueError('Incomplete or duplicate bundle scope')
out.write_text(json.dumps(dict(issues=sorted(issues,key=lambda r:r['issue']),
    requested_issues=c['requested_issues'],unavailable=c['unavailable'],source_hashes=sources,
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),historical_admission=False),indent=2))
print('Bound catalog',len(issues),'candidate issues;',len(c['unavailable']),'cash issues')
