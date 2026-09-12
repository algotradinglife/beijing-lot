"""Single-source market N7 replay; no strength features, fitting or swaps."""
from src.fundamentals_n7_single import n7_single_plan
from src.temporal_learning.core import stable_json_hash


def market_foundation_n7(frame, *, cutoffs, max_uses, max_pair_overlap,
                         budget_cny, unit_cny, payout_factor, seed, source_version):
    """Seal 2 singles + 5 doubles using only supplied market WDL fractions.

    Input exact identities/handicap and q_W/D/L, native fixture cutoffs. Reject
    extra columns, including all strength/settlement fields. The existing generic
    engine's p slots receive the SAME market triplet, never strength predictions.
    Top2 coverage orders disjoint groups; MILP expands under U/P caps. Each group's
    two highest Top1 probabilities become singles, with no extra 50% gate. No
    A/D/C quotas, disagreement exclusions, conversions, substitutions or protection.
    Fixed CNY1024 wallet, CNY2 units and one .65 ticket factor. Cash unspent stays cash.
    Returns sealed settlement-compatible plan. No I/O or training.
    """
    columns={'issue','slot','provider_id','handicap','q_W','q_D','q_L'}
    if (set(frame)!=columns or max_uses not in (3,6) or max_pair_overlap!=5
            or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)
            or source_version not in ('RAW_MARKET','market-balance-draw-1.0.0-diagnostic')):
        raise ValueError('Exact market-only input and fixed N7 comparison contract required')
    adapted=frame.copy()
    for direction in 'WDL':adapted['p_'+direction]=adapted['q_'+direction]
    plan=n7_single_plan(adapted,cutoffs=cutoffs,budget_cny=budget_cny,single_rule='MAX_SINGLE',
        single_count=2,max_uses=max_uses,unit_cny=unit_cny,payout_factor=payout_factor,
        allocation_seed=seed,max_pair_overlap=max_pair_overlap)
    plan.pop('seal')
    plan.update(probability_source=source_version,strength_used=False,substitution='NONE')
    return dict(plan,seal=stable_json_hash(plan))
