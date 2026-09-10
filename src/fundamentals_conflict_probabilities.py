"""Fixed score-distribution mixtures and exact-score offers for conflict research."""
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.nowscore_settlement import expected_option


def conflict_score_projection(grid, fixture, *, cutoff, market_weight):
    """Mix full score distributions only when market Top1 is outside current Top2.

    grid exact columns: home_goals, away_goals, p, q; one unique integer score
    per row, absent support represented by zero, each distribution normalized.
    fixture exact identity/handicap and frozen p_WDL/q_WDL columns. Cutoff is a
    shared fixture epoch. Weight 0/.5/1 is a declared policy, not fitted. Market
    q never changes. Marginals use frozen precision to reproduce the control;
    their agreement with score sums is checked to 1e-12 and disclosed.
    Returns score rows, updated fixture, conflict and sealed input/cutoff ledger.
    No labels, fitting, writes or caching. IDs, missing values and sums fail closed.
    """
    keys=['issue','slot','provider_id','handicap'];cols=[p+d for p in ['p_','q_'] for d in 'WDL']
    if set(fixture)!=set(keys+cols) or not isinstance(cutoff,Cutoff) or cutoff.target_issue!=fixture['issue']:
        raise ValueError('Exact label-free fixture and matching Cutoff required')
    if not isinstance(fixture['issue'],str) or not isinstance(fixture['provider_id'],str) or not fixture['provider_id'] or type(fixture['slot']) is not int or fixture['slot']<1:
        raise ValueError('String IDs and native positive slot required')
    if type(market_weight) not in (int,float) or market_weight not in (0,.5,1):
        raise ValueError('Fixed market mixture weight required')
    if not np.isfinite(fixture['handicap']) or fixture['handicap']!=int(fixture['handicap']):
        raise ValueError('Integer home handicap required')
    frame=pd.DataFrame(grid)
    if set(frame)!=set(['home_goals','away_goals','p','q']) or frame.empty or frame.duplicated(['home_goals','away_goals']).any():
        raise ValueError('Unique exact score schema required')
    values=frame[['home_goals','away_goals','p','q']].to_numpy(float)
    if not np.isfinite(values).all() or (values<0).any() or (values[:,:2]!=np.floor(values[:,:2])).any() or not np.allclose(values[:,2:].sum(axis=0),1,rtol=0,atol=1e-9):
        raise ValueError('Normalized finite grids and integer scores required')
    p=np.array([fixture['p_'+d] for d in 'WDL']);q=np.array([fixture['q_'+d] for d in 'WDL'])
    if not np.isfinite(np.r_[p,q]).all() or (p<0).any() or (q<=0).any() or not np.allclose([sum(p),sum(q)],1,rtol=0,atol=1e-9):
        raise ValueError('Normalized probabilities and positive market masses required')
    margin=values[:,0]-values[:,1]+fixture['handicap'];direction=np.where(margin>0,'W',np.where(margin==0,'D','L'))
    for i,d in enumerate('WDL'):
        if abs(values[direction==d,2].sum()-p[i])>1e-12 or abs(values[direction==d,3].sum()-q[i])>1e-12:
            raise ValueError('Frozen score/marginal identity mismatch')
    selected=np.argsort(-p,kind='stable')[:2];top=int(np.argmax(q));conflict=top not in selected
    alpha=float(market_weight) if conflict else 0.
    adjusted=frame.sort_values(['home_goals','away_goals']).copy()
    adjusted['p']=(1-alpha)*adjusted.p+alpha*adjusted.q
    changed=dict(fixture)
    for i,d in enumerate('WDL'):changed['p_'+d]=float((1-alpha)*p[i]+alpha*q[i])
    receipt=dict(cutoff=cutoff.cutoff_ts.isoformat(),issue=cutoff.target_issue,market_weight=market_weight,
        applied_weight=alpha,conflict=bool(conflict),input_hash=stable_json_hash(dict(fixture=fixture,grid=frame.sort_values(['home_goals','away_goals']).to_dict('records'))),
        market='FIXED_EURO_PLUS_TOTALS',marginal_precision='FROZEN_MARGINALS_SCORE_SUM_TOLERANCE_1e-12',historical_admission=False)
    payload=dict(fixture=changed,grid=adjusted.to_dict('records'),receipt=receipt)
    return dict(**payload,seal=stable_json_hash(payload))


def conflict_score_offer(projection, *, cutoff):
    """Nominate one bettable exact score in the CURRENT omitted direction.

    Uses a zero-weight validated projection only. Official 'other' buckets are
    excluded: they can span handicap directions. Score ties prefer fewer home,
    then away goals. SP proxy is 1/q_score; no final SP. Non-conflicts still get
    diagnostic offers but are never selected by the conflict-only portfolio.
    Returns READY or a reason when no positive-price exact option exists.
    """
    if stable_json_hash({k:v for k,v in projection.items() if k!='seal'})!=projection.get('seal'):
        raise ValueError('Score projection changed')
    f=projection['fixture'];receipt=projection['receipt']
    if not isinstance(cutoff,Cutoff) or cutoff.target_issue!=f['issue'] or cutoff.cutoff_ts.isoformat()!=receipt['cutoff'] or receipt['market_weight']!=0:
        raise ValueError('Current unmodified projection and exact Cutoff required')
    order=sorted('WDL',key=lambda d:(-f['p_'+d],'WDL'.index(d)));omitted=order[-1]
    rows=[]
    for r in projection['grid']:
        margin=r['home_goals']-r['away_goals']+f['handicap'];d='W' if margin>0 else 'D' if margin==0 else 'L'
        option=f"{int(r['home_goals'])}:{int(r['away_goals'])}"
        if d==omitted and expected_option(dict(play='bf',score=option))==option and r['q']>0 and r['p']>0:
            rows.append(dict(score_home=int(r['home_goals']),score_away=int(r['away_goals']),option=option,p_score=float(r['p']),q_score=float(r['q'])))
    out={k:f[k] for k in ['issue','slot','provider_id','handicap']}
    out.update(conflict=receipt['conflict'],omitted=omitted,market_omitted_probability=f['q_'+omitted],cutoff=receipt['cutoff'],projection_seal=projection['seal'])
    if rows:
        row=min(rows,key=lambda r:(-r['p_score'],r['score_home'],r['score_away']))
        out.update(row,status='READY',sp_proxy=1/row['q_score'])
    else:out.update(status='NO_EXACT_SCORE_WITH_POSITIVE_MODEL_AND_MARKET_MASS')
    return out
