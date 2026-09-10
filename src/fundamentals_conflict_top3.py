"""Fixed conflict routing: nonconflict N7 and all-conflict exact-score Top3."""
import pandas as pd
from src.fundamentals_conflict_probabilities import conflict_score_projection
from src.fundamentals_n7_baseline import n7_baseline_plan
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.nowscore_settlement import expected_option
from src.temporal_learning.core import stable_json_hash


def conflict_top3_plan(frame, grids, *, cutoffs, max_groups, unit_cny,
                       payout_factor, allocation_seed):
    """Return sealed base, nonconflict parlay and disjoint score-sidecar plan.

    frame: one issue, exact label-free fixture schema accepted by score projection.
    grids: string slot -> normalized p/q score rows; exact cohort and Cutoffs.
    Market Top1 outside model Top2 defines conflict (W,D,L ties). Every conflict,
    including fixtures outside original N7 selection, buys three distinct legal
    exact scores ranked by model p, ties home then away goals, CNY2 each. Other
    score buckets and zero model/market mass excluded; <3 candidates fails closed.
    Nonconflicts rerank by coverage, at most six complete disjoint N7 groups.
    Unused cash is NOT reinvested. No fixed-total-budget claim, fitting or I/O.
    Source score grids, cutoff identities and full routed ledger are sealed.
    All-conflict input returns zero parlay tickets and score bets only.
    """
    base=n7_baseline_plan(frame,cutoffs=cutoffs,selector='COVERAGE',shape='C0E0',
        funding='UNIT',max_groups=max_groups,unit_cny=unit_cny,group_budget_cny=432,
        payout_factor=payout_factor,allocation_seed=allocation_seed)
    if set(grids)!=set(cutoffs):raise ValueError('Exact score cohort required')
    retained=[];scores=[];ledger=[]
    for fixture in frame.sort_values('slot').to_dict('records'):
        slot=str(fixture['slot']);cutoff=cutoffs[slot]
        projection=conflict_score_projection(grids[slot],fixture,cutoff=cutoff,market_weight=0)
        conflict=projection['receipt']['conflict']
        ledger.append(dict(issue=fixture['issue'],slot=fixture['slot'],provider_id=fixture['provider_id'],
            conflict=conflict,projection_seal=projection['seal']))
        if not conflict:
            retained.append(fixture);continue
        eligible=[]
        for r in projection['grid']:
            h,a=int(r['home_goals']),int(r['away_goals']);option=f'{h}:{a}'
            if expected_option(dict(play='bf',score=option))==option and r['p']>0 and r['q']>0:
                eligible.append(dict(score_home=h,score_away=a,option=option,
                    p_score=r['p'],q_score=r['q'],sp_proxy=1/r['q']))
        if len(eligible)<3:raise ValueError('Three positive-price exact scores required per conflict')
        for rank,r in enumerate(sorted(eligible,key=lambda r:(-r['p_score'],r['score_home'],r['score_away']))[:3],1):
            scores.append(dict(**{k:fixture[k] for k in ['issue','slot','provider_id','handicap']},
                **r,rank=rank,stake=unit_cny,cutoff=cutoff.cutoff_ts.isoformat()))
    if retained:
        subset={str(r['slot']):cutoffs[str(r['slot'])] for r in retained}
        main=n7_baseline_plan(pd.DataFrame(retained),cutoffs=subset,selector='COVERAGE',shape='C0E0',
            funding='UNIT',max_groups=max_groups,unit_cny=unit_cny,group_budget_cny=432,
            payout_factor=payout_factor,allocation_seed=allocation_seed)
    else:main=limit_decision_chain_plan(base,groups=0,cutoffs=cutoffs)
    payload=dict(main=main,scores=scores,stake=main['stake']+sum(r['stake'] for r in scores),
        base_stake=base['stake'],unit_cny=unit_cny,payout_factor=payout_factor,
        funding='UNIT_NO_REINVESTMENT',ledger=ledger,source_plan_seal=base['seal'],
        historical_admission=False)
    return dict(base=base,plan=dict(**payload,seal=stable_json_hash(payload)))
