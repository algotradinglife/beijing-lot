"""Independent full-grid source, selection, simulation and settlement replay."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from src.n7_sleeve_expansion_check import check_expansion_bundle
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--study',required=True);args=cli.parse_args();root=Path(args.study)
    frozen=json.loads((root/'plans-frozen.json').read_bytes());fr=frozen['receipt'];cfg=fr['parameters']
    assert frozen['seal']==stable_json_hash(fr) and fr['historical_admission'] is False
    verify_implementation_closure(Path.cwd(),fr['implementation'])
    closure=implementation_closure(Path.cwd(),['scripts.check_n7_sleeve_expansion'],distributions=['numpy','pandas','scipy'])
    for path,digest in {**fr['source_hashes'],**fr['bundle_hashes'],**fr['plan_hashes']}.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    er=json.loads((root/'evaluation-receipt.json').read_bytes())
    assert er['freeze_sha256']==hashlib.sha256((root/'plans-frozen.json').read_bytes()).hexdigest()
    assert er['result_sha256']==hashlib.sha256((root/'results.json').read_bytes()).hexdigest()
    assert er['audit_sha256']==hashlib.sha256(Path(er['audit_path']).read_bytes()).hexdigest()
    assert er['prior_receipt_sha256']==hashlib.sha256((root/'prior-evaluation-snapshot.json').read_bytes()).hexdigest()
    result=json.loads((root/'results.json').read_bytes());assert result['freeze_seal']==frozen['seal'] and result['issue_order']==fr['issues']
    rows={(r['issue'],r['pool_size'],r['weighting'],r['seed']):r for r in result['rows']}
    expected={(i,n,w,s) for i in fr['issues'] for n in cfg['pool_sizes'] for w in cfg['weightings'] for s in cfg['seeds']}
    assert set(rows)==expected and len(rows)==len(result['rows'])==len(fr['plan_hashes'])
    audit=pd.DataFrame(json.loads(Path(er['audit_path']).read_bytes())['rows']);audit.issue=audit.issue.astype(str)
    assert not audit.duplicated(['issue','slot','provider_id']).any()
    count=0;candidate_count=0
    for issue in fr['issues']:
        b=json.loads(gzip.decompress((root/'bundles'/f'{issue}.json.gz').read_bytes()))
        old=json.loads(gzip.decompress((Path(cfg['prior_study'])/'bundles'/f'{issue}.json.gz').read_bytes()))
        pool=json.loads(gzip.decompress((Path(cfg['pool_root'])/f'{issue}.json.gz').read_bytes()))
        assert b['fixtures']==pool['fixtures'] and b['cutoffs']==pool['cutoffs'] and b['pool_seal']==pool['seal']
        cuts={s:Cutoff.decision_epoch(issue,t) for s,t in b['cutoffs'].items()}
        assert b['parameters']==dict(candidate_count=max(cfg['pool_sizes']),original_count=24,
            seed=cfg['candidate_seed'],maximum_attempts=cfg['maximum_attempts'],
            budget_cny=cfg['budget_cny'],unit_cny=cfg['unit_cny'],payout_factor=cfg['payout_factor'])
        candidate_count+=check_expansion_bundle(b,cutoffs=cuts,original_groups=[s['fixture_indices'] for s in old['sleeves']],source_pool=pool)
        for new,previous in zip(b['sleeves'],old['sleeves']):
            assert new['state_ids']==previous['options']['PROB']['state_ids']
            assert abs(new['coverage']-previous['options']['PROB']['coverage'])<1e-12
        f=pd.DataFrame(b['fixtures']);p=f[[f'p_{d}' for d in 'WDL']].to_numpy()
        a=f.merge(audit[audit.issue==issue],on=['issue','slot','provider_id'],validate='one_to_one',suffixes=('','_audit'))
        assert len(a)==len(f) and a.handicap.eq(a.handicap_audit).all() and a.actual_direction.isin(list('WDL')).all()
        actual=a.actual_direction.map(dict(W=0,D=1,L=2)).to_numpy();sp=a.spf_sp.to_numpy()
        for n in cfg['pool_sizes']:
            ss=b['sleeves'][:n];eligible=[s for s in ss if s['coverage']>cfg['coverage_floor']]
            cr=[r for r in result['candidates'] if (r['issue'],r['pool_size'])==(issue,n)]
            assert len(cr)==1 and cr[0]['actual']==len(ss) and cr[0]['eligible']==len(eligible)
            assert np.isclose(cr[0]['min_coverage'],min(s['coverage'] for s in ss))
            assert np.isclose(cr[0]['max_coverage'],max(s['coverage'] for s in ss))
            assert np.isclose(cr[0]['mean_coverage'],np.mean([s['coverage'] for s in ss]))
            for weighting in cfg['weightings']:
                for seed in cfg['seeds']:
                    path=root/'plans'/f'{issue}_{n}_{weighting}_{seed}.json.gz';z=json.loads(gzip.decompress(path.read_bytes()))
                    assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
                    assert z['expansion_seal']==b['seal'] and z['fixtures']==b['fixtures'] and z['cutoffs']==b['cutoffs']
                    assert z['parameters']==dict(pool_size=n,coverage_floor=cfg['coverage_floor'],weighting=weighting,seed=seed,evaluation_worlds=cfg['evaluation_worlds'])
                    assert (z['budget_cny'],z['unit_cny'],z['payout_factor'])==(1024,2,.65)
                    assert z['eligible_count']==len(eligible) and z['historical_admission'] is False
                    remain=list(eligible);chosen=[];rng=np.random.default_rng(np.random.SeedSequence([seed,0]))
                    if len(remain)>=8:
                        for d in z['draws']:
                            weights=np.array([s['expected_gross'] if weighting=='EXPECTED_GROSS' else 1. for s in remain])
                            j=int(rng.choice(len(remain),p=weights/weights.sum()));s=remain.pop(j);chosen.append(s)
                            assert d['sleeve_id']==s['id'] and np.isclose(d['probability'],weights[j]/weights.sum(),rtol=1e-12)
                            assert np.isclose(d['weight'],weights[j]) and np.isclose(d['remaining_weight'],weights.sum())
                        assert len(chosen)==8
                    else:assert not z['draws']
                    assert z['sleeve_ids']==[s['id'] for s in chosen]
                    idx=np.array(z['fixture_indices'],dtype=int).reshape(-1,7);codes=np.array(z['outcomes'],dtype=int).reshape(-1,7)
                    assert len(idx)==len(chosen)*64==z['groups'] and z['stake']==2*len(idx) and z['cash_cny']+z['stake']==1024
                    assert len({tuple(3*i+d) for i,d in zip(idx,codes)})==len(idx)
                    for j,s in enumerate(chosen):
                        assert np.all(idx[j*64:(j+1)*64]==s['fixture_indices'])
                        sid=np.ravel_multi_index(codes[j*64:(j+1)*64].T,(3,)*7)
                        assert sid.tolist()==s['state_ids']
                    won=np.all(actual[idx]==codes,axis=1);gross=float(np.sum(1.3*np.prod(sp[idx[won]],axis=1)))
                    r=rows[issue,n,weighting,seed]
                    assert (r['groups'],r['stake'],r['hits'])==(len(idx),2*len(idx),int(won.sum()))
                    assert r['status']==('COMPLETE' if len(idx) else 'NO_BET')
                    assert np.isclose(r['gross'],gross,rtol=1e-12) and np.isclose(r['net'],gross-z['stake'],rtol=1e-12)
                    assert r['eligible_count']==len(eligible)
                    expected_gross=sum(s['expected_gross'] for s in chosen)
                    assert np.isclose(z['expected_net'],expected_gross-z['stake'])
                    if chosen:
                        assert np.isclose(r['expected_roi'],expected_gross/z['stake']-1)
                        assert np.isclose(r['selected_mean_coverage'],np.mean([s['coverage'] for s in chosen]))
                    else:assert r['expected_roi'] is None and r['selected_mean_coverage'] is None
                    assert np.isclose(r['independent_counterfactual'],1-np.prod([1-s['coverage'] for s in chosen]))
                    worlds=cfg['evaluation_worlds'];rng=np.random.default_rng(np.random.SeedSequence([seed,1]))
                    outcome=np.array([np.searchsorted(np.r_[row.cumsum()[:2],1.],rng.random(worlds),side='right') for row in p])
                    hits=np.zeros(worlds,dtype=int)
                    for s in chosen:
                        sid=np.ravel_multi_index(outcome[s['fixture_indices']],(3,)*7)
                        hits+=np.isin(sid,s['state_ids'])
                    assert z['eval_coverage']==r['eval_coverage']==float(np.mean(hits>0))
                    assert np.allclose(z['hit_sleeve_distribution'],np.bincount(hits,minlength=9)/worlds,rtol=0,atol=1e-15)
                    count+=1
        print(f'Checked {issue}, {count} plans',flush=True)
    verify_implementation_closure(Path.cwd(),closure)
    (root/'independent-replay.json').write_text(json.dumps(dict(freeze=frozen['seal'],checked=count,
        candidates=candidate_count,result_sha256=er['result_sha256'],implementation=closure,historical_admission=False)))
