"""Materialize a hash-verified archived report fixture; no model execution."""
import argparse,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New fixture directory required')
 saved=json.loads(gzip.decompress(Path('tests/fixtures/integration_weight_report.json.gz').read_bytes()))
 required={'results.json','candidates.json','endpoints.json','penalty-selection.json'}
 if set(saved['files'])!=required:raise ValueError('Unexpected fixture scope')
 for name,text in saved['files'].items():
  if hashlib.sha256(text.encode()).hexdigest()!=saved['hashes'][name]:raise ValueError('Archived fixture changed')
 out.mkdir(parents=True)
 for name,text in saved['files'].items():(out/name).write_text(text)
 verification=dict(saved['original_check']);verification['source_hashes']={str(out/name):digest for name,digest in saved['hashes'].items()}
 verification['fixture_mode']='ARCHIVED_RENDER_ONLY_ORIGINAL_REPLAY_NOT_RERUN'
 (out/'independent-check.json').write_text(json.dumps(verification,indent=2))
 print('Archived render fixture',len(saved['files']))
