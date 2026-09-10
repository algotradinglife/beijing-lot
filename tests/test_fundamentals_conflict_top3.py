from copy import deepcopy
import pandas as pd
import pytest
from src.fundamentals_conflict_top3 import conflict_top3_plan
from src.fundamentals_conflict_portfolios import settle_conflict_protection
from src.temporal_learning import Cutoff


@pytest.fixture
def sample():
    rows=[];grids={};cuts={}
    for slot in range(1,17):
        conflict=slot>14
        p=[.2,.4,.4] if conflict else [.5,.3,.2]
        rows.append(dict(issue='100101',slot=slot,provider_id=str(slot),handicap=0,
            **dict(zip(['p_W','p_D','p_L'],p)),q_W=.5,q_D=.3,q_L=.2))
        grids[str(slot)]=[dict(home_goals=h,away_goals=a,p=p[i],q=[.5,.3,.2][i]) for i,(h,a) in enumerate([(1,0),(0,0),(0,1)])]
        cuts[str(slot)]=Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z')
    return pd.DataFrame(rows),grids,cuts


def test_routing_all_conflicts_top3_and_settlement(sample):
    frame,grids,cuts=sample
    kw=dict(cutoffs=cuts,max_groups=6,unit_cny=2,payout_factor=.65,allocation_seed=0)
    saved=deepcopy(grids);b=conflict_top3_plan(frame,grids,**kw);p=b['plan']
    assert p['main']['groups']==2 and p['stake']==524
    assert {r['slot'] for r in p['scores']}=={15,16}
    assert set(r['slot'] for r in p['main']['legs']).isdisjoint({15,16})
    assert [r['option'] for r in p['scores'][:3]]==['0:0','0:1','1:0']
    audit=frame[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,actual_home=1,actual_away=0,bf_option='1:0',bf_sp=8.,status='READY')
    result=settle_conflict_protection(p,audit)
    assert result['score_hits']==2 and result['score_gross']==pytest.approx(20.8)
    assert result['main_gross']==pytest.approx(2*2*.65*2**7)
    audit['bf_sp']=999.;audit['spf_sp']=99.
    assert conflict_top3_plan(frame,grids,**kw)==b and grids==saved
    bad=frame.assign(actual_home=1)
    with pytest.raises(ValueError):conflict_top3_plan(bad,grids,**kw)


@pytest.mark.parametrize('scope',['ALL','NONE','SHORT'])
def test_empty_routing_and_small_parlay(sample,scope):
    f,g,c=sample
    slots=list(range(15,17)) if scope=='ALL' else list(range(1,15)) if scope=='NONE' else list(range(10,17))
    f=f[f.slot.isin(slots)];g={str(s):g[str(s)] for s in slots};c={str(s):c[str(s)] for s in slots}
    p=conflict_top3_plan(f,g,cutoffs=c,max_groups=6,unit_cny=2,payout_factor=.65,allocation_seed=0)['plan']
    assert p['main']['groups']==(2 if scope=='NONE' else 0)
    assert len(p['scores'])==(0 if scope=='NONE' else 6)


def test_exact_cohort_missing_price_and_wrong_cutoff_fail(sample):
    f,g,c=sample;kw=dict(cutoffs=c,max_groups=6,unit_cny=2,payout_factor=.65,allocation_seed=0)
    with pytest.raises(ValueError):conflict_top3_plan(f,{k:v for k,v in g.items() if k!='1'},**kw)
    # Move the only win score to an unbettable 'other' bucket: do not silently buy <3.
    g['15'][0]['home_goals']=9
    with pytest.raises(ValueError,match='Three'):conflict_top3_plan(f,g,**kw)
    g['15'][0]['home_goals']=1;c['15']=Cutoff.decision_epoch('100102','2010-01-01T00:00:00Z')
    with pytest.raises(ValueError):conflict_top3_plan(f,g,**kw)


def test_archived_report_fixture(tmp_path):
    import subprocess,sys,json,hashlib
    out=tmp_path/'report'
    cmd=[sys.executable,'scripts/prepare_conflict_top3_fixture.py','--output',str(out)]
    subprocess.run(cmd,check=True)
    archive=json.loads((out/'archive.json').read_text())
    assert archive['mode']=='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY'
    for path,h in archive['hashes'].items():
        from pathlib import Path
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    assert len(json.loads((out/'results.json').read_text())['rows'])==160
    assert subprocess.run(cmd,capture_output=True).returncode!=0
