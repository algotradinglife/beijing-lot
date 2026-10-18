"""Assemble exact cache-only checkpoints through the existing whole-issue publisher."""
import gc,hashlib,json,pickle
import beidan_backend,importlib
from datetime import datetime,timezone
from pathlib import Path
from beidan_backend.source_market_publication import publish_market_issue,market_complete
control=Path(__file__).resolve().parent
checkpoint=control/'parsed-batches-v1'
out=Path('results/global-dynamic-26105-euro-publish-20261019-v3')
backend_root=Path(beidan_backend.__file__).resolve().parent
backend_files=sorted(backend_root.rglob('*.py'))
backend_before={str(p.relative_to(backend_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in backend_files}
roster_path=Path('results/global-dynamic-26105-readiness-20261018-v4/frozen-roster.json')
roster_sha=hashlib.sha256(roster_path.read_bytes()).hexdigest()
assert roster_sha=='bb6355e04281cb3b980bdf19477a89b309b1380fcfc37fd31b0c0716acc8feed'
parser_sha=hashlib.sha256((control/'parse-batches-v1.py').read_bytes()).hexdigest()
client_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
result=None;bindings=[]
for first in range(1,366,10):
    target=checkpoint/f'{first:03d}.pickle';receipt_path=checkpoint/f'{first:03d}.json'
    binding=json.loads(receipt_path.read_bytes())
    assert binding['roster_input_sha256']==roster_sha and binding['script_sha256']==parser_sha
    assert hashlib.sha256(target.read_bytes()).hexdigest()==binding['pickle_sha256']
    with target.open('rb') as stream:part=pickle.load(stream)
    assert binding['receipt']==part['receipt']
    assert binding['slots']==list(range(first,min(first+10,366)))
    assert part['receipt']['network_attempts']==0 and part['receipt']['roster_slots']==365
    if result is None:result=part
    else:
        for key in ['implementation_sha256','roster_receipt','roster_sha256']:
            assert part['receipt'][key]==result['receipt'][key], 'Cross-batch source/code mutation'
        for key in result['tables']:result['tables'][key].extend(part['tables'][key])
    bindings.append(dict(first_slot=first,receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),pickle_sha256=binding['pickle_sha256']))
    del part;gc.collect()
# Match actual installed parser implementations, not merely agreement among checkpoints.
implementation_paths={}
for module_name in ['source_issue_markets','fundamentals','dual_euro','source_extraction',
    'extraction_cache','transport','market_capture.history','market_capture.service',
    'unified_sources','source_market_publication','issue_schedule.contract',
    'issue_schedule.sources','issue_schedule.decode']:
    module=importlib.import_module('beidan_backend.'+module_name)
    path=Path(module.__file__).resolve()
    assert path.name not in implementation_paths
    implementation_paths[path.name]=path
assert set(implementation_paths)==set(result['receipt']['implementation_sha256'])
for name,expected in result['receipt']['implementation_sha256'].items():
    assert hashlib.sha256(implementation_paths[name].read_bytes()).hexdigest()==expected, 'Installed parsing implementation differs'
assert len(result['tables']['status'])==365 and len(result['tables']['resources'])==730
assert sorted(r['slot'] for r in result['tables']['status'])==list(range(1,366))
assert all(r['state'] in {'VERIFIED','EMPTY'} for r in result['tables']['resources'])
receipt=result['receipt']
receipt.update(expected_slots=365,generated_at=datetime.now(timezone.utc).isoformat(),
    input_sha256=sorted({r['sha256'] for r in result['tables']['provenance']}),
    complete=market_complete(result['tables']))
receipt['parameters']['slots']=list(range(1,366))
assert hashlib.sha256(roster_path.read_bytes()).hexdigest()==roster_sha
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==client_sha
assert {str(p.relative_to(backend_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(backend_root.rglob('*.py'))}==backend_before
if out.exists() and not (out/'publication.json').exists():
    preserved=out.with_name(out.name+'.interrupted-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.rename(preserved)
    print('Preserved interrupted attempt: '+str(preserved),flush=True)
completed=out.exists()
if not completed:out.mkdir()
# Persist only small prepublication evidence; never claim partial tables were published.
assembly_record=dict(roster_input_sha256=roster_sha,
    client_sha256=client_sha,batches=bindings,table_rows={k:len(v) for k,v in result['tables'].items()},
    model_admission=False,receipt=receipt,backend_sha256=backend_before)
if completed:
    prior_assembly=json.loads((out/'assembly-receipt.json').read_bytes())
    for key in ['roster_input_sha256','client_sha256','batches','table_rows','backend_sha256']:
        assert prior_assembly[key]==assembly_record[key], 'Completed output identity differs'
else:
    with (out/'assembly-receipt.json').open('x') as stream:json.dump(assembly_record,stream,indent=2)
print('Whole365 assembled; beginning authoritative validation/publication',flush=True)
publication=publish_market_issue(result)
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==client_sha
assert {str(p.relative_to(backend_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(backend_root.rglob('*.py'))}==backend_before
if completed:
    prior=json.loads((out/'publication.json').read_bytes())
    assert prior['publication']['dataset']==publication['dataset'] and prior['publication']['version']==publication['version']
    assert prior['assembly_receipt_sha256']==hashlib.sha256((out/'assembly-receipt.json').read_bytes()).hexdigest()
    print('Verified completed output and idempotent authoritative publication',flush=True)
    raise SystemExit(0)
(out/'publication.json').write_text(json.dumps(dict(receipt=receipt,publication=publication,
    model_admission=False,roster_input_sha256=roster_sha,client_sha256=client_sha,
    assembly_receipt_sha256=hashlib.sha256((out/'assembly-receipt.json').read_bytes()).hexdigest()),indent=2))
print(json.dumps(publication),flush=True)
