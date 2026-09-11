"""Fixed-seed random support swaps only on repeated fixture occurrences."""
import copy
import hashlib
import itertools
import random
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def random_reuse_plan(base, *, cutoffs, seed, probability, group_size, budget_cny, unit_cny, payout_factor):
    """Replace repeated A singles by qTop2, doubles by source Top1+Top3.

    Input is sealed paired_double_source output; native Cutoffs and constants
    required. First appearance in ordered components stays unchanged, irrespective
    of role. Each later occurrence has an independent seeded Bernoulli decision;
    no cascading swaps. Single rank q; double rank p or q per double_source.
    Stable W/D/L ties. Hash(seed,issue,group,slot) gives common random draws across
    paired source arms, with no global RNG use. Return sealed full tickets and
    occurrence ledger; same groups, cost, cash. No fit, labels, I/O or mutation.
    Exposed historical diagnosis only; fixed seeds are not selected by results.
    """
    if type(seed) is not int or seed<0 or not isinstance(probability,(int,float)) or not 0<=probability<=1:
        raise ValueError('Explicit seed and probability in [0,1] required')
    if group_size not in (6,7) or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65) or base.get('double_source') not in ('BASELINE','MARKET'):
        raise ValueError('Fixed source and business constants required')
    if base.get('seal')!=stable_json_hash({k:v for k,v in base.items() if k!='seal'}):raise ValueError('Source changed')
    if set(cutoffs)!=set(base['cutoffs']):raise ValueError('Exact cutoff scope required')
    for s,c in cutoffs.items():
        if not isinstance(c,Cutoff) or c.target_issue!=base['issue'] or c.cutoff_ts.isoformat()!=base['cutoffs'][s]:
            raise ValueError('Source cutoff changed')
    unique={}
    for part in base['components']:
        if part['seal']!=stable_json_hash({k:v for k,v in part.items() if k!='seal'}):raise ValueError('Component changed')
        for r in part['legs']:
            data={k:r[k] for k in ['issue','slot','provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L']}
            if r['slot'] in unique and unique[r['slot']]!=data:raise ValueError('Inconsistent reused fixture')
            unique[r['slot']]=data
    if unique:rank_double_candidates(pd.DataFrame(unique.values()),cutoffs={str(s):cutoffs[str(s)] for s in unique})
    result=copy.deepcopy(base);result['components']=[copy.deepcopy(p) for p in base['components']];result.pop('seal');seen=set();ledger=[]
    for group,part in enumerate(result['components'],1):
        part.pop('seal')
        if part['n']!=group_size or len(part['legs'])!=group_size or len({r['slot'] for r in part['legs']})!=group_size or sum(len(r['support'])==1 for r in part['legs'])!=2:
            raise ValueError('Fixed N-leg two-single group required')
        for r in part['legs']:
            single=r['role']=='A';prefix='q' if single or base['double_source']=='MARKET' else 'p'
            order=sorted(range(3),key=lambda i:(-r[prefix+'_'+'WDL'[i]],i))
            original=''.join('310'[i] for i in range(3) if i in (order[:1] if single else order[:2]))
            if r['support']!=original:raise ValueError('Original rank support required')
            eligible=r['slot'] in seen;seen.add(r['slot'])
            draw=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{base["issue"]}|{group}|{r["slot"]}'.encode()).digest(),'big')).random()
            swap=eligible and draw<probability
            if swap:
                chosen=order[1:2] if single else [order[0],order[2]]
                r['support']=''.join('310'[i] for i in range(3) if i in chosen)
            ledger.append(dict(group=group,slot=r['slot'],eligible=eligible,single=single,draw=draw,swapped=swap,original=original,support=r['support']))
        part['tickets']=[dict(group=1,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in part['legs']))]
        if part['stake']!=unit_cny*2**(group_size-2) or len(part['tickets'])!=2**(group_size-2):raise ValueError('Fixed funding required')
        part['seal']=stable_json_hash(part)
    if sum(p['stake'] for p in result['components'])!=base['stake'] or base['cash_cny']+base['stake']!=budget_cny:
        raise ValueError('Funding changed')
    result.update(seed=seed,swap_probability=probability,swap_ledger=ledger,random_source_seal=base['seal'],model_any_hit=None)
    return dict(**result,seal=stable_json_hash(result))
