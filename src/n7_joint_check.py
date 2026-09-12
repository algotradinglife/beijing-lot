"""Independent arithmetic replay of frozen R joint portfolios (no selection)."""
from pathlib import Path
import gzip
import hashlib
import json
import numpy as np

from src.temporal_learning import verify_implementation_closure
from src.temporal_learning.core import stable_json_hash


def check_joint_plan(plan, worlds, config):
    """Rebuild physical identities, p/q values, dependent hit union and path loss.

    Inputs contain no actual settlement. Returns replay metrics; raises on any
    mismatch. Numpy arithmetic is independent of R option projection and MILP.
    Fixed research limits are enforced for each relevant arm, including NO_BET.
    """
    if plan["seal"] != stable_json_hash({k: v for k, v in plan.items() if k != "seal"}):
        raise ValueError("Plan seal mismatch")
    indices = np.asarray(plan["fixture_indices"], dtype=int).reshape(-1, 7)
    codes = np.asarray(plan["outcomes"], dtype=int).reshape(-1, 7)
    if (indices.shape != codes.shape or len(indices) not in (0, 512) or plan["groups"] != len(indices)
            or plan["stake"] != 2 * len(indices) or plan["cash_cny"] + plan["stake"] != 1024
            or (plan["budget_cny"], plan["unit_cny"], plan["payout_factor"]) != (1024, 2, .65)
            or plan["historical_admission"] is not False):
        raise ValueError("Fixed budget/shape contract mismatch")
    if (np.any(indices < 0) or np.any(indices >= len(plan["fixtures"])) or np.any(np.diff(indices, axis=1) <= 0)
            or np.any(codes < 0) or np.any(codes > 2)
            or len(set(map(tuple, (3 * indices + codes).tolist()))) != len(indices)):
        raise ValueError("Physical ticket identity mismatch")
    if len(indices) and plan["solver_status"] not in ("Optimal", "FIXED_RULE"):
        raise ValueError("Unapproved solver incumbent funded")
    if len(indices) and plan["solver_status"] == "Optimal":
        if plan["solver"]["mip_gap"] > config["solver_gap"] + 1e-9:
            raise ValueError("Solver gap exceeds declared limit")
    if len(indices) == 0 and plan["solver_status"] in ("Optimal", "FIXED_RULE"):
        raise ValueError("Successful selection silently discarded")
    triplets = np.array([[f[f"p_{d}"] for d in "WDL"] for f in plan["fixtures"]])
    quotes = np.array([[f[f"q_{d}"] for d in "WDL"] for f in plan["fixtures"]])
    expected = float(np.sum(1.3 * np.prod(triplets[indices, codes] / quotes[indices, codes], axis=1)))
    if not np.isclose(expected - plan["stake"], plan["expected_net"], atol=1e-6, rtol=1e-12):
        raise ValueError("Expected return arithmetic mismatch")
    if len(plan["sleeve_keys"]) != len(indices) // 64:
        raise ValueError("Sleeve count mismatch")
    sets, masses = [], []
    canonical = np.indices((3,) * 7).reshape(7, -1).T
    for j, key in enumerate(plan["sleeve_keys"]):
        ix = indices[j * 64:(j + 1) * 64]; outcome = codes[j * 64:(j + 1) * 64]
        if not np.all(ix == ix[0]):
            raise ValueError("Sleeve fixture set changes within 64 states")
        state = outcome @ (3 ** np.arange(6, -1, -1))
        if key["state_ids"] != state.tolist() or len(set(state)) != 64:
            raise ValueError("Selected state identity mismatch")
        sets.append(set(ix[0])); mass = np.prod(triplets[ix, outcome], axis=1).sum(); masses.append(mass)
        all_p = np.prod(triplets[ix[0], canonical], axis=1)
        best = np.sort(all_p)[-64:].sum()
        if key["rule"] == "PROB" and not np.isclose(mass, best, atol=1e-12, rtol=1e-10):
            raise ValueError("PROB64 mass is not maximal")
        if key["rule"] == "FRONTIER" and (mass + 1e-8 < config["coverage_fraction"] * best
                or key["expected_gross"] + 1e-6 < 128 * (1 + config["minimum_roi"])):
            raise ValueError("Frontier gate violated")
        if not np.isclose(key["coverage"], mass, atol=1e-12):
            raise ValueError("Sleeve mass mismatch")
    if len({tuple(sorted(g)) for g in sets}) != len(sets):
        raise ValueError("Repeated sleeve fixture set")
    reuse = max((sum(i in g for g in sets) for i in range(len(triplets))), default=0)
    overlap = max((len(a & b) for j, a in enumerate(sets) for b in sets[:j]), default=0)
    if reuse != plan["max_reuse"] or overlap != plan["max_overlap"]:
        raise ValueError("U/P accounting mismatch")
    if sets and not np.isclose(np.mean(masses), plan["mean_sleeve_coverage"], atol=1e-12):
        raise ValueError("Mean sleeve mass mismatch")
    if plan["arm"] in ("JOINT_UP", "JOINT_FULL", "JOINT_NO_RETURN"):
        if reuse > config["reuse_cap"] or overlap > config["overlap_cap"]:
            raise ValueError("U/P gate violated")
    if sets and plan["arm"] in ("JOINT_RETURN", "JOINT_UP", "JOINT_FULL", "JOINT_NO_UP"):
        if expected + 1e-6 < 1024 * (1 + config["minimum_roi"]):
            raise ValueError("Return gate violated")
    replay = {}
    for kind, prefix in (("training", "train"), ("evaluation", "eval")):
        w = np.asarray(worlds[kind], dtype=int)
        if w.shape != (config[f"{kind}_worlds"], len(triplets)) or np.any(w < 0) or np.any(w > 2):
            raise ValueError("Scenario shape mismatch")
        hit = np.zeros(len(w), dtype=bool); gross = np.zeros(len(w))
        for j, group in enumerate(sets):
            ix = sorted(group); states = w[:, ix] @ (3 ** np.arange(6, -1, -1))
            won = np.isin(states, plan["sleeve_keys"][j]["state_ids"])
            hit |= won
            gross[won] += 1.3 / np.prod(quotes[ix, w[won][:, ix]], axis=1)
        values = (gross - plan["stake"]).reshape(-1, config["path_steps"])
        equity = np.c_[np.zeros(len(values)), values.cumsum(axis=1)]
        dd = float((np.maximum.accumulate(equity, axis=1) - equity).max(axis=1).mean())
        coverage = float(hit.mean())
        if not np.isclose(coverage, plan[f"{prefix}_coverage"], atol=1e-12):
            raise ValueError("Shared-world union mismatch")
        if not np.isclose(dd, plan[f"{prefix}_path_drawdown"], atol=1e-6, rtol=1e-12):
            raise ValueError("Path drawdown mismatch")
        if prefix == "train" and plan["arm"] in ("JOINT_FULL", "JOINT_NO_RETURN", "JOINT_NO_UP"):
            if dd > config["mean_drawdown_cap"] + 1e-5:
                raise ValueError("Risk gate violated")
        replay[f"{prefix}_coverage"] = coverage; replay[f"{prefix}_path_drawdown"] = dd
    return replay


def check_joint_study(output, *, repository_root):
    """Verify every frozen plan and scenario file, then replay all R arithmetic.

    No result-based selection or mutation. Caller may persist this returned audit
    separately. This checks constraints and accounting, not an exact optimum beyond
    the declared MILP gap/node policy. Solver optimality is tested on tiny oracles.
    """
    output, root = Path(output), Path(repository_root)
    frozen = json.loads((output / "plans-frozen.json").read_text()); receipt = frozen["receipt"]
    if frozen["seal"] != stable_json_hash(receipt):
        raise ValueError("Freeze changed")
    verify_implementation_closure(root, receipt["implementation"])
    bundles = {}
    for p, h in receipt["source_hashes"].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h:
            raise ValueError("Source changed")
        if Path(p).parent.name == "bundles":
            b = json.loads(gzip.decompress(Path(p).read_bytes())); bundles[b["issue"]] = b
    for p, h in receipt["r_implementation"].items():
        if hashlib.sha256((root / p).read_bytes()).hexdigest() != h:
            raise ValueError("R code changed")
    count = 0
    for path, digest in receipt["raw_hashes"].items():
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Raw R output changed")
        result = json.loads(gzip.decompress(raw)); worlds = {w["seed"]: w for w in result["worlds"]}
        for plan in result["plans"]:
            issue = plan["issue"]
            b = bundles[issue]
            if plan["cutoffs"] != receipt["cutoffs"][issue] or plan["cutoffs"] != b["cutoffs"]:
                raise ValueError("Cutoff map changed")
            if plan["fixtures"] != b["expanded_pool"]["fixtures"]:
                raise ValueError("Plan probabilities/identities differ from frozen source")
            groupmap = {g["id"]: g["fixture_indices"] for g in b["sleeves"]}
            for j, key in enumerate(plan["sleeve_keys"]):
                if plan["fixture_indices"][j * 64] != groupmap[key["sleeve_id"]]:
                    raise ValueError("Selected group differs from source candidate")
            plan_path = output.resolve() / "plans" / f"{issue}_{plan['seed']}_{plan['arm']}.json.gz"
            raw_plan = plan_path.read_bytes()
            if hashlib.sha256(raw_plan).hexdigest() != receipt["plan_hashes"][str(plan_path)]:
                raise ValueError("Plan bytes changed")
            if json.loads(gzip.decompress(raw_plan)) != plan:
                raise ValueError("Packed plan differs from R output")
            check_joint_plan(plan, worlds[plan["seed"]], receipt["parameters"]); count += 1
    if count != len(receipt["plan_hashes"]):
        raise ValueError("Incomplete raw plan replay")
    return dict(status="PASS", plans_checked=count, freeze_seal=frozen["seal"], historical_admission=False)
