"""Fail-closed G0-to-B0/B1 binding for SCORE-HCAP-HIST-001.

B0/B1 must never score an operator-supplied panel.  It receives the panel
path only after the G0 package, its exact manifest assets, the G0 decision,
and the read-only source snapshot have all been independently verified.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .g0 import ELIGIBLE_SETTLEMENT_QUALITIES, FOLD_MAPPING
from src.research_freeze_protocol import ResearchFreezeError, sha256_file, verify_freeze_package


G0_EXPERIMENT_ID = "SCORE-HCAP-HIST-001-G0"
B0_B1_EXPERIMENT_ID = "SCORE-HCAP-HIST-001-B0-B1"
_G0_INPUTS = (
    "historical_panel.sqlite",
    "source_schema.json",
    "g0_audit.json",
    "feature_availability_matrix.csv",
)


@dataclass(frozen=True)
class G0Binding:
    """Verified immutable identities B0/B1 is permitted to consume."""

    g0_freeze_id: str
    g0_manifest_sha256: str
    g0_sha256s_sha256: str
    panel: Path
    panel_sha256: str
    source_database_bytes: int
    source_database_sha256: str
    feature_matrix_sha256: str
    audit_sha256: str

    def as_config(self) -> dict[str, Any]:
        return {
            "g0_freeze_id": self.g0_freeze_id,
            "g0_manifest_sha256": self.g0_manifest_sha256,
            "g0_sha256s_sha256": self.g0_sha256s_sha256,
            "g0_panel_sha256": self.panel_sha256,
            "source_database": {
                "bytes": self.source_database_bytes,
                "sha256": self.source_database_sha256,
            },
            "feature_availability_matrix_sha256": self.feature_matrix_sha256,
            "g0_audit_sha256": self.audit_sha256,
        }


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchFreezeError(f"invalid {label}") from exc
    if not isinstance(value, dict):
        raise ResearchFreezeError(f"invalid {label}")
    return value


def _regular_file(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink() or not expanded.is_file():
        raise ResearchFreezeError(f"{label} must be a regular file: {path}")
    return expanded.resolve()


def _asset(manifest: Mapping[str, Any], package: Path, name: str) -> tuple[Path, dict[str, Any]]:
    snapshot = manifest.get("dataset_snapshot")
    assets = snapshot.get("files") if isinstance(snapshot, dict) else None
    expected_path = f"inputs/{name}"
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("path") == expected_path] if isinstance(assets, list) else []
    if len(matches) != 1:
        raise ResearchFreezeError(f"G0 freeze must contain exactly one {expected_path}")
    asset = matches[0]
    target = _regular_file(package / expected_path, expected_path)
    expected_sha = asset.get("sha256")
    expected_bytes = asset.get("bytes")
    if not isinstance(expected_sha, str) or not isinstance(expected_bytes, int):
        raise ResearchFreezeError(f"invalid G0 asset record for {expected_path}")
    if target.stat().st_size != expected_bytes or sha256_file(target) != expected_sha:
        raise ResearchFreezeError(f"G0 asset digest mismatch: {expected_path}")
    return target, asset


def _identity(value: object, label: str) -> tuple[int, str]:
    if not isinstance(value, dict):
        raise ResearchFreezeError(f"invalid {label} identity")
    size, digest = value.get("bytes"), value.get("sha256")
    if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
        raise ResearchFreezeError(f"invalid {label} identity")
    return size, digest


def require_bound_panel(panel: Path, binding: G0Binding) -> Path:
    """Reject any byte stream other than the exact verified G0 panel."""

    candidate = _regular_file(panel, "B0/B1 panel")
    if sha256_file(candidate) != binding.panel_sha256:
        raise ResearchFreezeError("B0/B1 panel SHA-256 does not equal the verified G0 panel")
    return candidate


def verified_g0_binding(*, g0_freeze_dir: Path, source_db: Path) -> G0Binding:
    """Return the only legal panel after validating all G0/source links."""

    package = g0_freeze_dir.expanduser().resolve()
    verification = verify_freeze_package(package)
    if verification["experiment_id"] != G0_EXPERIMENT_ID:
        raise ResearchFreezeError("B0/B1 requires a SCORE-HCAP-HIST-001-G0 freeze")
    manifest = _read_json(package / "manifest.json", "G0 manifest")
    config_asset = manifest.get("config")
    if not isinstance(config_asset, dict) or not isinstance(config_asset.get("path"), str):
        raise ResearchFreezeError("invalid G0 config asset")
    g0_config = _read_json(package / str(config_asset["path"]), "G0 config")
    if g0_config.get("fold_mapping") != FOLD_MAPPING or g0_config.get("eligible_settlement_qualities") != list(ELIGIBLE_SETTLEMENT_QUALITIES):
        raise ResearchFreezeError("G0 config does not freeze chronology and settlement eligibility")
    panel, panel_asset = _asset(manifest, package, "historical_panel.sqlite")
    _schema, _ = _asset(manifest, package, "source_schema.json")
    audit_path, audit_asset = _asset(manifest, package, "g0_audit.json")
    matrix_path, matrix_asset = _asset(manifest, package, "feature_availability_matrix.csv")
    audit = _read_json(audit_path, "G0 audit")
    if audit.get("experiment_id") != "SCORE-HCAP-HIST-001" or audit.get("stage") != "G0":
        raise ResearchFreezeError("G0 audit has the wrong experiment identity")
    gate = audit.get("gate")
    if not isinstance(gate, dict) or gate.get("status") != "G0_ELIGIBLE_EVIDENCE_C" or gate.get("formal_b0_b1_authorized") is not True:
        raise ResearchFreezeError("G0 audit does not authorize formal B0/B1")
    coverage = audit.get("coverage")
    if not isinstance(coverage, dict) or coverage.get("qualified_panel_sha256") != panel_asset["sha256"]:
        raise ResearchFreezeError("G0 audit panel SHA-256 does not match the frozen panel")
    matrix = audit.get("feature_availability_matrix")
    if not isinstance(matrix, dict) or matrix.get("sha256") != matrix_asset["sha256"]:
        raise ResearchFreezeError("G0 audit feature matrix SHA-256 does not match the frozen matrix")
    audit_source_size, audit_source_sha = _identity(
        audit.get("provenance", {}).get("source_database") if isinstance(audit.get("provenance"), dict) else None,
        "G0 audit source database",
    )
    matrix_source_size, matrix_source_sha = _identity(matrix.get("source_database"), "feature matrix source database")
    if (matrix_source_size, matrix_source_sha) != (audit_source_size, audit_source_sha):
        raise ResearchFreezeError("feature matrix and G0 panel do not share one source database identity")
    datasets = manifest.get("input_dataset")
    if not isinstance(datasets, list) or len(datasets) != 1:
        raise ResearchFreezeError("G0 freeze must bind exactly one source database snapshot")
    manifest_source_size, manifest_source_sha = _identity(datasets[0], "G0 manifest source database")
    if (manifest_source_size, manifest_source_sha) != (audit_source_size, audit_source_sha):
        raise ResearchFreezeError("G0 manifest and audit do not share one source database identity")
    source = _regular_file(source_db, "source database")
    if source.stat().st_size != audit_source_size or sha256_file(source) != audit_source_sha:
        raise ResearchFreezeError("source database SHA-256 does not match the verified G0 snapshot")
    if sha256_file(matrix_path) != matrix_asset["sha256"] or sha256_file(audit_path) != audit_asset["sha256"]:
        raise ResearchFreezeError("G0 auxiliary artifact digest mismatch")
    return G0Binding(
        g0_freeze_id=str(verification["freeze_id"]),
        g0_manifest_sha256=str(verification["manifest_sha256"]),
        g0_sha256s_sha256=str(verification["sha256s_sha256"]),
        panel=panel,
        panel_sha256=str(panel_asset["sha256"]),
        source_database_bytes=audit_source_size,
        source_database_sha256=audit_source_sha,
        feature_matrix_sha256=str(matrix_asset["sha256"]),
        audit_sha256=str(audit_asset["sha256"]),
    )


def verify_b0_b1_package_binding(package_dir: Path, binding: G0Binding) -> None:
    """Confirm the published B0/B1 package retained the verified G0 panel."""

    package = package_dir.expanduser().resolve()
    verification = verify_freeze_package(package)
    if verification["experiment_id"] != B0_B1_EXPERIMENT_ID:
        raise ResearchFreezeError("wrong B0/B1 freeze experiment identity")
    manifest = _read_json(package / "manifest.json", "B0/B1 manifest")
    _panel, panel_asset = _asset(manifest, package, "historical_panel.sqlite")
    if panel_asset["sha256"] != binding.panel_sha256:
        raise ResearchFreezeError("published B0/B1 panel SHA-256 does not equal the verified G0 panel")
    config_path = package / str(manifest["config"]["path"])
    config = _read_json(config_path, "B0/B1 config")
    if config.get("g0_binding") != binding.as_config():
        raise ResearchFreezeError("published B0/B1 config does not retain the verified G0 binding")
    datasets = manifest.get("input_dataset")
    if not isinstance(datasets, list) or len(datasets) != 1:
        raise ResearchFreezeError("B0/B1 freeze must bind exactly one source database snapshot")
    source_size, source_sha = _identity(datasets[0], "B0/B1 source database")
    if (source_size, source_sha) != (binding.source_database_bytes, binding.source_database_sha256):
        raise ResearchFreezeError("published B0/B1 source snapshot does not match verified G0")
