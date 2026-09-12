"""Independent numerical replay of compact sleeve expansion contracts."""
import itertools
import math
import numpy as np
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def check_expansion_bundle(bundle, *, cutoffs, original_groups, source_pool):
    """Check every Top64 against independent exhaustive 3^7 state products.

    Source pool seal and cutoffs bind an independent replay of the entire ordered
    candidate stream, its origins and attempt ledger. Original groups match the
    prefix. Returns candidate count after checking
    unique fixture sets, exact canonical Top64 ties, mass, q-based CNY payout and
    retained totals. No I/O/selection/labels; invalid seals/cutoffs/numerics raise.
    """
    if bundle.get('seal')!=stable_json_hash({k:v for k,v in bundle.items() if k!='seal'}):
        raise ValueError('Expansion seal mismatch')
    f=pd.DataFrame(bundle['fixtures']);_,bound=rank_double_candidates(f,cutoffs=cutoffs)
    if bound!=bundle['cutoffs'] or not original_groups or bundle['historical_admission'] is not False:
        raise ValueError('Invalid cutoff/admission')
    if (source_pool.get('seal')!=stable_json_hash({k:v for k,v in source_pool.items() if k!='seal'})
        or source_pool['seal']!=bundle['pool_seal'] or source_pool['fixtures']!=bundle['fixtures']
        or source_pool['cutoffs']!=bound):raise ValueError('Bound source pool mismatch')
    params=bundle['parameters']
    if (params['original_count']!=len(original_groups)
        or type(params['candidate_count']) is not int or params['candidate_count']<len(original_groups)
        or type(params['seed']) is not int or params['seed']<0
        or type(params['maximum_attempts']) is not int or params['maximum_attempts']<1
        or (params['budget_cny'],params['unit_cny'],params['payout_factor'])!=(1024,2,.65)):
        raise ValueError('Invalid candidate recipe')
    sleeves=bundle['sleeves'];groups=[s['fixture_indices'] for s in sleeves]
    if (groups[:len(original_groups)]!=original_groups or len(set(map(tuple,groups)))!=len(groups)
        or len(groups)>bundle['parameters']['candidate_count']):raise ValueError('Prefix/unique groups failed')
    states=np.array(list(itertools.product(range(3),repeat=7)))
    p=f[[f'p_{d}' for d in 'WDL']].to_numpy();q=f[[f'q_{d}' for d in 'WDL']].to_numpy()
    # Independent ordered-stream oracle: consume the next unused quality set
    # from a ranked iterator; interleave the same two documented random lanes.
    tickets=np.array(source_pool['encoded_tickets'],dtype=int).reshape(-1,7)
    masses=np.prod(p[tickets//3,tickets%3],axis=1)
    ranking=sorted(range(len(tickets)),key=lambda i:(-masses[i],i))
    quality=iter(tuple((tickets[i]//3).tolist()) for i in ranking)
    generated=[list(g) for g in original_groups];seen=set(map(tuple,generated))
    origins=['ORIGINAL24']*len(generated);attempts=0
    rng=np.random.default_rng(params['seed']);top2=np.sort(p,axis=1)[:,1:].sum(axis=1)
    target=min(params['candidate_count'],math.comb(len(f),7))
    while len(generated)<target and attempts<params['maximum_attempts']:
        lane=attempts%3;attempts+=1;group=None
        if lane==0:
            for proposed in quality:
                if proposed not in seen:group=proposed;break
        if group is not None:origin='QUALITY_EXTENSION'
        else:
            weighted=lane!=2
            group=tuple(sorted(rng.choice(len(f),size=7,replace=False,p=top2/np.sum(top2) if weighted else None).tolist()))
            origin='TOP2_WEIGHTED' if weighted else 'UNIFORM'
        if group not in seen:
            seen.add(group);generated.append(list(group));origins.append(origin)
    if (groups!=generated or [s['origin'] for s in sleeves]!=origins
        or bundle['attempts']!=attempts):raise ValueError('Candidate stream/origin/attempt replay failed')
    for index,s in enumerate(sleeves):
        g=s['fixture_indices']
        if s['id']!=index or len(g)!=7 or g!=sorted(set(g)) or min(g)<0 or max(g)>=len(f):
            raise ValueError('Invalid fixture identity')
        mass=np.prod(p[g][np.arange(7),states],axis=1)
        payout=1.3/np.prod(q[g][np.arange(7),states],axis=1);value=mass*payout
        ids=sorted(np.lexsort((np.arange(2187),-value,-mass))[:64].tolist())
        if (s['state_ids']!=ids or not np.isclose(mass.sum(),1.,rtol=0,atol=1e-8)
            or not np.allclose(s['probabilities'],mass[ids],rtol=1e-12,atol=1e-14)
            or not np.allclose(s['estimated_payouts'],payout[ids],rtol=1e-12,atol=1e-12)
            or not np.isclose(s['coverage'],sum(mass[ids]),rtol=1e-12,atol=1e-14)
            or not np.isclose(s['expected_gross'],sum(value[ids]),rtol=1e-12,atol=1e-12)):
            raise ValueError('Top64 probability/payout contract failed')
    return len(sleeves)
