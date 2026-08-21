"""Build a matched issue-by-expert panel from accepted historical ledgers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_PATH = Path("evidence/bj296_expert_sources_v1/issue209_features_2019_2023.csv")

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
    if not frame["issue_year"].between(2019, 2023).all():
        raise AssertionError("Issue #296 feature projection is outside 2019-2023")
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
    invalid_zero_stake = (
        panel["available"]
        & panel["stake_unit_cny"].eq(0.0)
        & (
            panel["pnl_unit_cny"].ne(0.0)
            | panel["gross_unit_cny"].ne(0.0)
            | panel["hit_count"].ne(0.0)
        )
    )
    if invalid_zero_stake.any():
        raise AssertionError("a zero-stake expert row carries settlement economics")
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
    path = root / "evidence/bj296_expert_sources_v1/issue176_experts_2019_2023.csv"
    return _read_projection(path)


def _load_151_seed_ledger(root: Path) -> pd.DataFrame:
    path = root / "evidence/bj296_expert_sources_v1/issue151_wor_m64_2019_2023.csv"
    return _read_projection(path)


def _load_151(root: Path) -> pd.DataFrame:
    frame = _load_151_seed_ledger(root)
    return frame.groupby(["issue", "issue_year", "expert_id"], as_index=False)[
        ["stake_unit_cny", "pnl_unit_cny", "gross_unit_cny", "hit_count"]
    ].mean()


def _load_190(root: Path) -> pd.DataFrame:
    path = root / "evidence/bj296_expert_sources_v1/issue190_z100_k1_2019_2023.csv"
    return _read_projection(path)


def _load_291(root: Path) -> pd.DataFrame:
    path = root / "docs/research/artifacts/issue-291/ranking_issue_paths.csv"
    frame = pd.read_csv(path)
    if pd.to_numeric(frame["oof_year"], errors="raise").gt(2023).any():
        raise AssertionError("Issue #291 source carries a sealed row")
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


def _read_projection(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if pd.to_numeric(frame["issue_year"], errors="raise").gt(2023).any():
        raise AssertionError(f"pre-2024 projection contains a sealed row: {path}")
    return frame
