"""Offline replay of existing observed prematch-SP receipts; no as-of selection.

Only existing authoritative prematch parser interprets original saved bytes.
No settlement SP, network fetching or historical learning occurs in this client.
"""
import sys
import json
import hashlib
from pathlib import Path
from beidan_backend.prematch_sp import parse_prematch_sp
from beidan_backend.temporal_learning import implementation_closure

root=Path(sys.argv[1]).resolve();out=root/'results/fm171-26103-draw-20261017'
rows=[];receipts=[];diagnostics=[]
for path in sorted((root/'results').rglob('26103.source.json')):
    if '/raw-sp/26103/' not in str(path):continue
    r=json.loads(path.read_text())
    if r.get('market')!='beidan_handicap_sp_reference':continue
    assert r['issue_id']=='26103' and r['quote_time_basis']=='observed_availability'
    raw=root/r['raw_paths']['nowscore_beidan_sp_raw']
    sha=hashlib.sha256(raw.read_bytes()).hexdigest()
    assert sha==r['raw_sha256']['nowscore_beidan_sp']
    q,d=parse_prematch_sp(raw.read_bytes(),r['schedule'],r['observed_at'],research_only=r['research_only'])
    identities={s['fixture_key']:s for s in r['schedule']}
    for a in q:
        s=identities[a['fixture_id']]
        rows.append({**a,'provider_id':s['provider_id_nowscore'],'handicap':s['handicap'],
                     'scheduled_kickoff':s['kickoff_at'],'receipt_path':str(path.relative_to(root)),
                     'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'raw_sha256':sha})
    diagnostics.extend(d)
    receipts.append(dict(path=str(path.relative_to(root)),raw_path=str(raw.relative_to(root)),raw_sha256=sha,receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),quotes=len(q)))
body=dict(quotes=rows,receipts=receipts,diagnostics=diagnostics,network_attempts=0,
          client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          parser_sha256=hashlib.sha256((root/'packages/beidan/inst/python/beidan_backend/prematch_sp.py').read_bytes()).hexdigest())
body['implementation']=implementation_closure(root,('beidan_backend.prematch_sp',),distributions=('beautifulsoup4',))
(out/'sp-observed-inputs.json').write_text(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')))
print('receipts',len(receipts),'quote rows',len(rows),'fixtures',len({r['fixture_id'] for r in rows}))
