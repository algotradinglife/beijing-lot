"""Fixed N6 diagnostic built from the existing label-free N7 candidate pool."""
import copy
import itertools
import math
from collections import Counter
from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_compression_breadth import compression_surface
from src.temporal_learning.core import stable_json_hash


def n6_diagnostic_plan(frame,pool,*,cutoffs,depth,budget_cny,unit_cny,payout_factor,max_uses,max_pair_overlap):
    """Select N6 C1/C2 whole groups from all six-subsets of a frozen N7 pool.

    Fixed TOP2 ranking, TOP1 compression via shared compression_surface. Seed
    belongs to the input pool; no seed learning. Greedy disjoint prefix then
    capped reuse. CNY1024 wallet,2-unit tickets,.65 payout, unspent cash retained.
    Cutoffs and original input seal validated by shared implementation. No I/O,
    labels, fitting or mutation. Returns sealed six-leg plan and pool identity.
    """
    if (depth not in (1,2) or type(budget_cny) is not int or budget_cny!=1024 or
        unit_cny!=2 or payout_factor!=.65 or type(max_uses) is not int or max_uses<1 or
        type(max_pair_overlap) is not int or not 0<=max_pair_overlap<=5):
        raise ValueError('Explicit fixed budget, depth and reuse contracts required')
    ranked,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    # Validate the original pool before deriving the six-fixture candidate set.
    compression_surface(frame,pool,cutoffs=cutoffs,depth=depth,rule='TOP1',seed=0)
    if any(len(g)!=7 or len(set(g))!=7 for g in pool['groups']):raise ValueError('Seven-fixture source pool required')
    six={tuple(c) for g in pool['groups'] for c in itertools.combinations(sorted(g),6)}
    rows=ranked.sort_values('slot').to_dict('records')
    # Add a concentrated disjoint N6 prefix, matching the probability principle.
    rank=sorted(range(len(rows)),key=lambda i:(-rows[i]['coverage'],rows[i]['slot']))
    prefix=[tuple(sorted(rank[i:i+6])) for i in range(0,len(rank)-5,6)]
    six.update(prefix)
    derived={k:copy.deepcopy(v) for k,v in pool.items() if k!='seal'}
    derived.update(groups=[list(g) for g in sorted(six)],parent_pool_seal=pool['seal'],pool_size=len(six))
    derived['seal']=stable_json_hash(derived)
    surface=compression_surface(frame,derived,cutoffs=cutoffs,depth=depth,rule='TOP1',seed=0)
    candidates=derived['groups'];cost=unit_cny*2**(6-depth);limit=budget_cny//cost
    order=sorted(range(len(candidates)),key=lambda i:(-math.prod(rows[j]['coverage'] for j in candidates[i]),candidates[i]))
    selected=[candidates.index(list(g)) for g in prefix[:limit]]
    uses=Counter(j for i in selected for j in candidates[i]);sets=[set(candidates[i]) for i in selected]
    for i in order:
        if len(selected)>=limit:break
        g=set(candidates[i])
        if i in selected or any(uses[j]>=max_uses for j in g) or any(len(g&s)>max_pair_overlap for s in sets):continue
        selected.append(i);sets.append(g);uses.update(g)
    legs=[];tickets=[]
    for number,i in enumerate(selected,1):
        current=[]
        for j,mask in zip(candidates[i],surface['masks'][i]):
            r=dict(rows[j],group=number,support=''.join(code for b,code in enumerate('310') if mask&(1<<b)))
            current.append(r);legs.append(r)
        tickets.extend(dict(group=number,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in current)))
    plan=dict(issue=rows[0]['issue'],n=6,selector='TOP2',shape=f'C{depth}E0',funding='UNIT',
        single_rule='TOP1',single_count=depth,groups=len(selected),group_cost_cny=cost,
        legs=legs,tickets=tickets,stake=len(tickets)*unit_cny,cash_cny=budget_cny-len(tickets)*unit_cny,
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,cutoffs=bound,
        input_sha256=pool['input_sha256'],source_pool_seal=pool['seal'],surface_seal=surface['seal'],
        max_uses=max_uses,max_pair_overlap=max_pair_overlap,disjoint_groups=len(prefix[:limit]),
        candidate_count=len(candidates),historical_admission=False,scope='EXPOSED_FIXED_N6_DIAGNOSTIC')
    return dict(**plan,seal=stable_json_hash(plan))
