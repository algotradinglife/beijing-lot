"""Build and verify the #254 reproducible source-schema handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from physical_schema import build_representative_package, resolve_data_root, verify_package
from source_schema import publication

PACKAGE_NAME = "bj254_schema_integration_v2"
CONTRACT_VERSION = "BJ-UNIFIED-SCHEMA-INTEGRATION-001-v2"
ROOT = Path(__file__).resolve().parents[2]


class IntegrationError(ValueError):
    """Raised when the final integration handoff loses an accepted boundary."""


_PREDECESSORS = (
    (250, "60a2edc3b45ba092dd6eff2e9d1b177d0c096222", "99701cf984797db2646033c03467e404bfd8ecc8", "results/bj250_source_census_v3/MANIFEST.json"),
    (251, "277dc11140bf2694dd1383f9f05957558c697da6", "63729bc01c830f9a651ae55861c22b32a58bf3e6", "results/bj251_canonical_identity_evidence_v3/MANIFEST.json"),
    (252, "596d044cfb178710d3b533f66e0c439f50d3faf5", "17be9fdaef38e682ff88bd4d5f03f86771e920e1", "results/bj252_unified_temporal_semantics_v3/MANIFEST.json"),
    (253, "a086c4750b678f24f578c2fa8ee3032bdb9c02e2", "82fba7ed95354a5cf1f1087e3b640cfa28f46e4f", "results/bj253_physical_schema_v1/MANIFEST.json"),
)

# These are execution-readiness statements for the recovery issues, not claims
# that their eventual model inputs are already complete.
DOWNSTREAM_CONTRACTS = (
    (235, "BJ_SP_RECOVERY", "AFTER_234_CLOSE", "PI_USER_CHECKPOINT", "RECOVERY_REQUIRED", "issue_slot|observation|feature_cell", "historical_proxy|strict_forward", "M×3 schema; initial/10h/1h proxy semantics; strict sample", "Full historical native-line/SP panel is absent; #235 exists to build it."),
    (236, "EU_ODDS_RECOVERY", "AFTER_234_CLOSE", "PI_USER_CHECKPOINT", "RECOVERY_REQUIRED", "issue_slot|observation|feature_cell", "historical_proxy|strict_forward", "Aggregate 1X2 proxy plus strict EU sample", "Bookmaker-level history and non-zero BJ-line translation inputs are absent; #236 exists to recover them."),
    (237, "POWER_FEATURE_SUPPORT", "AFTER_234_CLOSE", "PI_SCOPE_REVIEW", "IDENTITY_GAP", "issue_slot|snapshot_manifest|feature_cell", "historical_proxy|strict_forward", "Issue-local slot identity and causal feature interface", "Canonical real-world team/competition IDs remain unavailable; #237 must freeze a lawful identity recovery path before modeling."),
    (248, "FORWARD_SNAPSHOTS", "AFTER_234_CLOSE", "READY_TO_IMPLEMENT", "COLLECTION_REQUIRED", "source_registry|observation|feature_cell|snapshot_manifest", "strict_forward", "Append-only strict-forward schema and live sample", ""),
    (249, "PORTABILITY", "AFTER_234_CLOSE", "READY_TO_IMPLEMENT", "PORTABILITY_REQUIRED", "control.sqlite|features/m3_feature_cells.parquet|labels/labels.sqlite|MANIFEST.json", "both", "Portable external-root package", ""),
)

DOWNSTREAM_COLUMNS = [
    "issue",
    "consumer",
    "graph_release",
    "execution_readiness",
    "model_data_readiness",
    "required_surfaces",
    "causal_grades",
    "available_now",
    "deterministic_blocker_reason",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inventory(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path != package / "MANIFEST.json"
    }


def _predecessors(repo_root: Path = ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue, accepted_head, merge_commit, artifact in _PREDECESSORS:
        path = repo_root / artifact
        if not path.is_file():
            raise IntegrationError(f"accepted predecessor artifact is missing: {artifact}")
        rows.append(
            {
                "issue": issue,
                "accepted_head": accepted_head,
                "merge_commit": merge_commit,
                "artifact": artifact,
                "artifact_sha256": _sha256(path),
            }
        )
    return rows


def _contracts_frame() -> pd.DataFrame:
    return pd.DataFrame(DOWNSTREAM_CONTRACTS, columns=DOWNSTREAM_COLUMNS)


def _data_dictionary_frame(snapshot: Path) -> pd.DataFrame:
    """Derive a compact dictionary from the actual SQLite and Parquet schemas."""
    rows: list[dict[str, object]] = []
    for store, database in (
        ("control_sqlite", snapshot / "control.sqlite"),
        ("label_sqlite", snapshot / "labels" / "labels.sqlite"),
    ):
        connection = sqlite3.connect(
            f"file:{database}?mode=ro&immutable=1", uri=True
        )
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            for table in tables:
                for _, name, field_type, not_null, default, primary_key in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ):
                    rows.append(
                        {
                            "store": store,
                            "surface": table,
                            "field": name,
                            "physical_type": field_type,
                            "nullable": not bool(not_null or primary_key),
                            "default": "" if default is None else str(default),
                            "semantic_boundary": "post_outcome_label"
                            if store == "label_sqlite"
                            else "pre_event_control_or_feature",
                        }
                    )
        finally:
            connection.close()
    for store, parquet_path in (
        ("feature_parquet", snapshot / "features" / "m3_feature_cells.parquet"),
        ("label_parquet", snapshot / "labels" / "settlement_labels.parquet"),
    ):
        for field in pq.read_schema(parquet_path):
            rows.append(
                {
                    "store": store,
                    "surface": parquet_path.name,
                    "field": field.name,
                    "physical_type": str(field.type),
                    "nullable": field.nullable,
                    "default": "",
                    "semantic_boundary": "post_outcome_label"
                    if store == "label_parquet"
                    else "pre_event_model_input",
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["store", "surface", "field"], kind="stable"
    ).reset_index(drop=True)


def _proxy_years(snapshot: Path) -> list[int]:
    features = pd.read_parquet(snapshot / "features" / "m3_feature_cells.parquet")
    issue_codes = features.loc[
        features["namespace"].eq("historical_proxy"), "issue_code"
    ].astype("string")
    return sorted({2000 + int(code[:2]) for code in issue_codes if len(code) >= 2})


def _req_evidence_frame(proxy_years: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("REQ-IN01", "PASS", "four predecessor accepted HEADs, merge commits, artifacts and SHA-256 values bound"),
            ("REQ-IN02", "PASS", f"deterministic representative proxy years={proxy_years} plus strict-forward sample"),
            ("REQ-IN03", "PASS", "combined physical verifier covers identity grain, temporal namespace, missingness and label isolation"),
            ("REQ-IN04", "PASS", "five-consumer machine-readable execution/model-data readiness matrix"),
            ("REQ-IN05", "PASS", "historical_proxy and strict_forward stay separate in schema, receipt and report"),
            ("REQ-IN06", "PASS", "absolute external-root build and clean isolated restore-copy verification"),
            ("REQ-IN07", "PASS", "executed notebook plus PI decision report and data dictionary"),
            ("REQ-IN08", "PENDING_EV", "focused adversarial tests complete; independent EV requested at final PR HEAD"),
        ],
        columns=["requirement", "status", "evidence"],
    )


def _verify_contract_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype="string").fillna("")
    expected = _contracts_frame().astype("string")
    if list(frame.columns) != list(expected.columns) or not frame.equals(expected):
        raise IntegrationError("downstream contract matrix is incomplete or changed")
    return frame


def _verify_data_dictionary(path: Path, snapshot: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype="string").fillna("")
    expected = _data_dictionary_frame(snapshot).astype("string").fillna("")
    if list(frame.columns) != list(expected.columns) or not frame.equals(expected):
        raise IntegrationError("data dictionary does not match the physical stores")
    return frame


def build_integration_package(data_root: str | Path | None = None, *, output: str | Path | None = None) -> Path:
    """Build a clean, external-root package containing the normalized snapshot and handoff."""
    root = resolve_data_root(data_root)
    target = Path(output).resolve() if output is not None else root / "derived" / PACKAGE_NAME

    def populate(staging: Path) -> None:
        snapshot = build_representative_package(
            root,
            output=staging / "normalized_snapshot",
            force=True,
            multi_year_proxy=True,
        )
        physical_receipt = verify_package(snapshot)
        predecessors = _predecessors()
        proxy_years = _proxy_years(snapshot)
        if len(proxy_years) < 2:
            raise IntegrationError("representative historical proxy is not multi-year")
        publication.atomic_write_json(staging / "predecessors.json", predecessors)
        publication.atomic_write_csv(_contracts_frame(), staging / "downstream_readiness.csv")
        publication.atomic_write_csv(
            _data_dictionary_frame(snapshot), staging / "data_dictionary.csv"
        )
        publication.atomic_write_csv(
            _req_evidence_frame(proxy_years), staging / "req_in_evidence.csv"
        )
        publication.atomic_write_json(staging / "physical_receipt.json", physical_receipt)
        with tempfile.TemporaryDirectory(prefix="bj254-replay-", dir=root) as replay_dir:
            replay = build_representative_package(
                root,
                output=Path(replay_dir) / "normalized_snapshot",
                force=True,
                multi_year_proxy=True,
            )
            replay_equal = _inventory(snapshot) == _inventory(replay)
        if not replay_equal:
            raise IntegrationError("representative physical replay is not byte-deterministic")
        with tempfile.TemporaryDirectory(prefix="bj254-restore-", dir=root) as restore_dir:
            restored = Path(restore_dir) / "normalized_snapshot"
            shutil.copytree(snapshot, restored)
            restore_physical = verify_package(restored)
            restore_equal = _inventory(snapshot) == _inventory(restored)
        if not restore_equal or restore_physical != physical_receipt:
            raise IntegrationError("external-root restore-copy verification failed")
        replay_receipt = {
            "byte_deterministic_replay": replay_equal,
            "restore_copy_verified": restore_equal,
            "historical_proxy_years": proxy_years,
            "strict_forward_feature_cells": physical_receipt[
                "namespace_feature_cells"
            ].get("strict_forward", 0),
        }
        publication.atomic_write_json(staging / "replay_receipt.json", replay_receipt)
        report = "\n".join([
            "# #254 final integration decision", "",
            "Historical proxy and strict-forward rows share a long M×3 shape but remain separate namespaces.",
            "The representative snapshot is an interface demonstration, not a full-history readiness claim.",
            "Settlement labels are physically separate and excluded from the feature reader.",
            "",
            "## Executed receipt", "",
            f"- Historical proxy years: {', '.join(map(str, proxy_years))}.",
            f"- Feature cells: {physical_receipt['feature_cells']} ({physical_receipt['missing_feature_cells']} explicitly missing).",
            "- Byte-deterministic rebuild: PASS.",
            "- Isolated restore-copy verification: PASS.",
            "",
            "## PI interpretation", "",
            "Historical exploration: only the declared historical-proxy European 1X2 lane.",
            "Forward validation: only poll-start strict-forward rows, bounded by current-schedule semantics.",
            "#235/#236 are ready for their PI/user recovery checkpoint after #234 closes; missing data is their objective, not a circular blocker.",
            "#237 needs an explicit identity-recovery decision because real-world team/competition IDs remain unavailable.",
            "#248/#249 may consume the interface but retain their own collection/portability evidence gates.",
        ]) + "\n"
        publication.atomic_write_text(staging / "DECISION_REPORT.md", report)
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "data_root_interface": "BEIJING_LOT_DATA_ROOT",
            "normalized_snapshot": "normalized_snapshot",
            "predecessors": predecessors,
            "downstream_contract_issues": [row[0] for row in DOWNSTREAM_CONTRACTS],
            "physical_receipt": physical_receipt,
            "replay_receipt": replay_receipt,
            "files": _inventory(staging),
        }
        publication.atomic_write_json(staging / "MANIFEST.json", manifest)
        verify_integration_package(staging)

    return publication.atomic_publish_directory(target, populate, force=True)


def verify_integration_package(package: str | Path) -> dict[str, Any]:
    """Verify all predecessor bindings, downstream interfaces, and physical invariants."""
    package = Path(package)
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise IntegrationError("integration contract version mismatch")
    if manifest.get("data_root_interface") != "BEIJING_LOT_DATA_ROOT":
        raise IntegrationError("integration external-root interface mismatch")
    if manifest.get("files") != _inventory(package):
        raise IntegrationError("integration manifest hash closure mismatch")
    expected_predecessors = _predecessors()
    recorded = json.loads((package / "predecessors.json").read_text(encoding="utf-8"))
    if recorded != expected_predecessors or manifest.get("predecessors") != expected_predecessors:
        raise IntegrationError("accepted predecessor binding mismatch")
    contracts = _verify_contract_frame(package / "downstream_readiness.csv")
    if manifest.get("downstream_contract_issues") != [row[0] for row in DOWNSTREAM_CONTRACTS]:
        raise IntegrationError("downstream interface list mismatch")
    physical = verify_package(package / "normalized_snapshot")
    if manifest.get("physical_receipt") != physical:
        raise IntegrationError("physical receipt mismatch")
    dictionary = _verify_data_dictionary(
        package / "data_dictionary.csv", package / "normalized_snapshot"
    )
    req_evidence = pd.read_csv(package / "req_in_evidence.csv", dtype="string")
    if list(req_evidence["requirement"]) != [f"REQ-IN{index:02d}" for index in range(1, 9)]:
        raise IntegrationError("REQ evidence is incomplete")
    if not req_evidence.loc[:6, "status"].eq("PASS").all() or req_evidence.loc[7, "status"] not in {
        "PENDING_EV",
        "PASS",
    }:
        raise IntegrationError("REQ evidence status is invalid")
    replay = json.loads((package / "replay_receipt.json").read_text(encoding="utf-8"))
    if (
        not replay.get("byte_deterministic_replay")
        or not replay.get("restore_copy_verified")
        or len(replay.get("historical_proxy_years", [])) < 2
        or replay.get("strict_forward_feature_cells", 0) <= 0
        or manifest.get("replay_receipt") != replay
    ):
        raise IntegrationError("replay/restore receipt is incomplete")
    return {
        "status": "PASS",
        "predecessors": len(expected_predecessors),
        "downstream_contracts": len(contracts),
        "dictionary_fields": len(dictionary),
        "replay_receipt": replay,
        "physical_receipt": physical,
    }
