#!/usr/bin/env python3
"""Freeze #193 Gate-A v2.1 P/Q structural-delete amendment.

This additive package corrects only the derived compatibility/builder binding
for the two accepted #167 structural controls.  It verifies and reads Gate-A
pre-event sources only; it cannot settle outcomes or report economics.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import os
import shutil
import sys
import uuid
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence


# Replaying the immutable package must not mutate it with import bytecode.
sys.dont_write_bytecode = True


CONTRACT = "BJ-HIST-N7-REGIME-META-POLICY-001"
VERSION = "bj193-gate-a-chain-interface-v2.1"
V2_PACKAGE = "bj193_gate_a_chain_interface_v2"
V2_MANIFEST_SHA256 = (
    "6a44f4b1b355f5476328424bc8d92271d61d585643d40ca42bb56ffda1c43933"
)
V2_CONTENT_SHA256 = (
    "a5f274f92edbff194be9ce60fa707196d20d255b608b08bf22c3f0d924bb7425"
)
V2_PORTABLE_SHA256 = (
    "2bd83000fabf0a4817a31964a02c881562489651cc98143c716aa09ac8dd92bd"
)
MATCH_VECTOR_SHA256 = (
    "d80eaedc0062eea6929c00fbfb08eef9a02445edc1f533a394a35c238ccf2b56"
)
ROLE_VECTOR_SHA256 = (
    "1a6ac41e5e34c400c5c2a62f9799e2f76d56f4aaa3d13b67b88505443788cdaa"
)
MIN_CHRONOLOGICAL_SUPPORT = 20
MIN_CHRONOLOGICAL_FOLDS = 5
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: no result, final/winning SP, payout, tax "
    "realization, ROI, settlement, or post-cutoff evidence is read or emitted"
)


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
DEFAULT_OUTPUT = ROOT / "results" / "bj193_gate_a_chain_interface_v21"
V2_SCRIPT = ROOT / "results" / V2_PACKAGE / "freeze_runner.py"
PACKAGED_ADAPTER = Path(__file__).resolve().with_name(
    "structural_delete_adapter.py"
)
ADAPTER_PATH = (
    PACKAGED_ADAPTER
    if PACKAGED_ADAPTER.exists()
    else ROOT / "scripts" / "bj193_structural_delete_adapter.py"
)
MATCH_VECTOR_PATH = (
    ROOT / "results" / "bj137_gate_a_preoutcome_v2" / "match_vectors.csv"
)
ROLE_VECTOR_PATH = (
    ROOT / "results" / "bj137_gate_a_preoutcome_v2" / "n7_role_vectors.csv.gz"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_payload_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(iter_csv(path))


def write_csv(
    path: Path,
    fields: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(
    path: Path,
    fields: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as compressed:
            with io.TextIOWrapper(
                compressed, encoding="utf-8", newline=""
            ) as text:
                writer = csv.DictWriter(
                    text, fieldnames=fields, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def verify_manifest(package: Path, expected_sha256: str) -> dict[str, str]:
    manifest_path = package / "SHA256SUMS.json"
    if sha256_file(manifest_path) != expected_sha256:
        raise RuntimeError(f"manifest drift: {package.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if sha256_file(package / name) != expected:
            raise RuntimeError(f"payload drift: {package.name}/{name}")
    return manifest


def verify_sources() -> dict[str, object]:
    v2 = ROOT / "results" / V2_PACKAGE
    manifest = verify_manifest(v2, V2_MANIFEST_SHA256)
    if sha256_file(v2 / "CONTENT_IDENTITY.json") != V2_CONTENT_SHA256:
        raise RuntimeError("accepted v2 content identity drift")
    if sha256_file(v2 / "PORTABLE_SHA256SUMS.json") != V2_PORTABLE_SHA256:
        raise RuntimeError("accepted v2 portable identity drift")
    if sha256_file(MATCH_VECTOR_PATH) != MATCH_VECTOR_SHA256:
        raise RuntimeError("#137 match-vector source drift")
    if sha256_file(ROLE_VECTOR_PATH) != ROLE_VECTOR_SHA256:
        raise RuntimeError("#137 role-vector source drift")
    return {
        "accepted_v2": {
            "package": V2_PACKAGE,
            "manifest_sha256": V2_MANIFEST_SHA256,
            "content_identity_sha256": V2_CONTENT_SHA256,
            "portable_manifest_sha256": V2_PORTABLE_SHA256,
            "payload_count": len(manifest),
        },
        "structural_source": {
            "package": "bj137_gate_a_preoutcome_v2",
            "match_vector_file": "match_vectors.csv",
            "match_vector_sha256": MATCH_VECTOR_SHA256,
            "role_vector_file": "n7_role_vectors.csv.gz",
            "role_vector_sha256": ROLE_VECTOR_SHA256,
        },
        "v2_1_adapter": {
            "file": "structural_delete_adapter.py",
            "sha256": sha256_file(ADAPTER_PATH),
            "execution": "copied into the immutable package and preferred by packaged replay",
        },
        "access": "OUTCOME_UNEXPOSED_GATE_A_ONLY",
    }


STRUCTURAL_REGISTRY_FIELDS = (
    "registry_kind",
    "source_package",
    "source_file",
    "source_file_sha256",
    "issue",
    "fold",
    "year",
    "issue_instance",
    "match_id",
    "match_idx",
    "kickoff_ts",
    "p_min",
    "p_model3",
    "p_model1",
    "p_model0",
    "q_weight3",
    "q_weight1",
    "q_weight0",
    "structural_registry_row_sha256",
    "outcome_boundary",
)


def complete_structural_registry() -> list[dict[str, object]]:
    adapter = load_module(ADAPTER_PATH, "bj193_v21_registry_adapter")
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in iter_csv(MATCH_VECTOR_PATH):
        key = (source["issue"], source["fold"], source["match_id"])
        if key in seen:
            raise RuntimeError("duplicate #137 structural registry key")
        seen.add(key)
        row: dict[str, object] = {
            "registry_kind": adapter.REGISTRY_KIND,
            "source_package": adapter.SOURCE_PACKAGE,
            "source_file": adapter.SOURCE_FILE,
            "source_file_sha256": adapter.SOURCE_FILE_SHA256,
            "issue": source["issue"],
            "fold": source["fold"],
            "year": source["year"],
            "issue_instance": source["issue_instance"],
            "match_id": source["match_id"],
            "match_idx": source["match_idx"],
            "kickoff_ts": source["kickoff_ts"],
            "p_min": source["p_min"],
            "p_model3": source["p3"],
            "p_model1": source["p1"],
            "p_model0": source["p0"],
            "q_weight3": source["q_weight3"],
            "q_weight1": source["q_weight1"],
            "q_weight0": source["q_weight0"],
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        row["structural_registry_row_sha256"] = (
            adapter.structural_registry_row_identity(row)
        )
        rows.append(row)
    rows.sort(
        key=lambda row: (
            int(str(row["issue"])),
            str(row["fold"]),
            int(str(row["match_idx"])),
            int(str(row["match_id"])),
        )
    )
    if len(rows) != 47_819:
        raise RuntimeError("#137 structural registry row census drift")
    return rows


def structural_class_key() -> str:
    return canonical_hash(
        {
            "contract": "BJ193_STAGE1_STAGE3_COMPATIBILITY_CLASS_V2_1",
            "source_identity_weight_source": "NA",
            "mechanisms": list(
                ("P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE")
            ),
            "registry": "BJ137_COMPLETE_STRUCTURAL_DELETE_REGISTRY_V2_1",
            "requirement": "EXACT_SEVEN_MATCH_FULL_COVERAGE",
        }
    )


ACTION_MAPPING_FIELDS = (
    "stage3_interface_action_key",
    "source_identity",
    "weight_source",
    "mechanism",
    "repeat_mode",
    "cap",
    "source_M",
    "native_economic_M",
    "replicate_count",
    "replicate_mode",
    "original_v2_compatibility_class_key",
    "effective_v21_compatibility_class_key",
    "compatibility_requirement",
    "source_identity_preserved",
    "outcome_boundary",
)


def effective_action_mapping() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    structural_key = structural_class_key()
    catalog = read_csv(
        ROOT / "results" / V2_PACKAGE / "stage3_bet_catalog.csv.gz"
    )
    for action in catalog:
        params = json.loads(action["parameters_json"])
        mechanism = str(params["mechanism"])
        structural = mechanism in {
            "P_MIN_GLOBAL_DELETE",
            "Q_MIN_GLOBAL_DELETE",
        }
        original_key = str(params["compatibility_class_key"])
        rows.append(
            {
                "stage3_interface_action_key": action["interface_action_key"],
                "source_identity": action["source_identity"],
                "weight_source": params["weight_source"],
                "mechanism": mechanism,
                "repeat_mode": params["repeat_mode"],
                "cap": params["cap"],
                "source_M": params["M"],
                "native_economic_M": 1458 if structural else params["M"],
                "replicate_count": params["replicate_count"],
                "replicate_mode": params["replicate_mode"],
                "original_v2_compatibility_class_key": original_key,
                "effective_v21_compatibility_class_key": (
                    structural_key if structural else original_key
                ),
                "compatibility_requirement": (
                    "COMPLETE_STRUCTURAL_REGISTRY_REQUIRED"
                    if structural
                    else (
                        "CONTROL_UNIT_WEIGHT_NO_REGISTRY_REQUIRED"
                        if params["weight_source"] == "NA"
                        else "COMPLETE_WEIGHT_REGISTRY_REQUIRED"
                    )
                ),
                "source_identity_preserved": True,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    rows.sort(key=lambda row: str(row["stage3_interface_action_key"]))
    if len(rows) != 963 or len({r["stage3_interface_action_key"] for r in rows}) != 963:
        raise RuntimeError("effective Stage-3 action mapping census drift")
    structural_rows = [
        row
        for row in rows
        if row["mechanism"]
        in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}
    ]
    if len(structural_rows) != 2:
        raise RuntimeError("structural action census drift")
    if any(
        row["weight_source"] != "NA"
        or row["replicate_count"] != "1"
        or row["replicate_mode"] != "DETERMINISTIC_SINGLETON"
        or row["native_economic_M"] != 1458
        for row in structural_rows
    ):
        raise RuntimeError("accepted structural identity/economics drift")
    return rows


def compatibility_classes(
    actions: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in actions:
        grouped[str(row["effective_v21_compatibility_class_key"])].append(row)
    rows: list[dict[str, object]] = []
    for key, members in grouped.items():
        requirements = {str(row["compatibility_requirement"]) for row in members}
        if len(requirements) != 1:
            raise RuntimeError("mixed compatibility requirements in class")
        identities = sorted(str(row["stage3_interface_action_key"]) for row in members)
        rows.append(
            {
                "compatibility_class_key": key,
                "compatibility_requirement": next(iter(requirements)),
                "weight_sources_json": canonical_json(
                    sorted({str(row["weight_source"]) for row in members})
                ),
                "mechanisms_json": canonical_json(
                    sorted({str(row["mechanism"]) for row in members})
                ),
                "stage3_action_count": len(members),
                "stage3_action_set_sha256": canonical_hash(identities),
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    rows.sort(key=lambda row: str(row["compatibility_class_key"]))
    if len(rows) != 8 or sum(int(row["stage3_action_count"]) for row in rows) != 963:
        raise RuntimeError("v2.1 compatibility class census drift")
    return rows


def coverage_registry(
    structural_rows: Sequence[Mapping[str, object]],
    class_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    base = load_module(V2_SCRIPT, "bj193_v21_base_contract")
    stage1 = base.stage1_catalog()
    source_records = base.stage1_support_records()
    registry_keys = {
        (str(row["issue"]), str(row["fold"]), str(row["match_id"]))
        for row in structural_rows
    }
    rows: list[dict[str, object]] = []
    for action in stage1:
        issue = int(action["upstream_issue"])
        source_identity = str(action["source_identity"])
        parameters = json.loads(str(action["parameters_json"]))
        record_identity = (
            str(parameters["arm"])
            if issue == 134 and action["source_file"] == "threshold_registry.csv"
            else source_identity
        )
        supports = source_records.get((issue, record_identity), [])
        supported = [
            support
            for support in supports
            if all(
                (str(support["issue"]), str(support["fold"]), str(match_id))
                in registry_keys
                for match_id in support["match_ids"]
            )
        ]
        total = len(supports)
        complete = len(supported)
        folds = sorted({str(row["fold"]) for row in supports})
        years = sorted({str(row["year"]) for row in supports})
        supported_folds = sorted({str(row["fold"]) for row in supported})
        supported_years = sorted({str(row["year"]) for row in supported})
        support_hash = canonical_hash(
            [
                {
                    "issue": str(row["issue"]),
                    "fold": str(row["fold"]),
                    "identity": str(row["identity"]),
                    "match_ids": list(row["match_ids"]),
                    "complete_structural_registry": row in supported,
                }
                for row in supports
            ]
        )
        adequate = total >= MIN_CHRONOLOGICAL_SUPPORT and len(folds) >= MIN_CHRONOLOGICAL_FOLDS
        for class_row in class_rows:
            requirement = str(class_row["compatibility_requirement"])
            if action["availability"] != "AVAILABLE":
                status = "STAGE1_UNAVAILABLE_ZERO_FLOW"
                reason = "UPSTREAM_STAGE1_ACTION_UNAVAILABLE"
            elif not adequate:
                status = "INCOMPATIBLE"
                reason = "INSUFFICIENT_CHRONOLOGICAL_STAGE1_SUPPORT"
            elif requirement == "CONTROL_UNIT_WEIGHT_NO_REGISTRY_REQUIRED":
                status = "COMPATIBLE"
                reason = "UNIT_WEIGHT_CONTROL_NO_MATCH_REGISTRY_REQUIRED"
            elif complete == total:
                status = "COMPATIBLE"
                reason = "COMPLETE_SEVEN_MATCH_PRE_EVENT_REGISTRY_COVERAGE"
            else:
                status = "INCOMPATIBLE"
                reason = "INCOMPLETE_PRE_EVENT_REGISTRY_COVERAGE_NO_FALLBACK"
            rows.append(
                {
                    "stage1_interface_action_key": action["interface_action_key"],
                    "stage1_upstream_issue": issue,
                    "stage1_source_identity": source_identity,
                    "stage3_compatibility_class_key": class_row[
                        "compatibility_class_key"
                    ],
                    "compatibility_requirement": requirement,
                    "stage3_action_count": class_row["stage3_action_count"],
                    "selected_output_count": total,
                    "complete_registry_output_count": complete,
                    "complete_registry_coverage_fraction": (
                        "" if total == 0 else format(complete / total, ".12f")
                    ),
                    "selected_fold_count": len(folds),
                    "selected_year_count": len(years),
                    "selected_folds_json": canonical_json(folds),
                    "selected_years_json": canonical_json(years),
                    "supported_fold_count": len(supported_folds),
                    "supported_year_count": len(supported_years),
                    "supported_folds_json": canonical_json(supported_folds),
                    "supported_years_json": canonical_json(supported_years),
                    "stage1_support_set_sha256": support_hash,
                    "compatibility_status": status,
                    "reason_code": reason,
                    "fallback_rule": (
                        "NONE; incompatible pairs are removed before Stage-3 "
                        "screening and emit zero stake"
                    ),
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    rows.sort(
        key=lambda row: (
            str(row["stage1_interface_action_key"]),
            str(row["stage3_compatibility_class_key"]),
        )
    )
    if len(rows) != 2_469 * 8:
        raise RuntimeError("v2.1 normalized coverage census drift")
    if sum(int(row["stage3_action_count"]) for row in rows) != 2_469 * 963:
        raise RuntimeError("v2.1 normalized pair census drift")
    return rows


def native_reconciliation(
    registry_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    adapter = load_module(ADAPTER_PATH, "bj193_v21_native_reconciliation")
    registry = {
        (str(row["issue"]), str(row["fold"]), str(row["match_id"])): row
        for row in registry_rows
    }
    digest = hashlib.sha256()
    role_rows = portfolio_count = p_matches = q_matches = 0
    legacy_p_marker_matches = legacy_p_marker_mismatches = 0
    legacy_q_marker_matches = legacy_q_marker_mismatches = 0
    first_fixture: dict[str, object] | None = None
    seen: set[tuple[str, str, str]] = set()
    source = iter_csv(ROLE_VECTOR_PATH)
    for key, grouped in itertools.groupby(
        source, key=lambda row: (row["issue"], row["fold"], row["portfolio_id"])
    ):
        if key in seen:
            raise RuntimeError("non-contiguous duplicate #137 role portfolio")
        seen.add(key)
        roles = list(grouped)
        role_rows += len(roles)
        portfolio_count += 1
        if len(roles) != 7:
            raise RuntimeError("#137 structural reconciliation is not N7")
        roles.sort(key=lambda row: int(row["selection_rank"]))
        exact_rows: list[Mapping[str, object]] = []
        for role in roles:
            row = registry.get((role["issue"], role["fold"], role["match_id"]))
            if row is None:
                raise RuntimeError("#137 native structural row missing")
            compared = {
                "p_min": role["p_min"],
                "p_model3": role["p_model3"],
                "p_model1": role["p_model1"],
                "p_model0": role["p_model0"],
                "q_weight3": role["q_weight3"],
                "q_weight1": role["q_weight1"],
                "q_weight0": role["q_weight0"],
            }
            if any(str(row[field]) != value for field, value in compared.items()):
                raise RuntimeError("#137 native structural value mismatch")
            exact_rows.append(row)
        p_delete = adapter.derive_structural_delete(
            "P_MIN_GLOBAL_DELETE", exact_rows
        )
        q_delete = adapter.derive_structural_delete(
            "Q_MIN_GLOBAL_DELETE", exact_rows
        )
        # Independent transcription of the accepted #167 rule.  This is the
        # controlling native anchor.  The older #137 marker columns used a
        # match_idx tie and rounded serialized weights; retain their agreement
        # only as diagnostics rather than silently changing the #167 rule.
        p_leg = min(
            range(7), key=lambda index: (float(roles[index]["p_min"]), index)
        )
        p_code = min(
            range(3),
            key=lambda index: (
                float(roles[p_leg][f"p_model{('3', '1', '0')[index]}"]),
                index,
            ),
        )
        q_leg, q_code = min(
            ((leg, code) for leg in range(7) for code in range(3)),
            key=lambda pair: (
                float(
                    roles[pair[0]][
                        f"q_weight{('3', '1', '0')[pair[1]]}"
                    ]
                ),
                pair[0],
                pair[1],
            ),
        )
        if (
            p_delete["delete_match_id"] != roles[p_leg]["match_id"]
            or p_delete["delete_code"] != ("3", "1", "0")[p_code]
        ):
            raise RuntimeError("#167 native P structural anchor mismatch")
        if (
            q_delete["delete_match_id"] != roles[q_leg]["match_id"]
            or q_delete["delete_code"] != ("3", "1", "0")[q_code]
        ):
            raise RuntimeError("#167 native Q structural anchor mismatch")
        legacy_p_match = all(
            role["p_min_delete_match_id"] == p_delete["delete_match_id"]
            and role["p_min_delete_code"] == p_delete["delete_code"]
            for role in roles
        )
        legacy_q_match = all(
            role["q_min_delete_match_id"] == q_delete["delete_match_id"]
            and role["q_min_delete_code"] == q_delete["delete_code"]
            for role in roles
        )
        legacy_p_marker_matches += int(legacy_p_match)
        legacy_p_marker_mismatches += int(not legacy_p_match)
        legacy_q_marker_matches += int(legacy_q_match)
        legacy_q_marker_mismatches += int(not legacy_q_match)
        p_matches += 1
        q_matches += 1
        record = {
            "issue": key[0],
            "fold": key[1],
            "portfolio_id": key[2],
            "ordered_match_ids": [row["match_id"] for row in exact_rows],
            "registry_row_sha256": [
                row["structural_registry_row_sha256"] for row in exact_rows
            ],
            "p_delete": p_delete,
            "q_delete": q_delete,
        }
        digest.update((canonical_json(record) + "\n").encode("utf-8"))
        if first_fixture is None:
            first_fixture = {**record, "registry_rows": [dict(row) for row in exact_rows]}
    if first_fixture is None or role_rows != 501_928:
        raise RuntimeError("#137 native structural reconciliation census drift")
    return (
        {
            "contract": "BJ193_NATIVE_137_STRUCTURAL_DELETE_RECONCILIATION_V2_1",
            "source_role_vector_sha256": ROLE_VECTOR_SHA256,
            "source_match_vector_sha256": MATCH_VECTOR_SHA256,
            "role_row_count": role_rows,
            "portfolio_count": portfolio_count,
            "p_anchor_match_count": p_matches,
            "q_anchor_match_count": q_matches,
            "mismatch_count": 0,
            "legacy_137_marker_diagnostic": {
                "tie_semantics": "legacy #137 marker used serialized-weight/match_idx ties; accepted #167 replay uses ordered leg/code ties",
                "p_match_count": legacy_p_marker_matches,
                "p_mismatch_count": legacy_p_marker_mismatches,
                "q_match_count": legacy_q_marker_matches,
                "q_mismatch_count": legacy_q_marker_mismatches,
                "controlling": False,
            },
            "reconciliation_stream_sha256": digest.hexdigest(),
            "outcome_boundary": OUTCOME_BOUNDARY,
        },
        first_fixture,
    )


def _comparable(output: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in output.items() if key != "counts"}


def golden_vectors(native: Mapping[str, object]) -> dict[str, object]:
    adapter = load_module(ADAPTER_PATH, "bj193_v21_golden_adapter")
    accepted_v2_adapter = load_module(
        ROOT / "results" / V2_PACKAGE / "conditional_chain_adapter.py",
        "bj193_v21_accepted_v2_signature_adapter",
    )
    rows = [dict(row) for row in native["registry_rows"]]
    ordered = [str(value) for value in native["ordered_match_ids"]]
    registry = {str(row["match_id"]): row for row in rows}
    actions = {
        json.loads(row["parameters_json"])["mechanism"]: row
        for row in read_csv(
            ROOT / "results" / V2_PACKAGE / "stage3_bet_catalog.csv.gz"
        )
        if json.loads(row["parameters_json"])["mechanism"]
        in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}
    }

    def active_weights() -> dict[str, object]:
        return {
            "status": "ACTIVE",
            "per_match": [
                {
                    "match_id": match_id,
                    "direction_weight_3_1_0": ["0.400000000000", "0.350000000000", "0.250000000000"],
                }
                for match_id in ordered
            ],
        }

    def run(mechanism: str, stage2: Mapping[str, object]) -> dict[str, object]:
        result = _comparable(
            adapter.compose_structural_delete(
                mechanism,
                ordered,
                stage2,
                registry,
                issue=str(native["issue"]),
                stage1_output_sha256="1" * 64,
                stage2_output_sha256="2" * 64,
                derived_stage3_action_sha256=str(
                    actions[mechanism]["derived_interface_identity_sha256"]
                ),
            )
        )
        expected_signature = accepted_v2_adapter.stage3_replay_signature(
            issue=str(native["issue"]),
            stage1_output_sha256="1" * 64,
            stage2_output_sha256="2" * 64,
            derived_stage3_action_sha256=str(
                actions[mechanism]["derived_interface_identity_sha256"]
            ),
        )
        if result["stage3_replay_signature_sha256"] != expected_signature:
            raise RuntimeError("v2.1 structural replay signature drift from accepted v2")
        return result

    p_base = run("P_MIN_GLOBAL_DELETE", active_weights())
    q_base = run("Q_MIN_GLOBAL_DELETE", active_weights())
    same = active_weights()
    same_leg = int(p_base["delete_leg_index_zero_based"])
    same_code = int(p_base["delete_code_index_zero_based"])
    same["per_match"][same_leg]["direction_weight_3_1_0"][same_code] = "0"
    p_same = run("P_MIN_GLOBAL_DELETE", same)
    distinct = active_weights()
    distinct_leg = (same_leg + 1) % 7
    distinct_code = (same_code + 1) % 3
    distinct["per_match"][distinct_leg]["direction_weight_3_1_0"][distinct_code] = "0"
    p_distinct = run("P_MIN_GLOBAL_DELETE", distinct)
    p_no_bet = run("P_MIN_GLOBAL_DELETE", {"status": "NO_BET"})
    p_unavailable = run("P_MIN_GLOBAL_DELETE", {"status": "UNAVAILABLE"})
    missing = dict(registry)
    missing.pop(ordered[-1])
    missing_result = _comparable(
        adapter.compose_structural_delete(
            "Q_MIN_GLOBAL_DELETE",
            ordered,
            active_weights(),
            missing,
            issue=str(native["issue"]),
            stage1_output_sha256="1" * 64,
            stage2_output_sha256="2" * 64,
            derived_stage3_action_sha256=str(
                actions["Q_MIN_GLOBAL_DELETE"]["derived_interface_identity_sha256"]
            ),
        )
    )
    issue_mismatch_result = _comparable(
        adapter.compose_structural_delete(
            "Q_MIN_GLOBAL_DELETE",
            ordered,
            active_weights(),
            registry,
            issue=str(int(str(native["issue"])) + 1),
            stage1_output_sha256="1" * 64,
            stage2_output_sha256="2" * 64,
            derived_stage3_action_sha256=str(
                actions["Q_MIN_GLOBAL_DELETE"]["derived_interface_identity_sha256"]
            ),
        )
    )
    tie_rows = []
    for index in range(7):
        row = {
            "registry_kind": adapter.REGISTRY_KIND,
            "source_package": adapter.SOURCE_PACKAGE,
            "source_file": adapter.SOURCE_FILE,
            "source_file_sha256": adapter.SOURCE_FILE_SHA256,
            "issue": "999999",
            "fold": "OOS_TEST",
            "year": "2099",
            "issue_instance": "999999@OOS_TEST",
            "match_id": str(900000 + index),
            "match_idx": str(index),
            "kickoff_ts": f"2099-01-01 0{index}:00:00",
            "p_min": "0.1",
            "p_model3": "0.2",
            "p_model1": "0.2",
            "p_model0": "0.2",
            "q_weight3": "0.3",
            "q_weight1": "0.3",
            "q_weight0": "0.3",
        }
        row["structural_registry_row_sha256"] = (
            adapter.structural_registry_row_identity(row)
        )
        tie_rows.append(row)
    return {
        "contract": "BJ193_STRUCTURAL_DELETE_GOLDEN_VECTORS_V2_1",
        "native_137_anchor": {
            "issue": native["issue"],
            "fold": native["fold"],
            "portfolio_id": native["portfolio_id"],
            "ordered_match_ids": ordered,
            "accepted_p_delete": native["p_delete"],
            "accepted_q_delete": native["q_delete"],
            "p_replay": p_base,
            "q_replay": q_base,
        },
        "composition": {
            "same_code_already_absent": p_same,
            "distinct_additional_delete": p_distinct,
            "stage2_no_bet": p_no_bet,
            "stage2_unavailable": p_unavailable,
            "missing_registry_row": missing_result,
            "registry_trace_issue_mismatch": issue_mismatch_result,
        },
        "tie_fixture": {
            "rows": tie_rows,
            "expected_p": adapter.derive_structural_delete(
                "P_MIN_GLOBAL_DELETE", tie_rows
            ),
            "expected_q": adapter.derive_structural_delete(
                "Q_MIN_GLOBAL_DELETE", tie_rows
            ),
        },
        "assertions": {
            "native_p_ticket_count": 1458,
            "native_q_ticket_count": 1458,
            "same_code_ticket_count": 1458,
            "same_code_reason": "STRUCTURAL_DELETE_ALREADY_ABSENT",
            "distinct_delete_ticket_count": 972,
            "distinct_delete_stake_yuan": 1944,
            "missing_status": "UNAVAILABLE",
            "missing_ticket_count": 0,
            "stage2_no_bet_status": "NO_BET",
            "stage2_unavailable_status": "UNAVAILABLE",
            "issue_mismatch_status": "UNAVAILABLE",
            "issue_mismatch_reason": "STRUCTURAL_REGISTRY_TRACE_ISSUE_MISMATCH",
            "tie_delete_leg_index_zero_based": 0,
            "tie_delete_code": "3",
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def compatibility_contract(
    actions: Sequence[Mapping[str, object]],
    classes: Sequence[Mapping[str, object]],
    coverage: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    structural_key = structural_class_key()
    structural_coverage = [
        row
        for row in coverage
        if row["stage3_compatibility_class_key"] == structural_key
    ]
    by_issue: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in structural_coverage:
        by_issue[str(row["stage1_upstream_issue"])][
            str(row["compatibility_status"])
        ] += 1
    return {
        "contract": "BJ193_STAGE1_STAGE3_COMPATIBILITY_V2_1",
        "lineage": {
            "v2_package": V2_PACKAGE,
            "v2_manifest_sha256": V2_MANIFEST_SHA256,
            "amendment_scope": [
                "P_MIN_GLOBAL_DELETE",
                "Q_MIN_GLOBAL_DELETE",
            ],
            "unchanged_source_identity": True,
        },
        "effective_join": {
            "action_mapping": "stage3_effective_compatibility_mapping_v21.csv.gz",
            "class_registry": "stage3_compatibility_class_registry_v21.csv",
            "coverage_registry": "stage1_stage3_coverage_registry_v21.csv.gz",
            "action_count": len(actions),
            "class_count": len(classes),
            "coverage_row_count": len(coverage),
            "pair_count": sum(int(row["stage3_action_count"]) for row in coverage),
        },
        "structural_class": {
            "compatibility_class_key": structural_key,
            "source_weight_source": "NA",
            "mechanisms": ["P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"],
            "native_M": 1458,
            "registry": "stage3_complete_structural_delete_registry.csv.gz",
            "coverage_rule": "100% exact seven-match rows plus >=20 outputs across >=5 chronological folds",
            "screen_order": "fail closed before Stage-3 outcome screen/model fit/action choice",
            "fallback": "NONE",
            "stage1_issue_status_census": dict(by_issue),
        },
        "composition": {
            "rule": "apply the exact structural code as one additional zero mask on the unchanged ordered Stage-1/Stage-2 support and enumerate every positive ticket exactly once at CNY 2",
            "already_absent": "do not reselect; STRUCTURAL_DELETE_ALREADY_ABSENT; unchanged Stage-2 support",
            "distinct": "additional zero mask; normally 1458 to 972 after one prior Stage-2 deletion",
            "invalid": "missing/mixed/invalid registry row is UNAVAILABLE with zero stake",
            "forbidden_fallbacks": [
                "ALLOW_ALL",
                "unit-weight substitution",
                "partial-row substitution",
                "alternate-code reselection",
                "losing stake",
            ],
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def write_readme(path: Path, counts: Mapping[str, int]) -> None:
    path.write_text(
        f"""# #193 Gate-A v2.1 structural-delete amendment

This immutable, additive, outcome-unexposed amendment corrects the derived
compatibility and conditional composition of `P_MIN_GLOBAL_DELETE` and
`Q_MIN_GLOBAL_DELETE`.  Their accepted #167 source identities remain `NA`,
deterministic singletons with native M=1458 economics.  They are no longer
misclassified as unit-weight controls: their effective compatibility class
requires complete seven-match coverage by the extended #137 pre-event role
registry.

- structural registry rows: {counts['registry_rows']:,}
- effective Stage-3 action mappings: {counts['actions']:,}
- effective compatibility classes: {counts['classes']:,}
- normalized Stage1×class coverage rows: {counts['coverage_rows']:,}
- represented Stage1×Stage3 pairs: {counts['pairs']:,}
- native #137 reconciled portfolios: {counts['native_portfolios']:,}

The executable adapter reproduces original P/Q float and tie ordering, composes
the exact deleted code as an additional Stage-2 zero mask, never reselects when
that code is already absent, and enumerates every remaining ticket once at
CNY 2. Missing, mixed, invalid, or incomplete rows fail closed with zero flow.

No outcome ledger was opened. Gate B remains held until PI accepts and lands
this v2.1 amendment; #192 remains blocked.
""",
        encoding="utf-8",
    )


def publish(output: Path) -> None:
    source_binding = verify_sources()
    registry = complete_structural_registry()
    actions = effective_action_mapping()
    classes = compatibility_classes(actions)
    coverage = coverage_registry(registry, classes)
    reconciliation, native_fixture = native_reconciliation(registry)
    golden = golden_vectors(native_fixture)
    contract = compatibility_contract(actions, classes, coverage)
    counts = {
        "registry_rows": len(registry),
        "actions": len(actions),
        "classes": len(classes),
        "coverage_rows": len(coverage),
        "pairs": sum(int(row["stage3_action_count"]) for row in coverage),
        "native_portfolios": int(reconciliation["portfolio_count"]),
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError(f"refusing to replace immutable package: {output}")
    stage = output.with_name(f"{output.name}.stage-{uuid.uuid4().hex}")
    stage.mkdir()
    try:
        write_json(stage / "source_binding.json", source_binding)
        write_gzip(
            stage / "stage3_complete_structural_delete_registry.csv.gz",
            STRUCTURAL_REGISTRY_FIELDS,
            registry,
        )
        write_gzip(
            stage / "stage3_effective_compatibility_mapping_v21.csv.gz",
            ACTION_MAPPING_FIELDS,
            actions,
        )
        write_csv(
            stage / "stage3_compatibility_class_registry_v21.csv",
            list(classes[0]),
            classes,
        )
        write_gzip(
            stage / "stage1_stage3_coverage_registry_v21.csv.gz",
            list(coverage[0]),
            coverage,
        )
        write_json(
            stage / "stage1_stage3_compatibility_contract_v21.json", contract
        )
        write_json(
            stage / "native_137_structural_delete_reconciliation.json",
            reconciliation,
        )
        write_json(stage / "structural_delete_golden_vectors.json", golden)
        lineage = {
            "contract": CONTRACT,
            "version": VERSION,
            "v1_plus_v2": source_binding["accepted_v2"],
            "v2_1_amendment": (
                "P/Q exact #167 structural-delete registry, compatibility, "
                "conditional composition and fail-closed replay"
            ),
            "outcome_access": False,
            "gate_b_authorized_by_this_package": False,
            "parent_192_authority": False,
        }
        write_json(stage / "lineage_binding.json", lineage)
        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "issue": 193,
            "parent_issue": 192,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_STRUCTURAL_DELETE_AMENDMENT",
            "status": "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY",
            "outcome_access": False,
            "gate_b_authorized_by_this_package": False,
            "source_identity_policy": "P/Q source identities, weight_source=NA, mechanisms, singleton replicate and native M=1458 preserved exactly",
            "counts": counts,
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        write_json(stage / "gate_a_card.json", card)
        write_readme(stage / "README.md", counts)
        shutil.copy2(Path(__file__).resolve(), stage / "freeze_runner.py")
        shutil.copy2(ADAPTER_PATH, stage / "structural_delete_adapter.py")
        runtime = {
            "contract": "BJ193_V21_TRANSPORT_RUNTIME_BINDING",
            "python_implementation": sys.implementation.name,
            "python_version": sys.version,
            "zlib_compile_version": zlib.ZLIB_VERSION,
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
            "gzip_transport": "RFC1952; filename empty; mtime=0; compresslevel=9",
            "scope": "byte transport receipt only; excluded from portable identity",
        }
        write_json(stage / "runtime_transport_binding.json", runtime)
        portable_payloads = {
            str(path.relative_to(stage)): portable_payload_sha256(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file()
            and path.name
            not in {
                "runtime_transport_binding.json",
                "PORTABLE_SHA256SUMS.json",
                "CONTENT_IDENTITY.json",
                "SHA256SUMS.json",
            }
        }
        write_json(stage / "PORTABLE_SHA256SUMS.json", portable_payloads)
        portable_manifest_sha = sha256_file(stage / "PORTABLE_SHA256SUMS.json")
        content = {
            "contract": CONTRACT,
            "version": VERSION,
            "identity_rule": "SHA-256 over canonical decompressed .gz payload bytes and raw bytes otherwise; runtime/identity/manifest files excluded",
            "portable_manifest_sha256": portable_manifest_sha,
            "controls": {
                **counts,
                "v2_manifest_sha256": V2_MANIFEST_SHA256,
                "v2_content_identity_sha256": V2_CONTENT_SHA256,
                "v2_portable_manifest_sha256": V2_PORTABLE_SHA256,
                "outcome_access": False,
            },
            "portable_payloads": portable_payloads,
        }
        write_json(stage / "CONTENT_IDENTITY.json", content)
        manifest = {
            str(path.relative_to(stage)): sha256_file(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS.json"
        }
        write_json(stage / "SHA256SUMS.json", manifest)
        for name, expected in manifest.items():
            if sha256_file(stage / name) != expected:
                raise RuntimeError(f"staged payload drift: {name}")
        os.replace(stage, output)
    except BaseException:
        if stage.exists():
            failed = stage.with_name(stage.name + ".failed")
            if not failed.exists():
                os.replace(stage, failed)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    publish(args.output)


if __name__ == "__main__":
    main()
