"""Independent NumPy replay for R core prefixes, copy exposure and risk.

Fixed prediction diagnostics only. Shared study checker owns receipts/cutoffs;
this module never loads labels, fits history, or writes data.
"""
import math
import numpy as np

from src.n7_capital_check import _capital_close
from src.temporal_learning.core import stable_json_hash


def core_replay_surface(bundle, config, *, cutoffs):
    """Rebuild all candidate curves from frozen source probabilities/prices.

    Explicit cutoff map must match. Returns one source-keyed record per sleeve
    with canonical arrays and coverage-target opening depth; units are CNY.
    Source enumeration is verified independently before its exact tie order is
    reused. Invalid probabilities/identities fail closed. No learning or I/O.
    """
    if cutoffs != bundle['cutoffs'] or bundle['historical_admission'] is not False:
        raise ValueError('Core replay cutoff mismatch')
    canonical = np.indices((3,)*7).reshape(7, -1).T
    rows = {}
    fixtures = bundle['expanded_pool']['fixtures']
    for g in bundle['sleeves']:
        f = np.asarray(g['fixture_indices']); e = g['enumeration']
        p = np.array([[fixtures[i][f'p_{d}'] for d in 'WDL'] for i in f])
        q = np.array([[fixtures[i][f'q_{d}'] for d in 'WDL'] for i in f])
        probability = np.prod(p[np.arange(7), canonical], axis=1)
        payout = 1.3/np.prod(q[np.arange(7), canonical], axis=1)
        ep, ev = np.asarray(e['probability']), np.asarray(e['expected_contribution'])
        if (len(set(f)) != 7 or not np.array_equal(e['states'], canonical)
                or not np.isfinite(p).all() or not np.isfinite(q).all()
                or (p < 0).any() or (q <= 0).any()
                or not np.allclose(p.sum(axis=1), 1) or not np.allclose(q.sum(axis=1), 1)
                or not np.allclose(probability, ep, rtol=1e-10, atol=1e-14)
                or not np.allclose(probability*payout, ev, rtol=1e-10, atol=1e-10)):
            raise ValueError('Core source enumeration mismatch')
        rank = np.lexsort((np.arange(2187), -ev, -ep))
        mass = np.r_[0., np.cumsum(ep[rank])]
        value = np.r_[0., np.cumsum(ev[rank])]
        opening = int(np.searchsorted(mass, config['core_open_coverage']))
        positive = ep[ep > 0]
        rows[g['id']] = dict(f=f, rank=rank, mass=mass, value=value, p=probability,
                            payout=payout, opening=opening, entropy=-float(np.dot(positive, np.log(positive))),
                            expected_rank_cost=float(np.dot(ep[rank], 2*np.arange(1, 2188))))
    if len(rows) != len(bundle['sleeves']):
        raise ValueError('Duplicate core candidate')
    return rows


def check_core_plan(plan, worlds, config, source_bundle):
    """Replay full physical layers, union coverage and paid-unit model returns.

    Copies must repeat whole prefixes; distinct roles cannot own the same sleeve.
    The action ledger must open all affordable new cores before depth/copies.
    Returns checked counts; all failures raise ValueError without altering plans.
    """
    if (plan['seal'] != stable_json_hash({k: v for k, v in plan.items() if k != 'seal'})
            or plan['schema'] != 'CORE_COPY_LAYERS_V1' or plan['cutoffs'] != source_bundle['cutoffs']
            or plan['issue'] != source_bundle['issue'] or worlds['seed'] != plan['seed']
            or plan['historical_admission'] is not False):
        raise ValueError('Core plan seal/identity mismatch')
    policy = next((p for p in config['policies'] if p['name'] == plan['arm']), None)
    if policy != plan['policy'] or plan['budget_cny'] not in config['budgets']:
        raise ValueError('Core registered policy mismatch')
    surface = core_replay_surface(source_bundle, config, cutoffs=plan['cutoffs'])
    ranked = sorted(surface, key=lambda i: (-surface[i]['mass'][64], -surface[i]['value'][64], i))
    core = ranked[:policy['core_count']]
    # The frozen R issue runner builds one shared depth pool: configured depths
    # plus opening crossings for every registered core cohort in this issue.
    # Those extra crossings are legal depth choices for any held core group.
    shared_core_count = max(p['core_count'] for p in config['policies'])
    legal_depths = set(config['depths']) | {
        surface[i]['opening'] for i in ranked[:shared_core_count]}
    remaining = [i for i in ranked if i not in core]
    def_score = {i: (surface[i]['mass'][15], surface[i]['value'][15]-30) for i in remaining}
    if policy['opportunity_rule'] == 'VALUE':
        def_score = {i: tuple(reversed(pair)) for i, pair in def_score.items()}
    opp = sorted(remaining, key=lambda i: (-def_score[i][0], -def_score[i][1], i))[:int(policy['opportunity_cap_cny']//30)]
    held, roles, previous = {}, {}, {}
    units = 0
    for layer in plan['layers']:
        role, copy = layer['role'], layer['copy_index']
        if (role not in ('CORE', 'OPPORTUNITY') or copy != previous.get(role, 0)+1
                or copy > (policy['max_copies'] if role == 'CORE' else 1)
                or any(layer[k] != plan[k] for k in ('issue', 'cutoffs', 'fixtures', 'budget_cny', 'unit_cny', 'payout_factor'))):
            raise ValueError('Core layer identity/copy mismatch')
        ix, outcomes, seen = [], [], set()
        for key in layer['sleeve_keys']:
            sid, k = key['sleeve_id'], key['depth']; r = surface[sid]
            if sid in seen or sid not in (core if role == 'CORE' else opp):
                raise ValueError('Core role/candidate mismatch')
            seen.add(sid)
            if (key['fixture_indices'] != r['f'].tolist() or key['state_ids'] != r['rank'][:k].tolist()
                    or k < 1 or k > 2187):
                raise ValueError('Core exact prefix mismatch')
            if role == 'OPPORTUNITY' and k != 15:
                raise ValueError('Opportunity exceeds fixed prefix')
            if role == 'CORE' and (k < r['opening'] or
                    (policy['mode'] != 'DEPTH' and k != r['opening']) or
                    (policy['mode'] == 'DEPTH' and k not in legal_depths)):
                raise ValueError('Core opening/depth mismatch')
            if copy == 1:
                if sid in held: raise ValueError('Repeated first-layer sleeve')
                held[sid] = [k, 1]; roles[sid] = role
            else:
                if sid not in held or held[sid] != [k, copy-1]:
                    raise ValueError('Core copies are not nested full prefixes')
                held[sid][1] += 1
            canonical = np.indices((3,)*7).reshape(7, -1).T
            order = np.argsort(r['f'])
            ix.extend(np.tile(r['f'][order], (k, 1)).tolist())
            outcomes.extend(canonical[r['rank'][:k]][:, order].tolist())
            for field, expected in [('coverage', r['mass'][k]), ('stake', 2*k), ('expected_gross', r['value'][k])]:
                _capital_close(key[field], float(expected), field, absolute=1e-6)
        if ix != layer['fixture_indices'] or outcomes != layer['outcomes'] or layer['stake'] != 2*len(ix):
            raise ValueError('Core packed physical permutation mismatch')
        if layer['groups'] != len(ix) or layer['cash_cny'] != plan['budget_cny']-layer['stake']:
            raise ValueError('Core layer budget mismatch')
        units += len(ix); previous[role] = copy
    if set(i for i in held if roles[i] == 'OPPORTUNITY') != set(opp):
        raise ValueError('Missing fixed opportunity group')
    if (plan['stake'] != 2*units or plan['groups'] != units or plan['stake'] > plan['budget_cny']
            or plan['cash_cny'] != plan['budget_cny']-plan['stake']
            or plan['unique_tickets'] != sum(k for k, _ in held.values())):
        raise ValueError('Core parent budget/unique coverage mismatch')
    # The ledger independently enforces the owner opening-order constraint.
    allocation = {}; cash = plan['budget_cny']-30*len(opp)
    for step, action in enumerate(plan['allocation'], 1):
        unopened = [i for i in core if i not in allocation]
        affordable = [i for i in unopened if 2*surface[i]['opening'] <= cash]
        sid, k, m = action['sleeve_id'], action['depth'], action['copies']
        if sid not in core or action['step'] != step:
            raise ValueError('Core action identity mismatch')
        if action['phase'] == 'OPEN':
            if sid not in affordable or (k, m) != (surface[sid]['opening'], 1):
                raise ValueError('Illegal core opening')
        else:
            if affordable or sid not in allocation or action['phase'] != policy['mode']:
                raise ValueError('Core copied/deepened before affordable breadth')
            old_k, old_m = allocation[sid]
            if policy['mode'] == 'MULTIPLY' and (k != old_k or m != old_m+1):
                raise ValueError('Invalid incremental core copy')
            if policy['mode'] == 'DEPTH' and (m != 1 or k <= old_k):
                raise ValueError('Invalid core depth action')
        old_k, old_m = allocation.get(sid, (0, 0)); cost = 2*(k*m-old_k*old_m)
        if cost <= 0 or cost > cash or action['added_stake'] != cost or action['cash_before'] != cash:
            raise ValueError('Core action cash mismatch')
        if action['affordable_new_core_count'] != len(affordable) or action['unopened_core_count'] != len(unopened):
            raise ValueError('Core action eligibility ledger mismatch')
        allocation[sid] = [k, m]; cash -= cost
    if allocation != {i: state for i, state in held.items() if roles[i] == 'CORE'} or cash != plan['cash_cny']:
        raise ValueError('Core actions do not reconcile to paid layers')
    expected = sum(surface[i]['value'][k]*m for i, (k, m) in held.items())
    for kind in ('training', 'evaluation'):
        w = np.asarray(worlds[kind]); hits = np.zeros(len(w)); gross = np.zeros(len(w))
        if w.shape != (config[kind+'_worlds'], len(plan['fixtures'])) or w.dtype.kind not in 'iu':
            raise ValueError('Core shared-world shape mismatch')
        for i, (k, m) in held.items():
            r = surface[i]; state = w[:, r['f']]@(3**np.arange(6, -1, -1))
            won = np.isin(state, r['rank'][:k]); hits += won
            gross += won*r['payout'][state]*m
        net = gross-plan['stake']; win = net > 1e-8; loss = net < -1e-8
        gain = float(net[win].mean()) if win.any() else None
        decline = float(net[loss].mean()) if loss.any() else None
        metrics = dict(stake=plan['stake'], cash=cash, expected_gross=expected,
            expected_net=expected-plan['stake'], expected_roi=expected/plan['stake']-1 if units else None,
            any_hit=float((hits>0).mean()), at_least_two=float((hits>=2).mean()), zero_hit=float((hits==0).mean()),
            profit_probability=float(win.mean()), loss_probability=float(loss.mean()),
            zero_net_probability=float((~win & ~loss).mean()), conditional_gain=gain, conditional_loss=decline,
            payoff_ratio=gain/abs(decline) if gain is not None and decline is not None else None,
            simulated_expected_net=float(net.mean()))
        cover = [surface[i]['mass'][k] for i, (k, _) in held.items()]
        money = [2*k*m for k, m in held.values()]
        metrics.update(sleeves=len(held), distinct_fixture_count=len({int(f) for i in held for f in surface[i]['f']}),
            gain_support=int(win.sum()), loss_support=int(loss.sum()), simulation_worlds=len(w),
            payoff_support_status='BOTH_EVENTS_OBSERVED' if win.any() and loss.any() else 'INSUFFICIENT_CONDITIONAL_SUPPORT',
            coverage_mean=float(np.mean(cover)) if cover else None,
            coverage_weighted_mean=float(np.dot(cover, money)/plan['stake']) if units else None,
            coverage_median=float(np.median(cover)) if cover else None,
            coverage_min=float(min(cover)) if cover else None, coverage_max=float(max(cover)) if cover else None)
        for key, val in metrics.items():
            _capital_close(plan[kind][key], val, 'core.'+kind+'.'+key, absolute=1e-6)
    return dict(status='PASS', paid_units=units, unique_tickets=plan['unique_tickets'])


def check_core_result(result, source_bundle, config):
    """Check every registered issue/arm/seed and descriptive curve feature.

    Feature reconstruction does not use outcomes. A missing/duplicate plan or
    altered threshold-cost/entropy/value feature raises instead of being dropped.
    """
    if result['issue'] != source_bundle['issue'] or result['cutoffs'] != source_bundle['cutoffs']:
        raise ValueError('Core result identity mismatch')
    surface = core_replay_surface(source_bundle, config, cutoffs=result['cutoffs'])
    rows = result['features']
    if len(rows) != len(surface) or {r['sleeve_id'] for r in rows} != set(surface):
        raise ValueError('Core feature scope mismatch')
    for row in rows:
        r = surface[row['sleeve_id']]
        values = dict(entropy=r['entropy'], effective_states=math.exp(r['entropy']),
                      normalized_entropy=r['entropy']/math.log(2187),
                      expected_rank_cost_cny=r['expected_rank_cost'],
                      gain_64_to_128=r['mass'][128]-r['mass'][64])
        for k in (15, 32, 64, 128, 256):
            values.update({f'coverage_{k}': r['mass'][k], f'expected_net_{k}': r['value'][k]-2*k,
                           f'expected_roi_{k}': r['value'][k]/(2*k)-1})
        for target in config['feature_targets']:
            values[f'target_{target:g}_cost_cny'] = 2*int(np.searchsorted(r['mass'], target))
        for name, val in values.items():
            _capital_close(row[name], float(val), 'core.feature.'+name, absolute=1e-6)
    expected = {(s, p['name']) for s in config['seeds'] for p in config['policies']}
    actual = [(p['seed'], p['arm']) for p in result['plans']]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('Core plan grid incomplete or duplicated')
    return dict(status='PASS', features_checked=len(rows), plans=len(actual))


def check_core_settlement(plan, audit_rows, result_row):
    """Independently aggregate canonical winning states across genuine copy layers.

    Reuses #425's state-based settlement checker for each layer; the authoritative
    unit-ticket evaluator supplies its separately implemented comparison value.
    First layers count unique wins, every layer counts paid units. Actual SP is
    read only here, after the caller verifies a complete frozen study. CNY units;
    missing winning SP, identity conflict or any mismatch fails acceptance.
    """
    import pandas as pd
    from src.n7_single_ticket_sampling import settle_single_tickets
    from src.n7_core_settlement import settle_core_layers
    from src.n7_capital_check import check_capital_settlement

    # Structural validation and missing-label semantics stay authoritative.
    authoritative = settle_core_layers(plan, pd.DataFrame(audit_rows))
    if authoritative['status'] not in ('COMPLETE', 'NO_BET'):
        raise ValueError('Core settlement still pending')
    parts = []
    for layer in plan['layers']:
        child = {k: v for k, v in layer.items() if k != 'seal'}
        child['seal'] = stable_json_hash(child)
        unit_result = settle_single_tickets(child, pd.DataFrame(audit_rows))
        independent = check_capital_settlement(child, audit_rows, unit_result)
        parts.append((layer['role'], layer['copy_index'], independent))
    stake = sum(r['stake'] for _, _, r in parts)
    gross = sum(r['gross'] for _, _, r in parts)
    expected = dict(issue=plan['issue'],cash=plan['budget_cny']-stake,
        unique_tickets=sum(r['groups'] for _, index, r in parts if index == 1),
        status='COMPLETE' if stake else 'NO_BET',stake=stake,gross=gross,net=gross-stake,
        groups=sum(r['groups'] for _, _, r in parts),
        hits=sum(r['hits'] for _, index, r in parts if index == 1),
        paid_hits=sum(r['hits'] for _, _, r in parts),roi=gross/stake-1 if stake else None)
    for role in ('CORE', 'OPPORTUNITY'):
        for field in ('stake', 'gross'):
            expected[role.lower()+'_'+field] = sum(r[field] for tag, _, r in parts if tag == role)
    for field, value in expected.items():
        _capital_close(result_row[field], value, 'core.settlement.'+field, absolute=1e-6)
        _capital_close(authoritative[field], value, 'core.authoritative.'+field, absolute=1e-6)
    return expected
