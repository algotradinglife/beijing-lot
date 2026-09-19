"""Settle an entirely frozen legacy market grid against an explicit verified audit."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.fundamentals_n7_single import settle_n7_single
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure, implementation_closure

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True)
    p.add_argument('--proof',required=True);p.add_argument('--audit',required=True)
    p.add_argument('--audit-sha256',required=True);a=p.parse_args();s=Path(a.study)
    if (s/'results.json').exists():raise FileExistsError('Immutable results required')
    raw=(s/'plans-frozen.json').read_bytes();f=json.loads(raw);r=f['receipt']
    assert stable_json_hash(r)==f['seal']
    proof_raw=Path(a.proof).read_bytes();proof=json.loads(proof_raw)
    assert proof['status']=='PASS' and proof['frozen_sha256']==hashlib.sha256(raw).hexdigest()
    assert proof['issues']==len(r['issues']) and proof['plans']==8*len(r['issues'])
    verify_implementation_closure(Path.cwd(),r['implementation'])
    for name,digest in {r['catalog']:r['catalog_sha256'],**r['source_hashes'],**r['plan_hashes']}.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    # First target-label access occurs only after all freeze/proof bindings pass.
    audit_raw=Path(a.audit).read_bytes();assert hashlib.sha256(audit_raw).hexdigest()==a.audit_sha256
    import io
    audit=pd.read_csv(io.BytesIO(audit_raw),dtype={'issue':str,'provider_id':str})
    assert not audit.duplicated(['issue','slot']).any()
    rows=[]
    for issue in r['issues']:
        plans=json.loads(gzip.decompress((s/'plans'/(issue+'.json.gz')).read_bytes()))
        for policy,plan in plans.items():
            result=settle_n7_single(plan,audit[audit.issue==issue])
            assert result['status'] in ('COMPLETE','NO_BET'),(issue,policy,result['status'])
            rows.append(dict(issue=issue,model='LEGACY_MARKET',policy=policy,
                status=result['status'],stake=result['stake'],gross=result['gross'],net=result['net'],
                groups=result['groups'],hits=result['hits'],budget_cny=1024,cash_cny=1024-result['stake']))
        print('SETTLED',issue,flush=True)
    target=s/'results.json';target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],upstream_freeze_seal=f['seal']),sort_keys=True))
    receipt=dict(status='SETTLED_PENDING_INDEPENDENT_REVIEW',freeze_sha256=hashlib.sha256(raw).hexdigest(),
        proof_sha256=hashlib.sha256(proof_raw).hexdigest(),audit_path=a.audit,audit_sha256=a.audit_sha256,
        result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),historical_admission=False,
        implementation=implementation_closure(Path.cwd(),['scripts.settle_legacy_market_grid'],distributions=['numpy','pandas','scipy']))
    (s/'evaluation-receipt.json').write_text(json.dumps(receipt,sort_keys=True))
