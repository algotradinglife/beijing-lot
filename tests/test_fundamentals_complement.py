import copy
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_complement import complementary_sources,complement_catalog,allocate_complement,settle_complements
from src.fundamentals_n7_single import n7_single_plan


@pytest.fixture(scope='module')
def data():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id='00'+str(i),handicap=0,p_W=.57+i*.002,
        p_D=.28-i*.001,p_L=.15-i*.001,q_W=.5,q_D=.3,q_L=.2) for i in range(1,29)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for i in f.slot}
    kw=dict(cutoffs=cuts,candidate_seeds=[1],random_seeds=[2],quality_pool_size=64,base_candidate_seed=41900,
        pool_size=128,design_seed=41901,design_draws=128,budget_cny=1024,unit_cny=2,payout_factor=.65)
    sources=complementary_sources(f,**kw)
    sources['C1']=n7_single_plan(f,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=1,
        max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
    return f,cuts,kw,sources


def test_sources_are_fixed_repeatable_and_cutoff_bound(data):
    f,cuts,kw,sources=data
    assert complementary_sources(f,**kw)=={k:v for k,v in sources.items() if k!='C1'}
    assert set(sources)=={'SEED_1','RANDOM_Q64_S2','UNION_Q64','C1'}
    with pytest.raises(ValueError):complementary_sources(f,**dict(kw,candidate_seeds=[1,1]))
    with pytest.raises(ValueError):complementary_sources(f,**dict(kw,random_seeds=[]))
    with pytest.raises(ValueError):complementary_sources(f,**dict(kw,budget_cny=2048))
    with pytest.raises(ValueError):complementary_sources(f,**dict(kw,quality_pool_size=1))


def test_wallets_whole_groups_dedup_and_authoritative_settlement(data):
    f,cuts,kw,sources=data;before=copy.deepcopy(sources)
    c=complement_catalog(sources,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    recipes={}
    for alternative in sources:
        for money in (0,512,768,1024):
            p=allocate_complement(c,cutoffs=cuts,main='SEED_1',alternative=alternative,main_budget_cny=money,budget_cny=1024)
            assert p['stake']+p['cash_cny']==1024
            assert sum(a['stake'] for a in p['allocations'] if a['role']=='MAIN')<=money
            assert sum(a['stake'] for a in p['allocations'] if a['role']=='ALTERNATIVE')<=1024-money
            assert len({a['component'] for a in p['allocations']})==p['groups']
            assert all(a['stake'] in (64,128) for a in p['allocations'])
            if alternative=='SEED_1':assert {a['component'] for a in p['allocations']}==set(c['source_order']['SEED_1'][:16])
            recipes[f'{alternative}_{money}']=p
    audit=f[['issue','slot','provider_id','handicap']].assign(status='READY',actual_direction='W',spf_sp=2.)
    results=settle_complements(c,recipes,audit)
    for r in results:
        p=recipes[r['policy']]
        wins=sum(all('3' in z['support'] for z in c['components'][a['component']]['plan']['legs']) for a in p['allocations'])
        assert r['gross']==pytest.approx(wins*2*.65*2**7)
        assert r['net']==pytest.approx(r['gross']-p['stake'])
        assert r['hits']==wins and r['budget_return']==pytest.approx(r['net']/1024)
    audit.actual_direction='L';losses=settle_complements(c,recipes,audit)
    assert all(r['gross']==0 and r['net']==-r['stake'] for r in losses)
    assert sources==before
    assert recipes=={k:allocate_complement(c,cutoffs=cuts,main='SEED_1',alternative=v['alternative'],
        main_budget_cny=v['main_budget_cny'],budget_cny=1024) for k,v in recipes.items()}


def test_boundaries_and_tampering_fail(data):
    f,cuts,kw,sources=data;c=complement_catalog(sources,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    p=allocate_complement(c,cutoffs=cuts,main='SEED_1',alternative='C1',main_budget_cny=512,budget_cny=1024)
    audit=f[['issue','slot','provider_id','handicap']].assign(status='READY',actual_direction='W',spf_sp=2.)
    for value in (True,500,512.,2048):
        with pytest.raises(ValueError):allocate_complement(c,cutoffs=cuts,main='SEED_1',alternative='C1',main_budget_cny=value,budget_cny=1024)
    wrong={s:Cutoff.decision_epoch('001','2011-01-01T00:00:00Z') for s in cuts}
    with pytest.raises(ValueError):allocate_complement(c,cutoffs=wrong,main='SEED_1',alternative='C1',main_budget_cny=512,budget_cny=1024)
    with pytest.raises(ValueError):complement_catalog({},cutoffs=cuts,unit_cny=2,payout_factor=.65)
    bad=copy.deepcopy(sources);bad['C1']['stake']+=2
    with pytest.raises(ValueError):complement_catalog(bad,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    bad=copy.deepcopy(c);bad['issue']='002'
    with pytest.raises(ValueError):allocate_complement(bad,cutoffs=cuts,main='SEED_1',alternative='C1',main_budget_cny=512,budget_cny=1024)
    with pytest.raises(ValueError):settle_complements(bad,{'x':p},audit)
    bad=copy.deepcopy(p);bad['stake']+=2
    with pytest.raises(ValueError):settle_complements(c,{'x':bad},audit)
    with pytest.raises(ValueError):settle_complements(c,{'x':p},audit.iloc[:0])
    with pytest.raises(ValueError):settle_complements(c,{'x':p},pd.concat([audit,audit.iloc[:1]]))
    missing=audit.copy();missing.spf_sp=float('nan')
    with pytest.raises(ValueError):settle_complements(c,{'x':p},missing)
