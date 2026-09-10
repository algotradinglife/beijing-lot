"""Materialize the archived report fixture, explicitly not a model replay."""
import argparse,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New fixture directory required')
 saved=json.loads(gzip.decompress(Path('tests/fixtures/decision_chain_report.json.gz').read_bytes()))
 if set(saved['files'])!={'results.json'}:raise ValueError('Unexpected archived fixture scope')
 for name,body in saved['files'].items():
  if hashlib.sha256(body.encode()).hexdigest()!=saved['hashes'][name]:raise ValueError('Fixture hash mismatch')
 out.mkdir(parents=True)
 for name,body in saved['files'].items():(out/name).write_text(body)
 check=dict(saved['original_check']);check['fixture_mode']='ARCHIVED_RENDER_ONLY_NOT_FRESH_REPLAY'
 check['source_hashes']={str(out/name):digest for name,digest in saved['hashes'].items()}
 (out/'independent-check.json').write_text(json.dumps(check,indent=2));print('ARCHIVED_RENDER_FIXTURE')
