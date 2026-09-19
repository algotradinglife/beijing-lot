import hashlib,json
import pytest
from src.handicap_line_inputs import read_handicap_line_inputs

@pytest.mark.parametrize('mutation',[None,'mass','duplicate','projection','missing'])
def test_grid_contract_and_explicit_exclusions(tmp_path,mutation):
 f=dict(issue='001',slot=1,provider_id='0003',handicap=-1,q_W=.2,q_D=.5,q_L=.3)
 g=[dict(home_goals=n,away_goals=0,probability=p) for n,p in enumerate([.3,.5,.2])]
 if mutation=='mass':g[0]['probability']=.4
 if mutation=='duplicate':g.append(g[0])
 if mutation=='projection':f['q_W']=.3
 x=dict(fixtures=[f],grids={'001/1':g} if mutation!='missing' else {})
 p=tmp_path/'source.json';p.write_text(json.dumps(x));m=dict(sources=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),kind='fixtures',issues=['001']),dict(archive='unused',issues=['002'])])
 mp=tmp_path/'manifest.json';mp.write_text(json.dumps(m));sha=hashlib.sha256(mp.read_bytes()).hexdigest()
 if mutation:
  with pytest.raises(ValueError):read_handicap_line_inputs(str(mp),sha)
 else:
  r=json.loads(read_handicap_line_inputs(str(mp),sha));assert r['rows'][0]['distribution'][1]==dict(net=1,probability=.5)
  assert r['exclusions']==[dict(issue='002',reason='ARCHIVED_GRID_NOT_INVENTORIED')]
