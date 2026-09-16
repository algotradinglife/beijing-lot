"""Independent elementary-ticket settlement replay; no production engine imports."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True)
    p.add_argument('--audit',required=True);p.add_argument('--audit-sha256',required=True)
    p.add_argument('--output',required=True);a=p.parse_args();s=Path(a.study)
    ar=Path(a.audit).read_bytes();assert hashlib.sha256(ar).hexdigest()==a.audit_sha256
    rows=json.loads(ar)['rows'] if a.audit.endswith('.json') else list(csv.DictReader(ar.decode().splitlines()))
    audit={(str(x['issue']),int(x['slot'])):x for x in rows};assert len(audit)==len(rows)
    rr=(s/'results.json').read_bytes();result=json.loads(rr)
    by={(x['issue'],x['policy']):x for x in result['rows']};assert len(by)==len(result['rows'])
    frozen_raw=(s/'plans-frozen.json').read_bytes();f=json.loads(frozen_raw)
    assert hashlib.sha256(json.dumps(f['receipt'],sort_keys=True,separators=(',',':')).encode()).hexdigest()==f['seal']
    unavailable=f['receipt'].get('unavailable',[])
    missing={x['issue'] for x in unavailable}
    expected_order=[i for i in f['receipt']['issues'] if i not in missing]
    assert result['issue_order']==expected_order and len(set(expected_order))==len(expected_order)
    assert result.get('unavailable',[])==unavailable
    assert result.get('upstream_freeze_seal',result.get('freeze_seal'))==f['seal']
    assert set(x['issue'] for x in result['rows'])==set(expected_order)
    count=0;groups=0;ticket_count=0
    for path,digest in f['receipt']['plan_hashes'].items():
        raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        bundle=json.loads(gzip.decompress(raw));plans=bundle.get('plans',bundle)
        for policy,plan in plans.items():
            parts=plan.get('components',[plan]);stake=0;gross=0;hits=0;n=0
            for part in parts:
                for group in range(1,part['groups']+1):
                    legs=[l for l in part['legs'] if l['group']==group]
                    assert len(legs)==7 and len({l['slot'] for l in legs})==7
                    code='';sp=1
                    for leg in legs:
                        obs=audit[(part['issue'],leg['slot'])]
                        assert str(obs['provider_id'])==leg['provider_id']
                        assert float(obs['handicap'])==leg['handicap']
                        delta=float(obs['actual_home'])-float(obs['actual_away'])+leg['handicap']
                        direction='W' if delta>0 else 'D' if delta==0 else 'L'
                        assert obs['actual_direction']==direction and obs['status']=='READY'
                        code+=dict(W='3',D='1',L='0')[direction]
                        price=float(obs['spf_sp']);assert math.isfinite(price) and price>0;sp*=price
                    tickets=[t for t in part['tickets'] if t['group']==group]
                    amount=sum(t['units'] for t in tickets)*2
                    winning=sum(t['units'] for t in tickets if t['code']==code)
                    stake+=amount;gross+=winning*2*.65*sp;hits+=int(winning>0);n+=1;ticket_count+=len(tickets)
            z=by.pop((plan['issue'],policy));assert z['groups']==n and z['hits']==hits
            for k,v in [('stake',stake),('gross',gross),('net',gross-stake)]:
                assert math.isclose(z[k],v,abs_tol=1e-7,rel_tol=1e-12),(plan['issue'],policy,k)
            assert z['cash_cny']==1024-stake and stake<=1024 and z['budget_cny']==1024
            assert z['status']==('COMPLETE' if n else 'NO_BET')
            count+=1;groups+=n
    assert not by
    Path(a.output).write_text(json.dumps(dict(status='PASS',plans=count,groups=groups,tickets=ticket_count,
        results_sha256=hashlib.sha256(rr).hexdigest(),audit_sha256=a.audit_sha256,
        frozen_sha256=hashlib.sha256(frozen_raw).hexdigest()),indent=2))
