import pandas as pd
import pytest
from src.fundamentals_score_events import score_event_rows


def test_fixed_events_and_contracts():
    f=pd.DataFrame([dict(issue='001',slot=1,provider_id='007',handicap=-1)])
    g=pd.DataFrame([dict(issue='001',slot=1,provider_id='007',home_goals=h,away_goals=a,probability=p)
        for h,a,p in [(0,0,.2),(1,0,.3),(3,0,.4),(0,5,.1)]])
    r=score_event_rows(g,f).set_index('event').probability
    assert r.to_dict()==pytest.approx(dict(ordinary_draw=.2,handicap_draw=.3,home_ge2=.4,away_ge2=.1,
        home_ge3=.4,away_ge3=.1,total_ge5=.1,giving_cover=.4))
    assert 'giving_cover' not in score_event_rows(g,f.assign(handicap=0)).event.tolist()
    assert score_event_rows(g,f.assign(handicap=1)).set_index('event').loc['giving_cover','probability']==pytest.approx(.1)
    for bad in [g.iloc[:-1],pd.concat([g,g.iloc[:1]]),g.assign(probability=float('nan')),g.assign(home_goals=.5),g.assign(provider_id='7')]:
        with pytest.raises(ValueError):score_event_rows(bad,f)
    with pytest.raises(ValueError):score_event_rows(g,pd.concat([f,f]))
    with pytest.raises(ValueError):score_event_rows(g,f.assign(handicap=.5))
    with pytest.raises(ValueError):score_event_rows(g,f.assign(provider_id=7))
