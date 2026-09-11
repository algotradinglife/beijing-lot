"""Fixed exposed N6/N7 anchor/consensus/one-converter experiment; no fitting."""
import copy
import itertools
from collections import Counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def consensus_component(frame, roles, *, cutoffs, complement, unit_cny, payout_factor, seed, group_size=7):
    """One N6/N7 component: two agreed singles, N-3 stable doubles, one C double.

    roles maps all slots to A/D/C (counts 2/N-3/1). Complement changes only
    C to the excluded baseline direction. Prices are not read. Inputs are not
    mutated. N7 primary/complement costs64/32 CNY; N6 costs32/16 CNY.
    Explicit native Cutoffs and fixed 2 CNY/.65 constants delegated upstream.
    """
    rank_double_candidates(frame, cutoffs=cutoffs)
    if (type(group_size) is not int or group_size not in (6,7) or len(frame) != group_size or set(roles) != set(map(int, frame.slot))
            or Counter(roles.values()) != Counter(A=2, D=group_size-3, C=1)
            or type(complement) is not bool):
        raise ValueError("Exact six/seven fixture role assignment required")
    if (unit_cny,payout_factor)!=(2,.65) or type(seed) is not int:
        raise ValueError("Explicit unit, payout and seed required")
    ranked,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    part=dict(issue=str(frame.issue.iloc[0]),selector="COVERAGE",funding="UNIT",
        groups=1,legs=[dict(r,group=1) for r in ranked.to_dict("records")],
        cutoffs=bound,n=group_size,unit_cny=unit_cny,payout_factor=payout_factor,
        allocation_seed=seed,historical_admission=False,
        input_sha256=stable_json_hash(frame.sort_values("slot").to_json(orient="records")),
        mode="EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET")
    for row in part["legs"]:
        p = sorted(range(3), key=lambda i: (-row["p_" + "WDL"[i]], i))
        q = sorted(range(3), key=lambda i: (-row["q_" + "WDL"[i]], i))
        role = roles[row["slot"]]
        if role == "A" and p[0] != q[0]:
            raise ValueError("Anchor must share top direction")
        if role == "D" and set(p[:2]) != set(q[:2]):
            raise ValueError("Stable double must share Top2 set")
        if role == "C" and set(p[:2]) == set(q[:2]):
            raise ValueError("Converter requires distinct Top2 sets")
        selected = p[:1] if role == "A" else p[2:] if role == "C" and complement else p[:2]
        row.update(role=role, support="".join("310"[j] for j in range(3) if j in selected))
    part["legs"].sort(key=lambda r: r["slot"])
    part["tickets"] = [
        dict(group=1, code="".join(c), units=1)
        for c in itertools.product(*(r["support"] for r in part["legs"]))]
    part.update(shape="CONSENSUS_COMPLEMENT" if complement else "CONSENSUS_PRIMARY",
                stake=unit_cny * len(part["tickets"]), complement=complement)
    return dict(**part, seal=stable_json_hash(part))


def consensus_candidates(frame, *, cutoffs, minimum_anchor_market, converter_market, anchor_score='TOP1'):
    """Validated A/D/C eligibility and fixed score objectives; no fit or labels.

    anchor_score TOP1 or RETENTION changes A objective only; RETENTION is
    q(pTop1)/q(pTop2 set), the market-assessed mass retained by compression.
    Pure arrays in slot order; explicit per-fixture Cutoffs are validated by the
    authoritative rank API. C uses baseline Top2 for primary groups, market
    probability of excluded baseline outcome for independent converter groups.
    """
    if anchor_score not in ('TOP1','RETENTION') or type(converter_market) is not bool or not 0 < minimum_anchor_market < 1:
        raise ValueError("Explicit converter mode and anchor threshold required")
    ranked, bound = rank_double_candidates(frame, cutoffs=cutoffs)
    ranked = ranked.sort_values("slot")
    rows = ranked.to_dict("records")
    slots = [int(r["slot"]) for r in rows]
    n = len(rows)
    eligibility = np.zeros((n, 3))
    objective = np.zeros((n, 3))
    for i, r in enumerate(rows):
        p = sorted(range(3), key=lambda j: (-r["p_" + "WDL"[j]], j))
        q = sorted(range(3), key=lambda j: (-r["q_" + "WDL"[j]], j))
        same = set(p[:2]) == set(q[:2])
        eligibility[i] = [p[0] == q[0] and r["q_" + "WDL"[q[0]]] >= minimum_anchor_market,
                          same, not same]
        masses = [r["q_" + "WDL"[q[0]]],
                  sum(r["q_" + "WDL"[j]] for j in q[:2]),
                  (r["q_" + "WDL"[p[2]]] if converter_market else sum(r["p_" + "WDL"[j]] for j in p[:2]))]
        if anchor_score=='RETENTION':
            masses[0] /= sum(r["q_"+"WDL"[j]] for j in p[:2])
        objective[i] = -np.log(np.maximum(masses, 1e-300)) + 1e-10 * (i * 3 + np.arange(3))
    return ranked, bound, eligibility, objective


def next_consensus_roles(frame, previous, *, cutoffs, minimum_anchor_market,
                         converter_market, max_uses, max_overlap, disjoint, anchor_max_uses=None, group_size=7, anchor_score='TOP1'):
    """One optimal 2A/(N-3)D/1C group for explicit N6/N7; no learning.

    Caps count actual supplied groups; explicit caller policy applies equally
    to original and converter groups. Returned role map is empty ONLY when
    infeasible. Solver timeout/failure raises. Parent plan binds full ledger.
    """
    if (type(max_uses) is not int or max_uses < 1 or type(max_overlap) is not int
            or type(group_size) is not int or group_size not in (6,7) or not 0 <= max_overlap < group_size or type(disjoint) is not bool):
        raise ValueError("Valid explicit reuse policy required")
    ranked, _, eligibility, objective = consensus_candidates(
        frame, cutoffs=cutoffs, minimum_anchor_market=minimum_anchor_market,
        converter_market=converter_market,anchor_score=anchor_score)
    slots=list(map(int,ranked.slot)); n=len(slots)
    if any(len(g)!=group_size or len(set(g))!=group_size or not set(g)<=set(slots) for g in previous):
        raise ValueError("Previous groups must match group size with distinct known fixtures")
    anchor_counts=Counter()
    if anchor_max_uses is not None:
        if type(anchor_max_uses) is not int or not 1<=anchor_max_uses<=max_uses:
            raise ValueError("Valid explicit anchor cap required")
        if any(not isinstance(g,dict) or Counter(g.values())!=Counter(A=2,D=group_size-3,C=1) for g in previous):
            raise ValueError("Anchor caps require previous role maps")
        anchor_counts=Counter(s for g in previous for s,role in g.items() if role=="A")
        if any(v>anchor_max_uses for v in anchor_counts.values()):
            raise ValueError("Previous anchors violate cap")
    counts=Counter(s for g in previous for s in g)
    if (any(v>max_uses for v in counts.values()) or
            any(len(set(a)&set(b))>max_overlap for a,b in itertools.combinations(previous,2))):
        raise ValueError("Previous groups violate requested caps")
    matrix = [np.tile(np.eye(3)[j], n) for j in range(3)]
    lower, upper = [2, group_size-3, 1], [2, group_size-3, 1]
    matrix.extend(np.eye(n).repeat(3, axis=1))
    lower += [0] * n
    upper += [1] * n
    for prior in previous:
        matrix.append(np.repeat([int(s in prior) for s in slots], 3))
        lower.append(0)
        upper.append(max_overlap)
    allowed = eligibility * np.array(
        [counts[s] < (1 if disjoint else max_uses) for s in slots])[:, None]
    if anchor_max_uses is not None:
        allowed[:,0]*=np.array([anchor_counts[s]<anchor_max_uses for s in slots])
    solved = milp(
        objective.ravel(), integrality=np.ones(n * 3),
        bounds=Bounds(np.zeros(n * 3), allowed.ravel()),
        constraints=LinearConstraint(np.asarray(matrix), lower, upper),
        options=dict(time_limit=30, mip_rel_gap=0))
    ledger=dict(disjoint=disjoint,status=int(solved.status))
    if solved.status==2:
        return {},ledger
    if solved.status!=0:
        raise RuntimeError("Solver did not prove optimum/infeasibility: "+str(solved.message))
    assignment=solved.x.reshape(n,3)>.5
    roles={slots[i]:"ADC"[j] for i,j in zip(*np.where(assignment))}
    if (Counter(roles.values())!=Counter(A=2,D=group_size-3,C=1) or len(roles)!=group_size or
            np.any(assignment>allowed) or
            any(len(set(roles)&set(g))>max_overlap for g in previous)):
        raise ValueError("Invalid solver role assignment")
    return roles,ledger


def consensus_portfolios(frame, *, cutoffs, budget_cny, minimum_anchor_market,
                         skeleton_max_uses, skeleton_pair_overlap, unit_cny,
                         payout_factor, seed):
    """Freeze three fixed-budget exposed scenarios with identical skeleton prefix.

    MILP assigns 2 A, 4 D, 1 C. A: agreed Top1 with market mass >= explicit
    minimum; D: agreed Top2; C: differing Top2. Rank A/D by market support mass,
    C by baseline Top2 mass. Maximize joint log support, slot tie penalty1e-10;
    fixed greedy skeleton sequence, not globally optimal portfolio selection.
    Prefer entirely unused fixtures; once infeasible allow explicit skeleton
    reuse/overlap. Solver must prove optimal/infeasible within30s.

    PRIMARY_FILL buys64-CNY originals; COMPLEMENT buys96-CNY pairs then an
    affordable64-CNY original; MATCHED_PRIMARY buys the identical originals as
    COMPLEMENT but holds its complement spend. No refit/labels/SP/IO.
    Pair components share all7 fixtures intentionally; caps apply across
    skeletons (actual holdings <= twice skeleton cap). Return sealed envelopes,
    role pool counts, solver ledger, and binding to prediction inputs/cutoffs.
    """
    ranked, bound = rank_double_candidates(frame, cutoffs=cutoffs)
    if (type(budget_cny) is not int or budget_cny < 0 or
            not 0 < minimum_anchor_market < 1 or
            type(skeleton_max_uses) is not int or skeleton_max_uses < 1 or
            type(skeleton_pair_overlap) is not int or not 0 <= skeleton_pair_overlap < 7 or
            (unit_cny, payout_factor) != (2, .65)):
        raise ValueError("Explicit valid diagnostic parameters required")
    ranked, bound, eligibility, _ = consensus_candidates(
        frame, cutoffs=cutoffs, minimum_anchor_market=minimum_anchor_market,
        converter_market=False)
    skeletons, ledger = [], []
    disjoint = True
    while len(skeletons) < budget_cny // 64:
        roles, step = next_consensus_roles(
            frame, skeletons, cutoffs=cutoffs, minimum_anchor_market=minimum_anchor_market,
            converter_market=False, max_uses=skeleton_max_uses,
            max_overlap=skeleton_pair_overlap, disjoint=disjoint)
        ledger.append(step)
        if not roles:
            if disjoint:
                disjoint=False
                continue
            break
        skeletons.append(roles)
    originals, alternatives = [], []
    for roles in skeletons:
        subset = frame[frame.slot.isin(roles)]
        cuts = {str(s): cutoffs[str(s)] for s in roles}
        originals.append(consensus_component(subset, roles, cutoffs=cuts, complement=False,
                         unit_cny=unit_cny, payout_factor=payout_factor, seed=seed))
        alternatives.append(consensus_component(subset, roles, cutoffs=cuts, complement=True,
                            unit_cny=unit_cny, payout_factor=payout_factor, seed=seed))
    paired, matched = [], []
    spend = 0
    for a, b in zip(originals, alternatives):
        if spend + 96 <= budget_cny:
            paired.extend([a, b])
            matched.append(a)
            spend += 96
        elif spend + 64 <= budget_cny:
            paired.append(a)
            matched.append(a)
            spend += 64
        else:
            break
    plans = {}
    for policy, parts in [("PRIMARY_FILL", originals), ("COMPLEMENT", paired),
                          ("MATCHED_PRIMARY", matched)]:
        stake = sum(p["stake"] for p in parts)
        envelope = dict(issue=str(frame.issue.iloc[0]), strategy=policy, funding="UNIT",
                        components=copy.deepcopy(parts), stake=stake, budget=budget_cny,
                        cash_cny=budget_cny-stake, model_any_hit=None, cutoffs=bound,
                        historical_admission=False,
                        mode="EXPOSED_FIXED_COMPOSITION_NOT_SIMULTANEOUS_TICKET",
                        input_sha256=stable_json_hash(frame.sort_values("slot").to_json(orient="records")))
        plans[policy] = dict(**envelope, seal=stable_json_hash(envelope))
    result = dict(plans=plans, skeletons=[{str(k): v for k, v in g.items()} for g in skeletons],
                  pool_counts=dict(zip("ADC", map(int, eligibility.sum(axis=0)))), solver_ledger=ledger,
                  parameters=dict(minimum_anchor_market=minimum_anchor_market,
                                  skeleton_max_uses=skeleton_max_uses,
                                  skeleton_pair_overlap=skeleton_pair_overlap,
                                  unit_cny=unit_cny, payout_factor=payout_factor,
                                  budget_cny=budget_cny, seed=seed))
    return dict(**result, seal=stable_json_hash(result))

def independent_consensus_portfolio(frame, *, cutoffs, conversion_budget_fraction,
                                    budget_cny, minimum_anchor_market, max_uses,
                                    max_pair_overlap, unit_cny, payout_factor, seed,
                                    anchor_max_uses=None, group_size=7, anchor_score='TOP1'):
    """Assemble N6/N7 components under one shared exposure ledger.

    group_size is 6 or 7; primary price is 32 or 64 CNY respectively.
    anchor_score TOP1 uses market favorite mass; RETENTION divides it by
    market mass on the baseline Top2 being compressed. Eligibility unchanged.
    The latter measures retained support, not whole-ticket hit probability.

    Conversion budget fraction is explicit (0/.25/.5/.75/1), never learned.
    Select type with lowest spent/target ratio, primary first on ties. Converter
    quota rounds down to complement group cost; primary receives remaining budget. Each group
    is reassembled: 2 agreed high-q anchors, N-3 agreed doubles, 1 different-Top2
    converter. Primary C ranks p-Top2; converter C ranks q of omitted p outcome.
    First use disjoint fixtures, then globally enforce actual-group U/P caps.
    Optional anchor_max_uses limits A-role holdings only; a used anchor may be
    a D double in another group. Available only with zero converter fraction,
    so each group's exact two singles are its two A roles. None adds no cap.
    No paired-clone exemption, no transferred quotas, no fractional tickets.
    Insufficient eligible groups or unspendable remainder stays cash. All
    candidates use prediction-only frames and explicit shared Cutoffs.
    Returns sealed settlement-compatible envelope, components and decision
    ledger. No fits, labels, cache, I/O, or prospective-admission claim.
    """
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    if (anchor_score not in ('TOP1','RETENTION') or conversion_budget_fraction not in (0,.25,.5,.75,1) or
            type(budget_cny) is not int or budget_cny<0 or
            not 0<minimum_anchor_market<1 or
            type(max_uses) is not int or max_uses<1 or
            type(max_pair_overlap) is not int or type(group_size) is not int or group_size not in (6,7) or not 0<=max_pair_overlap<group_size or
            type(seed) is not int or (unit_cny,payout_factor)!=(2,.65)):
        raise ValueError("Valid explicit fixed allocation policy required")
    if anchor_max_uses is not None and (type(anchor_max_uses) is not int or
            not 1<=anchor_max_uses<=max_uses or conversion_budget_fraction!=0):
        raise ValueError("Anchor cap requires non-converting groups and valid cap")
    primary_cost=unit_cny*2**(group_size-2)
    converter_cost=primary_cost//2
    converter_quota=int(budget_cny*conversion_budget_fraction)//converter_cost*converter_cost
    quota={False:budget_cny-converter_quota,True:converter_quota}
    spent={False:0,True:0};cost={False:primary_cost,True:converter_cost}
    roles_list=[];parts=[];ledger=[];disjoint=True
    while True:
        available=[k for k in (False,True) if spent[k]+cost[k]<=quota[k]]
        if not available:break
        kind=min(available,key=lambda k:(spent[k]/quota[k],k))
        roles,step=next_consensus_roles(
            frame,roles_list,cutoffs=cutoffs,minimum_anchor_market=minimum_anchor_market,
            converter_market=kind,max_uses=max_uses,max_overlap=max_pair_overlap,disjoint=disjoint,
            anchor_max_uses=anchor_max_uses,group_size=group_size,anchor_score=anchor_score)
        ledger.append(dict(step,converter=kind,spent_before=sum(spent.values())))
        if not roles:
            if disjoint:
                disjoint=False
                continue
            # Feasibility sets are identical for both types; only objectives differ.
            break
        subset=frame[frame.slot.isin(roles)]
        cuts={str(s):cutoffs[str(s)] for s in roles}
        part=consensus_component(subset,roles,cutoffs=cuts,complement=kind,
                                 unit_cny=unit_cny,payout_factor=payout_factor,seed=seed,group_size=group_size)
        if part["stake"]!=cost[kind]:raise ValueError("Unexpected component cost")
        parts.append(part);roles_list.append(roles);spent[kind]+=cost[kind]
    stake=sum(p["stake"] for p in parts)
    envelope=dict(issue=str(frame.issue.iloc[0]),
        strategy=f"INDEPENDENT_C{int(conversion_budget_fraction*100):03}",
        funding="UNIT",components=parts,stake=stake,budget=budget_cny,
        cash_cny=budget_cny-stake,model_any_hit=None,cutoffs=bound,historical_admission=False,
        mode="EXPOSED_INDEPENDENT_CONSENSUS_NOT_SIMULTANEOUS",
        input_sha256=stable_json_hash(frame.sort_values("slot").to_json(orient="records")),
        allocation=dict(conversion_budget_fraction=conversion_budget_fraction,
                        primary_quota_cny=quota[False],converter_quota_cny=quota[True],
                        primary_spend_cny=spent[False],converter_spend_cny=spent[True]),
        parameters=dict(minimum_anchor_market=minimum_anchor_market,max_uses=max_uses,
                        max_pair_overlap=max_pair_overlap,unit_cny=unit_cny,
                        payout_factor=payout_factor,seed=seed,anchor_max_uses=anchor_max_uses,group_size=group_size,anchor_score=anchor_score),
        decision_ledger=ledger)
    return dict(**envelope,seal=stable_json_hash(envelope))
