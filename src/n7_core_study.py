"""Prediction-only reporting projection for the core/opportunity study."""

CORE_R_SOURCES = (
    'r/n7_sleeve_tables.R', 'r/n7_joint_sleeves.R', 'r/n7_capital_depth.R',
    'r/n7_capital_portfolio.R', 'r/n7_core_opportunity.R', 'r/n7_core_plan.R',
    'r/n7_core_issue.R', 'scripts/run_n7_core_issue.R',
    'config/n7_joint_runtime.json', 'config/compression_breadth_runtime.json',
)


def describe_core_plan(plan):
    """Flatten frozen metrics into one issue/seed/policy row; money is CNY.

    ROI/probabilities are fractions; unsupported metrics remain None. No I/O,
    fitting, target settlement access or state. Missing fields raise KeyError.
    Settlement owns unique_tickets and paid-unit accounting; this projection
    supplies only the additional frozen policy and prediction fields.
    """
    out = {key: plan[key] for key in ('budget_cny', 'cash_cny', 'funded_sleeves',
                                     'opening_stop', 'solver_status')}
    out.update(plan['policy'])
    for prefix in ('training', 'evaluation'):
        out.update({f'{prefix}_{k}': v for k, v in plan[prefix].items()})
    return out
