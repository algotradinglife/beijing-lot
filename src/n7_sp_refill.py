"""Materialize R-selected refill sets using the authoritative state enumerator."""
from copy import deepcopy
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.n7_sleeve_states import enumerate_sleeve


def materialize_refill(bundle, groups, *, cutoffs, unit_cny, payout_factor):
    """Return a sealed full-state bundle for explicit one-based fixture groups.

    Retained sleeve IDs/contents stay unchanged; new IDs enumerate all2187 states.
    Cutoffs are exact slot->epoch strings, delegated to shared Cutoff objects.
    No selection, labels, fitting or I/O. Invalid identities/seals raise ValueError.
    Empty groups are rejected here; the caller represents an empty pool as cash.
    """
    if (not groups or bundle['cutoffs'] != cutoffs or (unit_cny,payout_factor)!=(2,.65)
            or bundle['seal'] != stable_json_hash({k:v for k,v in bundle.items() if k!='seal'})):
        raise ValueError('Invalid refill source or cutoffs')
    pool=bundle['expanded_pool'];fixtures=pool['fixtures']
    old={g['id']:g for g in bundle['sleeves']}
    output=[];seen=set();ids=set()
    union=set(map(tuple,pool['encoded_tickets']))
    for group in groups:
        gid=group['sleeve_id'];raw=group['fixtures']
        if (isinstance(gid,bool) or int(gid)!=gid or gid in ids or len(raw)!=7
                or any(isinstance(i,bool) or int(i)!=i or not 1<=i<=len(fixtures) for i in raw)):
            raise ValueError('Invalid refill coordinates')
        ix=[int(i)-1 for i in raw];key=tuple(sorted(ix))
        if len(set(ix))!=7 or key in seen or ix!=sorted(ix):
            raise ValueError('Duplicate or noncanonical refill set')
        ids.add(gid);seen.add(key)
        if gid in old:
            if old[gid]['fixture_indices']!=ix or group['origin']!='RETAINED':
                raise ValueError('Retained identity changed')
            output.append(deepcopy(old[gid]));continue
        if group['origin']!='REFILL_TOP2':raise ValueError('Unknown refill origin')
        frame=pd.DataFrame([fixtures[i] for i in ix])
        native={str(f['slot']):Cutoff.decision_epoch(str(f['issue']),cutoffs[str(f['slot'])]) for f in fixtures if str(f['slot']) in set(frame.slot.astype(str))}
        e=enumerate_sleeve(frame,cutoffs=native,unit_cny=unit_cny,payout_factor=payout_factor)
        if e['fixtures'] != [fixtures[i] for i in ix]:raise ValueError('Fixture ordering changed')
        output.append(dict(id=int(gid),fixture_indices=ix,origin='REFILL_TOP2',enumeration=e,options={}))
        union.update(map(tuple,(3*np.asarray(ix)+np.asarray(e['states'])).tolist()))
    result=deepcopy(bundle)
    result['sleeves']=output
    result['expanded_pool']['encoded_tickets']=[list(t) for t in sorted(union)]
    result['expanded_pool']['minimum_scalar_rank']=[1]*len(union)
    result['expanded_pool']['seal']=stable_json_hash({k:v for k,v in result['expanded_pool'].items() if k!='seal'})
    result['refill_source_seal']=bundle['seal']
    result['actual_candidate_count']=len(output)
    result['seal']=stable_json_hash({k:v for k,v in result.items() if k!='seal'})
    return result
