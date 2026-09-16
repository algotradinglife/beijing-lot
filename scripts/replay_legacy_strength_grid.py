"""Replay fixed strength/consensus policies on a verified diagnostic archive.

Archived predictions are inventoried historical evidence, not a clean learning
interface. No fitting or prospective admission. Missing factors stay missing.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.data_archive import read_archive_members
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure
from src.fundamentals_n7_single import n7_single_plan, settle_n7_single
from src.fundamentals_n7_twocover import settle_n7_twocover
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement
from src.fundamentals_consensus_portfolio import consensus_portfolios, independent_consensus_portfolio

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle'])
    p.add_argument('--archive',required=True);p.add_argument('--archive-sha256',required=True)
    p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
    prefix='updated100-strategies-v1/'
    if a.phase=='freeze':
        members=read_archive_members(a.archive,[prefix+'factors.json',prefix+'prepared.json'],expected_sha256=a.archive_sha256)
        data=json.loads(members[prefix+'factors.json']);prepared=json.loads(members[prefix+'prepared.json'])
        assert stable_json_hash(prepared['receipt'])==prepared['seal']
        frame=pd.DataFrame(data['rows']);assert not frame.duplicated(['issue','slot']).any()
        out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
        receipt=dict(archive=a.archive,archive_sha256=a.archive_sha256,historical_admission=False,
            mode='ARCHIVED_PREDICTION_DIAGNOSTIC_NO_FIT',issues=data['issues'],unavailable=[],plan_hashes={},
            input_hashes={k:hashlib.sha256(v).hexdigest() for k,v in members.items()},
            implementation=implementation_closure(Path.cwd(),['scripts.replay_legacy_strength_grid'],distributions=['numpy','pandas','scipy']),
            parameters=dict(budget_cny=1024,unit_cny=2,payout_factor=.65,pair_overlap=5,seed=41902))
        (out/'contract.json').write_text(json.dumps(receipt,sort_keys=True))
        for issue in data['issues']:
            f=frame[frame.issue==issue].copy()
            if f.empty:
                receipt['unavailable'].append(dict(issue=issue,reason='NO_READY_FACTORS'));continue
            cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in f.slot}
            bundle={}
            for count in (1,2):
                for u in (3,6):
                    bundle[f'STRENGTH_C{count}_U{u}']=n7_single_plan(f,cutoffs=cuts,budget_cny=1024,
                        single_rule='MAX_SINGLE',single_count=count,max_uses=u,unit_cny=2,payout_factor=.65,
                        allocation_seed=41902,max_pair_overlap=5)
            filtered,excluded=exclude_zero_top2_disagreement(f,cutoffs=cuts)
            cc={str(s):cuts[str(s)] for s in filtered.slot}
            bundle['CONSENSUS_C2_U3']=consensus_portfolios(filtered,cutoffs=cc,budget_cny=1024,
                minimum_anchor_market=.5,skeleton_max_uses=3,skeleton_pair_overlap=5,
                unit_cny=2,payout_factor=.65,seed=41902)['plans']['PRIMARY_FILL']
            bundle['CONSENSUS_C2_U6']=independent_consensus_portfolio(filtered,cutoffs=cc,budget_cny=1024,
                minimum_anchor_market=.5,max_uses=6,max_pair_overlap=5,unit_cny=2,payout_factor=.65,
                seed=41902,conversion_budget_fraction=0,group_size=7)
            path=out/'plans'/(issue+'.json.gz')
            path.write_bytes(gzip.compress(json.dumps(dict(plans=bundle,exclusions=excluded),sort_keys=True).encode(),mtime=0))
            receipt['plan_hashes'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            print('FROZEN',issue,6,flush=True)
        verify_implementation_closure(Path.cwd(),receipt['implementation'])
        (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),sort_keys=True))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        f=json.loads((out/'plans-frozen.json').read_text());r=f['receipt'];assert stable_json_hash(r)==f['seal']
        assert r['archive']==a.archive and r['archive_sha256']==a.archive_sha256
        verify_implementation_closure(Path.cwd(),r['implementation'])
        for path,digest in r['plan_hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
        content=read_archive_members(a.archive,[prefix+'settlement-audit.json'],expected_sha256=a.archive_sha256)
        raw=content[prefix+'settlement-audit.json'];audit=pd.DataFrame(json.loads(raw)['rows'])
        assert not audit.duplicated(['issue','slot']).any()
        rows=[];unavailable={x['issue'] for x in r['unavailable']}
        for issue in r['issues']:
            if issue in unavailable:continue
            plans=json.loads(gzip.decompress((out/'plans'/(issue+'.json.gz')).read_bytes()))['plans']
            for policy,plan in plans.items():
                result=(settle_n7_single if policy.startswith('STRENGTH') else settle_n7_twocover)(plan,audit[audit.issue==issue])
                assert result['status'] in ('COMPLETE','NO_BET'),(issue,policy,result['status'])
                rows.append(dict(issue=issue,policy=policy,model='ARCHIVED_STRENGTH',status=result['status'],
                    stake=result['stake'],gross=result['gross'],net=result['net'],hits=result['hits'],
                    groups=result['groups'],budget_cny=1024,cash_cny=1024-result['stake']))
        (out/'results.json').write_text(json.dumps(dict(rows=rows,issue_order=[i for i in r['issues'] if i not in unavailable],
            unavailable=r['unavailable'],freeze_seal=f['seal'],audit_sha256=hashlib.sha256(raw).hexdigest()),sort_keys=True))
