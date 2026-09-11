"""Fixed market-favorite single selection inside frozen seven-fixture groups."""
import copy
import itertools
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def reselect_group_singles(plan, frame, *, cutoffs, policy, budget_cny, unit_cny, payout_factor):
    """Rebuild exact D2 supports on unchanged groups; no I/O or fitting.

    MARKET ranks each fixture's market favorite by q. VALUE ranks the same
    favorite by baseline p/q, with estimated SP=1/q. This is a one-leg return
    proxy, not optimization of whole-ticket EV. Both choose two slots; ties
    resolve by slot. Direction ties use W,D,L. Other five use baseline Top2.
    Native cutoffs/input hash must match source plan; prices/labels forbidden.
    Groups, stake, cash, total/pair reuse remain unchanged. No single-use cap.
    """
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    if (policy not in ("MARKET","VALUE") or type(budget_cny) is not int
            or budget_cny!=plan["budget"] or (unit_cny,payout_factor)!=(2,.65)
            or plan["cutoffs"]!=bound
            or plan["input_sha256"]!=stable_json_hash(frame.sort_values("slot").to_json(orient="records"))
            or plan["seal"]!=stable_json_hash({k:v for k,v in plan.items() if k!="seal"})):
        raise ValueError("Matching sealed source, cutoffs and explicit policy required")
    indexed=frame.set_index("slot");parts=[]
    for source in plan["components"]:
        if (source["seal"]!=stable_json_hash({k:v for k,v in source.items() if k!="seal"})
                or source["complement"] or source["groups"]!=1 or source["stake"]!=64
                or len(source["legs"])!=7 or len({l["slot"] for l in source["legs"]})!=7):
            raise ValueError("Sealed non-converting D2 source component required")
        ranks=[]
        for leg in source["legs"]:
            row=indexed.loc[leg["slot"]]
            if any(row[k]!=leg[k] for k in ["provider_id","handicap","p_W","p_D","p_L","q_W","q_D","q_L"]):
                raise ValueError("Source leg/input mismatch")
            favorite=min(range(3),key=lambda j:(-leg["q_"+"WDL"[j]],j))
            q=leg["q_"+"WDL"[favorite]];p=leg["p_"+"WDL"[favorite]]
            ranks.append(dict(slot=leg["slot"],direction="310"[favorite],market_probability=q,
                baseline_probability=p,estimated_sp=1/q,return_proxy=p/q,
                rank_score=q if policy=="MARKET" else p/q))
        ranks.sort(key=lambda r:(-r["rank_score"],r["slot"]))
        selected={r["slot"]:r["direction"] for r in ranks[:2]}
        part=copy.deepcopy(source);part.pop("seal")
        for leg in part["legs"]:
            ids=sorted(range(3),key=lambda j:(-leg["p_"+"WDL"[j]],j))[:2]
            support=selected.get(leg["slot"],"".join("310"[j] for j in sorted(ids)))
            leg.update(original_role=leg["role"],role="A" if leg["slot"] in selected else "D",support=support,
                coverage=sum(leg["p_"+"WDL"[j]] for j in range(3) if "310"[j] in support),
                value=sum(leg["p_"+"WDL"[j]]/leg["q_"+"WDL"[j]] for j in range(3) if "310"[j] in support))
        part["legs"].sort(key=lambda r:r["slot"])
        part["tickets"]=[dict(group=1,code="".join(c),units=1) for c in itertools.product(*(l["support"] for l in part["legs"]))]
        if len(part["tickets"])!=32:raise ValueError("Exact two singles required")
        part.update(selector="WITHIN_GROUP_"+policy,shape="D2",upstream_component_seal=source["seal"],
            single_ranking=ranks,unit_cny=unit_cny,payout_factor=payout_factor)
        parts.append(dict(**part,seal=stable_json_hash(part)))
    stake=sum(p["stake"] for p in parts)
    if stake!=plan["stake"] or stake+plan["cash_cny"]!=budget_cny:
        raise ValueError("Source budget invariant")
    env=dict(issue=plan["issue"],strategy="WITHIN_GROUP_"+policy,funding="UNIT",
        components=parts,stake=stake,budget=budget_cny,cash_cny=plan["cash_cny"],
        model_any_hit=None,cutoffs=bound,input_sha256=plan["input_sha256"],
        upstream_plan_seal=plan["seal"],historical_admission=False,
        mode="EXPOSED_FIXED_GROUP_SINGLE_RESELECTION",parameters=dict(policy=policy,
            budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
            single_count=2,price_proxy="1/q",direction="MARKET_FAVORITE"))
    return dict(**env,seal=stable_json_hash(env))
