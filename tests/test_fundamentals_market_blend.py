import copy
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_market_blend import blend_market_scores


def test_grid_blending_projects_mass_and_keeps_small_handicaps():
 fs=[];scores=[];grids={};status=[];cuts={}
 for slot in range(1,15):
  f=dict(issue='001',slot=slot,provider_id=f'{slot:03}',home='H',away='A',handicap=-2 if slot%2 else 0,scenario='baseline');fs.append(f)
  cells=[]
  for (h,a),b,q in zip([(0,0),(2,0),(4,0),(0,4)],[.4,.3,.1,.2],[.1,.2,.5,.2]):
   margin=h-a+f['handicap'];outcome='W' if margin>0 else 'L' if margin<0 else 'D'
   scores.append(dict(**f,home_goals=h,away_goals=a,probability=b,outcome=outcome))
   cells.append(dict(home_goals=h,away_goals=a,probability=q,outcome=outcome))
  grids[f'001/{slot}']=cells;status.append(dict(**f,status='READY'));cuts[str(slot)]=Cutoff.decision_epoch('001','2010-01-01T00:00:00Z')
 clocks={'001':{s:c.cutoff_ts.isoformat() for s,c in cuts.items()}}
 control=dict(fixtures=fs,scores=scores,cutoffs=clocks);market=dict(grids=grids,status=status,cutoffs=clocks)
 old=copy.deepcopy((control,market))
 for weight in [0,.25,.5,.75,1]:
  out=blend_market_scores(control,market,cutoffs=cuts,market_weight=weight,minimum_handicap=2)
  f=pd.DataFrame(out['rows'])
  assert f.loc[f.slot==1,'p_W'].iloc[0]==pytest.approx(.1+weight*.4)
  assert f.loc[f.slot==2,'p_W'].iloc[0]==pytest.approx(.4)
  assert f.loc[f.slot==1,'q_W'].iloc[0]==pytest.approx(.5)
  assert f[['p_W','p_D','p_L']].sum(axis=1).eq(1).all()
 assert (control,market)==old
 with pytest.raises(ValueError):blend_market_scores(control,market,cutoffs=cuts,market_weight=.3,minimum_handicap=2)
 bad=copy.deepcopy(market);bad['grids']['001/1'][0]['probability']=.9
 with pytest.raises(ValueError):blend_market_scores(control,bad,cutoffs=cuts,market_weight=.5,minimum_handicap=2)
 badcuts=dict(cuts);badcuts['1']=Cutoff.decision_epoch('001','2011-01-01T00:00:00Z')
 with pytest.raises(ValueError):blend_market_scores(control,market,cutoffs=badcuts,market_weight=.5,minimum_handicap=2)
