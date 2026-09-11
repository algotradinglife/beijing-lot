"""Fixed gate on inventoried historical plans; no fitting or regrouping."""
import copy
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def gate_zero_converter(plan, frame, *, cutoffs, zero_only, budget_cny):
    """Keep originals; optionally drop converters whose C handicap is nonzero.

    Explicit native fixture cutoffs must equal the inventoried plan. Frame is
    prediction-only and must match its input hash. Returns a new sealed plan,
    preserving component bytes/order. Freed CNY stays cash; no quota transfer.
    Missing identities/seals/handicaps fail. No I/O, learning or source mutation.
    Old allocation/solver metadata is retained only by the upstream seal.
    """
    _, bound = rank_double_candidates(frame, cutoffs=cutoffs)
    if (type(zero_only) is not bool or type(budget_cny) is not int
            or budget_cny != plan["budget"] or plan["cutoffs"] != bound
            or plan["input_sha256"] != stable_json_hash(frame.sort_values("slot").to_json(orient="records"))
            or plan["seal"] != stable_json_hash({k:v for k,v in plan.items() if k!="seal"})):
        raise ValueError("Valid inventoried plan, identical cutoff/input and budget required")
    kept=[]; dropped=[]
    indexed=frame.set_index("slot")
    for i,part in enumerate(plan["components"]):
        if part["seal"] != stable_json_hash({k:v for k,v in part.items() if k!="seal"}):
            raise ValueError("Invalid component seal")
        converters=[leg for leg in part["legs"] if leg["role"]=="C"]
        if len(converters)!=1 or type(part["complement"]) is not bool:
            raise ValueError("Exactly one converter position required")
        for leg in part["legs"]:
            r=indexed.loc[leg["slot"]]
            if any(r[k]!=leg[k] for k in ["provider_id","handicap","p_W","p_D","p_L","q_W","q_D","q_L"]):
                raise ValueError("Component identity/probability differs from source")
        if zero_only and part["complement"] and converters[0]["handicap"]!=0:
            dropped.append(i)
        else:
            kept.append(copy.deepcopy(part))
    stake=sum(p["stake"] for p in kept)
    if not 0<=stake<=budget_cny:
        raise ValueError("Invalid budget")
    env=dict(issue=plan["issue"],strategy=plan["strategy"]+("_ZERO" if zero_only else "_ALL"),
        funding="UNIT",components=kept,stake=stake,budget=budget_cny,cash_cny=budget_cny-stake,
        model_any_hit=None,cutoffs=bound,historical_admission=False,
        mode="EXPOSED_INVENTORIED_PLAN_GATE_NO_REGROUPING",upstream_plan_seal=plan["seal"],
        input_sha256=plan["input_sha256"],zero_only=zero_only,dropped_indices=dropped)
    return dict(**env,seal=stable_json_hash(env))
