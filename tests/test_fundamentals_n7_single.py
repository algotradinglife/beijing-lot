import itertools
import pandas as pd
import pytest
from src.fundamentals_n7_single import n7_single_plan,next_overlap_group,settle_n7_single
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff


@pytest.fixture
def sample():
    rows=[dict(issue='100101',slot=s,provider_id=str(s),handicap=0,p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for s in range(1,64)]
    rows[0].update(p_W=.61,p_D=.29)
    rows[1].update(p_W=.59,p_D=.2,p_L=.21)
    f=pd.DataFrame(rows);c={str(s):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for s in f.slot}
    return f,c


@pytest.mark.parametrize('rule',['MAX_SINGLE','MIN_RELATIVE_LOSS'])
def test_complete_support_budget_disjoint_groups_and_settlement(sample,rule):
    f,c=sample
    plan=n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=1536,single_rule=rule,unit_cny=2,payout_factor=.65,allocation_seed=0)
    assert plan['groups']==12 and plan['stake']==1536 and plan['cash_cny']==0
    assert plan['disjoint_groups']==9 and plan['overlap_groups']==3
    assert len({r['slot'] for r in plan['legs']})==63
    from collections import Counter
    assert max(Counter(r['slot'] for r in plan['legs']).values())<=2
    sets=[{r['slot'] for r in plan['legs'] if r['group']==g} for g in range(1,13)]
    assert all(len(a&b)<=2 for a,b in itertools.combinations(sets,2))
    for g in range(1,13):
        legs=[r for r in plan['legs'] if r['group']==g];tickets=[t for t in plan['tickets'] if t['group']==g]
        assert sorted(len(r['support']) for r in legs)==[1,2,2,2,2,2,2]
        assert len(tickets)==64 and set(t['code'] for t in tickets)==set(''.join(z) for z in itertools.product(*(r['support'] for r in legs)))
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    result=settle_n7_single(plan,audit)
    assert result['hits']==12 and result['gross']==pytest.approx(12*2*.65*2**7)
    missing=audit.copy();missing.loc[0,'spf_sp']=None
    assert settle_n7_single(plan,missing)['status']=='PENDING_AUDIT_OR_WINNING_SP'
    audit['spf_sp']=99
    assert n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=1536,single_rule=rule,unit_cny=2,payout_factor=.65,allocation_seed=0)==plan


def test_rules_choose_different_legs_and_cash_boundaries(sample):
    f,c=sample;f=f.head(7).copy();c={str(s):c[str(s)] for s in f.slot}
    # One complete group contains all candidates; relative retention favors slot2.
    for rule,slot in [('MAX_SINGLE',1),('MIN_RELATIVE_LOSS',2)]:
        p=n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=255,single_rule=rule,unit_cny=2,payout_factor=.65,allocation_seed=0)
        assert p['contraction_ledger'][0]['slot']==slot and p['cash_cny']==127
    for budget in [0,127]:
        p=n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=budget,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)
        assert not p['tickets'] and p['cash_cny']==budget
    for budget in [-1,True,1.5]:
        with pytest.raises(ValueError):n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=budget,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)
    with pytest.raises(ValueError):n7_single_plan(f,max_uses=2,single_count=1,cutoffs={},budget_cny=128,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)


def test_overlap_infeasible_capacity_and_invalid_prior(sample):
    f,c=sample;f=f.head(14);c={str(s):c[str(s)] for s in f.slot}
    groups=[list(range(1,8)),list(range(8,15))]
    assert next_overlap_group(f,groups,cutoffs=c,max_uses=2,max_pair_overlap=2)['status']=='PROVEN_INFEASIBLE'
    p=n7_single_plan(f,max_uses=2,single_count=1,cutoffs=c,budget_cny=512,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)
    assert p['stake']==256 and p['cash_cny']==256
    with pytest.raises(ValueError):next_overlap_group(f,[groups[0],groups[0]],cutoffs=c,max_uses=2,max_pair_overlap=2)
    with pytest.raises(ValueError):next_overlap_group(f,groups,cutoffs={},max_uses=2,max_pair_overlap=2)


def test_overlap_timeout_is_not_reported_as_cash_infeasibility(sample,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr('src.fundamentals_n7_single.milp',lambda *a,**k:SimpleNamespace(status=1,message='time limit'))
    f,c=sample
    with pytest.raises(RuntimeError,match='optimality'):next_overlap_group(f,[],cutoffs=c,max_uses=2,max_pair_overlap=2)


@pytest.mark.parametrize('fixture,count',[('n7_single_report',120),('n7_compression_report',360),('n7_c2_relax_report',480),('compression_bridge_report',1440),('repeated_double_report',640)])
def test_report_archive_restore(tmp_path,fixture,count):
    import subprocess,sys,json,hashlib
    from pathlib import Path
    cmd=[sys.executable,'scripts/prepare_n7_single_fixture.py','--fixture',f'tests/fixtures/{fixture}.json.gz','--output',str(tmp_path/'archive')]
    subprocess.run(cmd,check=True)
    archive=json.loads((tmp_path/'archive/archive.json').read_text())
    assert archive['mode']=='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY'
    for path,h in archive['hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
    assert len(json.loads((tmp_path/'archive/results.json').read_text())['rows'])==count
    assert subprocess.run(cmd,capture_output=True).returncode!=0


@pytest.mark.parametrize('k',range(8))
def test_all_compression_counts_full_support_and_cash(sample,k):
    f,c=sample;f=f.head(14);c={str(s):c[str(s)] for s in f.slot}
    plan=n7_single_plan(f,max_uses=2,single_count=k,cutoffs=c,budget_cny=512,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)
    assert plan['groups']==2 and plan['stake']==4*2**(7-k) and plan['cash_cny']==512-plan['stake']
    for group in range(1,3):
        legs=[r for r in plan['legs'] if r['group']==group]
        assert sum(len(r['support'])==1 for r in legs)==k
        assert len([t for t in plan['tickets'] if t['group']==group])==2**(7-k)
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    assert settle_n7_single(plan,audit)['gross']==pytest.approx(2*2*.65*2**7)


@pytest.mark.parametrize('k',[-1,8,True,1.5])
def test_invalid_compression_count(sample,k):
    f,c=sample
    with pytest.raises(ValueError):n7_single_plan(f,max_uses=2,single_count=k,cutoffs=c,budget_cny=512,single_rule='MAX_SINGLE',unit_cny=2,payout_factor=.65,allocation_seed=0)
