"""Independent verification of fixed OPEN_FIRST allocations; no fitting or IO."""
import numpy as np


def replay_open_first(snapshot, cutoff, budget, objective):
    """Return R one-based option indices for a frozen breadth/depth snapshot.

    Explicit matching cutoff, CNY budget in two-yuan units, frozen 0/1 worlds
    and option records are required. Reject malformed inputs with ValueError.
    Uses no actual labels, randomness or learned parameters.
    """
    if (not cutoff or snapshot['cutoffs']!=cutoff or snapshot['train']['cutoffs']!=cutoff
            or snapshot['mode'] not in ('BREADTH','DEPTH')
            or objective not in ('any_hit','coverage_sum','expected_net')
            or not np.isfinite(budget) or budget<0 or budget%2):
        raise ValueError('Invalid allocation contract')
    opts=snapshot['options'];n=len(opts)
    cost=np.array([o['stake'] for o in opts],dtype=float)
    value=np.array([o['expected_gross'] for o in opts],dtype=float)
    mass=np.array([o['coverage'] for o in opts],dtype=float)
    ids=np.array([o['sleeve_id'] for o in opts])
    hits=np.asarray(snapshot['train']['hits'])
    if (hits.ndim!=2 or hits.shape[1]!=n or not hits.shape[0]
            or not np.isin(hits,[0,1]).all() or not np.isfinite(cost).all()
            or (cost<=0).any() or (cost%2).any() or not np.isfinite(value).all()
            or (value<0).any() or not np.isfinite(mass).all()
            or ((mass<0)|(mass>1)).any() or any(o['unit_copies']!=1 for o in opts)):
        raise ValueError('Invalid options/worlds')
    opening=np.atleast_1d(snapshot['opening_options']).tolist()
    held=np.atleast_1d(snapshot['opportunity_options']).tolist()
    for values in (opening,held):
        if len(set(values))!=len(values) or any(j!=int(j) or not 1<=j<=n for j in values):
            raise ValueError('Invalid option indices')
    opening=[int(j)-1 for j in opening];held=[int(j)-1 for j in held]
    if len(set(ids[held]))!=len(held) or cost[held].sum()>budget:
        raise ValueError('Invalid initial allocation')
    for _ in range(n+1):
        spent=cost[held].sum();events=hits[:,held].sum(axis=1)
        unused=[j for j in opening if ids[j] not in ids[held]]
        candidates=[j for j in unused if cost[j]<=budget-spent]
        if not candidates:
            if snapshot['mode']=='BREADTH':return [j+1 for j in held]
            candidates=[]
            for j,o in enumerate(opts):
                prior=[k for k in held if ids[k]==ids[j]]
                if (o['role']=='CORE' and len(prior)==1 and cost[j]>cost[prior[0]]
                        and cost[j]-cost[prior[0]]<=budget-spent
                        and o['depth']>opts[prior[0]]['depth']):candidates.append(j)
            if not candidates:return [j+1 for j in held]
        scores=[]
        for j in candidates:
            old=[k for k in held if ids[k]==ids[j]]
            proposal=[k for k in held if k not in old]+[j]
            delta=cost[proposal].sum()-spent
            gain=float((hits[:,proposal].sum(axis=1)>0).mean()-(events>0).mean())
            value_rate=((value[proposal].sum()-cost[proposal].sum())-(value[held].sum()-spent))/delta
            coverage_gain=mass[j]-(mass[old[0]] if old else 0)
            primary={'any_hit':gain/delta,'coverage_sum':coverage_gain/delta,'expected_net':value_rate}[objective]
            scores.append(((-primary,-value_rate,-gain,ids[j],j),proposal))
        held=min(scores,key=lambda item:item[0])[1]
    raise ValueError('Nonterminating allocation')
