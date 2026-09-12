"""Frozen diagnostic threshold grid; no selection uses target settlement."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.n7_probability_gate import probability_gate_candidates,select_probability_gate
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);args=cli.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    (out/'plans').mkdir();(out/'pools').mkdir()
    implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_probability_gate'],distributions=['numpy','pandas','scipy'])
    origin=Path('data/derived/fundamentals_417/market-foundation-n7-v1')
    raw=(origin/'plans-frozen.json').read_bytes();frozen=json.loads(raw);r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal'];verify_implementation_closure(Path.cwd(),r['implementation'])
    sources={**r['source_hashes'],**r['plan_hashes'],str(origin/'plans-frozen.json'):hashlib.sha256(raw).hexdigest()}
    for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    pred_path='data/derived/fundamentals_417/market-balance-draw-v1/predictions.csv'
    raw=Path(pred_path).read_bytes();assert hashlib.sha256(raw).hexdigest()==sources[pred_path]
    data=pd.read_csv(io.BytesIO(raw),dtype={'issue':str,'provider_id':str})
    counts=[0,1,5,10,25,50,100,200];depths=[512,2048]
    tradeoffs=[0.,.1,.25,.5,1.,2.,4.,8.,'PROBABILITY']
    hashes={};pool_hashes={};jobs={};clocks={}
    with ProcessPoolExecutor(max_workers=4) as executor:
        for issue in r['issues']:
            x=data[data.issue==issue]
            frame=x[['issue','slot','provider_id','handicap','new_W','new_D','new_L','q_W','q_D','q_L']].rename(columns={f'new_{d}':f'p_{d}' for d in 'WDL'})
            base_path=origin/'plans'/f'{issue}_CAL_U3.json.gz';raw=base_path.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==sources[str(base_path)]
            base=json.loads(gzip.decompress(raw))
            cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()};clocks[issue]=cuts
            jobs[executor.submit(probability_gate_candidates,frame,cutoffs=cuts,n=7,depth=max(depths),tradeoffs=tradeoffs)]=issue
        for ordinal,job in enumerate(as_completed(jobs),1):
            issue=jobs.pop(job);pool=job.result()
            path=out/'pools'/f'{issue}.json.gz'
            raw=gzip.compress(json.dumps(pool,sort_keys=True).encode(),mtime=0);path.write_bytes(raw)
            pool_hashes[str(path)]=hashlib.sha256(raw).hexdigest()
            for depth in depths:
                for count in counts:
                    for ranking in ('EV','PROB_POS','PROB'):
                        plan=select_probability_gate(pool,cutoffs=clocks[issue],min_probability=count/10000,
                            ranking=ranking,search_depth=depth,budget_cny=1024,unit_cny=2,payout_factor=.65)
                        path=out/'plans'/f'{issue}_{depth}_{count}_{ranking}.json.gz'
                        raw=gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0);path.write_bytes(raw)
                        hashes[str(path)]=hashlib.sha256(raw).hexdigest()
            if ordinal%10==0:print(f'Frozen {ordinal}/100 issues',flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    receipt=dict(issues=r['issues'],counts=counts,depths=depths,tradeoffs=tradeoffs,
        source_hashes=sources,pool_hashes=pool_hashes,plan_hashes=hashes,implementation=implementation,
        historical_admission=False,parameters=dict(n=7,budget_cny=1024,unit_cny=2,payout_factor=.65))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    print('All 4800 plans frozen before settlement',flush=True)
    # Same bytes parsed and hashed; preserve settlement independently of upstream refreshes.
    audit_path=out/'audit-snapshot.json'
    raw=Path('data/derived/fundamentals_417/updated100-strategies-v1/settlement-audit.json').read_bytes();audit_path.write_bytes(raw)
    audit_hash=hashlib.sha256(raw).hexdigest();audit=pd.DataFrame(json.loads(raw)['rows']);audit.issue=audit.issue.astype(str)
    rows=[]
    for ordinal,issue in enumerate(r['issues'],1):
        for depth in depths:
            for count in counts:
                for ranking in ('EV','PROB_POS','PROB'):
                    path=out/'plans'/f'{issue}_{depth}_{count}_{ranking}.json.gz';raw=path.read_bytes()
                    assert hashlib.sha256(raw).hexdigest()==hashes[str(path)]
                    p=json.loads(gzip.decompress(raw));z=settle_single_tickets(p,audit[audit.issue==issue])
                    assert z['status'] in ('COMPLETE','NO_BET')
                    rows.append(dict(issue=issue,model=f'C{count:03d}_D{depth}',policy=ranking,count=count,depth=depth,
                        stake=z['stake'],gross=z['gross'],net=z['net'],groups=z['groups'],hits=z['hits'],
                        expected_net=p['expected_net'],expected_roi=p['expected_roi'],mean_coverage=p['mean_coverage'],
                        min_selected_probability=p['min_selected_probability'],candidate_count=p['candidate_count'],
                        gated_count=p['gated_count'],positive_count=p['positive_count'],max_reuse=p['max_reuse']))
        if ordinal%10==0:print(f'Settled {ordinal}/100 issues',flush=True)
    raw=(origin/'results.json').read_bytes();controls_path=out/'controls-snapshot.json';controls_path.write_bytes(raw)
    controls_hash=hashlib.sha256(raw).hexdigest();prior=json.loads(raw)
    prior_er_raw=(origin/'evaluation-receipt.json').read_bytes();prior_er=json.loads(prior_er_raw)
    assert prior_er['freeze_sha256']==sources[str(origin/'plans-frozen.json')]
    assert prior_er['result_sha256']==controls_hash and prior_er['audit_sha256']==audit_hash
    controls_er_path=out/'controls-evaluation-snapshot.json';controls_er_path.write_bytes(prior_er_raw)
    controls=[dict(issue=z['issue'],model=z['policy'],policy='CONTROL',stake=z['stake'],gross=z['gross'],net=z['net'],
        groups=z['groups'],hits=z['hits']) for z in prior['rows'] if z['policy'].startswith('CAL')]
    assert len(rows)==4800 and len(controls)==200
    verify_implementation_closure(Path.cwd(),implementation)
    result=dict(rows=sorted(rows,key=lambda z:(z['model'],z['policy'],z['issue'])),controls=controls,
        issue_order=r['issues'],freeze_seal=freeze['seal'])
    raw=json.dumps(result).encode();(out/'results.json').write_bytes(raw)
    er=dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256(raw).hexdigest(),audit_path=str(audit_path),audit_sha256=audit_hash,
        controls_path=str(controls_path),controls_sha256=controls_hash,
        controls_receipt_path=str(controls_er_path),controls_receipt_sha256=hashlib.sha256(prior_er_raw).hexdigest())
    (out/'evaluation-receipt.json').write_text(json.dumps(er))
    print('Completed 4800 plans and 200 controls',flush=True)
