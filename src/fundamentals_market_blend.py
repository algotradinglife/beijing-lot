"""Fixed score-grid mixture for large handicaps; no fitting or label access."""
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_score_events import score_event_rows


def blend_market_scores(control,market,*,cutoffs,market_weight,minimum_handicap):
    """Mix normalized baseline/market grids on union of score cells then project.

    Inputs use saved control/market JSON shapes. Native per-slot Cutoffs must
    exactly match both fixture-relative clock maps. Only abs(handicap)>=2 uses
    fixed market_weight in {0,.25,.5,.75,1}; market q never changes. No labels,
    fitting, I/O or mutation. Return factors, mixed score cells, event masses,
    explicit parameters/input hashes and sealed provenance.
    """
    if type(market_weight) not in (int,float) or market_weight not in (0,.25,.5,.75,1) or type(minimum_handicap) is not int or minimum_handicap!=2:
        raise ValueError('Fixed weight grid and handicap threshold2 required')
    fs=pd.DataFrame(control['fixtures']);keys=['issue','slot','provider_id']
    if fs.empty or fs.issue.nunique()!=1 or fs.duplicated(keys).any() or not fs.scenario.eq('baseline').all():raise ValueError('Unique baseline fixtures required')
    issue=fs.issue.iloc[0]
    if control['cutoffs']!=market['cutoffs'] or set(cutoffs)!=set(fs.slot.astype(str)):raise ValueError('Exact cutoff scope required')
    for s,c in cutoffs.items():
        if not isinstance(c,Cutoff) or c!=Cutoff.decision_epoch(issue,control['cutoffs'][issue][s]):raise ValueError('Original native cutoffs required')
    status=pd.DataFrame(market['status'])
    if status.duplicated(keys).any():raise ValueError('Duplicate market identities')
    bs=pd.DataFrame(control['scores']);factors=[];mixed=[]
    for f in fs.to_dict('records'):
        b=bs[(bs.issue==issue)&(bs.slot==f['slot'])&(bs.provider_id==f['provider_id'])&(bs.scenario=='baseline')]
        st=status[(status.issue==issue)&(status.slot==f['slot'])&(status.provider_id==f['provider_id'])]
        if len(st)!=1 or st.iloc[0]['status']!='READY' or st.iloc[0]['handicap']!=f['handicap']:raise ValueError('Market status/handicap mismatch')
        q=pd.DataFrame(market['grids'][f"{issue}/{f['slot']}"])
        fixture=pd.DataFrame([f])
        for grid in [b,q]:
            check=grid.assign(**{k:f[k] for k in keys})
            score_event_rows(check,fixture)
            net=grid.home_goals-grid.away_goals+f['handicap']
            if not np.array_equal(grid.outcome,np.where(net>0,'W',np.where(net<0,'L','D'))):raise ValueError('Outcome projection mismatch')
        g=b[['home_goals','away_goals','probability']].merge(q[['home_goals','away_goals','probability']],
            on=['home_goals','away_goals'],how='outer',validate='one_to_one',suffixes=('_b','_q')).fillna(0)
        w=float(market_weight) if abs(f['handicap'])>=minimum_handicap else 0.
        g['probability']=(1-w)*g.probability_b+w*g.probability_q
        net=g.home_goals-g.away_goals+f['handicap'];g['outcome']=np.where(net>0,'W',np.where(net<0,'L','D'))
        row={k:f[k] for k in keys+['home','away','handicap']}
        for d in 'WDL':
            row['p_'+d]=float(g.loc[g.outcome==d,'probability'].sum());row['q_'+d]=float(q.loc[q.outcome==d,'probability'].sum())
        factors.append(row)
        for cell in g[['home_goals','away_goals','probability','outcome']].to_dict('records'):
            mixed.append({**{k:f[k] for k in keys},**cell})
    frame=pd.DataFrame(factors);_,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    events=score_event_rows(pd.DataFrame(mixed),fs)
    result=dict(rows=factors,scores=mixed,events=events.to_dict('records'),cutoffs=bound,market_weight=float(market_weight),
        minimum_handicap=minimum_handicap,control_hash=stable_json_hash(control),market_hash=stable_json_hash(market),historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))
