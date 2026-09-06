"""Materialize the saved regression fixture for CI, with no network access."""
from pathlib import Path
import argparse
import base64
import gzip
import hashlib
import json

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir/'raw-browser').mkdir()
    fixtures = Path(__file__).resolve().parents[1]/'tests/fixtures/fundamentals_census'
    for source in ('nowscore','titan'):
        raw = gzip.decompress((fixtures/f'{source}-1870517.html.gz').read_bytes())
        record = json.loads((fixtures/f'{source}-1870517.provenance.json').read_text())
        record['body_base64'] = base64.b64encode(raw).decode()
        (args.output_dir/'raw-browser'/f'{source}-1870517.json').write_text(json.dumps(record))
    # Fixed observed source-native regression identity, independently asserted in tests.
    roster_raw = gzip.decompress((fixtures / 'roster-20064.gz').read_bytes())
    roster = json.loads((fixtures / 'roster-20064.provenance.json').read_text())
    roster['body_base64'] = base64.b64encode(roster_raw).decode()
    roster['sha256'] = hashlib.sha256(roster_raw).hexdigest()
    (args.output_dir / 'roster-20064.json').write_text(json.dumps(roster))
    row = dict(issue='20064',slot=293,provider_id='1870517',league='英乙',
               period='historical',panel_kind='regression',
               roster_home='埃克塞特',roster_away='科切斯特',roster_sha256=roster['sha256'],
               kickoff_utc='2020-06-22T16:15:00+00:00',reason='regulation_extra_time_regression')
    for name in ('panel','denominator'):
        (args.output_dir/f'{name}.json').write_text(json.dumps([row]))
