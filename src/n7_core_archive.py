"""Portable, independently checked #433 descriptive report inputs."""
from pathlib import Path
import gzip
import hashlib
import json

from src.n7_joint_check import check_prefix_study
from src.n7_core_check import check_core_plan, check_core_result, check_core_settlement
from src.temporal_learning import implementation_closure


def package_core_report(study, destination, *, frozen_source_root, checker_root,
                        baseline_archive, baseline_body_sha256, baseline_arm):
    """Replay every frozen plan and paid layer before packaging all result rows.

    Explicit paths identify the immutable production export and current checker.
    Baseline is the separately accepted #425 archive, pinned by its body SHA256;
    issue/seed coverage must match exactly. Actual labels are diagnostic only and
    opened after the common complete-freeze replay. CNY and fractional ROI. No
    fitting, ranking, network or overwrites; failures leave no success artifact.
    """
    study=Path(study).resolve(); destination=Path(destination)
    if destination.exists():
        raise ValueError('Refusing to overwrite core report archive')
    replay=check_prefix_study(study,repository_root=frozen_source_root,
        check_plan=check_core_plan,check_result=check_core_result,
        physical_plans=lambda p:p['layers'])
    frozen_raw=(study/'plans-frozen.json').read_bytes();frozen=json.loads(frozen_raw)
    receipt=frozen['receipt']
    er_raw=(study/'evaluation-receipt.json').read_bytes();er=json.loads(er_raw)
    result_raw=(study/'results.json').read_bytes();audit_raw=(study/'audit-snapshot.json').read_bytes()
    for name,raw in [('freeze',frozen_raw),('result',result_raw),('audit',audit_raw)]:
        if hashlib.sha256(raw).hexdigest()!=er[name+'_sha256']:
            raise ValueError('Core report '+name+' binding changed')
    payload=json.loads(result_raw)
    if (payload['freeze_seal']!=frozen['seal'] or payload['historical_admission'] is not False
            or payload['issue_order']!=receipt['issues']):
        raise ValueError('Core report freeze/admission/issue mismatch')
    rows={(r['issue'],r['seed'],r['arm']):r for r in payload['rows']}
    config=receipt['parameters']
    expected={(i,s,p['name']) for i in receipt['issues'] for s in config['seeds'] for p in config['policies']}
    if set(rows)!=expected or len(rows)!=len(payload['rows']) or any(r['reference'] for r in rows.values()):
        raise ValueError('Core result grid mismatch')
    audit={}
    for row in json.loads(audit_raw)['rows']:
        audit.setdefault(str(row['issue']),[]).append(row)
    seen=set(); allocations=[]; sleeves=[]
    for path,digest in receipt['plan_hashes'].items():
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Core plan changed after replay')
        p=json.loads(gzip.decompress(raw)); key=(p['issue'],p['seed'],p['arm'])
        if key in seen or key not in rows:
            raise ValueError('Duplicate or unexpected core plan')
        seen.add(key)
        check_core_settlement(p,audit.get(p['issue'],[]),rows[key])
        ident=dict(issue=p['issue'],seed=p['seed'],arm=p['arm'])
        allocations.extend(dict(**ident,**a) for a in p['allocation'])
        for layer in p['layers']:
            sleeves.extend(dict(**ident,role=layer['role'],copy_index=layer['copy_index'],
                **{k:s[k] for k in ('sleeve_id','depth','coverage','stake','expected_gross')})
                for s in layer['sleeve_keys'])
    if seen!=expected:
        raise ValueError('Incomplete core settlement replay')
    base_raw=Path(baseline_archive).read_bytes();wrapper=json.loads(gzip.decompress(base_raw))
    if (wrapper['schema']!='bj425_capital_report_v1' or wrapper['sha256']!=baseline_body_sha256
            or hashlib.sha256(wrapper['body'].encode()).hexdigest()!=baseline_body_sha256):
        raise ValueError('Baseline archive identity changed')
    base=json.loads(wrapper['body'])
    if (base['historical_admission'] is not False or base['issue_order']!=receipt['issues']
            or base['independent_replay']['status']!='PASS' or base['settlement_replay']['status']!='PASS'):
        raise ValueError('Baseline scope or acceptance mismatch')
    controls=[dict(r,reference=True) for r in base['rows']
              if r['arm']==baseline_arm and r['seed'] in config['seeds']]
    control_keys={(r['issue'],r['seed']) for r in controls}
    if (control_keys!={(i,s) for i in receipt['issues'] for s in config['seeds']}
            or len(controls)!=len(control_keys) or baseline_arm in {p['name'] for p in config['policies']}):
        raise ValueError('Baseline paired grid mismatch')
    comparisons=[]
    for p in config['policies']:
        comparisons.append(dict(treatment=p['name'],control=baseline_arm,comparison='ORIGINAL_ANY'))
        if p['opportunity_cap_cny']:
            matched=[c for c in config['policies'] if c['core_count']==p['core_count']
                and c['mode']==p['mode'] and c['objective']==p['objective'] and c['opportunity_cap_cny']==0]
            if len(matched)!=1:
                raise ValueError('Missing or ambiguous core-only control')
            comparisons.append(dict(treatment=p['name'],control=matched[0]['name'],comparison='MATCHED_CORE_ONLY'))
    body=dict(**dict(payload,rows=payload['rows']+controls),parameters=config,
        comparisons=comparisons,allocations=allocations,sleeves=sleeves,
        independent_replay=replay,settlement_replay=dict(status='PASS',plans_checked=len(seen)),
        baseline_body_sha256=baseline_body_sha256,baseline_freeze_seal=base['freeze_seal'],
        evaluation_receipt_sha256=hashlib.sha256(er_raw).hexdigest(),
        generator_implementation=implementation_closure(checker_root,['src.n7_core_archive'],
            distributions=['numpy','pandas']))
    encoded=json.dumps(body,sort_keys=True,allow_nan=False,separators=(',',':'))
    wrapper=dict(schema='bj433_core_report_v1',body=encoded,
                 sha256=hashlib.sha256(encoded.encode()).hexdigest())
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as f:
        f.write(gzip.compress(json.dumps(wrapper).encode(),mtime=0))
    return dict(status='PASS',path=str(destination),sha256=wrapper['sha256'],plans=len(seen),
                rows=len(body['rows']),freeze_seal=frozen['seal'])
