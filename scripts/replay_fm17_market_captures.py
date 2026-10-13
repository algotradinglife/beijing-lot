#!/usr/bin/env python3
"""Offline source replay, preserving old receipts and per-channel failures."""
import argparse
import hashlib
import json
from pathlib import Path
from beidan_backend.market_capture.replay import replay_fixture_capture
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True);p.add_argument('--scope',type=Path,required=True)
p.add_argument('--identity-scope',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args();root=a.root.resolve();a.output.mkdir(parents=True,exist_ok=True)
scope=json.loads(a.scope.read_bytes());identities={x['fixture_id']:{k:x[k] for k in ('home_id','away_id')} for x in json.loads(a.identity_scope.read_bytes())};outputs=[]
for f in scope:
 path=root/f['original_capture'];payload=path.read_bytes()
 assert hashlib.sha256(payload).hexdigest()==f['original_capture_sha256']
 rec=json.loads(payload);assert rec['fixture']['fixture_id']==f['fixture_id']
 result=replay_fixture_capture(rec,str(root),identities[f['fixture_id']])
 result['identity_scope_sha256']=hashlib.sha256(a.identity_scope.read_bytes()).hexdigest()
 result['scope_sha256']=hashlib.sha256(a.scope.read_bytes()).hexdigest()
 result['original_capture_sha256']=f['original_capture_sha256']
 target=a.output/(f['fixture_id'].replace(':','_')+'.json')
 encoded=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
 if target.exists():assert target.read_bytes()==encoded
 else:target.write_bytes(encoded)
 outputs.append(dict(path=str(target),sha256=hashlib.sha256(encoded).hexdigest()))
 print(f['fixture_id'],result['identity_status'],*[len(result[k]) for k in ('euro','asian','totals')],flush=True)
manifest=dict(identity_scope_sha256=hashlib.sha256(a.identity_scope.read_bytes()).hexdigest(),scope_sha256=hashlib.sha256(a.scope.read_bytes()).hexdigest(),client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),outputs=outputs)
t=a.output/'manifest.json';encoded=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
if t.exists():assert t.read_bytes()==encoded
else:t.write_bytes(encoded)
