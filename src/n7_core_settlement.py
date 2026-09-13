"""Settle explicitly nested core copies via the existing unit-ticket API.

No learning, fetching, database writes or alternative payout formula. The outer
seal binds all layers; only nested identical CORE tickets may repeat. Opportunity
layers are one-copy and disjoint. Returns both unique hits and paid hit units.
"""
import math

from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning.core import stable_json_hash


def settle_core_layers(plan, audit):
    """Validate the frozen layer contract and aggregate authoritative settlements.

    Audit semantics and missing-SP handling are delegated unchanged. Budget CNY,
    CNY2 paid units and one0.65 ticket factor are explicit. No-bet returns zero;
    pending returns remain unknown and cannot be treated as losing bets.
    """
    if (plan.get('seal') != stable_json_hash({k: v for k, v in plan.items() if k != 'seal'})
            or plan.get('schema') != 'CORE_COPY_LAYERS_V1'):
        raise ValueError('Invalid frozen core plan')
    budget = plan['budget_cny']
    if (isinstance(budget, bool) or not isinstance(budget, (int, float))
            or not math.isfinite(budget) or budget < 0 or budget % 2
            or (plan['unit_cny'], plan['payout_factor']) != (2, .65)):
        raise ValueError('Invalid core budget')
    results, previous, first, ordinal = [], {}, {}, {}
    first_groups, previous_groups = {}, {}
    for layer in plan['layers']:
        role, index = layer['role'], layer['copy_index']
        if (role not in ('CORE', 'OPPORTUNITY') or type(index) is not int
                or index != ordinal.get(role, 0) + 1
                or (role == 'OPPORTUNITY' and index != 1)):
            raise ValueError('Invalid copy order')
        for key in ('issue', 'fixtures', 'cutoffs', 'budget_cny', 'unit_cny', 'payout_factor'):
            if layer[key] != plan[key]:
                raise ValueError('Layer identity mismatch')
        # Delegate coordinate shape, uniqueness, audit and coefficient validation.
        child = {k: v for k, v in layer.items() if k != 'seal'}
        child['seal'] = stable_json_hash(child)
        result = settle_single_tickets(child, audit)
        tickets = {tuple(zip(i, d)) for i, d in zip(layer['fixture_indices'], layer['outcomes'])}
        if not tickets:
            raise ValueError('Empty layer')
        groups = {}
        for ticket in tickets:
            fixture_key = tuple(i for i, _ in ticket)
            groups.setdefault(fixture_key, set()).add(tuple(d for _, d in ticket))
        if index == 1:
            if any(set(groups) & other for other in first_groups.values()):
                raise ValueError('Core and opportunity sleeves overlap')
            first_groups[role] = set(groups)
            if any(tickets & other for other in first.values()):
                raise ValueError('Core and opportunity tickets overlap')
            first[role] = tickets
        elif not tickets <= previous[role]:
            raise ValueError('Copy layers must be nested')
        if index > 1 and any(key not in previous_groups[role] or
                             states != previous_groups[role][key] for key, states in groups.items()):
            raise ValueError('Copies must repeat whole purchased prefixes')
        previous_groups[role] = groups
        previous[role] = tickets
        ordinal[role] = index
        results.append((role, index, result))
    stake = sum(r['stake'] for _, _, r in results)
    units = sum(r['groups'] for _, _, r in results)
    unique = sum(map(len, first.values()))
    if (stake != plan['stake'] or units != plan['groups'] or unique != plan['unique_tickets']
            or stake > budget or plan['cash_cny'] != budget - stake):
        raise ValueError('Core layer totals mismatch')
    base = dict(issue=plan['issue'], stake=stake, groups=units, unique_tickets=unique, cash=budget-stake)
    pending = [r['status'] for _, _, r in results if r['status'] not in ('COMPLETE', 'NO_BET')]
    if pending:
        return dict(base, status=pending[0], gross=None, net=None, hits=None, paid_hits=None, roi=None)
    gross = sum(r['gross'] for _, _, r in results)
    out = dict(base, status='COMPLETE' if units else 'NO_BET', gross=gross,
               net=gross-stake, hits=sum(r['hits'] for _, i, r in results if i == 1),
               paid_hits=sum(r['hits'] for _, _, r in results), roi=gross/stake-1 if stake else None)
    for role in ('CORE', 'OPPORTUNITY'):
        selected = [r for tag, _, r in results if tag == role]
        out[role.lower()+'_stake'] = sum(r['stake'] for r in selected)
        out[role.lower()+'_gross'] = sum(r['gross'] for r in selected)
    return out
