"""Bind accepted snapshots and prepare the fixed-policy diagnostic inputs."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_updated_scope import prepare_updated_issue

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--acceptance',required=True);a=p.parse_args()
    out=Path(a.output);root=Path.cwd();accept=Path(a.acceptance);accepted=json.loads(accept.read_text())
    if out.exists():raise FileExistsError('New immutable output required')
    if accepted['status']!='ACCEPTED_DIAGNOSTIC_BATCH' or accepted['historical_admission'] is not False:raise ValueError('Accepted diagnostic batch required')
    hashes=dict(accepted['source_hashes']);hashes[str(accept)]=hashlib.sha256(accept.read_bytes()).hexdigest()
    ap=next(k for k in hashes if 'analysis-audit' in k and k.endswith('/summary.json'))
    mp=next(k for k in hashes if 'full-market-audit' in k and k.endswith('/summary.json'))
    analysis=json.loads(Path(ap).read_text());market=json.loads(Path(mp).read_text())
    scope_path=analysis['scope_path'];hashes[scope_path]=analysis['scope_sha256'];scope=json.loads(Path(scope_path).read_text())
    archived_implementations={}
    for row in analysis['rows']:
        hashes.update(row['source_hashes']);hashes[row['path']]=row['output_sha256']
        for name,digest in row['implementation_hashes'].items():
            snapshots=sorted(k for k,v in row['source_hashes'].items() if v==digest and k.endswith('/'+name))
            evidence=snapshots[0] if snapshots else name
            hashes[evidence]=digest;archived_implementations[name]=dict(sha256=digest,evidence=evidence)
    hashes.update(market['source_hashes'])
    impl=Path(mp).parent.with_name(Path(mp).parent.name+'-implementation')
    hashes.update({str(impl/k):v for k,v in market['implementation_hashes'].items()})
    hashes.update({str(Path(mp).parent/k):v for k,v in market['output_hashes'].items()})
    verify_clean_file_bindings(hashes,repository_root=root)
    issues=scope['issues'];assert len(issues)==accepted['scope']['issues']==len(analysis['rows'])
    receipt=dict(contract=dict(issues=issues,window=10,minimum=10,learning='NONE',historical_admission=False),
        source_hashes=hashes,files={},cutoffs={},archived_implementations=archived_implementations,implementation=implementation_closure(root,['scripts.prepare_updated_scope']))
    (out/'inputs').mkdir(parents=True);rows=[]
    for inv in scope['inventories']:
        issue=inv['issue'];ar=next(r for r in analysis['rows'] if r['issue']==issue)
        payload=json.loads(Path(ar['path']).read_text());mfile=Path(mp).parent/(issue+'.json')
        cuts={s:Cutoff.decision_epoch(issue,t) for s,t in inv['cutoffs'].items()}
        source={ar['path']:ar['output_sha256'],str(mfile):hashes[str(mfile)],scope_path:hashes[scope_path]}
        result=prepare_updated_issue(payload,json.loads(mfile.read_text()),inv,cutoffs=cuts,source_hashes=source,repository_root=root,window=10,minimum=10)
        f=out/'inputs'/(issue+'.json.gz');f.write_bytes(gzip.compress(json.dumps(result).encode(),mtime=0));receipt['files'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest();receipt['cutoffs'][issue]=inv['cutoffs']
        for w,m in zip(result['forms']['windows'],result['market']['rows'],strict=True):
            assert w['slot']==m['slot'];rows.append(dict(issue=issue,slot=w['slot'],provider_id=w['provider_id'],form_status=w['status'],market_status=m['status'],ready=w['status']=='OK_DIAGNOSTIC' and m['status']=='READY'))
        print('PREPARED',issue,sum(r['ready'] for r in rows if r['issue']==issue),flush=True)
    (out/'prepared.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt),readiness=rows)))
