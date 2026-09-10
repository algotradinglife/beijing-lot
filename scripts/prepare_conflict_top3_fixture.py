"""Restore exact archived Top3 report inputs for CI rendering only."""
import argparse,gzip,hashlib,json
from pathlib import Path
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable fixture directory required')
 saved=json.loads(gzip.decompress(Path('tests/fixtures/conflict_top3_report.json.gz').read_bytes()))
 if set(saved['files'])!={'results.json','plans-frozen.json'}:raise ValueError('Unexpected fixture scope')
 for name,body in saved['files'].items():
  if hashlib.sha256(body.encode()).hexdigest()!=saved['hashes'][name]:raise ValueError('Fixture changed')
 out.mkdir(parents=True)
 for name,body in saved['files'].items():(out/name).write_text(body)
 (out/'archive.json').write_text(json.dumps(dict(mode='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY',hashes={str(out/n):h for n,h in saved['hashes'].items()})))
