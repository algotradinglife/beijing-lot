"""Package hash-bound report inputs, reusing the existing two-file archive format."""
import argparse,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--fixture',required=True);a=p.parse_args();root=Path(a.study);out=root/'report'
 if out.exists():raise FileExistsError('Immutable report directory required')
 result=json.loads((root/'results.json').read_text());prepared=json.loads((root/'prepared.json').read_text());audit=json.loads((root/'settlement-audit.json').read_text())
 result.update(readiness=prepared['readiness'],audit_status=[{k:r[k] for k in ['issue','slot','provider_id','status']} for r in audit['rows']],
  source_hashes={str(root/n):hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['results.json','prepared.json','settlement-audit.json']})
 out.mkdir();(out/'results.json').write_text(json.dumps(result,indent=2));(out/'plans-frozen.json').write_bytes((root/'plans-frozen.json').read_bytes())
 files={n:(out/n).read_text() for n in ['results.json','plans-frozen.json']}
 saved=dict(files=files,hashes={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()})
 Path(a.fixture).write_bytes(gzip.compress(json.dumps(saved).encode(),mtime=0))
