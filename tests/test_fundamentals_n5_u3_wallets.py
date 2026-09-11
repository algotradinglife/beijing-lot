import copy
import itertools
import pandas as pd
import pytest
from tests.test_fundamentals_double_source import source
from src.fundamentals_missed_portfolio import flatten_component_groups,fixed_n67_wallets
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning.core import stable_json_hash


def test_equal_wallets_keep_whole_groups_and_source_order(source):
    original,cuts=source;envelopes={}
    for name,n,count in [('N5',5,40),('U3',7,10)]:
        p=copy.deepcopy(original);part=p['components'][0];part.pop('seal')
        part['legs']=[r for r in part['legs'] if r['slot'] not in ({5,6} if n==5 else set())]
        part.update(n=n,tickets=[dict(group=1,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in part['legs']))])
        part['stake']=2*len(part['tickets']);part['seal']=stable_json_hash(part)
        parts=[]
        # Unique fixture identities per group preserve unit-complete holdings.
        # Both sources share identical candidate input/cutoff contract.
        for j in range(count):
            c=copy.deepcopy(part);c.pop('seal')
            for r in c['legs']:
                if r['slot']==1:
                    r['support']='3' if j%2==0 else '1'
                    r['slot']=100+j;r['provider_id']=str(100+j)
            c['tickets']=[dict(group=1,code=''.join(x),units=1) for x in itertools.product(*(r['support'] for r in sorted(c['legs'],key=lambda r:r['slot'])))]
            c['legs'].sort(key=lambda r:r['slot'])
            c['cutoffs']=dict(original['cutoffs'],**{str(100+k):next(iter(original['cutoffs'].values())) for k in range(40)})
            c['seal']=stable_json_hash(c);parts.append(c)
        p.pop('seal');p.update(components=parts,stake=count*part['stake'],cash_cny=1024-count*part['stake'],cutoffs=parts[0]['cutoffs'],input_sha256=original['components'][0]['input_sha256'])
        p['seal']=stable_json_hash(p);envelopes[name]=p
    from src.temporal_learning import Cutoff
    cuts={s:Cutoff.decision_epoch(original['issue'],t) for s,t in envelopes['N5']['cutoffs'].items()}
    before=copy.deepcopy(envelopes)
    flat={k:flatten_component_groups(p,cutoffs=cuts,n=5 if k=='N5' else 7,budget_cny=1024,unit_cny=2,payout_factor=.65) for k,p in envelopes.items()}
    assert envelopes==before
    z=fixed_n67_wallets(flat,cutoffs=cuts,wallets=dict(N5=512,U3=512),budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert z['stake']==1024 and z['cash_cny']==0
    assert [x['source'] for x in z['components']]==['N5']*32+['U3']*8
    for k,count in [('N5',32),('U3',8)]:
        selected=[x['plan'] for x in z['components'] if x['source']==k]
        assert [c['legs'] for c in selected]==[c['legs'] for c in envelopes[k]['components'][:count]]
    # Short source retains cash; no wallet transfer or payout scaling.
    short=copy.deepcopy(flat['U3']);short.pop('seal');short.update(groups=1,legs=[r for r in short['legs'] if r['group']==1],tickets=[t for t in short['tickets'] if t['group']==1],stake=64,cash_cny=960);short['seal']=stable_json_hash(short)
    held=fixed_n67_wallets(dict(N5=flat['N5'],U3=short),cutoffs=cuts,wallets=dict(N5=512,U3=512),budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert held['stake']==576 and held['cash_cny']==448
    a=pd.DataFrame([{**{k:r[k] for k in ('issue','slot','provider_id','handicap')},'status':'READY','actual_direction':'W','spf_sp':2.} for r in held['components'][0]['plan']['legs']])
    assert settle_n7_baseline(held['components'][0]['plan'],a)['gross']==pytest.approx(2*.65*2**5)
    with pytest.raises(ValueError):flatten_component_groups(envelopes['N5'],cutoffs={},n=5,budget_cny=1024,unit_cny=2,payout_factor=.65)
    bad=copy.deepcopy(envelopes['N5']);bad['stake']+=2
    with pytest.raises(ValueError):flatten_component_groups(bad,cutoffs=cuts,n=5,budget_cny=1024,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):flatten_component_groups(envelopes['N5'],cutoffs=cuts,n=6,budget_cny=1024,unit_cny=2,payout_factor=.65)
    bad=copy.deepcopy(envelopes['N5']);bad.pop('seal');bad['components'][0]['stake']+=2;bad['seal']=stable_json_hash(bad)
    with pytest.raises(ValueError):flatten_component_groups(bad,cutoffs=cuts,n=5,budget_cny=1024,unit_cny=2,payout_factor=.65)
    empty=copy.deepcopy(envelopes['N5']);empty.pop('seal');empty.update(components=[],stake=0,cash_cny=1024);empty['seal']=stable_json_hash(empty)
    assert flatten_component_groups(empty,cutoffs=cuts,n=5,budget_cny=1024,unit_cny=2,payout_factor=.65)['groups']==0
