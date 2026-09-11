"""Fixed exposed N7 anchor/consensus/one-converter experiment; no fitting."""
import copy
import itertools
from collections import Counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from src.fundamentals_n7_baseline import rank_double_candidates, n7_baseline_plan
from src.temporal_learning.core import stable_json_hash


def consensus_component(frame, roles, *, cutoffs, complement, unit_cny, payout_factor, seed):
    """One settled-API-compatible N7: 2 agreed singles, 4 agreed doubles, 1 converter.

    roles maps all seven slots to A/D/C (counts 2/4/1). Complement changes only
    C to the excluded baseline direction. Prices are not read. Inputs are not
    mutated. Complete Cartesian unit tickets cost 64 or 32 CNY respectively.
    Explicit native Cutoffs and fixed 2 CNY/.65 constants delegated upstream.
    """
    rank_double_candidates(frame, cutoffs=cutoffs)
    if (len(frame) != 7 or set(roles) != set(map(int, frame.slot))
            or Counter(roles.values()) != Counter(A=2, D=4, C=1)
            or type(complement) is not bool):
        raise ValueError("Exact seven-fixture role assignment required")
    part = n7_baseline_plan(
        frame, cutoffs=cutoffs, selector="COVERAGE", shape="C0E0", funding="UNIT",
        max_groups=6, unit_cny=unit_cny, group_budget_cny=432,
        payout_factor=payout_factor, allocation_seed=seed)
    part.pop("seal")
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
                  sum(r["p_" + "WDL"[j]] for j in p[:2])]
        objective[i] = -np.log(np.maximum(masses, 1e-300)) + 1e-10 * (i * 3 + np.arange(3))
    skeletons, ledger = [], []
    counts = Counter()
    disjoint = True
    while len(skeletons) < budget_cny // 64:
        matrix = [np.tile(np.eye(3)[j], n) for j in range(3)]
        lower, upper = [2, 4, 1], [2, 4, 1]
        matrix.extend(np.eye(n).repeat(3, axis=1))
        lower += [0] * n
        upper += [1] * n
        for prior in skeletons:
            matrix.append(np.repeat([int(s in prior) for s in slots], 3))
            lower.append(0)
            upper.append(skeleton_pair_overlap)
        allowed = eligibility * np.array(
            [counts[s] < (1 if disjoint else skeleton_max_uses) for s in slots])[:, None]
        solved = milp(
            objective.ravel(), integrality=np.ones(n * 3),
            bounds=Bounds(np.zeros(n * 3), allowed.ravel()),
            constraints=LinearConstraint(np.asarray(matrix), lower, upper),
            options=dict(time_limit=30, mip_rel_gap=0))
        ledger.append(dict(disjoint=disjoint, status=int(solved.status)))
        if solved.status == 2:
            if disjoint:
                disjoint = False
                continue
            break
        if solved.status != 0:
            raise RuntimeError("Solver did not prove optimum/infeasibility: " + str(solved.message))
        assignment = solved.x.reshape(n, 3) > .5
        rolemap = {slots[i]: "ADC"[j] for i, j in zip(*np.where(assignment))}
        if (Counter(rolemap.values()) != Counter(A=2, D=4, C=1) or len(rolemap) != 7 or
                np.any(assignment > allowed) or
                any(len(set(rolemap) & set(g)) > skeleton_pair_overlap for g in skeletons)):
            raise ValueError("Invalid solver role assignment")
        skeletons.append(rolemap)
        counts.update(rolemap.keys())
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
