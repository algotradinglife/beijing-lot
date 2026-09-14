"""Independent verification of fixed #455 local exchanges; no fitting or IO."""
from itertools import combinations
from math import fsum
import hashlib
import json
from pathlib import Path

import numpy as np
from src.n7_union_inputs import verify_union_binding


def verify_exchange_provenance(freeze, prior, repository_root):
    """Read-only verification of bound implementations and shared source clocks.

    Delegates all source/chronology/closure validation to n7_union_inputs;
    checks the domain receipt's R file hashes and exact cutoff-map agreement.
    """
    required = {"r/n7_capital_portfolio.R", "r/n7_core_opportunity.R",
                "r/n7_frozen_scenarios.R", "r/n7_group_exchange.R",
                "scripts/run_n7_group_exchanges.R", "src/n7_quality_replay.py"}
    if not required.issubset(freeze.get("implementation", {})):
        raise ValueError("incomplete exchange implementation binding")
    for receipt in (freeze, prior):
        if not receipt.get("implementation"):
            raise ValueError("missing implementation binding")
        for name, expected in receipt["implementation"].items():
            if hashlib.sha256((Path(repository_root) / name).read_bytes()).hexdigest() != expected:
                raise ValueError("bound implementation changed")
    if freeze["input_binding"] != prior["input_binding"]:
        raise ValueError("source binding differs")
    bound = json.loads(freeze["input_binding"])
    if not (freeze["cutoffs"] == prior["cutoffs"] == bound["cutoffs"]):
        raise ValueError("source-bound cutoff mismatch")
    if not verify_union_binding(freeze["input_binding"], prior["config"]["catalog"],
                                prior["config"]["rank_dir"], repository_root):
        raise ValueError("shared source verification failed")
    return True


def replay_group_exchange(snapshot, cutoff, initial, budget, max_add):
    """Return R one-based selected indices. Explicit frozen cutoff, CNY budget.

    Only strict integer scenario-coverage gains are accepted. Mandatory options
    stay selected; ties are net, spend, numeric group-ID lexicographic order.
    Invalid indices/cutoff/matrices/amounts fail with ValueError.
    """
    if (not cutoff or snapshot["cutoffs"] != cutoff
            or snapshot["train"]["cutoffs"] != cutoff or max_add not in (1, 2)
            or not np.isfinite(budget) or budget < 0 or budget % 2):
        raise ValueError("invalid exchange contract")
    opts = snapshot["options"]
    hits = np.asarray(snapshot["train"]["hits"])
    costs = np.array([o["stake"] for o in opts], dtype=float)
    expected = np.array([o["expected_gross"] for o in opts], dtype=float)
    ids = [o["sleeve_id"] for o in opts]
    if (hits.ndim != 2 or hits.shape[1] != len(opts) or not hits.shape[0]
            or not np.isin(hits, [0, 1]).all() or len(set(ids)) != len(ids)
            or not np.isfinite(costs).all() or (costs <= 0).any() or (costs % 2).any()
            or not np.isfinite(expected).all() or (expected < 0).any()
            or any(o["unit_copies"] != 1 for o in opts)):
        raise ValueError("invalid options or scenarios")
    opening = np.atleast_1d(snapshot["opening_options"]).tolist()
    mandatory = np.atleast_1d(snapshot["opportunity_options"]).tolist()
    for seq in (opening, mandatory, initial):
        if len(set(seq)) != len(seq) or any(j != int(j) or j < 1 or j > len(opts) for j in seq):
            raise ValueError("invalid indices")
    opening = [int(j)-1 for j in opening]
    mandatory = [int(j)-1 for j in mandatory]
    selected = [int(j)-1 for j in initial]
    if (not set(mandatory).issubset(selected)
            or not set(selected).issubset(set(opening) | set(mandatory))
            or costs[selected].sum() > budget):
        raise ValueError("invalid initial portfolio")
    while True:
        count = (hits[:, selected].sum(axis=1) > 0).sum()
        available = [j for j in opening if j not in selected]
        adds = [(j,) for j in available]
        if max_add == 2:
            adds.extend(combinations(available, 2))
        moves = []
        for remove in [None] + [j for j in selected if j not in mandatory]:
            kept = [j for j in selected if j != remove]
            for add in adds:
                candidate = kept + list(add)
                stake = costs[candidate].sum()
                if stake > budget:
                    continue
                covered = (hits[:, candidate].sum(axis=1) > 0).sum()
                if covered <= count:
                    continue
                net = fsum(float(expected[j]-costs[j]) for j in candidate)
                key = (-int(covered), -net, stake, tuple(sorted(ids[j] for j in candidate)))
                moves.append((key, candidate))
        if not moves:
            return [j+1 for j in selected]
        selected = min(moves, key=lambda x: x[0])[1]
