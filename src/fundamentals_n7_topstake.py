"""Fixed stake multipliers for the highest-probability concentrated N7 group."""
import math
from src.fundamentals_n7_twocover import n7_twocover_plan,settle_n7_twocover
from src.temporal_learning.core import stable_json_hash


def n7_topstake_plan(frame, *, cutoffs, top_multiplier, max_groups, unit_cny, payout_factor, allocation_seed):
    """Seal BASE/TOP2/TOP3 without changing fixtures/supports or distinct groups.

    Highest product of seven Top2 coverages wins; exact ties use smallest group
    ID. Its entire128-ticket support receives multiplier1/2/3, all others1.
    No-group plan spends0 and uses top_group=0, top_probability=0. Explicit
    native cutoffs/business constants validated by common baseline API. No fit,
    settlement data, writes, or outcome-dependent choice.
    """
    if top_multiplier not in [1,2,3]:raise ValueError('Multiplier must be1,2,3')
    p=n7_twocover_plan(frame,cutoffs=cutoffs,strategy='BASE',max_groups=max_groups,
        unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=allocation_seed)
    part=p['components'][0]
    probs={g:math.prod(r['coverage'] for r in part['legs'] if r['group']==g) for g in range(1,part['groups']+1)}
    top=min(probs,key=lambda g:(-probs[g],g)) if probs else 0
    part.pop('seal')
    for t in part['tickets']:t['units']=top_multiplier if t['group']==top else 1
    part['stake']=unit_cny*sum(t['units'] for t in part['tickets']);part['seal']=stable_json_hash(part)
    p.pop('seal');p.update(strategy={1:'BASE',2:'TOP2',3:'TOP3'}[top_multiplier],top_multiplier=top_multiplier,
        top_group=top,top_probability=probs.get(top,0.),stake=part['stake'],budget=part['stake'])
    p['seal']=stable_json_hash(p)
    return p


def settle_n7_topstake(plan,audit):
    """Use shared cash API, retaining nonnullable selected-group metadata.

    Nullable payouts/status semantics unchanged. Multiplier doesn't increase
    group hits. Top-group stand-alone cash is derived by TOP2 minus BASE in R.
    """
    row=settle_n7_twocover(plan,audit)
    row.update(top_group=plan['top_group'],top_probability=plan['top_probability'])
    return row
