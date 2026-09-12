"""Independent frozen ticket, payout and held-out union audit."""
import argparse, gzip, hashlib, json, math
from pathlib import Path
import numpy as np
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning import verify_implementation_closure
if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--study', required=True)
    args = cli.parse_args()
    root = Path(args.study)
    frozen = json.loads((root / 'plans-frozen.json').read_text())
    r = frozen['receipt']
    if not stable_json_hash(r) == frozen['seal']:
        raise ValueError("Integrity contract failed: stable_json_hash(r) == frozen['seal']")
    verify_implementation_closure(Path.cwd(), r['implementation'])
    for path, digest in {**r['source_hashes'], **r['plan_hashes']}.items():
        if not hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest:
            raise ValueError('Integrity contract failed: hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest')
    er = json.loads((root / 'evaluation-receipt.json').read_text())
    for path, digest in [(root / 'plans-frozen.json', er['freeze_sha256']), (root / 'results.json', er['result_sha256']), (Path(er['audit_path']), er['audit_sha256']), (root / 'prior-evaluation-snapshot.json', er['prior_receipt_sha256'])]:
        if not hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            raise ValueError('Integrity contract failed: hashlib.sha256(path.read_bytes()).hexdigest() == digest')
    result = json.loads((root / 'results.json').read_text())
    expected = {(issue, seed, count, ranking) for issue in r['issues'] for seed in r['seeds']
                for count in r['counts'] for ranking in ('COVERAGE', 'PROB', 'EV')}
    keys = [(z['issue'], z['seed'], z['count'], z['ranking']) for z in result['rows']]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('Incomplete or duplicate issue/seed/gate/ranking grid')
    if not result['freeze_seal'] == frozen['seal']:
        raise ValueError("Integrity contract failed: result['freeze_seal'] == frozen['seal']")
    audit = json.loads(Path(er['audit_path']).read_text())['rows']
    lookup = {(str(x['issue']), int(x['slot']), str(x['provider_id'])): x for x in audit}
    if not len(lookup) == len(audit):
        raise ValueError('Integrity contract failed: len(lookup) == len(audit)')
    checked_union = False
    controls = {}
    for row in result['rows']:
        issue = row['issue']
        seed = row['seed']
        count = row['count']
        ranking = row['ranking']
        p = json.loads(gzip.decompress((root / 'plans' / f'{issue}_{seed}_{count}_{ranking}.json.gz').read_bytes()))
        if not p['seal'] == stable_json_hash({k: v for k, v in p.items() if k != 'seal'}):
            raise ValueError("Integrity contract failed: p['seal'] == stable_json_hash({k: v for k, v in p.items() if k != 'seal'})")
        idx = np.array(p['fixture_indices'], dtype=int).reshape(-1, 7)
        codes = np.array(p['outcomes'], dtype=int).reshape(-1, 7)
        if not (idx.shape == codes.shape and np.all(np.diff(idx, axis=1) > 0)):
            raise ValueError('Integrity contract failed: idx.shape == codes.shape and np.all(np.diff(idx, axis=1) > 0)')
        if not len(set(zip(map(tuple, idx), map(tuple, codes)))) == len(idx):
            raise ValueError('Integrity contract failed: len(set(zip(map(tuple, idx), map(tuple, codes)))) == len(idx)')
        if not (p['stake'] == row['stake'] == 2 * len(idx) <= 1024 and p['cash_cny'] == 1024 - row['stake']):
            raise ValueError("Integrity contract failed: p['stake'] == row['stake'] == 2 * len(idx) <= 1024 and p['cash_cny'] == 1024 - row['stake']")
        f = p['fixtures']
        prob = np.array([[x[f'p_{d}'] for d in 'WDL'] for x in f])
        q = np.array([[x[f'q_{d}'] for d in 'WDL'] for x in f])
        if not np.all(np.prod(prob[idx, codes], axis=1) >= count / 10000):
            raise ValueError('Integrity contract failed: np.all(np.prod(prob[idx, codes], axis=1) >= count / 10000)')
        if ranking == 'EV':
            if not np.all(0.65 * np.prod(prob[idx, codes] / q[idx, codes], axis=1) > 1):
                raise ValueError('Integrity contract failed: np.all(0.65 * np.prod(prob[idx, codes] / q[idx, codes], axis=1) > 1)')
        actual = [lookup[str(x['issue']), int(x['slot']), str(x['provider_id'])] for x in f]
        outcome = np.array(['WDL'.index(x['actual_direction']) for x in actual])
        sp = np.array([x['spf_sp'] for x in actual])
        used = np.unique(idx)
        if not all((actual[i]['handicap'] == f[i]['handicap'] and 'spf:IDENTITY' not in actual[i]['status'] for i in used)):
            raise ValueError("Integrity contract failed: all((actual[i]['handicap'] == f[i]['handicap'] and 'spf:IDENTITY' not in actual[i]['status'] for i in used))")
        win = np.all(outcome[idx] == codes, axis=1)
        if not (np.isfinite(sp[idx[win]]).all() and (sp[idx[win]] > 0).all()):
            raise ValueError('Integrity contract failed: np.isfinite(sp[idx[win]]).all() and (sp[idx[win]] > 0).all()')
        gross = math.fsum((1.3 * math.prod(sp[t]) for t in idx[win]))
        if not (int(win.sum()) == row['hits'] and math.isclose(gross, row['gross'], abs_tol=1e-06)):
            raise ValueError("Integrity contract failed: int(win.sum()) == row['hits'] and math.isclose(gross, row['gross'], abs_tol=1e-06)")
        if not math.isclose(gross - row['stake'], row['net'], abs_tol=1e-06):
            raise ValueError("Integrity contract failed: math.isclose(gross - row['stake'], row['net'], abs_tol=1e-06)")
        if ranking != 'COVERAGE':
            key = (issue, count, ranking)
            ticket_key = (idx.tolist(), codes.tolist())
            if not (key not in controls or controls[key] == ticket_key):
                raise ValueError('Integrity contract failed: key not in controls or controls[key] == ticket_key')
            controls[key] = ticket_key
        if ranking == 'COVERAGE' and (not checked_union) and len(idx):
            rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(2)[1])
            worlds = p['simulation']['evaluation_worlds']
            simulated = np.array([np.searchsorted(np.r_[triplet.cumsum()[:2], 1.0], rng.random(worlds), side='right') for triplet in prob])
            covered = np.zeros(worlds, dtype=bool)
            for ii, dd in zip(idx, codes):
                covered |= np.all(simulated[ii] == dd[:, None], axis=0)
            if not covered.mean() == p['simulation']['evaluation_hit_rate']:
                raise ValueError("Integrity contract failed: covered.mean() == p['simulation']['evaluation_hit_rate']")
            checked_union = True
        if ranking == 'COVERAGE':
            if not sum(p['marginal_training_counts']) / p['simulation']['training_worlds'] == p['simulation']['training_hit_rate']:
                raise ValueError("Integrity contract failed: sum(p['marginal_training_counts']) / p['simulation']['training_worlds'] == p['simulation']['training_hit_rate']")
    if not (len(result['rows']) == 7200 and checked_union):
        raise ValueError("Integrity contract failed: len(result['rows']) == 7200 and checked_union")
    (root / 'independent-replay.json').write_text(json.dumps(dict(checked=7200, freeze=frozen['seal'], result_sha256=er['result_sha256'], checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())))
    print('PASS: 7200 ticket/payout audits; direct Boolean held-out union; controls invariant across seeds')
