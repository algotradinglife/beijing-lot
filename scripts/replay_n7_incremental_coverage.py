"""Frozen 100-issue incremental-coverage comparison on existing candidates."""
import argparse, gzip, hashlib, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
from src.n7_incremental_coverage import incremental_coverage_plans
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff, verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', required=True)
    args = cli.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'plans').mkdir()
    origin = Path('data/derived/fundamentals_417/n7-probability-gate-v2')
    raw = (origin / 'plans-frozen.json').read_bytes()
    frozen = json.loads(raw)
    r = frozen['receipt']
    if not stable_json_hash(r) == frozen['seal']:
        raise ValueError("Integrity contract failed: stable_json_hash(r) == frozen['seal']")
    verify_implementation_closure(Path.cwd(), r['implementation'])
    sources = {**r['source_hashes'], **r['pool_hashes'], str(origin / 'plans-frozen.json'): hashlib.sha256(raw).hexdigest()}
    for path, digest in sources.items():
        if not hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest:
            raise ValueError('Integrity contract failed: hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest')
    implementation = implementation_closure(Path.cwd(), ['scripts.replay_n7_incremental_coverage'], distributions=['numpy', 'pandas', 'scipy'])
    seeds = [41901, 41902, 41903]
    thresholds = [c / 10000 for c in r['counts']]
    hashes = {}
    jobs = {}
    with ProcessPoolExecutor(max_workers=4) as executor:
        for issue in r['issues']:
            path = origin / 'pools' / f'{issue}.json.gz'
            raw = path.read_bytes()
            if not hashlib.sha256(raw).hexdigest() == sources[str(path)]:
                raise ValueError('Integrity contract failed: hashlib.sha256(raw).hexdigest() == sources[str(path)]')
            pool = json.loads(gzip.decompress(raw))
            cuts = {s: Cutoff.decision_epoch(issue, t) for s, t in pool['cutoffs'].items()}
            for seed in seeds:
                jobs[executor.submit(incremental_coverage_plans, pool, cutoffs=cuts, seed=seed, training_worlds=20000, evaluation_worlds=50000, min_probabilities=thresholds, budget_cny=1024, unit_cny=2, payout_factor=0.65)] = (issue, seed)
        for ordinal, job in enumerate(as_completed(jobs), 1):
            issue, seed = jobs.pop(job)
            for p in job.result():
                count = round(p['parameters']['min_probability'] * 10000)
                ranking = p['parameters']['ranking']
                path = out / 'plans' / f'{issue}_{seed}_{count}_{ranking}.json.gz'
                raw = gzip.compress(json.dumps(p, sort_keys=True).encode(), mtime=0)
                path.write_bytes(raw)
                hashes[str(path)] = hashlib.sha256(raw).hexdigest()
            if ordinal % 30 == 0:
                print(f'Frozen {ordinal}/300 issue-seed runs', flush=True)
    verify_implementation_closure(Path.cwd(), implementation)
    receipt = dict(issues=r['issues'], seeds=seeds, counts=r['counts'], source_hashes=sources, plan_hashes=hashes, implementation=implementation, historical_admission=False, parameters=dict(training_worlds=20000, evaluation_worlds=50000, n=7, budget_cny=1024, unit_cny=2, payout_factor=0.65))
    freeze = dict(receipt=receipt, seal=stable_json_hash(receipt))
    (out / 'plans-frozen.json').write_text(json.dumps(freeze, sort_keys=True))
    print('All 7200 plans frozen before settlement', flush=True)
    er_raw = (origin / 'evaluation-receipt.json').read_bytes()
    prior_er = json.loads(er_raw)
    if not prior_er['freeze_sha256'] == sources[str(origin / 'plans-frozen.json')]:
        raise ValueError("Integrity contract failed: prior_er['freeze_sha256'] == sources[str(origin / 'plans-frozen.json')]")
    audit_raw = Path(prior_er['audit_path']).read_bytes()
    if not hashlib.sha256(audit_raw).hexdigest() == prior_er['audit_sha256']:
        raise ValueError("Integrity contract failed: hashlib.sha256(audit_raw).hexdigest() == prior_er['audit_sha256']")
    audit_path = out / 'audit-snapshot.json'
    audit_path.write_bytes(audit_raw)
    audit = pd.DataFrame(json.loads(audit_raw)['rows'])
    audit.issue = audit.issue.astype(str)
    rows = []
    for ordinal, issue in enumerate(r['issues'], 1):
        for seed in seeds:
            for count in r['counts']:
                for ranking in ('COVERAGE', 'PROB', 'EV'):
                    path = out / 'plans' / f'{issue}_{seed}_{count}_{ranking}.json.gz'
                    raw = path.read_bytes()
                    if not hashlib.sha256(raw).hexdigest() == hashes[str(path)]:
                        raise ValueError('Integrity contract failed: hashlib.sha256(raw).hexdigest() == hashes[str(path)]')
                    p = json.loads(gzip.decompress(raw))
                    z = settle_single_tickets(p, audit[audit.issue == issue])
                    if not z['status'] in ('COMPLETE', 'NO_BET'):
                        raise ValueError("Integrity contract failed: z['status'] in ('COMPLETE', 'NO_BET')")
                    rows.append(dict(issue=issue, model=f'C{count:03d}', policy=f'{ranking}_{seed}', ranking=ranking, seed=seed, count=count, stake=z['stake'], gross=z['gross'], net=z['net'], groups=z['groups'], hits=z['hits'], train_coverage=p['simulation']['training_hit_rate'], eval_coverage=p['simulation']['evaluation_hit_rate'], expected_net=p['expected_net'], max_reuse=p['max_reuse'], zero_gain_tickets=sum((v == 0 for v in p.get('marginal_training_counts', [])))))
        if ordinal % 10 == 0:
            print(f'Settled {ordinal}/100 issues', flush=True)
    verify_implementation_closure(Path.cwd(), implementation)
    raw = json.dumps(dict(rows=rows, issue_order=r['issues'], freeze_seal=freeze['seal'])).encode()
    (out / 'results.json').write_bytes(raw)
    (out / 'prior-evaluation-snapshot.json').write_bytes(er_raw)
    er = dict(freeze_sha256=hashlib.sha256((out / 'plans-frozen.json').read_bytes()).hexdigest(), result_sha256=hashlib.sha256(raw).hexdigest(), audit_path=str(audit_path), audit_sha256=hashlib.sha256(audit_raw).hexdigest(), prior_receipt_sha256=hashlib.sha256(er_raw).hexdigest())
    (out / 'evaluation-receipt.json').write_text(json.dumps(er))
    print('Completed 7200 plans', flush=True)
