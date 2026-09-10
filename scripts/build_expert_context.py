"""Thin offline entry: rebuild explicit fixture contexts using existing collector."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_draw_context import draw_context_inputs

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ('inventories','review','root','cache','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    review=json.loads(Path(args.review).read_text())
    targets=[{k:r[k] for k in ('issue','slot','provider_id','handicap')} for r in review['fixtures']]
    result=draw_context_inputs(json.loads(Path(args.inventories).read_text()),targets,
        repository_root=Path(args.root),cache_dir=args.cache,window=10,minimum=10)
    output=Path(args.output)
    temporary=output.with_suffix(output.suffix+'.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    temporary.replace(output)
    print('Context rows:',len(result['rows']))
