"""Post-freeze opportunity coverage attribution, with original R cross-checks."""
from pathlib import Path
import gzip
import hashlib
import json

import numpy as np

from src.temporal_learning import implementation_closure
from src.temporal_learning.core import stable_json_hash


def core_role_coverage(plan, worlds, *, cutoffs):
    """Return scenario counts for fixed core/opp tickets; no allocation or labels.

    Cutoffs must equal the frozen fixture map. Worlds contain 0/1/2 canonical
    outcomes, rows are scenarios. Each original R role-layer union and parent
    union are independently reproduced in NumPy. Copies add no coverage.
    Counts are integer; probabilities are fractions, not percentage points.
    Invalid identities, shapes or R metrics raise ValueError. No side effects.
    """
    if not cutoffs or plan['cutoffs'] != cutoffs:
        raise ValueError('Role coverage cutoff mismatch')
    out=[]
    for kind in ('training', 'evaluation'):
        w=np.asarray(worlds[kind])
        if (w.ndim != 2 or w.shape[1] != len(plan['fixtures']) or not len(w)
                or w.dtype.kind not in 'iu' or np.any((w<0)|(w>2))):
            raise ValueError('Invalid role coverage worlds')
        roles={r:np.zeros(len(w),dtype=bool) for r in ('CORE','OPPORTUNITY')}
        for layer in plan['layers']:
            if layer['role'] not in roles or layer['cutoffs'] != cutoffs:
                raise ValueError('Role layer identity mismatch')
            hit=np.zeros(len(w),dtype=bool)
            for key in layer['sleeve_keys']:
                ix=np.asarray(key['fixture_indices']);states=np.asarray(key['state_ids'])
                if (ix.shape != (7,) or ix.dtype.kind not in 'iu' or np.any(np.diff(ix)<=0)
                        or np.any((ix<0)|(ix>=w.shape[1])) or states.ndim != 1
                        or states.dtype.kind not in 'iu' or len(states)!=key['depth']
                        or len(np.unique(states))!=len(states) or np.any((states<0)|(states>=2187))):
                    raise ValueError('Invalid role ticket identity')
                sampled=w[:,ix]@(3**np.arange(6,-1,-1))
                hit |= np.isin(sampled,states)
            if abs(float(hit.mean())-layer[kind]['any_hit'])>1e-12:
                raise ValueError('Original R role union mismatch')
            roles[layer['role']] |= hit
        core,opp=roles['CORE'],roles['OPPORTUNITY'];union=core|opp
        if abs(float(union.mean())-plan[kind]['any_hit'])>1e-12:
            raise ValueError('Original R parent union mismatch')
        counts=dict(worlds=len(w),core_hits=int(core.sum()),opportunity_hits=int(opp.sum()),
                    shared_hits=int((core&opp).sum()),union_hits=int(union.sum()),
                    incremental_hits=int((opp&~core).sum()))
        out.append(dict(issue=plan['issue'],arm=plan['arm'],seed=plan['seed'],kind=kind,**counts,
            core_probability=float(core.mean()),opportunity_probability=float(opp.mean()),
            union_probability=float(union.mean()),incremental_probability=float((opp&~core).mean())))
    return out


def package_core_coverage(study, report_archive, destination, *, repository_root,
                          expected_report_sha256):
    """Bind the descriptive extension to an accepted full replay and raw worlds.

    All paths are explicit. Rechecks frozen raw/plan hashes and complete grid;
    verifies original R role metrics independently, with no settlement reads.
    Refuses overwrite; no output on failed verification. Does not refit or alter
    the accepted report, the original policies, their worlds, or source export.
    """
    study=Path(study);destination=Path(destination);repository_root=Path(repository_root).resolve()
    if destination.exists():raise ValueError('Refusing coverage archive overwrite')
    wrapper=json.loads(gzip.decompress(Path(report_archive).read_bytes()))
    if (wrapper['schema']!='bj433_core_report_v1' or wrapper['sha256']!=expected_report_sha256
            or hashlib.sha256(wrapper['body'].encode()).hexdigest()!=expected_report_sha256):
        raise ValueError('Accepted report binding mismatch')
    report=json.loads(wrapper['body'])
    frozen_raw=(study/'plans-frozen.json').read_bytes();frozen=json.loads(frozen_raw)
    receipt=frozen['receipt']
    if (stable_json_hash(receipt)!=frozen['seal'] or frozen['seal']!=report['freeze_seal']
            or report['historical_admission'] is not False
            or report['independent_replay']['status']!='PASS' or report['settlement_replay']['status']!='PASS'):
        raise ValueError('Full report acceptance mismatch')
    expected={(r['issue'],r['seed'],r['arm']) for r in report['rows'] if not r['reference']}
    rows=[];seen=set()
    for path,digest in receipt['raw_hashes'].items():
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Frozen raw changed')
        result=json.loads(gzip.decompress(raw));worlds={w['seed']:w for w in result['worlds']}
        if len(worlds)!=len(result['worlds']):raise ValueError('Duplicate worlds')
        for plan in result['plans']:
            key=(plan['issue'],plan['seed'],plan['arm'])
            if key not in expected or key in seen:raise ValueError('Coverage grid mismatch')
            path=study.resolve()/'plans'/f"{key[0]}_{key[1]}_{key[2]}.json.gz"
            raw_plan=path.read_bytes()
            if (hashlib.sha256(raw_plan).hexdigest()!=receipt['plan_hashes'][str(path)]
                    or json.loads(gzip.decompress(raw_plan))!=plan):
                raise ValueError('Coverage plan binding mismatch')
            rows.extend(core_role_coverage(plan,worlds[key[1]],cutoffs=receipt['cutoffs'][key[0]]))
            seen.add(key)
    if seen!=expected:raise ValueError('Incomplete coverage grid')
    body=dict(rows=rows,issue_order=report['issue_order'],seeds=report['parameters']['seeds'],
        freeze_seal=frozen['seal'],report_sha256=expected_report_sha256,historical_admission=False,
        frozen_sha256=hashlib.sha256(frozen_raw).hexdigest(),raw_hashes=receipt['raw_hashes'],
        verification=dict(status='PASS',plans_checked=len(seen),method='NUMPY_VS_FROZEN_R_ROLE_AND_PARENT_UNIONS'),
        implementation=implementation_closure(repository_root,['src.n7_core_coverage'],distributions=['numpy']))
    encoded=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)
    digest=hashlib.sha256(encoded.encode()).hexdigest()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as f:
        f.write(gzip.compress(json.dumps(dict(schema='bj433_role_coverage_v1',body=encoded,sha256=digest)).encode(),mtime=0))
    return dict(status='PASS',plans=len(seen),sha256=digest,path=str(destination))
