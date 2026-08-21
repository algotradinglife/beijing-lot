#!/usr/bin/env python3
"""Create the pre-2024 expert projections consumed by Issue #296."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    root = Path(".")
    target = root / "evidence/bj296_expert_sources_v1"
    target.mkdir(parents=True, exist_ok=True)
    raw_features = root / "results/issue-209/dynamic_issue_states.csv"
    features = pd.read_csv(raw_features)
    calendar = features.loc[
        features["issue_year"].between(2019, 2023), ["issue", "issue_year"]
    ].copy()
    calendar["issue"] = calendar["issue"].astype(int)
    calendar["issue_year"] = calendar["issue_year"].astype(int)
    features = features[features["issue_year"].between(2019, 2023)].copy()
    features.to_csv(target / "issue209_features_2019_2023.csv", index=False)

    raw_176 = root / "results/bj176_issue_equity_risk_v1/issue_time_series.csv.gz"
    raw_151 = (
        root
        / "results/bj151_gate_b_outcome_settlement_v1/issue_m_grid_settlement.csv.gz"
    )
    raw_190 = (
        root
        / "results/bj190_gate_b_sparse_divergence_v1/issue_arm_settlement_d_direction_only.csv.gz"
    )

    source_176 = pd.read_csv(raw_176)
    mapping = {
        "BEST_FULL_FULL": "FULL_CONTROL",
        "MODEL_SOURCE_MODEL_CAP1_M512": "SMOOTH_M512",
        "Q_SOURCE_Q_TOP_MASS_M192": "Q_TAIL_M192",
    }
    source_176 = source_176[
        source_176["support_view"].eq("NATIVE_SELECTOR")
        & source_176["arm_id"].isin(mapping)
    ].copy()
    source_176["expert_id"] = source_176["arm_id"].map(mapping)
    source_176 = source_176.rename(
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
    ].merge(calendar, on=["issue", "issue_year"], how="inner", validate="many_to_one")
    source_176.to_csv(target / "issue176_experts_2019_2023.csv", index=False)

    source_151 = pd.read_csv(raw_151, low_memory=False)
    source_151 = source_151[
        source_151["sampling_role"].eq("SENSITIVITY_WOR_FIXED_CANDIDATE")
        & source_151["ticket_mechanism"].eq("Q_INFORMED_WOR_DISTINCT")
        & source_151["M"].eq(64)
    ].copy()
    source_151["expert_id"] = "Q_WOR_M64"
    source_151 = source_151.rename(
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
    ].merge(calendar, on=["issue", "issue_year"], how="inner", validate="many_to_one")
    source_151.to_csv(target / "issue151_wor_m64_2019_2023.csv", index=False)

    source_190 = pd.read_csv(raw_190, low_memory=False)
    source_190 = source_190[source_190["policy_id"].eq("DP_5970cc7b2874743a5698")]
    source_190 = (
        source_190.rename(columns={"year": "issue_year"})
        .groupby(["issue", "issue_year"], as_index=False)
        .agg(
            stake_unit_cny=("stake_yuan", "sum"),
            pnl_unit_cny=("pre_tax_net_yuan", "sum"),
            gross_unit_cny=("gross_pre_tax_yuan", "sum"),
            hit_count=("hit_ticket_count", "sum"),
        )
    )
    source_190["expert_id"] = "DIVERGENCE_Z100_K1"
    source_190 = source_190.merge(
        calendar, on=["issue", "issue_year"], how="inner", validate="one_to_one"
    )
    source_190.to_csv(target / "issue190_z100_k1_2019_2023.csv", index=False)

    for path in sorted(target.glob("*.csv")):
        frame = pd.read_csv(path)
        if frame["issue_year"].max() > 2023:
            raise AssertionError(f"projection contains a sealed row: {path}")
        print(path, len(frame))
    manifest = {
        "issue": 296,
        "boundary": "projection construction reads broad ledgers; model runner does not",
        "source_sha256": {
            str(path.relative_to(root)): _sha256(path)
            for path in [raw_features, raw_176, raw_151, raw_190]
        },
        "projection_sha256": {
            path.name: _sha256(path) for path in sorted(target.glob("*.csv"))
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
