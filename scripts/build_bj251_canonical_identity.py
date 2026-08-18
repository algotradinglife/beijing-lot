#!/usr/bin/env python3
"""Build the #251 canonical-identity package from read-only source tables.

The full trace package is deliberately written under the external data root:
it can be regenerated from the source databases and is not a Git raw-data
payload.  The committed evidence package contains the coverage/ledger/policy
summaries and hashes binding that external trace package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from canonical_identity import package, profile  # noqa: E402
from source_schema import publication  # noqa: E402


EVIDENCE_PACKAGE = "bj251_canonical_identity_evidence_v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _data_root(value: str | None) -> Path:
    raw = value or os.environ.get("BEIJING_LOT_DATA_ROOT")
    if not raw:
        raise ValueError("supply --data-root or BEIJING_LOT_DATA_ROOT")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    return root


def _specifications(data_root: Path) -> list[profile.SourceSpec]:
    return [
        profile.SourceSpec(
            source_id="beidan_xlsm_workbook",
            sqlite_path=data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite",
            table="matches",
            key_column="match_id",
            issue_column="issue",
            match_idx_column="match_idx",
            competition_column="league",
            home_column="home",
            away_column="away",
            kickoff_column="kickoff_ts",
            causal_grade="RETROSPECTIVE_PROXY",
        ),
        profile.SourceSpec(
            source_id="beidan_history_db",
            sqlite_path=data_root / "beidan_history.db",
            table="historical_matches",
            key_column="id",
            issue_column="issue",
            match_idx_column="match_idx",
            competition_column="league",
            home_column="home",
            away_column="away",
            kickoff_column="kickoff_ts",
            causal_grade="SETTLEMENT_ONLY",
        ),
        profile.SourceSpec(
            source_id="beidan_live_db",
            sqlite_path=data_root / "beidan_live.db",
            table="matches",
            key_column="match_id",
            issue_column="issue",
            match_idx_column="match_idx",
            competition_column="league",
            home_column="home",
            away_column="away",
            kickoff_column="kickoff_ts",
            causal_grade="STRICT_CAUSAL",
        ),
    ]


def _write_evidence(
    target: Path,
    built: Path,
    result: profile.ProfileResult,
    aliases: pd.DataFrame,
    policy: pd.DataFrame,
) -> Path:
    external_sums = _sha256(built / "SHA256SUMS.json")

    def populate(staging: Path) -> None:
        (staging / "tables").mkdir(parents=True)
        ledger_summary = (
            result.mapping.ledger.groupby(
                ["exception_class", "disposition", "source_id", "entity_kind"],
                dropna=False,
                as_index=False,
            )
            .size()
            .rename(columns={"size": "rows"})
        )
        ledger_sample = (
            result.mapping.ledger.sort_values(
                ["exception_class", "source_id", "source_key"], kind="stable"
            )
            .groupby("exception_class", group_keys=False)
            .head(10)
            .reset_index(drop=True)
        )
        alias_summary = (
            aliases.groupby(["alias_kind", "source_id"], as_index=False)
            .agg(
                observed_alias_rows=("source_alias", "size"),
                unique_source_aliases=("source_alias", "nunique"),
                unique_source_entities=("entity_id", "nunique"),
            )
        )
        alias_sample = (
            aliases.sort_values(
                ["alias_kind", "source_id", "source_alias"], kind="stable"
            )
            .groupby(["alias_kind", "source_id"], group_keys=False)
            .head(10)
            .reset_index(drop=True)
        )
        publication.atomic_write_csv(result.coverage, staging / "tables" / "coverage.csv")
        publication.atomic_write_csv(ledger_summary, staging / "tables" / "ambiguity_summary.csv")
        publication.atomic_write_csv(ledger_sample, staging / "tables" / "ambiguity_sample.csv")
        publication.atomic_write_csv(alias_summary, staging / "tables" / "temporal_alias_summary.csv")
        publication.atomic_write_csv(alias_sample, staging / "tables" / "temporal_alias_sample.csv")
        publication.atomic_write_csv(policy, staging / "tables" / "exceptional_case_policy.csv")
        read_boundary = {
            "source_columns_read": {key: list(value) for key, value in result.read_columns.items()},
            "prohibited_outcome_columns": ["result_code", "winning_sp", "outcome_code", "payout"],
            "outcome_exposed_inputs": False,
            "fuzzy_auto_acceptance": False,
        }
        publication.atomic_write_json(staging / "READ_BOUNDARY.json", read_boundary)
        manifest = {
            "contract_version": "BJ-UNIFIED-CANONICAL-IDENTITY-001-v2",
            "external_data_root_env": "BEIJING_LOT_DATA_ROOT",
            "external_package_relative": f"derived/{package.PACKAGE_NAME}",
            "external_sha256sums_sha256": external_sums,
            "issue_count": int(len(result.mapping.issues)),
            "issue_slot_count": int(len(result.mapping.slots)),
            "play_count": int(len(result.mapping.plays)),
            "outcome_cell_count": int(len(result.mapping.outcome_cells)),
            "trace_count": int(len(result.mapping.traces)),
            "exception_count": int(len(result.mapping.ledger)),
            "disposition": "CANDIDATE_PENDING_PI_ACCEPTANCE",
        }
        publication.atomic_write_json(staging / "MANIFEST.json", manifest)
        sums = {
            item.relative_to(staging).as_posix(): _sha256(item)
            for item in sorted(staging.rglob("*"))
            if item.is_file()
        }
        publication.atomic_write_json(staging / "SHA256SUMS.json", sums)

    return publication.atomic_publish_directory(target, populate, force=True)


def build(data_root: Path, evidence_root: Path) -> tuple[Path, Path]:
    result = profile.profile_sources(_specifications(data_root))
    aliases = profile.derive_temporal_aliases(result.mapping.traces)
    policy = profile.exceptional_case_policy()
    full = package.build_package(data_root / "derived", result.mapping, result.coverage, aliases)
    package.verify_package(full)
    evidence = _write_evidence(evidence_root / EVIDENCE_PACKAGE, full, result, aliases, policy)
    return full, evidence


def verify_evidence(evidence: Path, data_root: Path) -> None:
    """Verify committed evidence plus the externally regenerated full trace."""
    recorded = json.loads((evidence / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        item.relative_to(evidence).as_posix(): _sha256(item)
        for item in sorted(evidence.rglob("*"))
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    if recorded != actual:
        raise AssertionError("evidence package hash verification failed")
    manifest = json.loads((evidence / "MANIFEST.json").read_text(encoding="utf-8"))
    external = data_root / str(manifest["external_package_relative"])
    package.verify_package(
        external,
        trusted_anchor=str(manifest["external_sha256sums_sha256"]),
    )
    boundary = json.loads((evidence / "READ_BOUNDARY.json").read_text(encoding="utf-8"))
    if boundary.get("outcome_exposed_inputs") is not False or boundary.get("fuzzy_auto_acceptance") is not False:
        raise AssertionError("identity boundary verification failed")
    prohibited = set(boundary.get("prohibited_outcome_columns", []))
    if prohibited != {"result_code", "winning_sp", "outcome_code", "payout"}:
        raise AssertionError("unexpected prohibited-outcome contract")
    read_columns = boundary.get("source_columns_read")
    if not isinstance(read_columns, dict) or any(
        prohibited & set(columns) for columns in read_columns.values()
    ):
        raise AssertionError("outcome-exposed source column entered the identity read boundary")
    full_ledger = pd.read_csv(
        external / "tables" / "ambiguity_ledger.csv", dtype=str, keep_default_na=False
    )
    expected_ledger_summary = (
        full_ledger.groupby(
            ["exception_class", "disposition", "source_id", "entity_kind"],
            dropna=False,
            as_index=False,
        )
        .size()
        .rename(columns={"size": "rows"})
    )
    committed_ledger_summary = pd.read_csv(
        evidence / "tables" / "ambiguity_summary.csv", keep_default_na=False
    )
    full_aliases = pd.read_csv(
        external / "tables" / "temporal_aliases.csv", dtype=str, keep_default_na=False
    )
    expected_alias_summary = (
        full_aliases.groupby(["alias_kind", "source_id"], as_index=False)
        .agg(
            observed_alias_rows=("source_alias", "size"),
            unique_source_aliases=("source_alias", "nunique"),
            unique_source_entities=("entity_id", "nunique"),
        )
    )
    committed_alias_summary = pd.read_csv(
        evidence / "tables" / "temporal_alias_summary.csv", keep_default_na=False
    )
    for label, committed, expected in (
        ("coverage", pd.read_csv(evidence / "tables" / "coverage.csv"), pd.read_csv(external / "tables" / "coverage.csv")),
        ("ambiguity summary", committed_ledger_summary, expected_ledger_summary),
        ("temporal alias summary", committed_alias_summary, expected_alias_summary),
    ):
        try:
            pd.testing.assert_frame_equal(committed, expected, check_dtype=False)
        except AssertionError as error:
            raise AssertionError(f"evidence/full-package mismatch: {label}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "results")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    evidence_root = args.evidence_root.resolve()
    if args.verify_only:
        evidence = evidence_root / EVIDENCE_PACKAGE
        verify_evidence(evidence, _data_root(args.data_root))
        print(f"VERIFIED {evidence}")
        return
    full, evidence = build(_data_root(args.data_root), evidence_root)
    print(f"FULL_PACKAGE {full}")
    print(f"EVIDENCE_PACKAGE {evidence}")
    print(f"EVIDENCE_MANIFEST {evidence / 'MANIFEST.json'}")


if __name__ == "__main__":
    main()
