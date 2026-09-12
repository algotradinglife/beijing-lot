"""Freeze predefined conditional-reuse variants before reading audited outcomes."""
import argparse,gzip,hashlib,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.market_conditional_reuse import conditional_reuse_plan,settle_conditional_reuse
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    origin=Path('data/derived/fundamentals_417/market-foundation-n7-v1')
    frozen=json.loads((origin/'plans-frozen.json').read_text());r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal'];verify_implementation_closure(Path.cwd(),r['implementation'])
    sources={**r['source_hashes'],**r['plan_hashes'],str(origin/'plans-frozen.json'):hashlib.sha256((origin/'plans-frozen.json').read_bytes()).hexdigest()}
    for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    prediction=Path('data/derived/fundamentals_417/market-balance-draw-v1/predictions.csv')
    data=pd.read_csv(prediction,dtype={'issue':str,'provider_id':str})
    variants={'BASE':(None,None,False,'SWAP'),'S05':(.05,None,False,'SWAP'),
      'S10':(.10,None,False,'SWAP'),'DRAW_ANY':(None,None,True,'SWAP'),
      'DRAW05':(None,.05,True,'SWAP'),'DRAW10':(None,.10,True,'SWAP'),
      'BOTH05':(.05,.05,True,'SWAP'),'BOTH10':(.10,.10,True,'SWAP'),
      'AVOID05':(.05,.05,True,'AVOID'),'AVOID10':(.10,.10,True,'AVOID')}
    jobs={};plan_hashes={};bases={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for issue in r['issues']:
            x=data[data.issue==issue]
            frame=x[['issue','slot','provider_id','handicap','new_W','new_D','new_L','p_W','p_D','p_L']].rename(
                columns={**{f'new_{d}':f'q_{d}' for d in 'WDL'},**{f'p_{d}':f'strength_{d}' for d in 'WDL'}})
            for u in (3,6):
                base=json.loads(gzip.decompress((origin/'plans'/f'{issue}_CAL_U{u}.json.gz').read_bytes()))
                bases[issue,u]=base;cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
                for name,(single,gap,draw,mode) in variants.items():
                    jobs[pool.submit(conditional_reuse_plan,base,frame,cutoffs=cuts,
                        single_gap=single,draw_gap=gap,draw_enabled=draw,mode=mode)]=(issue,u,name)
        for job in as_completed(jobs):
            issue,u,name=jobs[job];plan=job.result();path=out/'plans'/f'{issue}_U{u}_{name}.json.gz'
            path.write_bytes(gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0))
            plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=dict(issues=r['issues'],variants=variants,source_hashes=sources,plan_hashes=plan_hashes,
        historical_admission=False,parameters=dict(budget_cny=1024,unit_cny=2,payout_factor=.65,uses=[3,6],pair_overlap=5),
        implementation=implementation_closure(Path.cwd(),['scripts.replay_market_conditional'],distributions=['numpy','pandas','scipy']))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    audit_path=Path('data/derived/fundamentals_417/updated100-strategies-v1/settlement-audit.json')
    audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);audit.issue=audit.issue.astype(str)
    rows=[];positions=[];disagreements=[]
    for issue in r['issues']:
        observed=audit[audit.issue==issue];actual=observed.set_index('slot').actual_direction.to_dict()
        x=data[data.issue==issue].set_index('slot')
        for u in (3,6):
            for name in variants:
                path=out/'plans'/f'{issue}_U{u}_{name}.json.gz';plan=json.loads(gzip.decompress(path.read_bytes()))
                assert hashlib.sha256(path.read_bytes()).hexdigest()==plan_hashes[str(path)]
                z=settle_conditional_reuse(plan,observed);assert z['status'] in ('COMPLETE','NO_BET')
                rows.append(dict(issue=issue,model=f'U{u}',policy=name,status=z['status'],stake=z['stake'],
                    gross=z['gross'],net=z['net'],groups=z['groups'],hits=z['hits'],budget_cny=1024,cash_cny=1024-z['stake']))
                for entry in plan['conditional_ledger']:
                    new_slot=entry['replacement_slot'] or entry['slot']
                    positions.append(dict(issue=issue,u=u,policy=name,**entry,
                      old_hit={'W':'3','D':'1','L':'0'}[actual[entry['slot']]] in entry['original'],
                      new_hit=False if entry['group_dropped'] else {'W':'3','D':'1','L':'0'}[actual[new_slot]] in entry['support']))
            seen=set()
            for leg in bases[issue,u]['legs']:
                v=x.loc[leg['slot']];q=sorted('WDL',key=lambda d:(-v['new_'+d],'WDL'.index(d)))
                strength=sorted('WDL',key=lambda d:(-v['p_'+d],'WDL'.index(d)))
                disagreements.append(dict(issue=issue,u=u,group=leg['group'],slot=leg['slot'],single=len(leg['support'])==1,
                    repeated=leg['slot'] in seen,draw_disagreement='D' not in q[:2] and 'D' in strength[:2],
                    market_draw=v.new_D,second_draw_gap=v['new_'+q[1]]-v.new_D,actual=actual[leg['slot']]))
                seen.add(leg['slot'])
    payload=dict(rows=rows,positions=positions,disagreements=disagreements,issue_order=r['issues'],upstream_freeze_seal=freeze['seal'])
    (out/'results.json').write_text(json.dumps(payload))
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        audit_path=str(audit_path),audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())))
    print(json.dumps(dict(issues=len(r['issues']),plans=len(plan_hashes),rows=len(rows))))
