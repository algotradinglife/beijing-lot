"""Post-freeze label adapter: accepted rosters plus original bound audit rows.

CLI: project-python scripts/prepare_n7_expanded_labels.py CONFIG
Never called before the full new prediction grid is frozen and replayed.
Preserves old allocations; old settlement is rechecked against current SQLite.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

from src.temporal_learning import verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_home_away import roster_observed_results
from src.n7_purchase_labels import bind_purchase_roster_labels

cfg=json.loads(Path(sys.argv[1]).read_text());study=Path(cfg['study'])
freeze_path=study/'all-plans-frozen.json';freeze_raw=freeze_path.read_bytes();freeze=json.loads(freeze_raw)
if freeze['status']!='ALL_PREDICTIONS_FROZEN_BEFORE_TARGET_SETTLEMENT':raise ValueError('Incomplete prediction freeze')
sources={str(freeze_path):hashlib.sha256(freeze_raw).hexdigest()}
label_implementation=Path(cfg['repository_root'])/'src/n7_purchase_labels.py'
sources[str(label_implementation)]=hashlib.sha256(label_implementation.read_bytes()).hexdigest()
for path,sha in freeze['files'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Prediction freeze changed')
    sources[path]=sha
# Receipts alone are insufficient: replay must still bind every plan/snapshot
# and its complete source/implementation graph immediately before label access.
verified_issues=[]
for path in freeze['files']:
    if Path(path).name!='plans-frozen.json':continue
    batch_path=Path(path);batch_raw=batch_path.read_bytes();batch=json.loads(batch_raw)
    catalog_path=Path(batch['config']['catalog']);catalog_raw=catalog_path.read_bytes()
    if hashlib.sha256(catalog_raw).hexdigest()!=batch['config']['catalog_sha256']:
        raise ValueError('Frozen allocation catalog changed')
    verified_issues.extend(json.loads(catalog_raw)['requested_issues'])
    proof_path=batch_path.parent/'prediction-replay.json'
    if str(proof_path) not in freeze['files']:raise ValueError('Missing batch replay binding')
    proof=json.loads(proof_path.read_text())
    if proof['status']!='PASS' or proof['freeze_sha256']!=hashlib.sha256(batch_raw).hexdigest():
        raise ValueError('Batch replay no longer binds freeze')
    for name,identity in batch['files'].items():
        p=batch_path.parent/name
        if hashlib.sha256(p.read_bytes()).hexdigest()!=identity:raise ValueError('Frozen allocation content changed')
        sources[str(p)]=identity
    for p,identity in batch['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=identity:raise ValueError('Frozen allocation source changed')
        sources[p]=identity
    for name,identity in {**batch['implementation'],**proof['implementation']}.items():
        if hashlib.sha256((Path(cfg['repository_root'])/name).read_bytes()).hexdigest()!=identity:
            raise ValueError('Frozen allocation/replay implementation changed')
    upstream=batch_path.parent.parent
    manifest=json.loads((upstream/'candidates/candidate-manifest.json').read_text())
    if manifest['seal']!=stable_json_hash(manifest['receipt']):raise ValueError('Candidate seal changed')
    verify_implementation_closure(Path(cfg['repository_root']),manifest['receipt']['implementation'])
    prediction=json.loads((upstream/'probabilities/predictions.json').read_text())
    for name,identity in prediction['projection_implementation'].items():
        if hashlib.sha256((Path(cfg['repository_root'])/name).read_bytes()).hexdigest()!=identity:
            raise ValueError('Upstream projection implementation changed')
    for model in prediction['models'].values():
        p=Path(model['path']);raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=model['sha256']:raise ValueError('Bound model changed')
        model_artifact=json.loads(raw)
        verify_implementation_closure(Path(cfg['repository_root']),model_artifact['receipt']['implementation'])
        sources[str(p)]=model['sha256']
if sorted(verified_issues)!=sorted(freeze['requested_issues']) or len(set(verified_issues))!=len(verified_issues):
    raise ValueError('Incomplete or repeated pre-label batch grid')
out=study/'settlement-inputs'
if out.exists():raise ValueError('Settlement inputs exist')
input_receipt=json.loads((study/'inputs/input-receipt.json').read_text())
if hashlib.sha256((study/'inputs/input-receipt.json').read_bytes()).hexdigest()!=freeze['source_receipt_sha256']:
    raise ValueError('Input receipt changed')
if (len(verified_issues)!=input_receipt['issues'] or sorted(verified_issues)!=
        sorted(i for batch in input_receipt['batches'] for i in batch['issues'])):
    raise ValueError('Frozen grid differs from accepted input scope')
catalog_raw=Path(cfg['old_catalog']).read_bytes()
if hashlib.sha256(catalog_raw).hexdigest()!=cfg['old_catalog_sha256']:raise ValueError('Old catalog changed')
sources[cfg['old_catalog']]=cfg['old_catalog_sha256']
catalog=json.loads(catalog_raw);items=catalog['issues'].copy();labels=[]
rank_receipt_path=Path(cfg['old_ranks'])/'receipt.json'
if hashlib.sha256(rank_receipt_path.read_bytes()).hexdigest()!=cfg['old_rank_receipt_sha256']:
    raise ValueError('Original rank evidence changed')
sources[str(rank_receipt_path)]=cfg['old_rank_receipt_sha256']
old_rows={}
for bound in json.loads(rank_receipt_path.read_text())['sources']:
    old=Path(bound['study']);ep=old/'evaluation-receipt.json'
    if hashlib.sha256(ep.read_bytes()).hexdigest()!=bound['evaluation_sha256']:raise ValueError('Old evaluation changed')
    e=json.loads(ep.read_text());ap=old/'audit-snapshot.json';araw=ap.read_bytes()
    if hashlib.sha256(araw).hexdigest()!=e['audit_sha256']:raise ValueError('Old audit changed')
    sources[str(ep)]=bound['evaluation_sha256'];sources[str(ap)]=e['audit_sha256']
    for row in json.loads(araw)['rows']:
        key=str(row['issue']),int(row['slot']),str(row['provider_id'])
        if key in old_rows and row!=old_rows[key]:raise ValueError('Conflicting old accepted audit')
        old_rows[key]=row
for i in items:
    raw=Path(i['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=i['sha256']:raise ValueError('Old bundle changed')
    bundle=json.loads(gzip.decompress(raw));i['cohort']='原200期'
    for f in bundle['expanded_pool']['fixtures']:
        old=old_rows[str(f['issue']),int(f['slot']),str(f['provider_id'])]
        labels.append({**{k:old[k] for k in ['issue','slot','provider_id','handicap','home','away','actual_home','actual_away']},
                       'result_state':'完场','cohort':'原200期'})
    sources[i['path']]=i['sha256']
for k,_ in enumerate(input_receipt['batches']):
    cp=study/f'batch-{k:03d}/catalog.json';cat=json.loads(cp.read_text())
    allocation=json.loads((study/f'batch-{k:03d}/allocations/plans-frozen.json').read_text())
    if hashlib.sha256(cp.read_bytes()).hexdigest()!=allocation['config']['catalog_sha256']:
        raise ValueError('New allocation catalog changed')
    sources[str(cp)]=hashlib.sha256(cp.read_bytes()).hexdigest()
    for i in cat['issues']:
        raw=Path(i['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=i['sha256']:raise ValueError('New bundle changed')
        bundle=json.loads(gzip.decompress(raw));issue=i['issue']
        i['cohort']='新增295期';items.append(i);sources[i['path']]=i['sha256']
        slots=[int(f['slot']) for f in bundle['expanded_pool']['fixtures']]
        rp=study/'inputs/rosters'/f'{issue}.json';rraw=rp.read_bytes()
        sha=input_receipt['roster_bindings'][issue]['sha256']
        if hashlib.sha256(rraw).hexdigest()!=sha:raise ValueError('Roster changed')
        sources[str(rp)]=sha
        meta,html=read_response(rp)
        inventory=issue_analysis_pages(html,roster_url=meta['url'],issue=issue,slots=slots)
        outcomes=roster_observed_results(rp,issue=issue,slots=slots)
        labels.extend(bind_purchase_roster_labels(issue,bundle['expanded_pool']['fixtures'],
                                                  inventory,outcomes,'新增295期'))
if len({(r['issue'],r['slot'],r['provider_id']) for r in labels})!=len(labels):raise ValueError('Duplicate label identity')
out.mkdir();(out/'labels.json').write_text(json.dumps(labels,allow_nan=False))
(out/'catalog.json').write_text(json.dumps(dict(issues=sorted(items,key=lambda i:i['issue']),
    requested_issues=json.loads((study/'inputs/scope.json').read_text())['all_issues'],source_hashes=sources),indent=2))
(out/'receipt.json').write_text(json.dumps(dict(config=cfg,source_hashes=sources,
    files={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['labels.json','catalog.json']},
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),historical_admission=False),indent=2))
print('Prepared post-freeze labels',len(labels),'for',len(items),'candidate issues')
