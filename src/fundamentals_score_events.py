"""Descriptive projection of frozen score grids; no fitting or selection."""
import numpy as np
import pandas as pd


def score_event_rows(scores, fixtures):
    """Return issue/slot/provider/event/probability rows from normalized grids.

    Scores require nonnegative integer home/away goals and finite probabilities.
    Fixtures have unique issue/slot/provider_id and integer handicap. Event
    definitions are fixed, not estimated from labels. No I/O or side effects.
    """
    keys=['issue','slot','provider_id']
    if fixtures.empty or fixtures.duplicated(keys).any() or fixtures.duplicated(['issue','slot']).any():
        raise ValueError('Unique nonempty fixture identities required')
    if fixtures[keys+['handicap']].isna().any().any() or scores[keys].isna().any().any():
        raise ValueError('Missing identities')
    if not all(isinstance(v,str) for k in ['issue','provider_id'] for v in fixtures[k]):
        raise ValueError('String identifiers required')
    if scores.duplicated(keys+['home_goals','away_goals']).any():raise ValueError('Duplicate score cells')
    v=scores[['home_goals','away_goals','probability']].to_numpy(dtype=float)
    if not np.isfinite(v).all() or (v<0).any() or not np.equal(v[:,:2],np.floor(v[:,:2])).all():
        raise ValueError('Invalid score grid')
    if set(map(tuple,scores[keys].drop_duplicates().to_numpy()))!=set(map(tuple,fixtures[keys].to_numpy())):
        raise ValueError('Fixture/grid mismatch')
    output=[]
    for z in fixtures.to_dict('records'):
        g=scores[(scores.issue==z['issue'])&(scores.slot==z['slot'])&(scores.provider_id==z['provider_id'])]
        if abs(g.probability.sum()-1)>1e-8 or not np.isfinite(z['handicap']) or z['handicap']!=int(z['handicap']):
            raise ValueError('Normalized grid and integer handicap required')
        d=g.home_goals-g.away_goals;t=g.home_goals+g.away_goals
        masks=dict(ordinary_draw=d==0,handicap_draw=d+z['handicap']==0,
            home_ge2=d>=2,away_ge2=d<=-2,home_ge3=d>=3,away_ge3=d<=-3,total_ge5=t>=5,
            giving_cover=(d+z['handicap']>0 if z['handicap']<0 else d+z['handicap']<0))
        for event,mask in masks.items():
            if event=='giving_cover' and z['handicap']==0:continue
            output.append({**{k:z[k] for k in keys},'event':event,'probability':float(g.loc[mask,'probability'].sum())})
    return pd.DataFrame(output)
