"""Freeze market-only N7 portfolios, then replay the bound R/SQLite audit."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.market_foundation_n7 import market_foundation_n7
from src.probability_foundation_draw import predict_draw_foundation
from src.fundamentals_n7_single import settle_n7_single
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--foundation',required=True)
    args=parser.parse_args();out=Path(args.output);root=Path.cwd();foundation=Path(args.foundation)
    out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    frozen=json.loads((foundation/'frozen.json').read_text())
    assert frozen['version']=='market-balance-draw-1.0.0-diagnostic' and frozen['historical_admission'] is False
    sources={**frozen['source_hashes'],str(foundation/'predictions.csv'):frozen['predictions_sha256'],
        str(foundation/'frozen.json'):hashlib.sha256((foundation/'frozen.json').read_bytes()).hexdigest()}
    for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    data=pd.read_csv(foundation/'predictions.csv',dtype={'issue':str,'provider_id':str})
    issues=list(frozen['models']);assert set(issues)==set(data.issue)
    plans={};jobs={};plan_hashes={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for issue in issues:
            x=data[data.issue==issue].copy();entry=frozen['models'][issue];path=Path(entry['path'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
            sources[str(path)]=entry['sha256'];artifact=json.loads(path.read_text())
            cut=Cutoff.decision_epoch(issue,artifact['receipt']['cutoff_ts'])
            base_columns=['issue','slot','provider_id','handicap','q_W','q_D','q_L']
            verified=predict_draw_foundation(artifact,x[base_columns+['fixture_decision_ts']],cut,repository_root=root)
            assert np.allclose(verified[['new_W','new_D','new_L']],x[['new_W','new_D','new_L']],atol=1e-14,rtol=0)
            assert set(x.model_seal)=={artifact['seal']}
            cuts={str(r.slot):Cutoff.decision_epoch(issue,r.fixture_decision_ts) for r in x.itertuples()}
            for source in ('RAW_MARKET',frozen['version']):
                frame=x[base_columns].copy()
                if source!='RAW_MARKET':
                    for d in 'WDL':frame['q_'+d]=x['new_'+d]
                for u in (3,6):
                    key=f'{issue}_{"RAW" if source=="RAW_MARKET" else "CAL"}_U{u}'
                    jobs[pool.submit(market_foundation_n7,frame,cutoffs=cuts,max_uses=u,max_pair_overlap=5,
                        budget_cny=1024,unit_cny=2,payout_factor=.65,seed=41902,source_version=source)]=key
        for job in as_completed(jobs):
            key=jobs[job];plan=job.result();path=out/'plans'/f'{key}.json.gz'
            path.write_bytes(gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0))
            plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();plans[key]=plan
    receipt=dict(historical_admission=False,mode='POST_EXPOSURE_MARKET_ONLY_NO_SUBSTITUTION',
        issues=issues,source_hashes=sources,plan_hashes=plan_hashes,
        implementation=implementation_closure(root,['scripts.replay_market_foundation_n7'],distributions=['numpy','pandas','scipy']),
        parameters=dict(n=7,single_count=2,budget_cny=1024,unit_cny=2,payout_factor=.65,
            uses=[3,6],pair_overlap=5,seed=41902,strength_used=False,single_threshold=None))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    # All 400 plans are sealed before opening an existing authoritative R/SQLite export.
    audit_path=Path('data/derived/fundamentals_417/updated100-strategies-v1/settlement-audit.json')
    audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);audit['issue']=audit.issue.astype(str)
    verify_implementation_closure(root,receipt['implementation'])
    rows=[]
    for key,plan in sorted(plans.items()):
        result=settle_n7_single(plan,audit[audit.issue==plan['issue']])
        assert result['status'] in ('COMPLETE','NO_BET'),(key,result['status'])
        rows.append(dict(issue=plan['issue'],model='MARKET_ONLY',policy=key.split('_',1)[1],
            status=result['status'],stake=result['stake'],gross=result['gross'],net=result['net'],
            groups=result['groups'],hits=result['hits'],budget_cny=1024,cash_cny=1024-result['stake']))
    (out/'results.json').write_text(json.dumps(dict(rows=rows,issue_order=issues,upstream_freeze_seal=freeze['seal'])))
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        audit_path=str(audit_path),audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())))
    print(json.dumps(dict(issues=len(issues),plans=len(plans),results=len(rows))))
