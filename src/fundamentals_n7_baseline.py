"""Fixed, label-free N7 baseline ablations on archived fixture-relative inputs.

No fitting or prospective admission. Reuses the corrected #369/#373 support
ranking; explicit budget policies are owner-authorized retrospective scenarios.
"""
from pathlib import Path
import hashlib
import itertools
import json
import math
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
from src.n7_support_shape.pipeline import _rank_shape_pair
from src.n7_support_transfer_grid.pipeline import _maximal_assignment


def archive_n7_inputs(studies, repository_root):
    """Read fixed archived baseline/market probabilities; return inputs and labels separately.

    Each study has predictions.json and comparison.json. Cohort is explicitly
    retrospective accepted/completed matches. Market-unavailable cases retain
    exclusion reasons; no substitute prices. Returns tidy rows, native cutoffs,
    outcomes, source hashes and transitive implementation receipt. No writes.
    """
    root=Path(repository_root); rows=[]; labels=[]; exclusions=[]; cutoffs={}; hashes={}; seen=set()
    for study in studies:
        paths=[root/study/'predictions.json',root/study/'comparison.json']
        raw=[p.read_bytes() for p in paths]
        for p,b in zip(paths,raw): hashes[str(p)]=hashlib.sha256(b).hexdigest()
        prediction,comparison=[json.loads(b) for b in raw]
        native=prediction['selected']['cutoffs']
        if native!=prediction['market']['cutoffs']: raise ValueError('Cutoff maps differ')
        score=pd.DataFrame(prediction['selected']['scores'])
        score=score[score.scenario.eq('baseline')]
        groups={k:g for k,g in score.groupby(['issue','slot','provider_id'],sort=False)}
        status_rows=prediction['market']['status']
        status={(r['issue'],r['slot'],r['provider_id']):r for r in status_rows}
        if len(status)!=len(status_rows): raise ValueError('Duplicate market identities')
        for f in comparison['fixtures']:
            if f['scenario']!='baseline': continue
            issue,slot,provider=[f[k] for k in ['issue','slot','provider_id']];key=(issue,slot,provider)
            if key in seen: raise ValueError('Duplicate cohort identities')
            seen.add(key)
            market=prediction['market']['grids'].get(f'{issue}/{slot}');st=status.get(key)
            if market is None or st is None or st['status']!='READY':
                exclusions.append(dict(issue=issue,slot=slot,provider_id=provider,reason=st['status'] if st else 'NO_MARKET_IDENTITY'));continue
            if st['handicap']!=f['handicap'] or key not in groups: raise ValueError('Handicap/identity mismatch')
            p=[];q=[]
            for grid,dest in [(groups[key],p),(pd.DataFrame(market),q)]:
                if (grid[['home_goals','away_goals']].duplicated().any() or
                    grid.probability.isna().any() or not np.isfinite(grid.probability).all() or
                    (grid.probability<0).any() or abs(grid.probability.sum()-1)>1e-8): raise ValueError('Invalid archived grid')
                net=grid.home_goals-grid.away_goals+f['handicap']
                dest.extend([float(grid.probability[net>0].sum()),float(grid.probability[net==0].sum()),float(grid.probability[net<0].sum())])
            row={k:f[k] for k in ['issue','slot','provider_id','handicap','home','away']}
            row.update({f'p_{d}':p[i] for i,d in enumerate('WDL')});row.update({f'q_{d}':q[i] for i,d in enumerate('WDL')})
            rows.append(row);labels.append({k:f[k] for k in ['issue','slot','provider_id','handicap','home','away','actual_home','actual_away']})
            cutoffs.setdefault(issue,{})[str(slot)]=native[issue][str(slot)]
    return dict(rows=rows,labels=labels,exclusions=exclusions,cutoffs=cutoffs,source_hashes=hashes,
        implementation=implementation_closure(root,['src.fundamentals_n7_baseline'],distributions=['numpy','pandas']),historical_admission=False)


def rank_double_candidates(frame, *, cutoffs):
    """Validate one-issue prediction inputs and native cutoffs; return Top2 factors and clocks.

    No labels, fitting, sorting policy or I/O. Probabilities normalized; market
    probabilities strictly positive. IDs unique; full cutoff scope mandatory.
    """
    forbidden={'actual_home','actual_away','actual_direction','spf_sp','draw_target','cover_target','result'}
    if forbidden & set(frame): raise ValueError('Prediction-only frame required')
    keys=['issue','slot','provider_id']; x=frame.copy()
    if x.empty or x[keys].isna().any().any() or x.issue.nunique()!=1 or x.slot.duplicated().any() or x.provider_id.duplicated().any():
        raise ValueError('Unique complete one-issue cohort required')
    if not np.isfinite(x.handicap).all() or not x.handicap.eq(np.floor(x.handicap)).all(): raise ValueError('Integer handicap required')
    for prefix in ['p','q']:
        a=x[[f'{prefix}_{d}' for d in 'WDL']].to_numpy(float)
        if not np.isfinite(a).all() or (a<0).any() or (prefix=='q' and (a<=0).any()) or not np.allclose(a.sum(axis=1),1,atol=1e-8,rtol=0):
            raise ValueError('Normalized positive-market triplets required')
    issue=str(x.issue.iloc[0]);bound={}
    if set(cutoffs)!=set(x.slot.astype(str)): raise ValueError('Exact cutoff scope required')
    for slot,epoch in cutoffs.items():
        if not isinstance(epoch,Cutoff) or epoch.target_issue!=issue: raise ValueError('Native target cutoffs required')
        bound[slot]=epoch.cutoff_ts.isoformat()
    codes=['3','1','0'];prob=x[[f'p_{d}' for d in 'WDL']].to_numpy(float);market=x[[f'q_{d}' for d in 'WDL']].to_numpy(float)
    rank=np.argsort(-prob,axis=1,kind='stable')[:,:2]
    x['coverage']=np.take_along_axis(prob,rank,axis=1).sum(axis=1)
    x['value']=np.take_along_axis(prob/market,rank,axis=1).sum(axis=1)
    x['support']=[''.join(codes[i] for i in sorted(r)) for r in rank]
    return x,bound


def n7_baseline_plan(frame, *, cutoffs, selector, shape, funding, max_groups, unit_cny,
                     group_budget_cny, payout_factor, allocation_seed):
    """Freeze disjoint groups and every Cartesian ticket before opening labels.

    frame is one issue of unique slot/provider IDs, integer home handicap,
    normalized p_W/D/L and q_W/D/L (market positive). cutoffs maps slots to
    shared Cutoff objects; each retains its native fixture-relative epoch.
    selector COVERAGE/VALUE; shape C0E0/C1E2/C1E3; funding UNIT/MATCHED.
    MATCHED spends group_budget_cny per group using integer equal allocation,
    deterministic hashed residuals. UNIT buys one unit each. No fitting/I/O.
    """
    if selector not in ['COVERAGE','VALUE'] or shape not in ['C0E0','C1E2','C1E3'] or funding not in ['UNIT','MATCHED']:
        raise ValueError('Explicit fixed ablation policy required')
    if max_groups!=6 or unit_cny!=2 or payout_factor!=.65 or group_budget_cny!=432 or not isinstance(allocation_seed,int):
        raise ValueError('Explicit owner-approved business constants required')
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    issue=str(x.issue.iloc[0]);codes=['3','1','0']
    x=x.sort_values([selector.lower(),'slot','provider_id'],ascending=[False,True,True],kind='stable')
    count=min(max_groups,len(x)//7);x=x.head(count*7).copy();x['group']=np.repeat(np.arange(1,count+1),7)
    tickets=[];leg_rows=[]
    for group,g in x.groupby('group',sort=True):
        g=g.sort_values('slot').copy();support={int(r.slot):tuple(r.support) for r in g.itertuples()}
        shape_input=g.rename(columns={'slot':'match_idx',**{f'p_{d}':f'q_eu_{c}' for d,c in zip('WDL',codes)}})
        if shape!='C0E0':
            _,_,scores=_rank_shape_pair(shape_input,support)
            contraction,expansion=_maximal_assignment(scores)
            retained=scores.set_index('match_idx').retained_outcome
            support[contraction[0]]=(retained.loc[contraction[0]],)
            for slot in expansion[:int(shape[-1])]: support[slot]=tuple(codes)
        cartesian=[''.join(c) for c in itertools.product(*(support[int(s)] for s in g.slot))]
        expected={'C0E0':128,'C1E2':144,'C1E3':216}[shape]
        if len(cartesian)!=expected or len(set(cartesian))!=expected: raise ValueError('Incomplete Cartesian support')
        total_units=expected if funding=='UNIT' else group_budget_cny//unit_cny
        base,remainder=divmod(total_units,expected)
        if base<1: raise ValueError('Unfundable full support')
        ranked=sorted(cartesian,key=lambda c:(hashlib.sha256(f'{allocation_seed}|{issue}|{group}|{c}'.encode()).hexdigest(),c))
        extra=set(ranked[:remainder])
        for code in cartesian: tickets.append(dict(group=int(group),code=code,units=base+int(code in extra)))
        for row in g.to_dict('records'):
            row['support']=''.join(support[int(row['slot'])]);leg_rows.append(row)
    artifact=dict(issue=issue,selector=selector,shape=shape,funding=funding,groups=count,
        legs=leg_rows,tickets=tickets,cutoffs=bound,n=7,unit_cny=unit_cny,payout_factor=payout_factor,
        group_budget_cny=group_budget_cny,allocation_seed=allocation_seed,
        stake=sum(t['units'] for t in tickets)*unit_cny,
        input_sha256=stable_json_hash(frame.sort_values('slot').to_json(orient='records')),
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET')
    artifact['seal']=stable_json_hash(artifact)
    return artifact


def settle_n7_baseline(plan, audit):
    """Settle a sealed plan from R/SQLite audited SPF only; never read BF prices.

    Missing winning SP leaves the entire portfolio PENDING (stake preserved).
    Missing SP on a losing group is unused; identity/score conflicts always
    prevent settlement. Returns gross/net/ROI, hits and ideal equal-stake gross.
    Pre-tax theoretical payoff with 0.65 once per winning ticket; no I/O.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan['seal']: raise ValueError('Plan changed')
    if audit.duplicated(['issue','slot','provider_id']).any(): raise ValueError('Duplicate audit identities')
    base={k:plan[k] for k in ['issue','selector','shape','funding','groups','stake']}
    if not plan['groups']: return dict(**base,status='NO_BET',gross=0.,net=0.,roi=None,hits=0,ideal_gross=0.)
    legs=pd.DataFrame(plan['legs']).merge(audit,on=['issue','slot','provider_id'],how='left',validate='one_to_one',suffixes=('','_audit'))
    if (legs.actual_direction.isna().any() or not legs.actual_direction.isin(['W','D','L']).all() or
        legs.status.isna().any() or legs.status.str.contains('spf:IDENTITY',regex=False).any() or
        not legs.handicap.eq(legs.handicap_audit).all()):
        return dict(**base,status='PENDING_AUDIT',gross=None,net=None,roi=None,hits=None,ideal_gross=None)
    gross=ideal=0.;hits=0;native=dict(W='3',D='1',L='0')
    for group,g in legs.groupby('group',sort=True):
        code=''.join(native[d] for d in g.sort_values('slot').actual_direction)
        tickets=[t for t in plan['tickets'] if t['group']==group];winner=[t for t in tickets if t['code']==code]
        if not winner: continue
        if not np.isfinite(g.spf_sp).all() or (g.spf_sp<=0).any():
            return dict(**base,status='PENDING_WINNING_SP',gross=None,net=None,roi=None,hits=None,ideal_gross=None)
        payout=plan['unit_cny']*plan['payout_factor']*math.prod(g.spf_sp)
        gross+=winner[0]['units']*payout;ideal+=sum(t['units'] for t in tickets)/len(tickets)*payout;hits+=1
    return dict(**base,status='COMPLETE',gross=gross,net=gross-plan['stake'],roi=gross/plan['stake']-1,hits=hits,ideal_gross=ideal)
