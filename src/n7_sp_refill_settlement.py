"""Post-freeze settlement of rebuilt groups through two independent evaluators."""
import pandas as pd
from src.n7_single_ticket_sampling import settle_single_tickets
from src.n7_capital_check import check_capital_settlement


def settle_refill_plans(plans, audit_rows):
    """Settle sealed physical plans using fixture identities, never old group IDs.

    Inputs: frozen plans and audit records with actual WDL and Beidan SP.
    Returns one accounting record per issue/arm/seed (CNY, fractional ROI).
    Missing winning SP, pending identities or duplicate plans raise ValueError.
    Calls the independent sleeve-state checker for every plan. No IO or fitting.
    """
    keys = [(p['issue'], p['arm'], p['seed']) for p in plans]
    if not plans or len(set(keys)) != len(keys):
        raise ValueError('Empty or duplicate refill plans')
    audit = pd.DataFrame(audit_rows)
    rows = []
    for plan in plans:
        result = settle_single_tickets(plan, audit)
        if result['status'] not in ('COMPLETE', 'NO_BET'):
            raise ValueError(f"Unsettled refill plan: {result['status']}")
        check_capital_settlement(plan, audit_rows, result)
        rows.append(dict(result, arm=plan['arm'], seed=plan['seed'],
                         physical_tickets=result['groups']))
    return rows
