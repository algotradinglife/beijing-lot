"""Offline domain client. No fitting, chronology admission or network requests.

Reads R-exported, hash-verified NAS fundamentals; metadata from the authoritative
raw cache must match the published provenance hashes. Produces competition/venue
keys for R to join to factual history. Missing/ambiguous metadata stays missing.
"""
import sys
import json
import hashlib
from pathlib import Path
from beidan_backend.unified_sources import SourceClient
from beidan_backend.opponent_history import parse_opponent_history
from beidan_backend.fundamentals import analysis_record
from beidan_backend.temporal_learning import implementation_closure

root=Path(sys.argv[1]).resolve()
out=root/'results/fm171-26103-draw-20261017'
x=json.loads((out/'inputs.json').read_text())
client=SourceClient()
frozen=json.loads((out/'metadata.json').read_text()) if 'replay' in sys.argv else None
pins={(p['fixture_id'],p['source'],r['url']):r['capture_id'] for p in (frozen or {}).get('packets',[]) for r in p.get('receipts',[])}
packets=[]
for f in x['fixtures']:
    id=f['fixture_id']
    # All accepted factual history in this pinned issue is selected_source=titan.
    # Do not reparse a second source whose rows are never used as fitting facts.
    assert {h['selected_source'] for h in x['history']}=={'titan'}
    for source in ('titan',):
        refs=[p for p in x['provenance'] if p['fixture_id']==id and p['source']==source]
        analysis=[p for p in refs if '/analysis/' in p['url']]
        if len(analysis)!=1:
            packets.append(dict(fixture_id=id,source=source,state='MISSING_ANALYSIS_PROVENANCE'))
            continue
        receipts=[]
        try:
            ref=analysis[0]
            cap=client.request(source,ref['url'],max_age=0,cache_only=True,capture_id=pins.get((id,source,ref['url'])))
            assert cap['receipt']['sha256']==ref['sha256'], 'Published analysis hash changed'
            receipts.append(cap['receipt'])
            aux=None
            aux_refs=[p for p in refs if '/analysisJs/' in p['url']]
            if aux_refs:
                assert len(aux_refs)==1
                a=client.request(source,aux_refs[0]['url'],max_age=0,cache_only=True,capture_id=pins.get((id,source,aux_refs[0]['url'])))
                assert a['receipt']['sha256']==aux_refs[0]['sha256'], 'Published auxiliary hash changed'
                aux=a['data'];receipts.append(a['receipt'])
            # Identity is parsed from each bound source, not guessed from names or clocks.
            head=analysis_record(cap['data'],source=source,provider_id=f['provider_id'],auxiliary_raw=aux,identity_only=True)
            expected={k:head[k] for k in ['provider_id','home','away','home_id','away_id','kickoff_utc']}
            assert expected['home_id']==f['home_id'] and expected['away_id']==f['away_id'], 'Published oriented teams differ'
            parsed=parse_opponent_history(cap['data'],source=source,provider_id=f['provider_id'],expected_identity=expected,auxiliary_raw=aux)
            packets.append(dict(fixture_id=id,source=source,state='PARSED',result=parsed,receipts=receipts))
        except (ValueError,AssertionError,KeyError) as error:
            packets.append(dict(fixture_id=id,source=source,state='REJECTED',error=str(error),receipts=receipts))
    if len(packets)%50==0:print('metadata',len(packets),flush=True)
body=dict(packets=packets,input_sha256=hashlib.sha256((out/'inputs.json').read_bytes()).hexdigest(),client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),network_attempts=sum(r['network_attempts'] for p in packets for r in p.get('receipts',[])))
body['implementation']=implementation_closure(root,('beidan_backend.opponent_history','beidan_backend.fundamentals','beidan_backend.unified_sources'),distributions=('beautifulsoup4','json5'))
assert body['network_attempts']==0
path=out/'metadata.json'
text=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
# Receipt processed_at changes on cache replay; the raw identities remain bound.
if 'replay' in sys.argv:
    old=json.loads(path.read_text())
    for b in (old,body):
        for p in b['packets']:
            for r in p.get('receipts',[]):r.pop('processed_at',None)
    assert old==body
    (out/'metadata-replay.json').write_text(json.dumps({'status':'IDENTICAL_METADATA_REPLAY','packets':len(packets)}))
else:
    assert not path.exists(), 'Refuse overwriting frozen metadata'
    path.write_text(text)
print('complete',len(packets),body['network_attempts'])
