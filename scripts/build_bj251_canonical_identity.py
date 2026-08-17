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


EVIDENCE_PACKAGE = "bj251_canonical_identity_evidence_v1"


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
        publication.atomic_write_csv(result.coverage, staging / "tables" / "coverage.csv")
        publication.atomic_write_csv(result.mapping.ledger, staging / "tables" / "ambiguity_ledger.csv")
        publication.atomic_write_csv(aliases, staging / "tables" / "temporal_aliases.csv")
        publication.atomic_write_csv(policy, staging / "tables" / "exceptional_case_policy.csv")
        read_boundary = {
            "source_columns_read": {key: list(value) for key, value in result.read_columns.items()},
            "prohibited_outcome_columns": ["result_code", "winning_sp", "outcome_code", "payout"],
            "outcome_exposed_inputs": False,
            "fuzzy_auto_acceptance": False,
        }
        publication.atomic_write_json(staging / "READ_BOUNDARY.json", read_boundary)
        manifest = {
            "contract_version": "BJ-UNIFIED-CANONICAL-IDENTITY-001-v1",
            "external_full_package": str(built),
            "external_sha256sums_sha256": external_sums,
            "fixture_count": int(len(result.mapping.fixtures)),
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


def verify_evidence(evidence: Path) -> None:
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
    package.verify_package(
        Path(manifest["external_full_package"]),
        trusted_anchor=str(manifest["external_sha256sums_sha256"]),
    )
    boundary = json.loads((evidence / "READ_BOUNDARY.json").read_text(encoding="utf-8"))
    if boundary.get("outcome_exposed_inputs") is not False or boundary.get("fuzzy_auto_acceptance") is not False:
        raise AssertionError("identity boundary verification failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--evidence-root", type=Path, default=ROOT / "results")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    evidence_root = args.evidence_root.resolve()
    if args.verify_only:
        evidence = evidence_root / EVIDENCE_PACKAGE
        verify_evidence(evidence)
        print(f"VERIFIED {evidence}")
        return
    full, evidence = build(_data_root(args.data_root), evidence_root)
    print(f"FULL_PACKAGE {full}")
    print(f"EVIDENCE_PACKAGE {evidence}")
    print(f"EVIDENCE_MANIFEST {evidence / 'MANIFEST.json'}")


if __name__ == "__main__":
    main()
