"""Expand deterministic saved test responses and build label-free context; no network."""
import argparse
import gzip
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_roster_handicap import roster_handicaps
from src.fundamentals_draw_context import draw_context_inputs
from src.temporal_learning.core import utc

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/'tests/fixtures/next_issue_experts'
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    for p in sorted(source.glob('*.json.gz')):
        (out/p.stem).write_bytes(gzip.decompress(p.read_bytes()))
    roster=out/'roster.json';meta,raw=read_response(roster)
    fixtures=issue_analysis_pages(raw,roster_url=meta['url'],issue='100104')
    cutoffs={str(f['slot']):utc(f['deadline_text'].replace('截止时间：','').replace('截止时间:','').strip()+'+08:00').isoformat() for f in fixtures}
    inventory=[dict(issue='100104',fixture_count=len(fixtures),roster_path=str(roster),
        response_paths=[str(out/p.stem) for p in sorted(source.glob('*-*.json.gz'))],cutoffs=cutoffs,adjudications=[])]
    (out/'inventories.json').write_text(json.dumps(inventory))
    lines=roster_handicaps(roster,issue='100104',slots=[f['slot'] for f in fixtures])
    targets=[dict(issue='100104',slot=r['slot'],provider_id=r['provider_id'],handicap=r['home_handicap']) for r in lines]
    context=draw_context_inputs(inventory,targets,repository_root=str(root),cache_dir=str(out/'cache'),window=10,minimum=10)
    (out/'context.json').write_text(json.dumps(context,separators=(',',':')))
