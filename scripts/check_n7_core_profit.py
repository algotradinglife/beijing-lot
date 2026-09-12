"""Independent frozen ticket, payout and held-out profit audit."""
import argparse, gzip, hashlib, json, math, csv
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
    tags=['PROB','PROFIT']+[f'{kind}_{frac}' for kind in ('FIXED','GAP','JOINT') for frac in (25,50,75)]
    expected = {(issue, seed, tag) for issue in r['issues'] for seed in r['seeds'] for tag in tags}
    keys = [(z['issue'], z['seed'], z['tag']) for z in result['rows']]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('Incomplete or duplicate issue/seed/gate/ranking grid')
    if not result['freeze_seal'] == frozen['seal']:
        raise ValueError("Integrity contract failed: result['freeze_seal'] == frozen['seal']")
    audit = json.loads(Path(er['audit_path']).read_text())['rows']
    lookup = {(str(x['issue']), int(x['slot']), str(x['provider_id'])): x for x in audit}
    if not len(lookup) == len(audit):
        raise ValueError('Integrity contract failed: len(lookup) == len(audit)')
    diagnostics = []
    checked_union = False
    controls = {}
    for row in result['rows']:
        issue = row['issue']
        seed = row['seed']
        count = 5
        tag = row['tag']
        ranking = row['ranking']
        p = json.loads(gzip.decompress((root / 'plans' / f'{issue}_{seed}_{tag}.json.gz').read_bytes()))
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
        if not (np.all(idx>=0) and np.all(idx<len(f)) and np.all(codes>=0) and np.all(codes<3)):
            raise ValueError('Invalid packed ticket bounds')
        if (row['groups']!=len(idx) or p['groups']!=len(idx) or p['issue']!=issue
            or p['parameters']['ranking']!=ranking or p['simulation']['seed']!=seed
            or row['fraction']!=p['parameters']['core_fraction'] or row['model']!='C005'
            or row['policy']!=f'{tag}_{seed}' or row['accepted']!=p['search'].get('accepted',0)):
            raise ValueError('Result identity/parameters disagree with frozen plan')
        for field,key in [('train_coverage','training_hit_rate'),('eval_coverage','evaluation_hit_rate'),
                          ('train_profit','training_profit_rate'),('eval_profit','evaluation_profit_rate')]:
            if row[field]!=p['simulation'][key]:
                raise ValueError('Result simulated rate differs from frozen plan: '+field)
        if (row['expected_net']!=p['expected_net'] or row['stress_low']!=p['simulation']['payout_stress'][0]['profit']
            or row['stress_high']!=p['simulation']['payout_stress'][2]['profit']):
            raise ValueError('Result expected payout/stress differs from frozen plan')
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
        prob_plan=json.loads(gzip.decompress((root/'plans'/f'{issue}_{seed}_PROB.json.gz').read_bytes()))
        prob_tickets={tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(prob_plan['fixture_indices'],prob_plan['outcomes'])}
        current=[tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(idx,codes)]
        prob_fixtures={c//3 for ticket in prob_tickets for c in ticket}
        current_fixtures=set(idx.ravel().tolist())
        uses=np.bincount(idx.ravel(),minlength=len(f))
        diagnostics.append(dict(issue=issue,seed=seed,tag=tag,
            shared_tickets_prob=len(set(current)&prob_tickets),
            different_tickets_prob=len(set(current)-prob_tickets),
            shared_fixtures_prob=len(current_fixtures&prob_fixtures),
            extra_fixtures_prob=len(current_fixtures-prob_fixtures),
            fixture_hhi=float(np.sum((uses/uses.sum())**2)) if uses.sum() else 0.,
            unique_winning_tickets=sum(bool(w) and t not in prob_tickets for w,t in zip(win,current)),
            unique_winning_gross=math.fsum(1.3*math.prod(sp[t]) for t,w,key in zip(idx,win,current) if w and key not in prob_tickets)))
        if ranking in ('PROB','PROFIT'):
            oldpath = Path('data/derived/fundamentals_417/n7-profit-periods-v1/plans') / f'{issue}_{seed}_5_{ranking}.json.gz'
            old = json.loads(gzip.decompress(oldpath.read_bytes()))
            if any(p[k] != old[k] for k in ('fixture_indices','outcomes','stake')):
                raise ValueError('Control holdings changed')
            if any(p['simulation'][k] != old['simulation'][k] for k in ('training_hit_rate','evaluation_hit_rate','training_profit_rate','evaluation_profit_rate')):
                raise ValueError('Control simulation changed')
        else:
            prob_plan=json.loads(gzip.decompress((root/'plans'/f'{issue}_{seed}_PROB.json.gz').read_bytes()))
            ordered=[tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(prob_plan['fixture_indices'],prob_plan['outcomes'])]
            core=ordered[:math.ceil(p['groups']*p['parameters']['core_fraction'])]
            tickets={tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(idx,codes)}
            if list(map(tuple,p['core_encoded_tickets']))!=core or not set(core)<=tickets or p['stake']!=prob_plan['stake']:
                raise ValueError('Probability core/fixed budget violated')
            if ranking=='JOINT':
                gap=json.loads(gzip.decompress((root/'plans'/f'{issue}_{seed}_GAP_{round(p["parameters"]["core_fraction"]*100)}.json.gz').read_bytes()))
                if p['simulation']['training_profit_rate']<gap['simulation']['training_profit_rate']:
                    raise ValueError('Joint search regressed')
        for key in ('training_hit_rate','evaluation_hit_rate','training_profit_rate','evaluation_profit_rate'):
            if not 0 <= p['simulation'][key] <= 1:
                raise ValueError('Invalid simulated probability')
        if ranking == 'JOINT' and (not checked_union) and len(idx):
            rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(2)[1])
            worlds = p['simulation']['evaluation_worlds']
            simulated = np.array([np.searchsorted(np.r_[triplet.cumsum()[:2], 1.0], rng.random(worlds), side='right') for triplet in prob])
            covered = np.zeros(worlds, dtype=bool)
            simulated_gross = np.zeros(worlds)
            for ii, dd in zip(idx, codes):
                winners = np.all(simulated[ii] == dd[:, None], axis=0)
                covered |= winners
                simulated_gross[winners] += 1.3 / np.prod(q[ii,dd])
            if not covered.mean() == p['simulation']['evaluation_hit_rate']:
                raise ValueError("Integrity contract failed: covered.mean() == p['simulation']['evaluation_hit_rate']")
            if np.mean(simulated_gross > p['stake']) != p['simulation']['evaluation_profit_rate']:
                raise ValueError('Independent profit simulation mismatch')
            for stress in p['simulation']['payout_stress']:
                if np.mean(simulated_gross*stress['scale'] > p['stake']) != stress['profit']:
                    raise ValueError('Payout stress mismatch')
            checked_union = True
    if not (len(result['rows']) == 3300 and checked_union):
        raise ValueError("Integrity contract failed: len(result['rows']) == 3300 and checked_union")
    with (root/'ticket-diagnostics.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(diagnostics[0]));writer.writeheader();writer.writerows(diagnostics)
    (root / 'independent-replay.json').write_text(json.dumps(dict(diagnostics_sha256=hashlib.sha256((root/'ticket-diagnostics.csv').read_bytes()).hexdigest(), checked=3300, freeze=frozen['seal'], result_sha256=er['result_sha256'], checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())))
    print('PASS: 3300 ticket/payout audits; direct held-out profit/union; original controls preserved')
