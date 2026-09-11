import copy
from collections import Counter
import pandas as pd
import pytest
from tests.test_fundamentals_n67_overlay import sample
from src.fundamentals_n7_twocover import n7_twocover_plan,settle_n7_twocover

@pytest.mark.parametrize('n',[5,7,14,21,42,50])
def test_two_cover_constraints_and_cash(n):
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']};kw['max_groups']=6
    plans={s:n7_twocover_plan(x,strategy=s,**kw) for s in ['BASE','DOUBLE_STAKE','TWO_COVER']}
    p=plans['TWO_COVER'];base=plans['BASE'];count=min(6,n//7)
    assert p==n7_twocover_plan(x.sample(frac=1,random_state=3),strategy='TWO_COVER',**kw)
    events=[frozenset(r['slot'] for r in part['legs'] if r['group']==g) for part in p['components'] for g in range(1,part['groups']+1)]
    assert len(set(events))==len(events)
    assert all(len(e)==7 for e in events)
    assert max(Counter(s for e in events for s in e).values(),default=0)<=2
    assert p['stake']==plans['DOUBLE_STAKE']['stake']==base['stake']*(2 if count>=2 else 1)
    assert p['model_any_hit']>=base['model_any_hit']-1e-12
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    result=settle_n7_twocover(p,a)
    assert result['gross']==pytest.approx(len(events)*2*.65*2**7)
    assert result['hits']==len(events)
    assert result['status']==('COMPLETE' if count else 'NO_BET')
    if count:
        a['spf_sp']=float('nan')
        assert settle_n7_twocover(p,a)['gross'] is None
    p['stake']+=2
    with pytest.raises(ValueError):settle_n7_twocover(p,a)
    with pytest.raises(ValueError):n7_twocover_plan(x.assign(actual_home=1),strategy='BASE',**kw)
    with pytest.raises(ValueError):n7_twocover_plan(x,strategy='BAD',**kw)

@pytest.mark.parametrize('n',[5,14])
def test_independent_cash_cli(tmp_path,n):
    import json,subprocess,sys
    from pathlib import Path
    x,old=sample(n);kw={k:v for k,v in old.items() if k not in ['max_n6','max_n7']};kw['max_groups']=6
    plans=[n7_twocover_plan(x,strategy=s,**kw) for s in ['BASE','DOUBLE_STAKE','TWO_COVER']]
    a=x[['issue','slot','provider_id','handicap']].copy();a['status']='READY';a['actual_direction']='W';a['spf_sp']=2.
    rows=[settle_n7_twocover(p,a) for p in plans]
    (tmp_path/'plans.json').write_text(json.dumps(plans))
    value=dict(results=rows,audit=a.to_dict('records'))
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/replay_n7_twocover.py'),str(tmp_path)]
    assert subprocess.run(cmd,capture_output=True).returncode==0
    # Strategy-name swaps formerly escaped replay's unreachable cross-arm checks.
    if n>=14:
        bad=copy.deepcopy(plans);bad[0]['strategy'],bad[1]['strategy']=bad[1]['strategy'],bad[0]['strategy']
        (tmp_path/'plans.json').write_text(json.dumps(bad))
        assert subprocess.run(cmd,capture_output=True).returncode!=0
        (tmp_path/'plans.json').write_text(json.dumps(plans))
        a['status']=None
        missing=dict(results=[settle_n7_twocover(p,a) for p in plans],audit=a.to_dict('records'))
        (tmp_path/'settlement.json').write_text(json.dumps(missing))
        assert subprocess.run(cmd,capture_output=True).returncode==0
    rows[0]['gross']+=1
    (tmp_path/'settlement.json').write_text(json.dumps(value))
    assert subprocess.run(cmd,capture_output=True).returncode!=0
