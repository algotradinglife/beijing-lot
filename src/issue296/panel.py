"""Build a matched issue-by-expert panel from accepted historical ledgers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_PATH = Path("results/issue-209/dynamic_issue_states.csv")

EXPERTS = (
    {
        "expert_id": "FULL_CONTROL",
        "source_issue": 176,
        "source_policy": "BEST_FULL_FULL",
        "role": "control",
        "training_status": "ELIGIBLE",
        "estimand": "REALIZED_POLICY",
    },
    {
        "expert_id": "SMOOTH_M512",
        "source_issue": 176,
        "source_policy": "MODEL_SOURCE_MODEL_CAP1_M512",
        "role": "smooth_core",
        "training_status": "ELIGIBLE",
        "estimand": "REALIZED_POLICY",
    },
    {
        "expert_id": "Q_TAIL_M192",
        "source_issue": 176,
        "source_policy": "Q_SOURCE_Q_TOP_MASS_M192",
        "role": "convex_tail",
        "training_status": "ELIGIBLE",
        "estimand": "REALIZED_POLICY",
    },
    {
        "expert_id": "Q_WOR_M64",
        "source_issue": 151,
        "source_policy": "Q_INFORMED_WOR_DISTINCT/M64",
        "role": "diversified_tail",
        "training_status": "ELIGIBLE",
        "estimand": "NUISANCE_SEED_MEAN",
    },
    {
        "expert_id": "DIVERGENCE_Z100_K1",
        "source_issue": 190,
        "source_policy": "DP_5970cc7b2874743a5698",
        "role": "sparse_direction",
        "training_status": "ELIGIBLE",
        "estimand": "REALIZED_POLICY",
    },
    {
        "expert_id": "RARE_LOGIT_TOP64",
        "source_issue": 291,
        "source_policy": "DATA_LOGIT_RIDGE/DIRECT_PNL/Top64",
        "role": "rare_jackpot",
        "training_status": "ELIGIBLE",
        "estimand": "REALIZED_POLICY",
    },
    {
        "expert_id": "N7_K16_WR",
        "source_issue": 292,
        "source_policy": "N7_K16_WEIGHTED_WR",
        "role": "candidate_only",
        "training_status": "SUMMARY_ONLY_INELIGIBLE",
        "estimand": "NO_TRUSTED_ISSUE_PATH",
    },
)


def build_expert_registry() -> pd.DataFrame:
    """Return the frozen expert inventory, including ineligible candidates."""

    return pd.DataFrame(EXPERTS)


def load_issue_features(root: str | Path) -> pd.DataFrame:
    """Load the causal issue state panel and enforce the 2024+ seal."""

    root = Path(root)
    frame = pd.read_csv(root / FEATURE_PATH)
    frame["issue"] = pd.to_numeric(frame["issue"], errors="raise").astype(int)
    frame["issue_year"] = pd.to_numeric(frame["issue_year"], errors="raise").astype(int)
    frame = frame[frame["issue_year"].between(2019, 2023)].copy()
    if frame["issue_year"].ge(2024).any():
        raise AssertionError("Issue #296 must not open 2024+ feature rows")
    if frame["issue"].duplicated().any():
        raise ValueError("issue feature panel must be unique by issue")
    return frame.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def build_expert_panel(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return a matched long expert panel and the nuisance-seed ledger.

    A ledger row with zero stake is a valid frozen NO_BET decision. An absent
    row is not silently converted to NO_BET; it remains unavailable.
    """

    root = Path(root)
    features = load_issue_features(root)
    calendar = features[["issue", "issue_year"]]
    frames = [
        _load_176(root),
        _load_151(root),
        _load_190(root),
        _load_291(root),
    ]
    raw = pd.concat(frames, ignore_index=True)
    eligible = build_expert_registry().query("training_status == 'ELIGIBLE'")
    scaffold = (
        calendar.assign(_key=1)
        .merge(eligible[["expert_id"]].assign(_key=1), on="_key", how="inner")
        .drop(columns="_key")
    )
    panel = scaffold.merge(
        raw,
        on=["issue", "issue_year", "expert_id"],
        how="left",
        validate="one_to_one",
    )
    panel["available"] = panel["stake_unit_cny"].notna()
    for column in ["stake_unit_cny", "pnl_unit_cny", "gross_unit_cny", "hit_count"]:
        panel[column] = panel[column].fillna(0.0).astype(float)
    panel = panel.merge(
        eligible[["expert_id", "role", "source_issue", "estimand"]],
        on="expert_id",
        how="left",
        validate="many_to_one",
    )
    panel["unit_roi"] = np.divide(
        panel["pnl_unit_cny"],
        panel["stake_unit_cny"],
        out=np.zeros(len(panel), dtype=float),
        where=panel["stake_unit_cny"].gt(0),
    )
    if (panel.loc[panel["available"], "unit_roi"] < -1.0 - 1e-9).any():
        raise AssertionError("an expert unit cannot lose more than its stake")
    nuisance = _load_151_seed_ledger(root).merge(
        calendar, on=["issue", "issue_year"], how="inner", validate="many_to_one"
    )
    return (
        panel.sort_values(["issue_year", "issue", "expert_id"]).reset_index(drop=True),
        nuisance.sort_values(["issue_year", "issue", "seed"]).reset_index(drop=True),
    )


def _load_176(root: Path) -> pd.DataFrame:
    path = root / "results/bj176_issue_equity_risk_v1/issue_time_series.csv.gz"
    frame = pd.read_csv(path)
    mapping = {
        "BEST_FULL_FULL": "FULL_CONTROL",
        "MODEL_SOURCE_MODEL_CAP1_M512": "SMOOTH_M512",
        "Q_SOURCE_Q_TOP_MASS_M192": "Q_TAIL_M192",
    }
    frame = frame[
        frame["support_view"].eq("NATIVE_SELECTOR") & frame["arm_id"].isin(mapping)
    ].copy()
    frame["expert_id"] = frame["arm_id"].map(mapping)
    return frame.rename(
        columns={
            "year": "issue_year",
            "stake_yuan": "stake_unit_cny",
            "pre_tax_net_yuan": "pnl_unit_cny",
            "gross_pre_tax_yuan": "gross_unit_cny",
            "hit_ticket_count": "hit_count",
        }
    )[
        [
            "issue",
            "issue_year",
            "expert_id",
            "stake_unit_cny",
            "pnl_unit_cny",
            "gross_unit_cny",
            "hit_count",
        ]
    ]


def _load_151_seed_ledger(root: Path) -> pd.DataFrame:
    path = (
        root
        / "results/bj151_gate_b_outcome_settlement_v1/issue_m_grid_settlement.csv.gz"
    )
    frame = pd.read_csv(path, low_memory=False)
    mask = (
        frame["sampling_role"].eq("SENSITIVITY_WOR_FIXED_CANDIDATE")
        & frame["ticket_mechanism"].eq("Q_INFORMED_WOR_DISTINCT")
        & frame["M"].eq(64)
    )
    frame = frame.loc[mask].copy()
    frame["expert_id"] = "Q_WOR_M64"
    return frame.rename(
        columns={
            "year": "issue_year",
            "planned_stake_yuan": "stake_unit_cny",
            "pre_tax_net_yuan": "pnl_unit_cny",
            "gross_pre_tax_yuan": "gross_unit_cny",
            "hit_ticket_count": "hit_count",
        }
    )[
        [
            "issue",
            "issue_year",
            "expert_id",
            "seed",
            "stake_unit_cny",
            "pnl_unit_cny",
            "gross_unit_cny",
            "hit_count",
        ]
    ]


def _load_151(root: Path) -> pd.DataFrame:
    frame = _load_151_seed_ledger(root)
    return frame.groupby(["issue", "issue_year", "expert_id"], as_index=False)[
        ["stake_unit_cny", "pnl_unit_cny", "gross_unit_cny", "hit_count"]
    ].mean()


def _load_190(root: Path) -> pd.DataFrame:
    path = (
        root
        / "results/bj190_gate_b_sparse_divergence_v1/issue_arm_settlement_d_direction_only.csv.gz"
    )
    frame = pd.read_csv(path, low_memory=False)
    frame = frame[frame["policy_id"].eq("DP_5970cc7b2874743a5698")].copy()
    frame["expert_id"] = "DIVERGENCE_Z100_K1"
    return (
        frame.rename(columns={"year": "issue_year"})
        .groupby(["issue", "issue_year", "expert_id"], as_index=False)
        .agg(
            stake_unit_cny=("stake_yuan", "sum"),
            pnl_unit_cny=("pre_tax_net_yuan", "sum"),
            gross_unit_cny=("gross_pre_tax_yuan", "sum"),
            hit_count=("hit_ticket_count", "sum"),
        )
    )


def _load_291(root: Path) -> pd.DataFrame:
    path = root / "docs/research/artifacts/issue-291/ranking_issue_paths.csv"
    frame = pd.read_csv(path)
    mask = (
        frame["domain"].eq("BASE")
        & frame["model"].eq("DATA_LOGIT_RIDGE")
        & frame["score"].eq("DIRECT_PNL")
        & frame["ticket_budget_per_issue"].eq(64)
    )
    frame = frame.loc[mask].copy()
    frame["expert_id"] = "RARE_LOGIT_TOP64"
    frame["issue_year"] = frame["oof_year"].astype(int)
    frame["gross_unit_cny"] = frame["gross_cny"]
    frame["hit_count"] = frame["hits"]
    return frame.rename(
        columns={"stake_cny": "stake_unit_cny", "pnl_cny": "pnl_unit_cny"}
    )[
        [
            "issue",
            "issue_year",
            "expert_id",
            "stake_unit_cny",
            "pnl_unit_cny",
            "gross_unit_cny",
            "hit_count",
        ]
    ]
