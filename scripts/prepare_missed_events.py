"""Read frozen pure baseline and market scores; retain all available fixtures."""
import argparse,json,hashlib,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_score_events import score_event_rows
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable new output required')
 path=Path(a.source)/'factors.json';f=json.loads(path.read_text())
 verify_clean_file_bindings(f['source_hashes'],repository_root=Path.cwd())
 source=Path(f['expert_source']);events=[];features=[]
 for issue in sorted({r['issue'] for r in f['rows']}):
  x=json.loads((source/'projected'/f'{issue}.json').read_text());fixtures=pd.DataFrame(x['control']['fixtures'])
  for model in ['baseline','market']:
   scores=pd.DataFrame(x['control']['scores']) if model=='baseline' else pd.concat([pd.DataFrame(v) for v in x['market']['grids'].values()],ignore_index=True)
   if model=='market':
    # Market cells omit fixture identity: assign from their authoritative keys.
    parts=[]
    for z in fixtures.to_dict('records'):
     g=pd.DataFrame(x['market']['grids'][f"{issue}/{z['slot']}"])
     for k in ['issue','slot','provider_id']:g[k]=z[k]
     parts.append(g)
    scores=pd.concat(parts,ignore_index=True)
   rows=score_event_rows(scores,fixtures);rows['model']=model;events.extend(rows.to_dict('records'))
  features.extend(x['features']);print('PROJECTED',issue,flush=True)
 audit=json.loads((source/'settlement-audit.json').read_text())['rows']
 hashes={**f['source_hashes'],str(path):hashlib.sha256(path.read_bytes()).hexdigest()}
 for p in [source/'settlement-audit.json',Path('src/fundamentals_score_events.py'),Path(__file__)]:hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 out.mkdir(parents=True)
 (out/'events.json').write_text(json.dumps(dict(events=events,features=features,audit=audit,scope='EXPOSED_ALL_AVAILABLE_FIXTURES_NO_FIT',source_hashes=hashes)))
