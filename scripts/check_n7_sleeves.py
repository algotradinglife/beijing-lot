"""Independent full-state, ticket, payout and shared-scenario replay for #424."""
import argparse,csv,functools,gzip,hashlib,json,math,operator
from pathlib import Path
import numpy as np
from src.temporal_learning import verify_implementation_closure
from src.temporal_learning.core import stable_json_hash

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--study',required=True);args=cli.parse_args();root=Path(args.study)
    raw=(root/'plans-frozen.json').read_bytes();freeze=json.loads(raw);r=freeze['receipt'];cfg=r['parameters']
    if stable_json_hash(r)!=freeze['seal']:raise ValueError('Freeze seal mismatch')
    verify_implementation_closure(Path.cwd(),r['implementation'])
    for path,digest in {**r['source_hashes'],**r['bundle_hashes'],**r['plan_hashes']}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Bound input/artifact changed: '+path)
    er=json.loads((root/'evaluation-receipt.json').read_bytes())
    for path,digest in [(root/'plans-frozen.json',er['freeze_sha256']),(root/'results.json',er['result_sha256']),
        (root/'prior-evaluation-snapshot.json',er['prior_receipt_sha256']),(Path(er['audit_path']),er['audit_sha256'])]:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Evaluation receipt mismatch')
    result=json.loads((root/'results.json').read_bytes());rows=result['rows']
    expected={(i,s,a) for i in r['issues'] for s in cfg['seeds'] for a in cfg['arms']}
    lookup={(x['issue'],x['seed'],x['arm']):x for x in rows}
    if len(lookup)!=len(rows) or set(lookup)!=expected or result['freeze_seal']!=freeze['seal'] or result['issue_order']!=r['issues']:raise ValueError('Incomplete/duplicate result grid')
    audit=json.loads(Path(er['audit_path']).read_bytes())['rows']
    actual={(str(x['issue']),int(x['slot']),str(x['provider_id'])):x for x in audit}
    if len(actual)!=len(audit):raise ValueError('Duplicate audit identity')
    sleeve_records=[];scenarios=[];checked=0
    for issue in r['issues']:
        bundle=json.loads(gzip.decompress((root/'bundles'/f'{issue}.json.gz').read_bytes()))
        if bundle['seal']!=stable_json_hash({k:v for k,v in bundle.items() if k!='seal'}):raise ValueError('Bundle seal mismatch')
        pool=bundle['expanded_pool'];f=pool['fixtures'];p=np.array([[x[f'p_{d}'] for d in 'WDL'] for x in f]);q=np.array([[x[f'q_{d}'] for d in 'WDL'] for x in f])
        if pool['seal']!=stable_json_hash({k:v for k,v in pool.items() if k!='seal'}):raise ValueError('Expanded pool seal')
        prior=json.loads(gzip.decompress((Path(cfg['pool_root'])/f'{issue}.json.gz').read_bytes()))
        if f!=prior['fixtures'] or pool['cutoffs']!=prior['cutoffs'] or bundle['cutoffs']!=prior['cutoffs'] or bundle['prior_pool_seal']!=prior['seal']:
            raise ValueError('Fixture/cutoff source identity changed')
        universe=set(map(tuple,prior['encoded_tickets']));groups={g['id']:g for g in bundle['sleeves']}
        if len(groups)!=len(bundle['sleeves']) or len({tuple(g['fixture_indices']) for g in groups.values()})!=len(groups):raise ValueError('Duplicate matchsets')
        for g in groups.values():
            e=g['enumeration'];idx=np.array(g['fixture_indices'],dtype=int);states=np.array(e['states'],dtype=int)
            if (len(idx)!=7 or np.any(idx<0) or np.any(idx>=len(f)) or e['fixtures']!=[f[i] for i in idx]
                or e['cutoffs']!={str(f[i]['slot']):pool['cutoffs'][str(f[i]['slot'])] for i in idx} or e['issue']!=issue):
                raise ValueError('Enumeration fixture identity/probabilities/cutoffs differ from frozen source')
            if (e['seal']!=stable_json_hash({k:v for k,v in e.items() if k!='seal'}) or len(idx)!=7
                or not np.all(np.diff(idx)>0) or states.shape!=(2187,7) or not np.array_equal(states,np.indices((3,)*7).reshape(7,-1).T)):
                raise ValueError('Full enumeration identity/uniqueness failed')
            mass=np.prod(p[idx,states],axis=1);pay=cfg['unit_cny']*cfg['payout_factor']/np.prod(q[idx,states],axis=1);value=mass*pay
            if (not math.isclose(mass.sum(),1.,abs_tol=1e-8) or not np.allclose(mass,e['probability'],rtol=1e-12,atol=0)
                or not np.allclose(pay,e['estimated_payout'],rtol=1e-12,atol=0) or not np.allclose(value,e['expected_contribution'],rtol=1e-12,atol=0)):
                raise ValueError('State probability/value arithmetic failed')
            universe.update(map(tuple,(3*idx+states).tolist()))
            for kind,s in g['options'].items():
                if s['seal']!=stable_json_hash({k:v for k,v in s.items() if k!='seal'}) or s['enumeration_seal']!=e['seal']:raise ValueError('State subset seal failed')
                ids=s['state_ids'];complete=s['status']=='COMPLETE'
                if (complete and (len(ids)!=64 or len(set(ids))!=64 or min(ids)<0 or max(ids)>=2187)) or (not complete and ids):raise ValueError('64 state cardinality failed')
                if not math.isclose(s['coverage'],mass[ids].sum(),abs_tol=1e-10) or not math.isclose(s['expected_gross'],value[ids].sum(),rel_tol=1e-10,abs_tol=1e-7):raise ValueError('Sleeve coverage/value failed')
                if complete and kind=='PROB' and not math.isclose(s['coverage'],np.sort(mass)[-64:].sum(),abs_tol=1e-10):raise ValueError('TOP64 probability is not maximal')
                if complete and kind=='VALUE' and not math.isclose(s['expected_gross'],np.sort(value)[-64:].sum(),rel_tol=1e-10,abs_tol=1e-7):raise ValueError('TOP64 value is not maximal')
                if complete and s['parameters']['kind']=='FRONTIER' and (s['coverage']+1e-8<s['parameters']['minimum_coverage'] or s['expected_gross']/128-1+1e-8<s['parameters']['minimum_roi']):raise ValueError('Frontier constraints failed')
                if complete:
                    distance=np.sum(states[ids,None,:]!=states[np.array(ids)[None,:],:],axis=2)
                    distances=distance[np.triu_indices(64,1)]
                    if s['minimum_hamming']!=int(distances.min()) or not math.isclose(s['mean_hamming'],float(distances.mean()),abs_tol=1e-12):raise ValueError('Hamming diagnostics failed')
                    if kind=='DIVERSITY' and np.min(distances)<s['parameters']['hamming_minimum']:raise ValueError('State diversity failed')
                    if not math.isclose(s['expected_roi'],value[ids].sum()/128-1,abs_tol=1e-9):raise ValueError('State ROI failed')
                a=[actual[issue,int(f[i]['slot']),str(f[i]['provider_id'])] for i in idx]
                realized=int(np.dot(['WDL'.index(x['actual_direction']) for x in a],3**np.arange(6,-1,-1)))
                sleeve_records.append(dict(issue=issue,sleeve_id=g['id'],origin=g['origin'],kind=kind,status=s['status'],coverage=s['coverage'],
                    expected_gross=s['expected_gross'],expected_roi=s['expected_roi'],realized_inclusion=int(realized in ids),
                    min_probability=float(mass[ids].min()) if ids else None,median_probability=float(np.median(mass[ids])) if ids else None,
                    max_probability=float(mass[ids].max()) if ids else None,min_contribution=float(value[ids].min()) if ids else None,
                    median_contribution=float(np.median(value[ids])) if ids else None,max_contribution=float(value[ids].max()) if ids else None,
                    minimum_hamming=s['minimum_hamming'],mean_hamming=s['mean_hamming'],solver_gap=s['solver'].get('gap')))
        if universe!=set(map(tuple,pool['encoded_tickets'])) or len(universe)!=len(pool['encoded_tickets']):raise ValueError('Unequal expanded candidate universe')
        actual_rows=[actual[issue,int(x['slot']),str(x['provider_id'])] for x in f]
        outcome=np.array(['WDL'.index(x['actual_direction']) for x in actual_rows]);sp=np.array([x['spf_sp'] for x in actual_rows],dtype=float)
        for seed in cfg['seeds']:
            legs=[]
            for child,n in zip(np.random.SeedSequence(seed).spawn(2),(cfg['training_worlds'],cfg['evaluation_worlds'])):
                rng=np.random.default_rng(child);bits=[]
                for triplet in p:
                    generated=np.searchsorted(np.r_[triplet.cumsum()[:2],1.],rng.random(n),side='right')
                    bits.extend(int.from_bytes(np.packbits(generated==d,bitorder='little').tobytes(),'little') for d in range(3))
                legs.append(bits)
            caches=[{},{}]
            for arm in cfg['arms']:
                row=lookup[issue,seed,arm];path=root/'plans'/f'{issue}_{seed}_{arm}.json.gz';plan=json.loads(gzip.decompress(path.read_bytes()))
                if plan['seal']!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):raise ValueError('Plan seal')
                if plan['fixtures']!=f or plan['cutoffs']!=pool['cutoffs'] or plan['bundle_seal']!=bundle['seal']:raise ValueError('Plan source/cutoff mismatch')
                idx=np.asarray(plan['fixture_indices'],dtype=int).reshape(-1,7);codes=np.asarray(plan['outcomes'],dtype=int).reshape(-1,7)
                if (idx.shape!=codes.shape or np.any(idx<0) or np.any(idx>=len(f)) or np.any(codes<0) or np.any(codes>2) or np.any(np.diff(idx,axis=1)<=0)):
                    raise ValueError('Invalid physical ticket')
                tickets=[tuple(t) for t in (3*idx+codes).tolist()]
                if len(tickets)!=len(set(tickets)) or not set(tickets)<=universe:raise ValueError('Duplicate/unadmitted physical tickets')
                if (len(idx) not in (0,512) or plan['stake']!=len(idx)*2 or plan['stake']+plan['cash_cny']!=1024 or plan['groups']!=len(idx)
                    or row['groups']!=len(idx) or row['stake']!=plan['stake'] or row['physical_ticket_identities']!=len(idx)):
                    raise ValueError('Budget/cardinality mismatch')
                keys=plan['sleeve_keys'];sleeve_masks=[]
                if keys:
                    if len(keys)!=8 or len({k[0] for k in keys})!=8 or len(idx)!=512:raise ValueError('8x64 shape failed')
                    expected_i=[];expected_d=[]
                    for gid,kind in keys:
                        group=groups[gid];subset=group['options'][kind]
                        if subset['status']!='COMPLETE':raise ValueError('Infeasible sleeve selected')
                        expected_i.extend([group['fixture_indices']]*64)
                        expected_d.extend(np.asarray(group['enumeration']['states'])[subset['state_ids']].tolist())
                    if idx.tolist()!=expected_i or codes.tolist()!=expected_d:raise ValueError('Sleeve ledger mismatch')
                elif arm.startswith('8x64') and len(idx):raise ValueError('Unregistered sleeves')
                if arm.startswith('8x64'):
                    expected_mean=math.fsum(groups[g]['options'][kind]['coverage'] for g,kind in keys)/len(keys) if keys else None
                    if expected_mean is None:
                        if plan['mean_coverage'] is not None:raise ValueError('Empty sleeve mean must be null')
                    elif not math.isclose(plan['mean_coverage'],expected_mean,rel_tol=1e-12,abs_tol=1e-14):raise ValueError('Sleeve-level mean coverage mismatch')
                used=np.unique(idx)
                if any(actual_rows[i]['handicap']!=f[i]['handicap'] or 'spf:IDENTITY' in actual_rows[i]['status'] for i in used):raise ValueError('Settlement identity mismatch')
                wins=np.all(outcome[idx]==codes,axis=1)
                if np.any(~np.isfinite(sp[idx[wins]])) or np.any(sp[idx[wins]]<=0):raise ValueError('Winning SP unavailable')
                gross=math.fsum(1.3*math.prod(sp[t]) for t in idx[wins])
                expected_net=float(np.sum(1.3*np.prod(p[idx,codes]/q[idx,codes],axis=1))-plan['stake'])
                if (int(wins.sum())!=row['hits'] or not math.isclose(gross,row['gross'],rel_tol=1e-10,abs_tol=1e-6)
                    or not math.isclose(gross-row['stake'],row['net'],abs_tol=1e-6)
                    or not math.isclose(expected_net,row['expected_net'],rel_tol=1e-10,abs_tol=1e-6)):
                    raise ValueError('Actual/model payout mismatch')
                if row['decision_year']!=min(pool['cutoffs'].values())[:4] or row['status']!=('COMPLETE' if len(idx) else 'NO_BET') or row['no_bet_reason']!=plan.get('no_bet_reason'):
                    raise ValueError('Result lifecycle metadata mismatch')
                if len(idx):
                    if not math.isclose(row['expected_roi'],expected_net/plan['stake'],abs_tol=1e-9):raise ValueError('Model ROI mismatch')
                elif row['expected_roi'] is not None:raise ValueError('Empty exposure has ROI')
                uses=np.bincount(idx.ravel(),minlength=len(f));directions=np.bincount((3*idx+codes).ravel(),minlength=3*len(f))
                for field,counts in [('fixture_hhi',uses),('outcome_hhi',directions)]:
                    hhi=float(np.sum((counts/counts.sum())**2)) if counts.sum() else 0.
                    if not math.isclose(row[field],hhi,abs_tol=1e-12):raise ValueError('Exposure HHI mismatch')
                sets=[set(groups[g]['fixture_indices']) for g,_ in keys]
                overlap=max([len(a&b) for i,a in enumerate(sets) for b in sets[:i]] or [0])
                reuse=max([sum(i in g for g in sets) for i in range(len(f))] or [0])
                if row['max_overlap']!=overlap or row['max_sleeve_reuse']!=reuse:raise ValueError('Overlap metadata mismatch')
                eval_ticket_masks=[]
                for index,n in enumerate((cfg['training_worlds'],cfg['evaluation_worlds'])):
                    for ticket in tickets:
                        if ticket not in caches[index]:caches[index][ticket]=functools.reduce(operator.and_,(legs[index][c] for c in ticket))
                    tm=[caches[index][t] for t in tickets];union=functools.reduce(operator.or_,tm,0);rate=union.bit_count()/n
                    field='train_coverage' if index==0 else 'eval_coverage';planfield='training_hit_rate' if index==0 else 'evaluation_hit_rate'
                    if rate!=row[field] or rate!=plan['simulation'][planfield]:raise ValueError('Independent shared-world union differs')
                    if index==1:eval_ticket_masks=tm
                n=cfg['evaluation_worlds'];modeled_gross=np.zeros(n)
                for ticket,mask in zip(tickets,eval_ticket_masks):
                    winners=np.flatnonzero(np.unpackbits(np.frombuffer(mask.to_bytes((n+7)//8,'little'),dtype=np.uint8),bitorder='little')[:n])
                    t=np.array(ticket);modeled_gross[winners]+=1.3/np.prod(q[t//3,t%3])
                histogram=None;independent=None
                if keys:
                    counts=np.zeros(n,dtype=np.uint8)
                    for k in range(8):
                        mask=functools.reduce(operator.or_,eval_ticket_masks[k*64:(k+1)*64],0)
                        counts+=np.unpackbits(np.frombuffer(mask.to_bytes((n+7)//8,'little'),dtype=np.uint8),bitorder='little')[:n]
                    histogram=(np.bincount(counts,minlength=9)/n).tolist()
                    independent=1-math.prod(1-groups[g]['options'][kind]['coverage'] for g,kind in keys)
                    if np.mean(counts>0)!=row['eval_coverage'] or row['hits']>8 or row['hit_sleeves']!=row['hits']:raise ValueError('Sleeve hit identity failed')
                scenarios.append(dict(issue=issue,seed=seed,arm=arm,joint_failure=1-row['eval_coverage'],
                    independent_sleeve_union=independent,modeled_profit_probability=float(np.mean(modeled_gross>plan['stake'])),
                    hit_sleeve_distribution=json.dumps(histogram),mean_modeled_gross=float(modeled_gross.mean())))
                checked+=1
        print(f'Independent replay {issue}: {checked}/{len(expected)} plans',flush=True)
    for name,data in [('sleeve-diagnostics.csv',sleeve_records),('scenario-diagnostics.csv',scenarios)]:
        with (root/name).open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    evidence=dict(checked=checked,freeze=freeze['seal'],result_sha256=er['result_sha256'],
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        diagnostics={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('sleeve-diagnostics.csv','scenario-diagnostics.csv')})
    (root/'independent-replay.json').write_text(json.dumps(evidence));print('PASS all state/ticket/budget/payout/shared-scenario contracts',flush=True)
