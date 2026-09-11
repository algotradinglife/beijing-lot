"""Replay selection and independently verify subset tickets and settlement."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n6_efficiency import n6_efficiency_catalog,n6_efficiency_plan


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--study',required=True);args=parser.parse_args()
    root=Path(args.study)
    frozen=json.loads((root/'frozen.json').read_text());r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal']
    verify_implementation_closure(Path.cwd(),r['implementation'])
    verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
    witness=json.loads((root/'plans-frozen.json').read_text())
    assert hashlib.sha256(witness['canonical_json'].encode()).hexdigest()==witness['seal']
    witness=json.loads(witness['canonical_json'])
    assert witness['plan_freeze_seal']==frozen['seal']
    assert witness['result_sha256']==hashlib.sha256((root/'results.json').read_bytes()).hexdigest()
    verify_clean_file_bindings(witness['source_hashes'],repository_root=Path.cwd())
    paths=[p for p in witness['source_hashes'] if p.endswith('settlement-audit.json')]
    assert len(paths)==1
    labels=json.loads(Path(paths[0]).read_text())['rows']
    audit={(a['issue'],a['slot'],a['provider_id']):a for a in labels}
    assert len(audit)==len(labels)
    result=json.loads((root/'results.json').read_text())
    assert result['upstream_freeze_seal']==frozen['seal']
    saved={(a['issue'],a['policy']):a for a in result['rows']}
    assert len(saved)==len(result['rows'])==576
    total=0
    for issue in r['issues']:
        data=json.loads(gzip.decompress((root/'plans'/f'{issue}.json.gz').read_bytes()))
        catalog=data['catalog'];source=catalog['source_plan']
        cuts={s:Cutoff.decision_epoch(issue,t) for s,t in source['cutoffs'].items()}
        replay=n6_efficiency_catalog(source,cutoffs=cuts,unit_cny=2,payout_factor=.65,
            scenario_seed=r['parameters']['scenario_seed'],scenario_draws=r['parameters']['scenario_draws'])
        assert replay==catalog
        for policy,z in data['bundles'].items():
            assert z==n6_efficiency_plan(catalog,cutoffs=cuts,method=z['method'],
                spend_cap_cny=z['spend_cap_cny'],budget_cny=1024,unit_cny=2,payout_factor=.65)
            original=saved[issue,'ORIGINAL'];row=saved[issue,policy]
            assert row['hits']<=original['hits'] and row['gross']<=original['gross']+1e-8
            parts=z['plan']['components'];cost=32 if z['method'].startswith('EXTRA_') else 64
            gross=0.;hits=0
            for component,group in zip(parts,z['selected_source_groups']):
                part=component['plan'];legs=part['legs']
                prior=sorted([l for l in source['legs'] if l['group']==group],key=lambda l:l['slot'])
                assert [(l['slot'],l['provider_id']) for l in legs]==[(l['slot'],l['provider_id']) for l in prior]
                assert all(set(l['support'])<=set(o['support']) for l,o in zip(legs,prior))
                assert all(l['support']==o['support'] for l,o in zip(legs,prior) if len(o['support'])==1)
                expected={''.join(c) for c in itertools.product(*(l['support'] for l in legs))}
                assert len(expected)==len(part['tickets'])==cost//2
                assert {t['code'] for t in part['tickets']}==expected
                assert all(t['units']==1 for t in part['tickets'])
                actual=[audit[issue,l['slot'],l['provider_id']] for l in legs]
                assert all(l['handicap']==a['handicap'] for l,a in zip(legs,actual))
                code=''.join(dict(W='3',D='1',L='0')[a['actual_direction']] for a in actual)
                if code in expected:
                    hits+=1;gross+=2*.65*math.prod(a['spf_sp'] for a in actual)
            assert len(parts)==len(z['selected_source_groups'])==row['groups']
            assert row['stake']==len(parts)*cost and row['stake']+row['cash_cny']==1024
            assert row['stake']<=z['spend_cap_cny']
            assert row['hits']==hits and math.isclose(row['gross'],gross,abs_tol=1e-8)
            assert math.isclose(row['net'],gross-row['stake'],abs_tol=1e-8)
            if z['method'].startswith('EXTRA_'):
                assert row['stake']==original['stake']/2 and row['groups']==original['groups']
            total+=len(parts)
    original=[a for a in result['rows'] if a['policy']=='ORIGINAL']
    assert sum(a['hits']>0 for a in original)==41
    assert math.isclose(sum(a['net'] for a in original),11357.614784795136,abs_tol=1e-8)
    print('PASS576 plans,',total,'groups; catalogue/selection replay, subsets, half-cost and payouts')
