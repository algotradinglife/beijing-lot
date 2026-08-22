"""Pre-2023 policy freeze and fixed-budget allocation for Issue #312."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from .design import CubeAction
from .model import add_policy_scores

COMMITTED_TICKETS = 512
COMMITTED_STAKE_CNY = 1_024.0
ACTION_COLUMNS = (
    "n",
    "k",
    "match_selector",
    "pool_excess",
    "outcome_direction",
    "generator",
    "protection",
)


def select_policy_allocations(
    prediction_sets: dict[str, pd.DataFrame],
    *,
    primary_family: str,
    issue306_allocations: pd.DataFrame,
    development_labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze all causal 2023 actions before loading 2023 settlement."""

    rows = []
    learned = add_policy_scores(prediction_sets["LEARNED"])
    selections: dict[str, pd.DataFrame] = {}
    for family, score_column in (("MEAN", "mean_score"), ("TAIL", "tail_score")):
        condition = f"JOINT_{family}"
        selected = _select_top(learned, score_column, condition)
        selections[family] = selected
        rows.append(selected)
    primary_condition = f"JOINT_{primary_family}"
    primary = selections[primary_family].copy()
    primary["condition"] = "JOINT_PRIMARY"
    rows.append(primary)

    for condition, published in (
        ("ISSUE_BLOCK_SHUFFLED", prediction_sets["ISSUE_BLOCK_SHUFFLED"]),
        ("IDENTITY_SHUFFLED", prediction_sets["IDENTITY_SHUFFLED"]),
    ):
        rows.append(_select_top(add_policy_scores(published), "mean_score", condition))

    static_key = _best_static_key(development_labels)
    static_action = _lookup_action(learned, static_key)
    rows.append(_fixed_action_for_issues(learned, static_action, "BEST_STATIC_ACTION"))
    fixed_n7_wor = CubeAction(
        7, 512, "GLOBAL_VALUE", -1, "RAW_VALUE", "WEIGHTED_WOR", "NONE"
    )
    rows.append(_fixed_action_for_issues(learned, fixed_n7_wor, "FIXED_N7_K512_WOR"))

    inherited = issue306_allocations[
        issue306_allocations["condition"].eq("LEARNED_MEAN_DETERMINISTIC")
        & issue306_allocations["issue_year"].eq(2023)
    ].copy()
    target_issues = set(learned["issue"])
    inherited = inherited[inherited["issue"].isin(target_issues)].copy()
    if set(inherited["issue"]) != target_issues:
        raise AssertionError("#306 interface comparator lacks exact common support")
    inherited["match_selector"] = "GLOBAL_VALUE"
    inherited["pool_excess"] = -1
    inherited["outcome_direction"] = "RAW_VALUE"
    inherited["protection"] = "NONE"
    inherited["action_key"] = inherited.apply(
        lambda row: CubeAction(
            int(row["n"]),
            int(row["k"]),
            "GLOBAL_VALUE",
            -1,
            "RAW_VALUE",
            str(row["generator"]),
            "NONE",
        ).key,
        axis=1,
    )
    inherited["condition"] = "ISSUE306_PRIMARY"
    rows.append(inherited[_allocation_columns()])

    for condition, mutate in (
        ("ABLATE_SELECTOR", {"match_selector": "GLOBAL_VALUE"}),
        ("ABLATE_OUTCOME", {"outcome_direction": "RAW_VALUE"}),
        ("ABLATE_PROTECTION", {"protection": "NONE"}),
    ):
        ablation = primary.copy()
        ablation["condition"] = condition
        for column, value in mutate.items():
            ablation[column] = value
        ablation["action_key"] = ablation.apply(_action_key_from_row, axis=1)
        rows.append(ablation)

    allocations = pd.concat(rows, ignore_index=True)
    expected_conditions = {
        "JOINT_MEAN",
        "JOINT_TAIL",
        "JOINT_PRIMARY",
        "ISSUE_BLOCK_SHUFFLED",
        "IDENTITY_SHUFFLED",
        "BEST_STATIC_ACTION",
        "FIXED_N7_K512_WOR",
        "ISSUE306_PRIMARY",
        "ABLATE_SELECTOR",
        "ABLATE_OUTCOME",
        "ABLATE_PROTECTION",
    }
    if set(allocations["condition"]) != expected_conditions:
        raise AssertionError("one or more required policy conditions lack common support")
    if not allocations.groupby(["condition", "issue"])["allocated_tickets"].sum().eq(
        COMMITTED_TICKETS
    ).all():
        raise AssertionError("pre-2023 allocation does not spend exactly 512 tickets")
    issue_sets = allocations.groupby("condition")["issue"].agg(lambda values: frozenset(values))
    if issue_sets.nunique() != 1:
        raise AssertionError("policy conditions do not share exact common issue support")
    evaluation_registry = allocations[["action_key", *ACTION_COLUMNS]].drop_duplicates(
        "action_key"
    )
    evaluation_registry["is_anchor"] = evaluation_registry.apply(
        lambda row: CubeAction(
            **{column: row[column] for column in ACTION_COLUMNS}
        ).is_anchor,
        axis=1,
    )
    evaluation_registry = evaluation_registry.sort_values("action_key").reset_index(
        drop=True
    )
    allocations.attrs["primary_condition"] = primary_condition
    allocations.attrs["best_static_action_key"] = static_key
    return allocations, evaluation_registry


def _select_top(
    predictions: pd.DataFrame, score_column: str, condition: str
) -> pd.DataFrame:
    selected = predictions.loc[
        predictions.groupby("issue")[score_column].idxmax()
    ].copy()
    selected["condition"] = condition
    selected["copies"] = COMMITTED_TICKETS // selected["k"].astype(int)
    selected["allocated_tickets"] = selected["copies"] * selected["k"].astype(int)
    return selected[_allocation_columns()]


def _fixed_action_for_issues(
    template: pd.DataFrame, action: CubeAction, condition: str
) -> pd.DataFrame:
    issues = template[["issue", "issue_year"]].drop_duplicates()
    feasible = issues.copy()
    for column, value in asdict(action).items():
        feasible[column] = value
    feasible["action_key"] = action.key
    feasible["condition"] = condition
    feasible["copies"] = COMMITTED_TICKETS // action.k
    feasible["allocated_tickets"] = COMMITTED_TICKETS
    return feasible[_allocation_columns()]


def _best_static_key(labels: pd.DataFrame) -> str:
    development = labels[labels["issue_year"].isin((2021, 2022))].copy()
    development["fixed_budget_pnl_cny"] = (
        development["mean_pnl_cny"] * COMMITTED_TICKETS / development["k"]
    )
    issue_count = development["issue"].nunique()
    summary = development.groupby("action_key", as_index=False).agg(
        issues=("issue", "nunique"),
        mean_fixed_budget_pnl_cny=("fixed_budget_pnl_cny", "mean"),
    )
    supported = summary[summary["issues"].eq(issue_count)]
    if supported.empty:
        raise ValueError("no static action has complete development support")
    return str(
        supported.sort_values(
            ["mean_fixed_budget_pnl_cny", "action_key"], ascending=[False, True]
        ).iloc[0]["action_key"]
    )


def _lookup_action(frame: pd.DataFrame, action_key: str) -> CubeAction:
    row = frame[frame["action_key"].eq(action_key)].iloc[0]
    return CubeAction(**{column: row[column] for column in ACTION_COLUMNS})


def _action_key_from_row(row: pd.Series) -> str:
    return CubeAction(**{column: row[column] for column in ACTION_COLUMNS}).key


def _allocation_columns() -> list[str]:
    return [
        "issue",
        "issue_year",
        "condition",
        "action_key",
        *ACTION_COLUMNS,
        "copies",
        "allocated_tickets",
    ]
