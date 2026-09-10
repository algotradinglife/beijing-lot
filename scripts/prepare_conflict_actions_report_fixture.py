"""Restore hash-verified archived report inputs, not an expert model replay."""
import argparse,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New fixture directory required')
 saved=json.loads(gzip.decompress(Path('tests/fixtures/conflict_actions_report.json.gz').read_bytes()))
 required={f'{s}/results.json' for s in ['reestimate','expand','protect','attribution-v2']}
 if set(saved['files'])!=required:raise ValueError('Unexpected archived fixture scope')
 for name,body in saved['files'].items():
  if hashlib.sha256(body.encode()).hexdigest()!=saved['hashes'][name]:raise ValueError('Fixture changed')
 for name,body in saved['files'].items():
  path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
 check=dict(saved['original_check']);check.update(source_hashes={str(out/n):v for n,v in saved['hashes'].items()},fixture_mode='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY')
 (out/'independent-check.json').write_text(json.dumps(check,indent=2));print('ARCHIVED_RENDER_INPUTS',len(required))
