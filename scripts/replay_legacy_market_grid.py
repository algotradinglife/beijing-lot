"""Freeze fixed old market C1/C2 U3/U6 strategies from explicit diagnostic bundles.

No settlement or fitting. Catalog and every bundle are hash-bound; existing
shared cutoff objects and the authoritative purchase engine are reused.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.market_foundation_n7 import market_foundation_n7
from src.strategy_diagnostic_inputs import read_verified_bundle_json
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--catalog', required=True)
    p.add_argument('--catalog-sha256', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--limit', type=int)
    a = p.parse_args()
    raw = Path(a.catalog).read_bytes()
    if hashlib.sha256(raw).hexdigest() != a.catalog_sha256:
        raise ValueError('Catalog identity mismatch')
    catalog = json.loads(raw)
    entries = catalog['issues']
    if a.limit is not None:
        if a.limit < 1:
            raise ValueError('Positive smoke limit required')
        entries = entries[:a.limit]
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'plans').mkdir()
    closure = implementation_closure(Path.cwd(), ['scripts.replay_legacy_market_grid'],
                                     distributions=['numpy', 'pandas', 'scipy'])
    receipt = dict(historical_admission=False, mode='FROZEN_DIAGNOSTIC_NO_FIT',
        catalog_sha256=a.catalog_sha256, catalog=a.catalog, smoke=a.limit is not None,
        issues=[x['issue'] for x in entries], source_hashes={}, plan_hashes={},
        implementation=closure, parameters=dict(single_counts=[1,2],uses=[3,6],
        pair_overlap=5,budget_cny=1024,unit_cny=2,payout_factor=.65,seed=41902))
    (out/'contract.json').write_text(json.dumps(receipt,sort_keys=True))
    for e in entries:
        b = json.loads(read_verified_bundle_json(e['path'], e['sha256']))
        if b['issue'] != e['issue']:
            raise ValueError('Issue identity mismatch')
        fixtures = pd.DataFrame(b['expanded_pool']['fixtures'])
        cuts = {str(s):Cutoff.decision_epoch(e['issue'], b['cutoffs'][str(s)]) for s in fixtures.slot}
        bundle = {}
        for source in ('RAW', 'CAL'):
            frame = fixtures[['issue','slot','provider_id','handicap']].copy()
            for d in 'WDL':
                frame['q_'+d] = fixtures[('q_' if source=='RAW' else 'p_')+d]
            for count in (1,2):
                for u in (3,6):
                    key = f'{source}_C{count}_U{u}'
                    bundle[key] = market_foundation_n7(frame,cutoffs=cuts,max_uses=u,
                        max_pair_overlap=5,budget_cny=1024,unit_cny=2,payout_factor=.65,
                        seed=41902,single_count=count,source_version='RAW_MARKET' if source=='RAW'
                        else 'market-balance-draw-1.0.0-diagnostic')
        target = out/'plans'/(e['issue']+'.json.gz')
        target.write_bytes(gzip.compress(json.dumps(bundle,sort_keys=True).encode(),mtime=0))
        receipt['plan_hashes'][str(target)] = hashlib.sha256(target.read_bytes()).hexdigest()
        receipt['source_hashes'][e['path']] = e['sha256']
        print('FROZEN',e['issue'],len(bundle),flush=True)
    verify_implementation_closure(Path.cwd(),closure)
    (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),sort_keys=True))
