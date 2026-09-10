"""Restore bounded hash-verified archived report inputs, never model execution."""
import argparse,base64,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--fixture',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable output directory required')
 saved=json.loads(gzip.decompress(Path(a.fixture).read_bytes()));expected={'plans-frozen.json','results.json','legs.json.gz','report-inputs.json'}
 if set(saved['files'])!=expected or set(saved['hashes'])!=expected:raise ValueError('Unexpected fixture scope')
 decoded={n:base64.b64decode(b,validate=True) for n,b in saved['files'].items()}
 for n,b in decoded.items():
  if hashlib.sha256(b).hexdigest()!=saved['hashes'][n]:raise ValueError('Fixture bytes changed')
 out.mkdir(parents=True)
 for n,b in decoded.items():(out/n).write_bytes(b)
 (out/'archive.json').write_text(json.dumps(dict(mode='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY',hashes={str(out/n):h for n,h in saved['hashes'].items()})))
