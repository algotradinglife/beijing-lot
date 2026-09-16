"""Frozen retrospective payout/exposure study IO and independent selection replay.

R owns decisions; shared temporal_learning owns cutoffs and provenance. No fitting,
clock inference, source admission or import-time IO. Legacy inputs remain evidence.
"""
import csv
import gzip
import hashlib
import io
import json
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from src.strategy_diagnostic_inputs import read_verified_bundle_json
from src.temporal_learning import Cutoff, implementation_closure, verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_n7_baseline import rank_double_candidates
from src.n7_single_ticket_sampling import settle_single_tickets

R_SOURCES = ['r/joint_payout_exposure.R', 'r/joint_payout_study.R',
             'r/n7_joint_sleeves.R', 'r/n7_sleeve_tables.R',
             'scripts/freeze_joint_payout_chunk.R', 'config/n7_joint_runtime.json',
             'config/compression_breadth_runtime.json']


def prepare_payout_study(catalog_path, catalog_sha256, groups_path, groups_sha256,
                         config_path, repository_root, output):
    """Create a new label-free job manifest from verified frozen allocations.

    Groups source may contain old diagnostic results; project ONLY issue/id/depth.
    Never reselect groups. Refuse existing output or changed bytes. Return manifest.
    """
    root, out = Path(repository_root), Path(output)
    if out.exists():
        raise ValueError('Study output already exists')
    sources = {}
    loaded = []
    for path, expected in [(catalog_path, catalog_sha256), (groups_path, groups_sha256)]:
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Frozen source changed')
        loaded.append(raw); sources[str(Path(path).resolve())] = expected
    catalog = json.loads(loaded[0])
    allocations = {}
    for row in csv.DictReader(io.StringIO(loaded[1].decode())):
        if row['policy'] != 'JOINT':
            continue
        depth = float(row['depth']); sid = float(row['sleeve_id'])
        if depth != int(depth) or sid != int(sid) or not 1 <= depth <= 2187:
            raise ValueError('Invalid frozen allocation')
        allocations.setdefault(row['issue'], []).append(dict(sleeve_id=int(sid), depth=int(depth)))
    config_raw = Path(config_path).read_bytes(); config = json.loads(config_raw)
    if (config['historical_admission'] is not False or config['unit_cny'] != 2
            or config['payout_factor'] != .65 or config['budget_cny'] != 1024):
        raise ValueError('Unexpected study accounting')
    sources[str(Path(config_path).resolve())] = hashlib.sha256(config_raw).hexdigest()
    issues = [r['issue'] for r in catalog['issues']]
    if not issues or len(set(issues)) != len(issues) or not set(allocations).issubset(issues):
        raise ValueError('Invalid issue scope')
    jobs = []
    for item in catalog['issues']:
        a = allocations.get(item['issue'], [])
        if len({r['sleeve_id'] for r in a}) != len(a) or sum(r['depth'] for r in a)*2 > 1024:
            raise ValueError('Duplicate or overbudget allocations')
        sources[item['path']] = item['sha256']
        jobs.append(dict(item, allocations=a))
    receipt = dict(jobs=jobs,config=config,source_hashes=sources,
        r_implementation={p: hashlib.sha256((root/p).read_bytes()).hexdigest() for p in R_SOURCES},
        implementation=implementation_closure(root, [__name__, 'src.__init__', 'src.temporal_learning'],
                                               distributions=['numpy','pandas']),
        historical_admission=False,evidence_class='EXPOSED_HISTORICAL_DIAGNOSTIC',
        maximum_source_availability=None,maximum_label_availability=None,
        partitions='NO_FIT_TUNE_CALIBRATION')
    receipt['seal'] = stable_json_hash(receipt)
    out.mkdir(parents=True); (out/'plans').mkdir()
    (out/'manifest.json').write_text(json.dumps(receipt, sort_keys=True))
    return receipt


def replay_payout_selection(bundle, allocations, cutoffs, floor, fixture_cap, direction_cap, unit_cny):
    """Independent NumPy/Python replay; returns ordered (sleeve,state1based).

    Requires native explicit cutoff objects matching every frozen fixture. Pure
    label-free fixed-grid selector, not historical training or parameter tuning.
    """
    _, bound = rank_double_candidates(pd.DataFrame(bundle['expanded_pool']['fixtures']), cutoffs=cutoffs)
    if bound != bundle['cutoffs'] or unit_cny != 2 or floor < 0 or min(fixture_cap,direction_cap)<unit_cny:
        raise ValueError('Invalid fixed replay contract')
    quotas = {r['sleeve_id']:r['depth'] for r in allocations}
    if len(quotas)!=len(allocations) or any(type(d) is not int or not 1<=d<=2187 for d in quotas.values()):
        raise ValueError('Invalid quotas')
    if sum(quotas.values())*unit_cny>1024:
        raise ValueError('Overbudget quotas')
    legs={}; candidates=[]
    for group in bundle['sleeves']:
        sid=group['id']
        if sid not in quotas:
            continue
        legs[sid]=group['fixture_indices']; e=group['enumeration']
        for k,(p,v,pay) in enumerate(zip(e['probability'],e['expected_contribution'],e['estimated_payout'])):
            candidates.append((-p,-v,sid,k,pay))
    if set(legs)!=set(quotas):
        raise ValueError('Missing frozen group')
    candidates.sort()
    fixture=np.zeros(len(bundle['expanded_pool']['fixtures']),dtype=int)
    direction=np.zeros((len(fixture),3),dtype=int); counts=dict.fromkeys(quotas,0);selected=[]
    for _,_,sid,k,pay in candidates:
        if counts[sid]>=quotas[sid] or pay<floor:
            continue
        ix=legs[sid]; state=[(k//3**i)%3 for i in range(6,-1,-1)]
        if any(fixture[i]+unit_cny>fixture_cap or direction[i,s]+unit_cny>direction_cap for i,s in zip(ix,state)):
            continue
        selected.append((sid,k+1));counts[sid]+=1
        for i,s in zip(ix,state):
            fixture[i]+=unit_cny;direction[i,s]+=unit_cny
        if counts==quotas:
            break
    return selected


def finalize_payout_freeze(output, repository_root, python, rscript):
    """Verify every input/code/plan and independently replay all arms before seal.

    No target settlement access. Full grid mandatory, no partial completion or
    implicit reuse. Writes plans-frozen.json only after all replay checks pass.
    """
    out,root=Path(output),Path(repository_root)
    if (out/'plans-frozen.json').exists():
        raise ValueError('Already frozen')
    manifest_raw=(out/'manifest.json').read_bytes();m=json.loads(manifest_raw)
    if m['seal']!=stable_json_hash({k:v for k,v in m.items() if k!='seal'}):
        raise ValueError('Manifest changed')
    verify_implementation_closure(root,m['implementation'])
    for name,expected in m['r_implementation'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('R implementation changed')
    for name,expected in m['source_hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Source changed')
    before_metrics={str(out/'plans'/f"{job['issue']}.json.gz"):hashlib.sha256(
        (out/'plans'/f"{job['issue']}.json.gz").read_bytes()).hexdigest() for job in m['jobs']}
    # A separate R process rederives probabilities, prices, exposure and shared
    # world coverage from frozen IDs. It does not invoke the decision selector.
    env=dict(os.environ,PYTHONPATH=str(root.resolve()),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[]
        for worker in range(1,5):
            log=(out/f'metrics-{worker}.log').open('w')
            jobs.append((pool.submit(subprocess.run,[str(rscript),'--vanilla','scripts/freeze_joint_payout_chunk.R',
                str(out/'manifest.json'),str(out),str(python),str(worker),'4','verify'],cwd=root,
                env=env,stdout=log,stderr=subprocess.STDOUT,check=True),log))
        try:
            for job,_ in jobs:job.result()
        finally:
            for _,log in jobs:log.close()
    hashes={}; cuts={};cfg=m['config'];replayed=0
    for n,job in enumerate(m['jobs'],1):
        path=out/'plans'/f"{job['issue']}.json.gz";raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=before_metrics[str(path)]:
            raise ValueError('Plan changed during metric verification')
        plan=json.loads(gzip.decompress(raw))
        b=json.loads(read_verified_bundle_json(job['path'],job['sha256']))
        if (plan['issue']!=job['issue'] or plan['cutoffs']!=b['cutoffs']
                or plan['source_sha256']!=job['sha256'] or plan['historical_admission'] is not False):
            raise ValueError('Plan identity changed')
        native={s:Cutoff.decision_epoch(job['issue'],t) for s,t in b['cutoffs'].items()}
        expected_arms={f"P{floor}_{e['name']}" for floor in cfg['payout_floor_grid_cny'] for e in cfg['exposure_grid']}
        if set(plan['plans'])!=expected_arms:
            raise ValueError('Incomplete arm grid')
        for floor in cfg['payout_floor_grid_cny']:
            for e in cfg['exposure_grid']:
                arm=f"P{floor}_{e['name']}"; z=plan['plans'][arm]
                expected=replay_payout_selection(b,job['allocations'],native,floor,e['fixture_cny'],e['direction_cny'],cfg['unit_cny'])
                actual=[(t['sleeve_id'],t['ticket_col_idx']) for t in z['tickets']]
                if actual!=expected or z['stake']!=2*len(expected) or z['cash']!=1024-z['stake']:
                    raise ValueError(f"Independent ticket replay mismatch: {job['issue']} {arm}")
                replayed+=1
        hashes[str(path)]=hashlib.sha256(raw).hexdigest();cuts[job['issue']]=b['cutoffs']
        if n%20==0:print(f'Independent replay {n}/{len(m["jobs"])}',flush=True)
    verify_implementation_closure(root,m['implementation'])
    if (out/'manifest.json').read_bytes()!=manifest_raw or any(
            hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected
            for name,expected in m['r_implementation'].items()):
        raise ValueError('Code or manifest changed during replay')
    receipt=dict(manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        plan_hashes=hashes,cutoffs=cuts,independent_replays=replayed,historical_admission=False,
        maximum_source_availability=None,maximum_label_availability=None,partitions='NO_FIT_TUNE_CALIBRATION')
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (out/'plans-frozen.json').write_text(json.dumps(frozen,sort_keys=True))
    return frozen


def evaluate_payout_study(output, repository_root, audit_path, audit_sha256):
    """Settle the fully sealed study with authoritative single-ticket accounting.

    Verify frozen bytes, source/code identity and all seven fixture identities.
    Write issue rows plus COMMON/REMOVED/ADDED ticket contribution ledgers. Actual
    price is never supplied to selection. Refuse repeated evaluation.
    """
    out,root=Path(output),Path(repository_root)
    if (out/'evaluation-receipt.json').exists():
        raise ValueError('Evaluation exists')
    frozen_raw=(out/'plans-frozen.json').read_bytes();frozen=json.loads(frozen_raw)
    if frozen['seal']!=stable_json_hash(frozen['receipt']):
        raise ValueError('Frozen receipt changed')
    manifest_raw=(out/'manifest.json').read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest()!=frozen['receipt']['manifest_sha256']:
        raise ValueError('Manifest changed')
    m=json.loads(manifest_raw);verify_implementation_closure(root,m['implementation'])
    for name,expected in m['r_implementation'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('R implementation changed')
    raw=Path(audit_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=audit_sha256:
        raise ValueError('Settlement changed')
    audit=pd.read_csv(io.BytesIO(raw),dtype={'issue':str,'provider_id':str})
    rows=[];contributions=[];group_rows=[]
    for n,job in enumerate(m['jobs'],1):
        issue=job['issue'];path=out/'plans'/f'{issue}.json.gz';raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=frozen['receipt']['plan_hashes'][str(path)]:
            raise ValueError('Frozen plan changed')
        allplans=json.loads(gzip.decompress(raw))
        b=json.loads(read_verified_bundle_json(job['path'],job['sha256']))
        fixtures=b['expanded_pool']['fixtures'];sleeves={g['id']:g for g in b['sleeves']}
        issue_audit=audit[audit.issue==issue]
        baseline={(t['sleeve_id'],t['ticket_col_idx']):t for t in allplans['plans']['P0_OPEN']['tickets']}
        aidx=issue_audit.set_index('slot'); labels={}
        for sid in {r['sleeve_id'] for r in job['allocations']}:
            legs=sleeves[sid]['fixture_indices'];codes=[];sp=[]
            for i in legs:
                fixture=fixtures[i];r=aidx.loc[fixture['slot']]
                if str(r.provider_id)!=fixture['provider_id'] or r.handicap!=fixture['handicap']:
                    raise ValueError('Fixture identity mismatch')
                codes.append('WDL'.index(r.actual_direction));sp.append(float(r.spf_sp))
            labels[sid]=(sum(code*3**power for code,power in zip(codes,range(6,-1,-1)))+1,
                         m['config']['unit_cny']*m['config']['payout_factor']*float(np.prod(sp)))
        for arm,z in allplans['plans'].items():
            selected={(t['sleeve_id'],t['ticket_col_idx']):t for t in z['tickets']}
            if len(selected)!=len(z['tickets']):raise ValueError('Duplicate ticket')
            ix=[];outcomes=[]
            for sid,k in selected:
                ix.append(sleeves[sid]['fixture_indices'])
                outcomes.append([((k-1)//3**power)%3 for power in range(6,-1,-1)])
            packed=dict(issue=issue,budget_cny=1024,unit_cny=2,payout_factor=.65,
                        fixture_indices=ix,outcomes=outcomes,groups=len(ix),fixtures=fixtures,
                        stake=z['stake'],cash_cny=z['cash'])
            packed['seal']=stable_json_hash(packed)
            settled=settle_single_tickets(packed,issue_audit)
            if settled['status'] not in ('COMPLETE','NO_BET'):
                raise ValueError(f'Unresolved settlement {issue} {arm}')
            contribution_gross=0
            for category,keys,source in [('COMMON',selected.keys()&baseline.keys(),selected),
                    ('ADDED',selected.keys()-baseline.keys(),selected),
                    ('REMOVED',baseline.keys()-selected.keys(),baseline)]:
                gross=sum(labels[sid][1] for sid,k in keys if k==labels[sid][0])
                if category!='REMOVED':contribution_gross+=gross
                contributions.append(dict(issue=issue,policy=arm,category=category,tickets=len(keys),
                    stake=2*len(keys),gross=gross,net=gross-2*len(keys),
                    expected_gross=sum(source[key]['expected_gross_contribution'] for key in keys),
                    probability_mass_sum=sum(source[key]['prob'] for key in keys)))
            if not np.isclose(contribution_gross,settled['gross'],atol=1e-7,rtol=1e-12):
                raise ValueError('Ticket contribution settlement mismatch')
            for group in z['groups']:
                sid=group['sleeve_id'];won=(sid,labels[sid][0]) in selected
                group_rows.append(dict(**group,policy=arm,hit=int(won),gross=labels[sid][1] if won else 0))
            rows.append(dict(issue=issue,policy=arm,stake=settled['stake'],gross=settled['gross'],
                net=settled['net'],hits=settled['hits'],cash_cny=settled['cash'],budget_cny=1024,
                model='FROZEN_JOINT',status=settled['status'],union_coverage=z['union_coverage'],
                union_mc_se=z['union_mc_se'],expected_gross=z['expected_gross'],
                max_fixture_exposure=z['max_fixture_exposure'],max_direction_exposure=z['max_direction_exposure']))
        if n%40==0:print(f'Settled {n}/{len(m["jobs"])}',flush=True)
    outputs={}
    for name,table in [('rows',rows),('contributions',contributions),('groups',group_rows)]:
        path=out/f'{name}.csv';pd.DataFrame(table).to_csv(path,index=False)
        outputs[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=dict(freeze_sha256=hashlib.sha256(frozen_raw).hexdigest(),audit_sha256=audit_sha256,
                 audit_path=str(audit_path),files=outputs,historical_admission=False)
    (out/'evaluation-receipt.json').write_text(json.dumps(receipt,sort_keys=True))
    return receipt
