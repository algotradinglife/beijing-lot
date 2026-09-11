"""Fixed N6 retention reconstruction on a prediction-only candidate pool."""
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement
from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_breadth import breadth_candidates, breadth_scenarios
from src.fundamentals_compression_bridge import bridge_surface, bridge_plan
from src.fundamentals_rescue_shapes import rescue_shape_plan
from src.temporal_learning.core import stable_json_hash


def high_hit_n6_plan(frame, *, cutoffs, exclude_zero_top2, budget_cny,
                     unit_cny, payout_factor, pool_seed, pool_size,
                     design_seed, design_draws):
    """Rebuild H1_R050_N6_C1_RETENTION, optionally filtering before grouping.

    Input: one issue, IDs, integer home handicap, normalized p/q WDL columns.
    Caller supplies p with the original large-handicap market adjustment and
    q from the market score grid. No new model is fitted here. Exact native
    cutoffs and business constants (1024 CNY, 2 CNY, once-only .65) required.
    Original fixed U6/P5 seven-leg source groups are rebuilt, then the weakest
    50/50 Top2-mass leg is removed and one retention single selected per group.
    Return sealed source/shape plans, filter ledger, explicit parameters/cash.
    Fewer than seven retained candidates, invalid inputs or clocks raise;
    there is no fallback strategy. No labels, I/O, mutation or prospective use.
    """
    rank_double_candidates(frame, cutoffs=cutoffs)
    if (type(exclude_zero_top2) is not bool or type(budget_cny) is not int
            or budget_cny != 1024 or unit_cny != 2 or payout_factor != .65):
        raise ValueError("Explicit exclusion and fixed business constants required")
    current = frame.copy()
    ledger = None
    if exclude_zero_top2:
        current, ledger = exclude_zero_top2_disagreement(current, cutoffs=cutoffs)
    if len(current) < 7:
        raise ValueError("Seven retained candidates required for original N7 source")
    bound = {str(s): cutoffs[str(s)] for s in current.slot}
    refs = {d: n7_single_plan(current, cutoffs=bound, budget_cny=budget_cny,
        single_rule="MAX_SINGLE", single_count=d, max_uses=2, unit_cny=unit_cny,
        payout_factor=payout_factor, allocation_seed=0) for d in (1, 2)}
    pool = breadth_candidates(current, cutoffs=bound, seed=pool_seed, pool_size=pool_size)
    surface = bridge_surface(current, pool, refs, cutoffs=bound, depth=2)
    design = breadth_scenarios(current, surface, cutoffs=bound,
                              seed=design_seed, draws=design_draws)
    source = bridge_plan(current, surface, design, refs[2], cutoffs=bound,
        preserve_prefix=True, quality="TOP2", overlap="CAPPED", cash_policy="HOLD",
        budget_cny=budget_cny, unit_cny=unit_cny, payout_factor=payout_factor,
        max_uses=6, max_pair_overlap=5)
    shape = rescue_shape_plan(source, cutoffs=bound, market_weight=.5,
        mode="N6_C1_RETENTION", budget_cny=budget_cny,
        unit_cny=unit_cny, payout_factor=payout_factor)
    result = dict(source_plan=source, shape_plan=shape, exclusion=ledger,
        parameters=dict(exclude_zero_top2=exclude_zero_top2, budget_cny=budget_cny,
            unit_cny=unit_cny, payout_factor=payout_factor, pool_seed=pool_seed,
            pool_size=pool_size, design_seed=design_seed, design_draws=design_draws,
            max_uses=6, max_pair_overlap=5, market_weight=.5), historical_admission=False)
    return dict(**result, seal=stable_json_hash(result))
