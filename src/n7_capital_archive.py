"""Build a portable descriptive report input after complete independent replay."""
from pathlib import Path
import gzip
import hashlib
import json

from src.n7_joint_check import check_prefix_study
from src.n7_capital_check import check_capital_plan, check_capital_result, check_capital_settlement
from src.temporal_learning import implementation_closure


def package_capital_report(study, destination, *, repository_root, example_issue):
    """Verify all plans/curves/results, then write one new hash-bound gzip archive.

    Reads actual settlement only from the completed evaluation snapshot. Replays
    it independently at sleeve-state level. The archive contains all issue-level
    results and allocation depths, plus one explicitly chosen full curve example.
    It does NOT replace the complete external freeze package. Refuses overwrite;
    failures before final write leave no successfully packaged report artifact.
    Paths, code root and illustrative issue are explicit; no fitting or network.
    """
    study, destination, root=Path(study).resolve(),Path(destination),Path(repository_root).resolve()
    if destination.exists():raise ValueError('Refusing to overwrite capital report archive')
    replay=check_prefix_study(study,repository_root=root,check_plan=check_capital_plan,check_result=check_capital_result)
    er_raw=(study/'evaluation-receipt.json').read_bytes();er=json.loads(er_raw)
    frozen_raw=(study/'plans-frozen.json').read_bytes();frozen=json.loads(frozen_raw)
    result_raw=(study/'results.json').read_bytes();audit_raw=(study/'audit-snapshot.json').read_bytes()
    for name,raw in [('freeze',frozen_raw),('result',result_raw),('audit',audit_raw)]:
        if hashlib.sha256(raw).hexdigest()!=er[f'{name}_sha256']:
            raise ValueError(f'Capital report {name} binding changed')
    payload=json.loads(result_raw)
    if payload['freeze_seal']!=frozen['seal'] or payload['historical_admission'] is not False:
        raise ValueError('Capital report freeze/admission mismatch')
    rows={(r['issue'],r['seed'],r['arm']):r for r in payload['rows'] if not r['reference']}
    if len(rows)!=len(frozen['receipt']['plan_hashes']) or len(rows)!=sum(not r['reference'] for r in payload['rows']):
        raise ValueError('Capital result grid mismatch')
    audit={}
    for row in json.loads(audit_raw)['rows']:audit.setdefault(str(row['issue']),[]).append(row)
    sleeves=[];solvers=[];count=0;seen=set()
    for path,digest in frozen['receipt']['plan_hashes'].items():
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Capital plan changed after replay')
        plan=json.loads(gzip.decompress(raw));key=(plan['issue'],plan['seed'],plan['arm'])
        if key in seen:raise ValueError('Duplicate capital plan key')
        seen.add(key)
        check_capital_settlement(plan,audit.get(plan['issue'],[]),rows[key]);count+=1
        solvers.append(dict(issue=plan['issue'],seed=plan['seed'],arm=plan['arm'],
            budget_cny=plan['budget_cny'],solver_status=plan['solver_status'],stake=plan['stake'],
            depth_configuration=';'.join(f"{s['sleeve_id']}:{s['depth']}" for s in
                sorted(plan['sleeve_keys'],key=lambda s:s['sleeve_id'])),**plan['solver']))
        for sleeve in plan['sleeve_keys']:
            sleeves.append(dict(issue=plan['issue'],seed=plan['seed'],arm=plan['arm'],budget_cny=plan['budget_cny'],
                model_id=plan['model_id'],sleeve_id=sleeve['sleeve_id'],depth=sleeve['depth'],
                coverage=sleeve['coverage'],stake=sleeve['stake'],expected_gross=sleeve['expected_gross'],
                fixture_indices=sleeve['fixture_indices']))
    if seen!=set(rows):raise ValueError('Unreplayed capital result')
    if example_issue not in frozen['receipt']['issues']:raise ValueError('Unknown curve example issue')
    examples=[p for p in frozen['receipt']['raw_hashes'] if Path(p).name==f'{example_issue}.json.gz']
    if len(examples)!=1:raise ValueError('Curve example identity mismatch')
    raw=Path(examples[0]).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=frozen['receipt']['raw_hashes'][examples[0]]:
        raise ValueError('Curve example changed')
    curves=json.loads(gzip.decompress(raw))['curves']
    body=dict(**payload,parameters=frozen['receipt']['parameters'],sleeves=sleeves,
        example_issue=example_issue,example_curves=curves,
        example_cutoffs=frozen['receipt']['cutoffs'][example_issue],solver_diagnostics=solvers,independent_replay=replay,
        settlement_replay=dict(plans_checked=count,status='PASS'),
        evaluation_receipt_sha256=hashlib.sha256(er_raw).hexdigest(),
        generator_implementation=implementation_closure(root,['src.n7_capital_archive','src.temporal_learning'],
            distributions=['numpy','pandas']))
    encoded=json.dumps(body,sort_keys=True,allow_nan=False,separators=(',',':'))
    wrapper=dict(schema='bj425_capital_report_v1',body=encoded,sha256=hashlib.sha256(encoded.encode()).hexdigest())
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as output:output.write(gzip.compress(json.dumps(wrapper).encode(),mtime=0))
    return dict(status='PASS',path=str(destination),sha256=wrapper['sha256'],plans=count,sleeve_rows=len(sleeves))
