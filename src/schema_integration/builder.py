"""Build and verify the #254 reproducible source-schema handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from physical_schema import build_representative_package, resolve_data_root, verify_package
from source_schema import publication

PACKAGE_NAME = "bj254_schema_integration_v1"
CONTRACT_VERSION = "BJ-UNIFIED-SCHEMA-INTEGRATION-001-v1"
ROOT = Path(__file__).resolve().parents[2]


class IntegrationError(ValueError):
    """Raised when the final integration handoff loses an accepted boundary."""


_PREDECESSORS = (
    (250, "99701cf984797db2646033c03467e404bfd8ecc8", "results/bj250_source_census_v3/MANIFEST.json"),
    (251, "63729bc01c830f9a651ae55861c22b32a58bf3e6", "results/bj251_canonical_identity_evidence_v3/MANIFEST.json"),
    (252, "17be9fdaef38e682ff88bd4d5f03f86771e920e1", "results/bj252_unified_temporal_semantics_v3/MANIFEST.json"),
    (253, "a086c4750b678f24f578c2fa8ee3032bdb9c02e2", "results/bj253_physical_schema_v1/MANIFEST.json"),
)

# This is intentionally a complete declared interface, not a best-effort summary.
DOWNSTREAM_CONTRACTS = (
    (235, "BJ_SP_RECOVERY", "issue_slot_id|observation|feature_cell", "strict_forward|historical_proxy", "BLOCKED", "Need append-only native-line and three-SP observations; prototype sample is not a recovery panel."),
    (236, "EU_ODDS_RECOVERY", "issue_slot_id|observation|feature_cell", "strict_forward|historical_proxy", "BLOCKED", "Need bookmaker-level/translation inputs; prototype contains only aggregate 1X2 surfaces."),
    (237, "POWER_FEATURE_SUPPORT", "issue_slot_id|snapshot_manifest|feature_cell", "historical_proxy|strict_forward", "BLOCKED", "Real-world team/competition IDs remain unavailable; do not manufacture joins from labels."),
    (248, "FORWARD_SNAPSHOTS", "source_registry|observation|feature_cell|snapshot_manifest", "strict_forward", "READY_INTERFACE", "Schema is ready; prospective collector must supply raw capture, receive clock, sale state, and per-cell lineage."),
    (249, "PORTABILITY", "control.sqlite|features/m3_feature_cells.parquet|labels/labels.sqlite|MANIFEST.json", "both", "READY_INTERFACE", "Schema package is portable; snapshot/restore implementation and a WSL dry run remain required."),
)


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
        if path.is_file() and path.name != "MANIFEST.json"
    }


def _predecessors(repo_root: Path = ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for issue, commit, artifact in _PREDECESSORS:
        path = repo_root / artifact
        if not path.is_file():
            raise IntegrationError(f"accepted predecessor artifact is missing: {artifact}")
        rows.append({"issue": issue, "accepted_commit": commit, "artifact": artifact, "artifact_sha256": _sha256(path)})
    return rows


def _contracts_frame() -> pd.DataFrame:
    return pd.DataFrame(DOWNSTREAM_CONTRACTS, columns=["issue", "consumer", "required_surfaces", "causal_grades", "readiness", "deterministic_blocker_reason"])


def _verify_contract_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype="string").fillna("")
    expected = _contracts_frame().astype("string")
    if list(frame.columns) != list(expected.columns) or not frame.equals(expected):
        raise IntegrationError("downstream contract matrix is incomplete or changed")
    return frame


def build_integration_package(data_root: str | Path | None = None, *, output: str | Path | None = None) -> Path:
    """Build a clean, external-root package containing the normalized snapshot and handoff."""
    root = resolve_data_root(data_root)
    target = Path(output).resolve() if output is not None else root / "derived" / PACKAGE_NAME

    def populate(staging: Path) -> None:
        snapshot = build_representative_package(root, output=staging / "normalized_snapshot", force=True)
        physical_receipt = verify_package(snapshot)
        predecessors = _predecessors()
        publication.atomic_write_json(staging / "predecessors.json", predecessors)
        publication.atomic_write_csv(_contracts_frame(), staging / "downstream_readiness.csv")
        publication.atomic_write_json(staging / "physical_receipt.json", physical_receipt)
        report = "\n".join([
            "# #254 final integration decision", "",
            "Historical proxy and strict-forward rows share a long M×3 shape but remain separate namespaces.",
            "The representative snapshot is an interface demonstration, not a full-history readiness claim.",
            "Settlement labels are physically separate and excluded from the feature reader.",
            "",
            "## PI interpretation", "",
            "Historical exploration: only the declared historical-proxy European 1X2 lane.",
            "Forward validation: only poll-start strict-forward rows, bounded by current-schedule semantics.",
            "#235/#236/#237 remain data-limited; #248/#249 may consume the interface but retain their own evidence gates.",
        ]) + "\n"
        publication.atomic_write_text(staging / "DECISION_REPORT.md", report)
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "data_root_interface": "BEIJING_LOT_DATA_ROOT",
            "normalized_snapshot": "normalized_snapshot",
            "predecessors": predecessors,
            "downstream_contract_issues": [row[0] for row in DOWNSTREAM_CONTRACTS],
            "physical_receipt": physical_receipt,
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
    return {"status": "PASS", "predecessors": len(expected_predecessors), "downstream_contracts": len(contracts), "physical_receipt": physical}
