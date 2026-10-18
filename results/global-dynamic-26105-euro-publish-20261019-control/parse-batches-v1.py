"""Operational cache-only checkpoints; no publication or model admission."""
import hashlib,json,pickle,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from beidan_backend.unified_sources import SourceClient
from beidan_backend.source_issue_markets import collect_euro_issue
from beidan_backend.source_market_publication import validate_market_tables
control=Path(__file__).resolve().parent
roster_path=Path('results/global-dynamic-26105-readiness-20261018-v4/frozen-roster.json')
roster_bytes=roster_path.read_bytes();roster=json.loads(roster_bytes)
assert len(roster['data'])==365
roster_sha=hashlib.sha256(roster_bytes).hexdigest()
assert roster_sha=='bb6355e04281cb3b980bdf19477a89b309b1380fcfc37fd31b0c0716acc8feed'
script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
out=control/'parsed-batches-v1';out.mkdir(exist_ok=True)
if len(sys.argv)==1:
    assert not list(out.glob('*.pickle')), 'Existing checkpoints require explicit verified resume'
    for first in range(1,366,10):
        subprocess.run([sys.executable,str(Path(__file__).resolve()),str(first)],check=True)
    print('All37 batches completed; full-issue assembly/publication remains required',flush=True)
else:
    first=int(sys.argv[1]);assert first in range(1,366,10)
    slots=list(range(first,min(first+10,366)))
    target=out/f'{first:03d}.pickle';receipt=out/f'{first:03d}.json'
    assert not target.exists() and not receipt.exists()
    result=collect_euro_issue(SourceClient(),'26105',roster=roster,slots=slots,cache_only=True)
    validate_market_tables(result)
    assert result['receipt']['network_attempts']==0
    assert result['receipt']['expected_slots']==len(slots)
    assert result['receipt']['roster_slots']==365
    assert result['receipt']['roster_sha256']==roster['receipt']['sha256']
    assert sorted(r['slot'] for r in result['tables']['status'])==slots
    assert len(result['tables']['resources'])==2*len(slots)
    assert all(r['state'] in {'VERIFIED','EMPTY'} for r in result['tables']['resources'])
    assert hashlib.sha256(roster_path.read_bytes()).hexdigest()==roster_sha
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==script_sha
    with target.open('xb') as stream:pickle.dump(result,stream,protocol=5)
    record=dict(slots=slots,roster_input_sha256=roster_sha,script_sha256=script_sha,
        pickle_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        generated_at=datetime.now(timezone.utc).isoformat(),network_attempts=0,
        model_admission=False,table_rows={k:len(v) for k,v in result['tables'].items()},
        receipt=result['receipt'])
    with receipt.open('x') as stream:json.dump(record,stream,indent=2)
    print(json.dumps(dict(slots=slots,table_rows=record['table_rows'],network_attempts=0)),flush=True)
