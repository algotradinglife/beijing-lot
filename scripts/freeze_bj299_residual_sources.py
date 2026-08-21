#!/usr/bin/env python3
"""Freeze the exact accepted BEST_FULL issue path to a pre-2024 projection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "results/bj190_gate_b_sparse_divergence_v1/issue_arm_settlement_b0_best_full.csv.gz"
)
OUTPUT = ROOT / "evidence/bj299_residual_sources_v1"
PROJECTION = OUTPUT / "best_full_2019_2023.csv"

RESIDUAL_SOURCES = [
    {
        "expert_id": "SMOOTH_M512",
        "path": "evidence/bj296_expert_sources_v1/issue176_experts_2019_2023.csv",
        "filter": "expert_id == SMOOTH_M512",
    },
    {
        "expert_id": "DIVERGENCE_Z100_K1",
        "path": "evidence/bj296_expert_sources_v1/issue190_z100_k1_2019_2023.csv",
        "filter": "expert_id == DIVERGENCE_Z100_K1",
    },
    {
        "expert_id": "RARE_LOGIT_TOP64",
        "path": "docs/research/artifacts/issue-291/ranking_issue_paths.csv",
        "filter": (
            "domain == BASE; model == DATA_LOGIT_RIDGE; score == DIRECT_PNL; "
            "ticket_budget_per_issue == 64"
        ),
    },
]

IDENTITY_COLUMNS = [
    "year",
    "issue_instance",
    "first_kickoff_ts",
    "arm",
    "gate_a_policy_status",
    "settlement_status",
    "n7_identity_sha256",
    "ticket_identity_sha256",
    "executed_ticket_count",
    "stake_yuan",
    "gross_pre_tax_yuan",
    "pre_tax_net_yuan",
    "hit_ticket_count",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    frame = pd.read_csv(SOURCE, compression="gzip")
    if not frame["arm"].eq("B0_BEST_FULL").all():
        raise AssertionError("source contains a non-BEST_FULL arm")
    uniqueness = frame.groupby("issue", sort=False)[IDENTITY_COLUMNS].nunique(
        dropna=False
    )
    if uniqueness.to_numpy().max() != 1:
        raise AssertionError("BEST_FULL economics differ across source policy aliases")
    projection = (
        frame.sort_values(["issue", "policy_id"])
        .drop_duplicates("issue")
        .loc[lambda value: value["year"].between(2019, 2023)]
        .rename(columns={"year": "issue_year"})
    )
    keep = ["issue", "issue_year", *[c for c in IDENTITY_COLUMNS if c != "year"]]
    projection = (
        projection[keep].sort_values(["issue_year", "issue"]).reset_index(drop=True)
    )
    if len(projection) != 270 or projection["issue"].duplicated().any():
        raise AssertionError("unexpected 2019-2023 BEST_FULL issue calendar")
    if not projection["issue_year"].between(2019, 2023).all():
        raise AssertionError("projection opened a sealed year")
    active = projection["stake_yuan"].gt(0)
    if not projection.loc[active, "stake_yuan"].eq(4374.0).all():
        raise AssertionError("active BEST_FULL row is not the atomic CNY4374 bundle")
    if not projection.loc[active, "executed_ticket_count"].eq(2187).all():
        raise AssertionError("active BEST_FULL row is not 2,187 FULL tickets")
    if (
        not projection.loc[
            ~active, ["stake_yuan", "gross_pre_tax_yuan", "pre_tax_net_yuan"]
        ]
        .eq(0)
        .all(axis=None)
    ):
        raise AssertionError("NO_BET row carries settlement economics")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    projection.to_csv(
        PROJECTION, index=False, float_format="%.12f", lineterminator="\n"
    )
    manifest = {
        "issue": 299,
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": _sha256(SOURCE),
        "projection": str(PROJECTION.relative_to(ROOT)),
        "projection_sha256": _sha256(PROJECTION),
        "rows": len(projection),
        "active_rows": int(active.sum()),
        "years": sorted(projection["issue_year"].unique().tolist()),
        "identity": "accepted #167/#170 B0_BEST_FULL reproduced by #134/#190",
        "residual_sources": [
            {**source, "sha256": _sha256(ROOT / source["path"])}
            for source in RESIDUAL_SOURCES
        ],
    }
    (OUTPUT / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
