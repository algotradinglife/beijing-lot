"""Independent prediction-only checks of rebuilt support and physical prefixes."""
import numpy as np
from src.temporal_learning.core import stable_json_hash


def check_refill_prefixes(plan, bundle, *, minimum_sp, unit_cny, payout_factor):
    """Rebuild prefix probability/accounting from fixture p/q without R surfaces.

    Accepts sealed physical plans, materialized source bundle, explicit SP gate
    and CNY constants. Checks cutoffs, legal fixture support, sorted prefix states,
    physical tickets and mass/price arithmetic. Returns counts; no labels or IO.
    """
    if ((unit_cny,payout_factor)!=(2,.65) or minimum_sp<1 or
        plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}) or
        plan['cutoffs']!=bundle['cutoffs']):
        raise ValueError('Refill plan identity mismatch')
    original=bundle['expanded_pool']['fixtures']
    numeric={f'{k}_{d}' for k in ('p','q') for d in 'WDL'}
    if len(original)!=len(plan['fixtures']):raise ValueError('Fixture count mismatch')
    for actual,source in zip(plan['fixtures'],original):
        if ({k:v for k,v in actual.items() if k not in numeric}!=
            {k:v for k,v in source.items() if k not in numeric} or
            any(not np.isclose(actual[k],source[k],rtol=0,atol=1e-14) for k in numeric)):
            raise ValueError('Fixture identity/probability mismatch')
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in plan['fixtures']])
    q=np.array([[f[f'q_{d}'] for d in 'WDL'] for f in plan['fixtures']])
    eligible=1/q[np.arange(len(q)),p.argmax(axis=1)]>=minimum_sp
    source={str(s['id']):s['fixture_indices'] for s in bundle['sleeves']}
    enumerations={str(s['id']):s['enumeration'] for s in bundle['sleeves']}
    states=np.indices((3,)*7).reshape(7,-1).T
    ix=[];outcomes=[];seen=set();expected=0.
    for s in plan['sleeve_keys']:
        f=np.asarray(s['fixture_indices'],dtype=int);ids=np.atleast_1d(s['state_ids'])
        if (str(s['sleeve_id']) not in source or f.tolist()!=source[str(s['sleeve_id'])] or
            len(f)!=7 or len(set(f))!=7 or not eligible[f].all() or
            tuple(sorted(f)) in seen or len(ids)!=s['depth'] or len(set(ids))!=len(ids) or
            ids.dtype.kind not in 'iu' or np.any(ids<0) or np.any(ids>=2187)):
            raise ValueError('Invalid refill support')
        seen.add(tuple(sorted(f)))
        prob=np.prod(p[f,states],axis=1)
        value=unit_cny*payout_factor*np.prod(p[f,states]/q[f,states],axis=1)
        enum=enumerations[str(s['sleeve_id'])]
        frozen_prob=np.asarray(enum['probability']);frozen_value=np.asarray(enum['expected_contribution'])
        if (not np.allclose(frozen_prob,prob,rtol=1e-10,atol=1e-14) or
            not np.allclose(frozen_value,value,rtol=1e-10,atol=1e-7)):
            raise ValueError('Source enumeration arithmetic mismatch')
        canonical=np.lexsort((np.arange(2187),-frozen_value,-frozen_prob))
        if not np.array_equal(ids,canonical[:len(ids)]):
            raise ValueError('Not the canonical probability/value/state prefix')
        mass=prob[ids].sum();gross=(unit_cny*payout_factor*np.prod(p[f,states]/q[f,states],axis=1))[ids].sum()
        if not np.allclose([s['coverage'],s['expected_gross'],s['stake']],
                           [mass,gross,unit_cny*len(ids)],rtol=1e-10,atol=1e-7):
            raise ValueError('Prefix arithmetic mismatch')
        order=np.argsort(f)
        ix.extend(np.tile(f[order],(len(ids),1)).tolist())
        outcomes.extend(states[ids][:,order].tolist());expected+=gross
    if (ix!=plan['fixture_indices'] or outcomes!=plan['outcomes'] or
        plan['stake']!=unit_cny*len(ix) or plan['groups']!=len(ix) or
        plan['cash_cny']+plan['stake']!=plan['budget_cny'] or plan['cash_cny']<0):
        raise ValueError('Physical ticket mismatch')
    if not np.isclose(plan['evaluation']['expected_net'],expected-plan['stake'],rtol=1e-10,atol=1e-7):
        raise ValueError('Plan expectation mismatch')
    return dict(status='PASS',tickets=len(ix),sleeves=len(seen))
