"""Fixed conflict routing over frozen expert probabilities; no fitting or labels."""
import copy
import numpy as np
import pandas as pd
from src.fundamentals_integration_weight import select_integration_weights
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure


def route_decision_chain(candidates, *, cutoffs, policy, fallback_weight,
                         repository_root, source_hashes):
    """Route one issue, using market Top1 excluded by current Top2 as conflict.

    candidates: exact integration-weight schema plus integer home handicap;
    one row per native issue/slot/provider/weight. Current draw weight is .5;
    explicit fallback is 0 or .25; high expert remains frozen upstream at .5.
    cutoffs: exact slot -> shared Cutoff objects. KEEP, REDUCE and SKIP do not
    add directions or score protection. Returns retained label-free rows, all
    current rows, a per-fixture ledger and source/implementation-bound receipt.
    Tie order W,D,L, matching the N7 planner. No learned cache or data writes.
    Missing/invalid schema, chronology, prices and identities fail closed.
    """
    keys=['issue','slot','provider_id']
    probs=[p+d for p in ['p_','q_'] for d in 'WDL']
    columns=keys+['weight','handicap']+probs
    if policy not in {'KEEP','REDUCE','SKIP'} or type(fallback_weight) not in (int,float) or fallback_weight not in (0,.25):
        raise ValueError('Explicit fixed policy and fallback weight 0/.25 required')
    if set(candidates.columns)!=set(columns) or candidates.empty or candidates.issue.nunique()!=1:
        raise ValueError('Exact nonempty one-issue label-free schema required')
    if not source_hashes or any(not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in source_hashes.values()):
        raise ValueError('Explicit SHA256 source bindings required')
    frame=candidates.sort_values(keys+['weight']).copy()
    if frame.handicap.isna().any() or not np.isfinite(frame.handicap).all() or not frame.handicap.eq(np.floor(frame.handicap)).all():
        raise ValueError('Integer home handicap required')
    if frame.groupby(keys).handicap.nunique().ne(1).any():
        raise ValueError('Handicap changes across weights')
    identity=frame[keys].drop_duplicates()
    if identity.slot.duplicated().any() or identity.provider_id.duplicated().any():
        raise ValueError('Native slot/provider must each be unique')
    if set(cutoffs)!=set(identity.slot.astype(str)):
        raise ValueError('Exact fixture cutoff scope required')
    issue=frame.issue.iloc[0]
    for cutoff in cutoffs.values():
        if not isinstance(cutoff,Cutoff) or cutoff.target_issue!=issue:
            raise ValueError('Matching shared cutoff required')
    routing_args=dict(cutoffs={issue:cutoffs},mode='FIXED',penalty=0)
    current=select_integration_weights(frame.drop(columns='handicap'),fixed_weight=.5,**routing_args)
    fallback=select_integration_weights(frame.drop(columns='handicap'),fixed_weight=fallback_weight,**routing_args)
    alternatives={r['slot']:r for r in fallback['rows']}
    handicaps=frame.drop_duplicates('slot').set_index('slot').handicap.to_dict()
    retained=[];baseline=[];ledger=[]
    for r in current['rows']:
        p=np.array([r['p_'+d] for d in 'WDL']);q=np.array([r['q_'+d] for d in 'WDL'])
        top2=np.argsort(-p,kind='stable')[:2];market_top=int(np.argmax(q))
        conflict=market_top not in top2
        action='SKIP' if conflict and policy=='SKIP' else 'REDUCE' if conflict and policy=='REDUCE' else 'KEEP'
        chosen=alternatives[r['slot']] if action=='REDUCE' else r
        b={k:r[k] for k in keys+probs};b['handicap']=int(handicaps[r['slot']]);baseline.append(b)
        if action!='SKIP':
            selected={k:chosen[k] for k in keys+probs};selected['handicap']=b['handicap'];retained.append(selected)
        ledger.append(dict(**{k:r[k] for k in keys},conflict=bool(conflict),action=action,
            market_top='WDL'[market_top],current_top2=''.join('WDL'[i] for i in sorted(top2)),
            routed_top2=None if action=='SKIP' else ''.join('WDL'[i] for i in sorted(np.argsort(-np.array([chosen['p_'+d] for d in 'WDL']),kind='stable')[:2])),
            draw_weight=None if action=='SKIP' else chosen['weight'],market_excluded_probability=float(q[market_top]) if conflict else None))
    receipt=dict(policy=policy,fallback_weight=fallback_weight,current_weight=.5,
        conflict='MARKET_TOP1_EXCLUDED_BY_CURRENT_MODEL_TOP2',tie_order='WDL',
        cutoffs={s:c.cutoff_ts.isoformat() for s,c in sorted(cutoffs.items())},
        source_hashes=source_hashes,input_hash=stable_json_hash(frame.to_json(orient='records')),
        implementation=implementation_closure(repository_root,['src.fundamentals_decision_chain'],distributions=['numpy','pandas']),
        historical_admission=False,learning='NONE_FIXED_RULE',cache='NONE')
    payload=dict(rows=retained,baseline=baseline,ledger=ledger,receipt=receipt)
    return dict(**payload,seal=stable_json_hash(payload))


def limit_decision_chain_plan(plan, *, groups, cutoffs):
    """Keep first K existing concentrated groups for an exact-stake control.

    K may be zero. Does not refill, re-rank, multiply stakes or read labels.
    Requires original sealed plan and exact native shared cutoffs. Returns a
    new sealed plan binding its parent; input is not mutated. CNY accounting
    and individual ticket units remain those of the authoritative N7 planner.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan.get('seal'):
        raise ValueError('Plan changed')
    if type(groups) is not int or not 0<=groups<=plan['groups']:
        raise ValueError('Group cap must be integer within original plan')
    if set(cutoffs)!=set(plan['cutoffs']) or any(not isinstance(c,Cutoff) or c.target_issue!=plan['issue'] or c.cutoff_ts.isoformat()!=plan['cutoffs'][s] for s,c in cutoffs.items()):
        raise ValueError('Original exact shared cutoffs required')
    result=copy.deepcopy(plan);result.pop('seal');result['parent_seal']=plan['seal']
    result['groups']=groups
    result['legs']=[r for r in result['legs'] if r['group']<=groups]
    result['tickets']=[r for r in result['tickets'] if r['group']<=groups]
    result['stake']=sum(t['units'] for t in result['tickets'])*result['unit_cny']
    result['seal']=stable_json_hash(result)
    return result
