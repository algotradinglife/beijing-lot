import copy
import gzip
import json
from pathlib import Path

import pytest

from src.n7_core_check import core_replay_surface, check_core_plan
from src.temporal_learning.core import stable_json_hash


def test_shared_issue_opening_crossings_are_legal_depth_choices():
    x=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/n7_core433_shared_depth.json.gz').read_bytes()))
    p=x['plans'][0]; c=x['config']; b=x['bundle']
    surface=core_replay_surface(b,c,cutoffs=b['cutoffs'])
    sleeve=next(k for layer in p['layers'] for k in layer['sleeve_keys']
                if k['sleeve_id']==2 and layer['role']=='CORE')
    assert sleeve['depth']==90 and surface[2]['opening']==48
    assert 90 not in c['depths']
    assert check_core_plan(p,x['worlds'],c,b)['status']=='PASS'


def test_core_replay_prefixes_layers_and_adversarial_changes():
    x=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/n7_core433_replay.json.gz').read_bytes()))
    b,c,w=x['bundle'],x['config'],x['worlds']
    s=core_replay_surface(b,c,cutoffs=b['cutoffs'])
    assert len(s)==24 and all(0<r['opening']<=2187 for r in s.values())
    with pytest.raises(ValueError,match='cutoff'):
        core_replay_surface(b,c,cutoffs={})
    bad=copy.deepcopy(b);bad['sleeves'][0]['enumeration']['probability'][0]+=.1
    with pytest.raises(ValueError,match='enumeration'):
        core_replay_surface(bad,c,cutoffs=b['cutoffs'])
    for p in x['plans']:
        assert check_core_plan(p,w,c,b)['status']=='PASS'
    p=x['plans'][-1]
    mutations=[
        lambda z:z['evaluation'].update(any_hit=.99),
        lambda z:z.update(unique_tickets=z['unique_tickets']+1),
        lambda z:z['allocation'][0].update(phase='MULTIPLY'),
        lambda z:z['allocation'][0].update(affordable_new_core_count=99),
        lambda z:z['layers'][0]['sleeve_keys'][0].update(state_ids=[0]),
        lambda z:z['layers'][1].update(copy_index=3),
        lambda z:z.update(stake=z['stake']+2),
    ]
    for mutate in mutations:
        z=copy.deepcopy(p);z.pop('seal');mutate(z);z['seal']=stable_json_hash(z)
        with pytest.raises(ValueError):check_core_plan(z,w,c,b)


def test_result_grid_and_curve_features():
    from src.n7_core_check import check_core_result
    x=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/n7_core433_replay.json.gz').read_bytes()))
    b=x['bundle'];c=x['config']
    c['policies']=[p for p in c['policies'] if p['name'] in {z['arm'] for z in x['plans']}]
    result=dict(issue=b['issue'],cutoffs=b['cutoffs'],features=x['features'],plans=x['plans'])
    assert check_core_result(result,b,c)['features_checked']==24
    bad=copy.deepcopy(result);bad['features'][0]['coverage_64']+=.01
    with pytest.raises(ValueError,match='feature'):check_core_result(bad,b,c)
    bad=copy.deepcopy(result);bad['plans']=bad['plans'][:-1]
    with pytest.raises(ValueError,match='grid'):check_core_result(bad,b,c)


def test_shared_receipt_checker_visits_all_physical_layers(tmp_path):
    import hashlib
    from src.n7_joint_check import check_prefix_study
    from src.n7_core_check import check_core_result
    from src.temporal_learning.provenance import implementation_closure
    root=Path(__file__).resolve().parents[1]
    x=json.loads(gzip.decompress((root/'tests/fixtures/n7_core433_replay.json.gz').read_bytes()))
    b=x['bundle'];c=x['config'];plans=x['plans']
    c['policies']=[p for p in c['policies'] if p['name'] in {z['arm'] for z in plans}]
    for sub in ('bundles','raw','plans'):(tmp_path/sub).mkdir()
    source=tmp_path/'bundles'/f"{b['issue']}.json.gz"
    source.write_bytes(gzip.compress(json.dumps(b).encode()))
    raw=tmp_path/'raw/result.json.gz'
    raw.write_bytes(gzip.compress(json.dumps(dict(issue=b['issue'],cutoffs=b['cutoffs'],
        plans=plans,worlds=[x['worlds']],features=x['features'])).encode()))
    plan_hashes={}
    for p in plans:
        path=tmp_path/'plans'/f"{p['issue']}_{p['seed']}_{p['arm']}.json.gz"
        path.write_bytes(gzip.compress(json.dumps(p).encode()));plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=dict(source_hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()},
        raw_hashes={str(raw):hashlib.sha256(raw.read_bytes()).hexdigest()},plan_hashes=plan_hashes,
        implementation=implementation_closure(root,['src.n7_core_check']),r_implementation={},
        cutoffs={b['issue']:b['cutoffs']},parameters=c)
    (tmp_path/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
    result=check_prefix_study(tmp_path,repository_root=root,check_plan=check_core_plan,
        check_result=check_core_result,physical_plans=lambda p:p['layers'])
    assert result['plans_checked']==3 and result['status']=='PASS'


def test_independent_core_settlement_counts_paid_copies_separately():
    import pandas as pd
    from src.n7_core_settlement import settle_core_layers
    from src.n7_core_check import check_core_settlement
    x=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/n7_core433_replay.json.gz').read_bytes()))
    p=x['plans'][-1]
    audit=[dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],handicap=f['handicap'],
        actual_direction='W',spf_sp=2.,status='READY') for f in p['fixtures']]
    # Force a selected first-layer prefix to win; probabilities stay frozen.
    first=p['layers'][0]
    for idx, direction in zip(first['fixture_indices'][0],first['outcomes'][0]):
        audit[idx]['actual_direction']='WDL'[direction]
    result=settle_core_layers(p,pd.DataFrame(audit))
    checked=check_core_settlement(p,audit,result)
    assert checked['hits']>0 and checked['paid_hits']>=checked['hits']
    assert checked['gross']==pytest.approx(result['gross'])
    assert checked['core_gross']+checked['opportunity_gross']==pytest.approx(checked['gross'])
    for field in ('gross','hits','paid_hits','core_gross','opportunity_stake'):
        with pytest.raises(ValueError,match='settlement'):
            check_core_settlement(p,audit,dict(result,**{field:result[field]+1}))
