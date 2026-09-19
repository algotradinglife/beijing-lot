"""Read saved score grids, collapse exactly to goal-difference mass; no fitting."""
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from src.zero_handicap_inputs import verified_zero_json


def read_handicap_line_inputs(manifest_path, manifest_sha256):
    """Explicit file projections only; archives without inventoried grids excluded.

    JSON rows keyed issue/slot/provider_id, handicap, saved q_WDL and distribution
    of integer net goals. Invalid/missing grids fail; excluded issue ledger is
    returned. Raw score matrices are read unchanged, never inferred from q.
    """
    m=verified_zero_json(manifest_path,manifest_sha256)
    hashes={str(manifest_path):manifest_sha256};rows=[];excluded=[];seen=set();assigned=set()
    for s in m['sources']:
        if assigned.intersection(s['issues']):raise ValueError('Duplicate issue assignment')
        assigned.update(s['issues'])
        if 'path' not in s:
            excluded.extend(dict(issue=i,reason='ARCHIVED_GRID_NOT_INVENTORIED') for i in s['issues']);continue
        x=verified_zero_json(s['path'],s['sha256']);hashes[s['path']]=s['sha256']
        if s['kind']!='fixtures' or 'grids' not in x:raise ValueError('Missing saved grids')
        for f in x['fixtures']:
            if f['issue'] not in s['issues']:continue
            key=(f['issue'],f['slot'],f['provider_id'])
            if key in seen:raise ValueError('Duplicate fixture')
            seen.add(key);grid=x['grids'].get(f"{f['issue']}/{f['slot']}")
            if not grid:raise ValueError('Missing fixture grid')
            masses=defaultdict(float);scores=set()
            for a in grid:
                h,v,p=a['home_goals'],a['away_goals'],a['probability']
                if not all(type(n) is int and n>=0 for n in (h,v)) or not math.isfinite(p) or p<0 or (h,v) in scores:raise ValueError('Invalid score cell')
                scores.add((h,v));masses[h-v]+=p
            if abs(sum(masses.values())-1)>1e-8:raise ValueError('Non-unit mass')
            h=f['handicap']
            for d in 'WDL':
                mass=sum(p for n,p in masses.items() if ('W' if n+h>0 else 'D' if n+h==0 else 'L')==d)
                if abs(mass-f['q_'+d])>1e-8:raise ValueError('Grid projection differs')
            rows.append({k:f[k] for k in ['issue','slot','provider_id','handicap','q_W','q_D','q_L']} |
                        {'distribution':[{'net':n,'probability':p} for n,p in sorted(masses.items())]})
    return json.dumps(dict(rows=rows,exclusions=excluded,source_hashes=hashes,historical_learning='NONE'),allow_nan=False)
