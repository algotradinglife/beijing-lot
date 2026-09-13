"""#425 domain reporting adapter; orchestration/receipts remain shared with #424.

No import-time work, fitting, labels or implicit paths. This callback copies
frozen prediction diagnostics only; authoritative settlement adds realized P&L.
"""


def describe_capital_plan(plan):
    """Return issue-level capital diagnostics with separately named model worlds.

    All money is CNY; probabilities and ROI are fractions. Missing conditional
    support remains None. The complete sleeve ledger stays in the sealed plan.
    Missing required fields raise KeyError instead of manufacturing defaults.
    """
    result = {key: plan[key] for key in (
        "budget_cny", "cash_cny", "funded_sleeves", "support_space", "solver_status",
        "max_reuse", "max_overlap", "max_fixture_exposure_cny", "max_outcome_exposure_cny")}
    for prefix in ("training", "evaluation"):
        result.update({f"{prefix}_{key}": value for key, value in plan[prefix].items()})
    return result
