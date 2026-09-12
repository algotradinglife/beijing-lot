"""Check cap and frozen fixed64 comparison against source/audit bindings."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from src.n7_sleeve_cap_check import check_capped_plan
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--study',required=True);args=cli.parse_args();root=Path(args.study)
    frozen=json.loads((root/'plans-frozen.json').read_bytes());fr=frozen['receipt'];cfg=fr['parameters'];origin=Path(cfg['origin'])
    assert frozen['seal']==stable_json_hash(fr) and fr['historical_admission'] is False
    verify_implementation_closure(Path.cwd(),fr['implementation'])
    closure=implementation_closure(Path.cwd(),['scripts.check_n7_sleeve_probability_cap'],distributions=['numpy','pandas','scipy'])
    for path,digest in {**fr['source_hashes'],**fr['plan_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    parent=json.loads((origin/'plans-frozen.json').read_bytes());old_ir=json.loads((origin/'independent-replay.json').read_bytes())
    assert old_ir['freeze']==parent['seal'] and old_ir['checked']==1800
    verify_implementation_closure(Path.cwd(),old_ir['implementation'])
    er=json.loads((root/'evaluation-receipt.json').read_bytes())
    assert er['freeze_sha256']==hashlib.sha256((root/'plans-frozen.json').read_bytes()).hexdigest()
    assert er['result_sha256']==hashlib.sha256((root/'results.json').read_bytes()).hexdigest()
    assert er['audit_sha256']==hashlib.sha256(Path(er['audit_path']).read_bytes()).hexdigest()
    assert er['prior_receipt_sha256']==hashlib.sha256((root/'prior-evaluation-snapshot.json').read_bytes()).hexdigest()
    result=json.loads((root/'results.json').read_bytes());assert result['freeze_seal']==frozen['seal'] and result['issue_order']==fr['issues']
    rows={(r['issue'],r['pool_size'],r['seed'],r['arm']):r for r in result['rows']}
    entries={(r['issue'],r['pool_size'],r['seed'],r['arm']):r for r in fr['entries']}
    expected={(i,n,s,a) for i in fr['issues'] for n in cfg['pool_sizes'] for s in cfg['seeds'] for a in ('CAP25','FIXED64')}
    assert set(rows)==set(entries)==expected and len(rows)==len(result['rows'])==len(fr['entries'])==len(fr['plan_hashes'])
    audit=pd.DataFrame(json.loads(Path(er['audit_path']).read_bytes())['rows']);audit.issue=audit.issue.astype(str)
    assert not audit.duplicated(['issue','slot','provider_id']).any();checked=0
    for issue in fr['issues']:
        b=json.loads(gzip.decompress((origin/'bundles'/f'{issue}.json.gz').read_bytes()))
        cuts={s:Cutoff.decision_epoch(issue,t) for s,t in b['cutoffs'].items()}
        f=pd.DataFrame(b['fixtures']);a=f.merge(audit[audit.issue==issue],on=['issue','slot','provider_id'],validate='one_to_one',suffixes=('','_audit'))
        assert len(a)==len(f) and a.handicap.eq(a.handicap_audit).all() and a.actual_direction.isin(list('WDL')).all()
        actual=a.actual_direction.map(dict(W=0,D=1,L=2)).to_numpy();sp=a.spf_sp.to_numpy()
        for n in cfg['pool_sizes']:
            for seed in cfg['seeds']:
                for arm in ('CAP25','FIXED64'):
                    e=entries[issue,n,seed,arm];z=json.loads(gzip.decompress(Path(e['path']).read_bytes()))
                    assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
                    assert z['fixtures']==b['fixtures'] and z['cutoffs']==b['cutoffs'] and z['expansion_seal']==b['seal']
                    if arm=='CAP25':
                        assert z['parameters']==dict(pool_size=n,coverage_floor=cfg['coverage_floor'],coverage_cap=cfg['coverage_cap'],seed=seed,evaluation_worlds=cfg['evaluation_worlds'],weighting='EXPECTED_GROSS')
                        sleeve_count=check_capped_plan(z,b,cutoffs=cuts)
                    else:
                        path=str(origin/'plans'/f'{issue}_{n}_EXPECTED_GROSS_{seed}.json.gz')
                        assert e['path']==path and fr['plan_hashes'][path]==parent['receipt']['plan_hashes'][path]
                        sleeve_count=len(z['sleeve_ids'])
                    idx=np.array(z['fixture_indices'],dtype=int).reshape(-1,7);codes=np.array(z['outcomes'],dtype=int).reshape(-1,7)
                    won=np.all(actual[idx]==codes,axis=1);gross=float(np.sum(1.3*np.prod(sp[idx[won]],axis=1)))
                    r=rows[issue,n,seed,arm]
                    assert (r['groups'],r['stake'],r['hits'],r['cash'],r['sleeve_count'])==(len(idx),2*len(idx),int(won.sum()),1024-2*len(idx),sleeve_count)
                    assert r['status']==('COMPLETE' if len(idx) else 'NO_BET') and r['eval_coverage']==z['eval_coverage']
                    assert np.isclose(r['gross'],gross,rtol=1e-12) and np.isclose(r['net'],gross-r['stake'],rtol=1e-12)
                    assert r['expected_roi']==z['expected_roi'] and r['eligible_count']==z['eligible_count'];checked+=1
        print(f'Checked {issue}: {checked} plans',flush=True)
    verify_implementation_closure(Path.cwd(),closure)
    (root/'independent-replay.json').write_text(json.dumps(dict(freeze=frozen['seal'],checked=checked,result_sha256=er['result_sha256'],implementation=closure,historical_admission=False)))
