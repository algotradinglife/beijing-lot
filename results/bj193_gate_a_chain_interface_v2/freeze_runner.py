#!/usr/bin/env python3
"""Freeze #193's outcome-unexposed three-stage chain interface amendment.

This is a narrow Gate-A amendment to the accepted v1 package.  It verifies
and references only accepted Gate-A artifacts, defines the interfaces between
selection, direction, and ticket construction, and never opens an outcome
ledger or Gate-B result payload.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import uuid
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


CONTRACT = "BJ-HIST-N7-REGIME-META-POLICY-001"
VERSION = "bj193-gate-a-chain-interface-v2"
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target result, final/winning SP, payout, tax "
    "realization, ROI, settlement, and any post-cutoff evidence are forbidden "
    "from X_i, every stage output, fitting inputs, screens, and tie-breaks"
)
V1_PACKAGE = "bj193_gate_a_preoutcome_v1"
V1_MANIFEST_SHA256 = (
    "408e8aa69cf2d336f8b3b65b1c94b30a3456864af01517a78fc27b3f2bab0c45"
)
V1_CONTENT_SHA256 = (
    "9bf90d1553613cbb50770ea51deece1fb40cfb05a0ace9103ab62194faff3131"
)
V1_ACTION_STREAM_SHA256 = (
    "2bda1f41fdf35dc330194b6c27aa4ec9980afbf6112c5e5aee0545841a149e0b"
)


def repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
DEFAULT_OUTPUT = ROOT / "results" / "bj193_gate_a_chain_interface_v2"
ADAPTER_PATH = ROOT / "scripts" / "bj193_conditional_chain_adapter.py"
ALLOCATION_ENGINE_PATH = (
    ROOT / "results" / "bj145_gate_a_preoutcome_v8" / "bj145_allocation_engine.py"
)
ALLOCATION_ENGINE_SHA256 = (
    "5b1ac6631ce22a447d883d514ed73e6795584c89d514e6be7562b2fd91bfa4ce"
)
ROLE_VECTOR_PATH = (
    ROOT / "results" / "bj137_gate_a_preoutcome_v2" / "n7_role_vectors.csv.gz"
)
ROLE_VECTOR_SHA256 = (
    "1a6ac41e5e34c400c5c2a62f9799e2f76d56f4aaa3d13b67b88505443788cdaa"
)
MATCH_VECTOR_PATH = (
    ROOT / "results" / "bj137_gate_a_preoutcome_v2" / "match_vectors.csv"
)
MATCH_VECTOR_SHA256 = (
    "d80eaedc0062eea6929c00fbfb08eef9a02445edc1f533a394a35c238ccf2b56"
)
MIN_CHRONOLOGICAL_SUPPORT = 20
MIN_CHRONOLOGICAL_FOLDS = 5


@dataclass(frozen=True)
class Source:
    issue: int
    package: str
    manifest_sha256: str
    content_sha256: str
    stages: str
    parsed_files: tuple[str, ...]


SOURCES = (
    Source(
        127,
        "bj127_gate_a_preoutcome_v2",
        "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",
        "ac99388115df79c6c76b13f5d168ab9d3607b3db508c0a467025b1a7f79db29c",
        "STAGE_1_SELECTION",
        ("threshold_census.csv", "portfolio_role_assignments.csv.gz"),
    ),
    Source(
        134,
        "bj134_gate_a_preoutcome_v2",
        "ed8ae73827a759ef50e3ca07309b8bf8eb13475ef0e186105b7b9c576ef5ff44",
        "c99334985c22a465a241b37f5718bcab271fe17c9c88e96d300a67f934237e86",
        "STAGE_1_SELECTION",
        (
            "arm_registry.csv", "threshold_registry.csv",
            "selection_freeze.csv", "match_feature_scores.csv.gz",
        ),
    ),
    Source(
        137,
        "bj137_gate_a_preoutcome_v2",
        "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
        "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236",
        "STAGE_3_BET",
        ("sampler_plan.csv", "match_vectors.csv", "n7_role_vectors.csv.gz"),
    ),
    Source(
        145,
        "bj145_gate_a_preoutcome_v8",
        "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
        "074c9b06c024a1db80b5b53cfc99a1bc164001b205fcd94a0c159daf445dab7f",
        "STAGE_3_BET",
        (
            "m_grid.csv", "mechanism_contract.csv", "allocation_binding.json",
            "bj145_allocation_engine.py",
        ),
    ),
    Source(
        167,
        "bj167_gate_a_strategy_atlas_v3r1",
        "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
        "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147",
        "STAGE_3_BET",
        ("allocation_grid.csv", "selector_grid.csv", "selector_census.csv"),
    ),
    Source(
        190,
        "bj190_gate_a_preoutcome_v3r1",
        "490579f7813d260d11965377462f7aa3b20161dd4672e2b42b600b493d24f1bc",
        "f88a3dc7d010c69e5a1e50274f979f62e95cec47702f0aa842e30d7ffb024cb8",
        "STAGE_1_SELECTION;STAGE_2_DIRECTION",
        (
            "detector_grid.csv",
            "estimator_registry.csv",
            "estimator_match_freeze.csv.gz",
            "line_direction_forecast.csv.gz",
            "policy_issue_selection_freeze_part_01_of_04.csv.gz",
            "policy_issue_selection_freeze_part_02_of_04.csv.gz",
            "policy_issue_selection_freeze_part_03_of_04.csv.gz",
            "policy_issue_selection_freeze_part_04_of_04.csv.gz",
            "attribution_arm_registry.csv",
            "directional_ticket_contract.json",
            "directional_allocation_input_catalog.csv.gz",
        ),
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def portable_payload_sha256(path: Path) -> str:
    """Hash canonical payload content, decompressing gzip transport bytes."""

    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
        ) as binary:
            handle = io.TextIOWrapper(binary, newline="", encoding="utf-8")
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            handle.detach()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def verify_package(package: Path, manifest_sha: str, content_sha: str) -> None:
    manifest_path = package / "SHA256SUMS.json"
    content_path = package / "CONTENT_IDENTITY.json"
    if sha256_file(manifest_path) != manifest_sha:
        raise RuntimeError(f"manifest drift: {package.name}")
    if sha256_file(content_path) != content_sha:
        raise RuntimeError(f"content identity drift: {package.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        str(path.relative_to(package))
        for path in package.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS.json"
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    # Some accepted packages bind CONTENT_IDENTITY separately rather than
    # listing it inside their payload manifest.  It is still hash-bound above.
    expected_census = set(manifest) | ({"CONTENT_IDENTITY.json"} - set(manifest))
    if actual != expected_census:
        raise RuntimeError(f"payload census drift: {package.name}")
    for name, expected in manifest.items():
        if sha256_file(package / name) != expected:
            raise RuntimeError(f"payload drift: {package.name}/{name}")


def verify_sources() -> list[dict[str, object]]:
    v1 = ROOT / "results" / V1_PACKAGE
    verify_package(v1, V1_MANIFEST_SHA256, V1_CONTENT_SHA256)
    v1_census = json.loads((v1 / "action_catalog_census.json").read_text())
    if v1_census["expanded_action_stream_sha256"] != V1_ACTION_STREAM_SHA256:
        raise RuntimeError("#193 v1 action stream drift")
    rows: list[dict[str, object]] = [
        {
            "issue": 193,
            "package": V1_PACKAGE,
            "manifest_sha256": V1_MANIFEST_SHA256,
            "content_sha256": V1_CONTENT_SHA256,
            "stages": "COMMON_LINEAGE",
            "parsed_files": (
                "issue_regime_features.csv.gz;feature_contract.csv;"
                "causal_allocation_catalog.csv;model_family_grid.csv;"
                "chronological_nested_folds.csv;holding_feasibility_contract.json;"
                "holding_definition_fixture.json"
            ),
            "access": "OUTCOME_UNEXPOSED_GATE_A_ONLY",
            "identity_rule": "immutable v1 lineage; flattened topology superseded only",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
    ]
    for source in SOURCES:
        package = ROOT / "results" / source.package
        verify_package(package, source.manifest_sha256, source.content_sha256)
        manifest = json.loads((package / "SHA256SUMS.json").read_text())
        if not set(source.parsed_files) <= set(manifest):
            raise RuntimeError(f"declared source payload missing: {source.package}")
        rows.append(
            {
                "issue": source.issue,
                "package": source.package,
                "manifest_sha256": source.manifest_sha256,
                "content_sha256": source.content_sha256,
                "stages": source.stages,
                "parsed_files": ";".join(source.parsed_files),
                "access": "OUTCOME_UNEXPOSED_GATE_A_ONLY",
                "identity_rule": "preserve exact upstream identity; stage-qualified key is an interface wrapper, not a rename",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return rows


def interface_key(stage: str, package: str, source_file: str, source_identity: str) -> str:
    return f"{stage}_{canonical_hash([stage, package, source_file, source_identity])}"


CATALOG_FIELDS = (
    "stage",
    "interface_action_key",
    "upstream_issue",
    "source_package",
    "source_file",
    "source_identity_field",
    "source_identity",
    "parameters_json",
    "availability",
    "scientific_role",
    "upstream_source_identity_bound",
    "preserved_source_identity",
    "interface_semantics",
    "derived_interface_identity_sha256",
    "adapter_sha256",
    "outcome_boundary",
)


def catalog_row(
    stage: str,
    issue: int,
    package: str,
    source_file: str,
    identity_field: str,
    identity: str,
    parameters: Mapping[str, object],
    availability: str,
    role: str,
    *,
    preserved_source_identity: bool = True,
    interface_semantics: str = "PRESERVED_UPSTREAM_ACTION",
    derived_interface_identity_sha256: str = "",
    adapter_sha256: str = "",
) -> dict[str, object]:
    key_identity = derived_interface_identity_sha256 or identity
    return {
        "stage": stage,
        "interface_action_key": interface_key(
            stage, package, source_file, key_identity
        ),
        "upstream_issue": issue,
        "source_package": package,
        "source_file": source_file,
        "source_identity_field": identity_field,
        "source_identity": identity,
        "parameters_json": canonical_json(parameters),
        "availability": availability,
        "scientific_role": role,
        "upstream_source_identity_bound": True,
        "preserved_source_identity": preserved_source_identity,
        "interface_semantics": interface_semantics,
        "derived_interface_identity_sha256": derived_interface_identity_sha256,
        "adapter_sha256": adapter_sha256,
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def stage1_catalog() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    package = "bj127_gate_a_preoutcome_v2"
    for source in read_csv(ROOT / "results" / package / "threshold_census.csv"):
        identity = source["variant_id"]
        rows.append(
            catalog_row(
                "STAGE_1_SELECTION", 127, package, "threshold_census.csv",
                "variant_id", identity, {"variant_id": identity}, "AVAILABLE",
                "ACCEPTED_GLOBAL_CODE_PRUNING_SELECTOR_FAMILY",
            )
        )
    package = "bj134_gate_a_preoutcome_v2"
    for source in read_csv(ROOT / "results" / package / "arm_registry.csv"):
        identity = source["arm"]
        params = {
            key: source[key]
            for key in (
                "arm", "score_field", "definition", "candidate_selector_id",
                "incumbent_selector_id", "selection_scope", "missing_rule",
            )
        }
        rows.append(
            catalog_row(
                "STAGE_1_SELECTION", 134, package, "arm_registry.csv", "arm",
                identity, params, "AVAILABLE", "ACCEPTED_FUNDAMENTAL_SELECTOR_ARM",
            )
        )
    for source in read_csv(ROOT / "results" / package / "threshold_registry.csv"):
        identity = "|".join(
            source[key]
            for key in ("threshold_family", "arm", "metric", "threshold_label")
        )
        params = {
            key: source[key]
            for key in (
                "threshold_family", "arm", "metric", "operator",
                "threshold_label", "threshold_value", "application_rule",
                "missing_rule",
            )
        }
        rows.append(
            catalog_row(
                "STAGE_1_SELECTION", 134, package, "threshold_registry.csv",
                "threshold_family|arm|metric|threshold_label", identity, params,
                "AVAILABLE", "ACCEPTED_FUNDAMENTAL_SELECTOR_THRESHOLD",
            )
        )
    package = "bj190_gate_a_preoutcome_v3r1"
    for source in read_csv(ROOT / "results" / package / "detector_grid.csv"):
        identity = source["policy_id"]
        params = {key: value for key, value in source.items() if key != "outcome_boundary"}
        rows.append(
            catalog_row(
                "STAGE_1_SELECTION", 190, package, "detector_grid.csv",
                "policy_id", identity, params, source["availability"],
                "ACCEPTED_SPARSE_DIVERGENCE_MATCH_SELECTOR",
            )
        )
    rows.sort(key=lambda row: str(row["interface_action_key"]))
    if len(rows) != 2_469 or len({row["interface_action_key"] for row in rows}) != len(rows):
        raise RuntimeError("#193 Stage-1 catalog census drift")
    return rows


def stage2_catalog() -> list[dict[str, object]]:
    adapter = load_module(ADAPTER_PATH, "bj193_conditional_adapter_catalog")
    adapter_sha = sha256_file(ADAPTER_PATH)
    package = "bj190_gate_a_preoutcome_v3r1"
    arms = {
        row["arm"]: row
        for row in read_csv(ROOT / "results" / package / "attribution_arm_registry.csv")
    }
    rows = [
        catalog_row(
            "STAGE_2_DIRECTION", 190, package, "attribution_arm_registry.csv",
            "arm", "B0_BEST_FULL", arms["B0_BEST_FULL"], "AVAILABLE",
            "STATIC_ALLOW_ALL_OUTCOME_CODES_CONTROL",
        )
    ]
    for source in read_csv(ROOT / "results" / package / "detector_grid.csv"):
        identity = source["policy_id"]
        derived_identity = adapter.derived_direction_identity(
            source, adapter_sha256=adapter_sha
        )
        params = {
            key: value
            for key, value in source.items()
            if key not in {"policy_id", "outcome_boundary"}
        }
        params.update(
            {
                "upstream_reference_only": "#190 D_DIRECTION_ONLY/B0 semantics inform the adapter but are not preserved unchanged",
                "derived_direction_action_sha256": derived_identity,
                "adapter_version": adapter.ADAPTER_VERSION,
                "adapter_sha256": adapter_sha,
                "estimator_source_binding": "bj190_gate_a_preoutcome_v3r1/estimator_match_freeze.csv.gz + estimator_registry.csv",
                "direction_rule": "on the exact ordered Stage-1 N7, require every match estimator/base gate; rank magnitude desc, match_idx asc, numeric match_id asc; require frozen top_k threshold; delete the most-negative code only at the strongest passing match and retain exact estimator probabilities for every match",
                "protection_rule": "no additional protection; exact target-safe/history/breadth/uncertainty/threshold gates; any failed selected leg is NO_BET",
                "zero_flow_rule": "non-N7 or threshold/base/estimator failure => NO_BET zero tickets/stake; upstream unavailable => UNAVAILABLE zero tickets/stake",
                "support_rule": "consume and hash the exact ordered Stage-1 match IDs; never replace, reorder, add, or remove Stage-1 matches",
            }
        )
        rows.append(
            catalog_row(
                "STAGE_2_DIRECTION", 190, package, "detector_grid.csv",
                "policy_id", identity, params, source["availability"],
                "DERIVED_STAGE1_CONDITIONAL_DIRECTION_ADAPTER",
                preserved_source_identity=False,
                interface_semantics="DERIVED_STAGE1_CONDITIONAL_FROM_BOUND_190_POLICY",
                derived_interface_identity_sha256=derived_identity,
                adapter_sha256=adapter_sha,
            )
        )
    rows.sort(key=lambda row: str(row["interface_action_key"]))
    if len(rows) != 2_425 or len({row["interface_action_key"] for row in rows}) != len(rows):
        raise RuntimeError("#193 Stage-2 catalog census drift")
    return rows


def stage3_compatibility_class_key(weight_source: str) -> str:
    return canonical_hash(
        {
            "contract": "BJ193_STAGE1_STAGE3_COMPATIBILITY_CLASS_V1",
            "weight_source": weight_source,
            "registry": (
                "CONTROL_UNIT_WEIGHT"
                if weight_source == "NA"
                else "BJ137_COMPLETE_MATCH_WEIGHT_REGISTRY_V1"
            ),
        }
    )


def stage3_catalog() -> list[dict[str, object]]:
    v1 = ROOT / "results" / V1_PACKAGE / "causal_allocation_catalog.csv"
    rows: list[dict[str, object]] = []
    adapter_sha = sha256_file(ADAPTER_PATH)
    engine_sha = sha256_file(ALLOCATION_ENGINE_PATH)
    if engine_sha != ALLOCATION_ENGINE_SHA256:
        raise RuntimeError("accepted #145 allocation engine drift")
    for source in read_csv(v1):
        if source["namespace"] != "ATLAS167":
            continue
        identity = source["causal_allocation_factor_id"]
        params = {
            key: source[key]
            for key in (
                "weight_source", "mechanism", "repeat_mode", "cap", "M",
                "replicate_count", "replicate_mode", "frozen_seed_set_sha256",
                "replay_row_set_sha256", "seed_aggregation_rule",
                "selection_identity_json",
            )
        }
        params["accepted_source_chain"] = [
            "bj137_gate_a_preoutcome_v2",
            "bj145_gate_a_preoutcome_v8",
            "bj167_gate_a_strategy_atlas_v3r1",
        ]
        derived_identity = canonical_hash(
            {
                "adapter_version": "BJ193_STAGE2_TO_STAGE3_BUILDER_V4",
                "adapter_sha256": adapter_sha,
                "allocation_engine_sha256": engine_sha,
                "upstream_causal_allocation_factor_id": identity,
                "support": "EXACT_STAGE2_ALLOWED_WEIGHTED_FULL_ORDINAL_VECTOR",
            }
        )
        params.update(
            {
                "derived_bet_action_sha256": derived_identity,
                "conditional_builder_version": "BJ193_STAGE2_TO_STAGE3_BUILDER_V4",
                "conditional_builder_sha256": adapter_sha,
                "accepted_allocation_engine_sha256": engine_sha,
                "compatibility_class_key": stage3_compatibility_class_key(
                    str(source["weight_source"])
                ),
                "weight_registry": (
                    "CONTROL_UNIT_WEIGHT"
                    if source["weight_source"] == "NA"
                    else "BJ137_COMPLETE_MATCH_WEIGHT_REGISTRY_V1"
                ),
            }
        )
        rows.append(
            catalog_row(
                "STAGE_3_BET", 167, V1_PACKAGE,
                "causal_allocation_catalog.csv", "causal_allocation_factor_id",
                identity, params, "AVAILABLE", "ACCEPTED_ALLOCATOR_REPEAT_M_ACTION",
                preserved_source_identity=False,
                interface_semantics="DERIVED_STAGE2_CONDITIONAL_ACTION_WITH_BOUND_167_PARAMETERS",
                derived_interface_identity_sha256=derived_identity,
                adapter_sha256=adapter_sha,
            )
        )
    rows.sort(key=lambda row: str(row["interface_action_key"]))
    if len(rows) != 963 or len({row["interface_action_key"] for row in rows}) != len(rows):
        raise RuntimeError("#193 Stage-3 catalog census drift")
    return rows


COMPLETE_WEIGHT_SOURCE_MAP = {
    "p_model3": "p3",
    "p_model1": "p1",
    "p_model0": "p0",
    "p_market_cal3": "market_cal3",
    "p_market_cal1": "market_cal1",
    "p_market_cal0": "market_cal0",
    "p_blend_a25_3": "blend_a25_3",
    "p_blend_a25_1": "blend_a25_1",
    "p_blend_a25_0": "blend_a25_0",
    "p_blend_a50_3": "blend_a50_3",
    "p_blend_a50_1": "blend_a50_1",
    "p_blend_a50_0": "blend_a50_0",
    "p_blend_a75_3": "blend_a75_3",
    "p_blend_a75_1": "blend_a75_1",
    "p_blend_a75_0": "blend_a75_0",
    "q_weight3": "q_weight3",
    "q_weight1": "q_weight1",
    "q_weight0": "q_weight0",
}

COMPLETE_MATCH_WEIGHT_FIELDS = (
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
    *COMPLETE_WEIGHT_SOURCE_MAP,
    "weight_registry_row_sha256",
    "outcome_boundary",
)


def complete_match_weight_registry() -> list[dict[str, object]]:
    if sha256_file(MATCH_VECTOR_PATH) != MATCH_VECTOR_SHA256:
        raise RuntimeError("#137 complete match-vector source drift")
    adapter = load_module(ADAPTER_PATH, "bj193_complete_match_registry")
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in iter_csv(MATCH_VECTOR_PATH):
        key = (source["issue"], source["fold"], source["match_id"])
        if key in seen:
            raise RuntimeError("duplicate #137 complete match-vector key")
        seen.add(key)
        row: dict[str, object] = {
            "registry_kind": adapter.COMPLETE_MATCH_REGISTRY_KIND,
            "source_package": "bj137_gate_a_preoutcome_v2",
            "source_file": "match_vectors.csv",
            "source_file_sha256": MATCH_VECTOR_SHA256,
            "issue": source["issue"],
            "fold": source["fold"],
            "year": source["year"],
            "issue_instance": source["issue_instance"],
            "match_id": source["match_id"],
            "match_idx": source["match_idx"],
            "kickoff_ts": source["kickoff_ts"],
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for target, origin in COMPLETE_WEIGHT_SOURCE_MAP.items():
            row[target] = source[origin]
        row["weight_registry_row_sha256"] = (
            adapter.complete_match_weight_row_identity(row)
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
        raise RuntimeError("#137 complete match-vector row census drift")
    return rows


def native_137_weight_reconciliation(
    registry_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    registry = {
        (str(row["issue"]), str(row["fold"]), str(row["match_id"])): row
        for row in registry_rows
    }
    digest = hashlib.sha256()
    role_count = matched_count = missing_count = mismatch_count = 0
    for role in iter_csv(ROLE_VECTOR_PATH):
        role_count += 1
        key = (role["issue"], role["fold"], role["match_id"])
        complete = registry.get(key)
        if complete is None:
            missing_count += 1
            continue
        mismatched_fields = [
            field
            for field in COMPLETE_WEIGHT_SOURCE_MAP
            if str(complete[field]) != str(role[field])
        ]
        if mismatched_fields:
            mismatch_count += 1
            continue
        matched_count += 1
        digest.update(
            (
                canonical_json(
                    {
                        "issue": role["issue"],
                        "fold": role["fold"],
                        "portfolio_id": role["portfolio_id"],
                        "match_id": role["match_id"],
                        "registry_row": complete["weight_registry_row_sha256"],
                    }
                )
                + "\n"
            ).encode("utf-8")
        )
    if missing_count or mismatch_count or matched_count != role_count:
        raise RuntimeError("#137 native role-vector reconciliation failed")
    return {
        "contract": "BJ193_NATIVE_137_COMPLETE_MATCH_RECONCILIATION_V1",
        "source_role_vector_sha256": ROLE_VECTOR_SHA256,
        "source_match_vector_sha256": MATCH_VECTOR_SHA256,
        "role_row_count": role_count,
        "matched_role_row_count": matched_count,
        "missing_role_row_count": missing_count,
        "mismatched_role_row_count": mismatch_count,
        "complete_match_registry_row_count": len(registry_rows),
        "reconciliation_stream_sha256": digest.hexdigest(),
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def _support_record(
    *,
    issue: str,
    fold: str,
    year: str,
    identity: str,
    match_ids: Sequence[str],
) -> dict[str, object]:
    ordered = tuple(str(match_id) for match_id in match_ids)
    if len(ordered) != 7 or len(set(ordered)) != 7:
        raise RuntimeError("Stage-1 coverage record is not exact N7")
    return {
        "issue": str(issue),
        "fold": str(fold),
        "year": str(year),
        "identity": str(identity),
        "match_ids": ordered,
    }


def stage1_support_records() -> dict[tuple[int, str], list[dict[str, object]]]:
    records: dict[tuple[int, str], list[dict[str, object]]] = defaultdict(list)

    grouped: dict[tuple[str, str, str, str, str], dict[int, str]] = defaultdict(
        dict
    )
    for row in iter_csv(
        ROOT
        / "results"
        / "bj127_gate_a_preoutcome_v2"
        / "portfolio_role_assignments.csv.gz"
    ):
        key = (
            row["variant_id"],
            row["portfolio_id"],
            row["issue"],
            row["fold"],
            row["year"],
        )
        rank = int(row["selection_rank"])
        if rank in grouped[key]:
            raise RuntimeError("duplicate #127 selection rank")
        grouped[key][rank] = row["match_id"]
    for (variant, portfolio, issue, fold, year), ranked_matches in grouped.items():
        if sorted(ranked_matches) != list(range(1, 8)):
            raise RuntimeError("#127 selection rank coverage drift")
        records[(127, variant)].append(
            _support_record(
                issue=issue,
                fold=fold,
                year=year,
                identity=portfolio,
                match_ids=[ranked_matches[rank] for rank in range(1, 8)],
            )
        )

    for row in iter_csv(
        ROOT
        / "results"
        / "bj134_gate_a_preoutcome_v2"
        / "selection_freeze.csv"
    ):
        if row["policy_status"] != "SELECTED_PREOUTCOME":
            continue
        records[(134, row["arm"])].append(
            _support_record(
                issue=row["issue"],
                fold=row["fold"],
                year=row["year"],
                identity=row["selected_identity_fingerprint"],
                match_ids=row["selected_match_ids"].split("|"),
            )
        )

    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    for shard in range(1, 5):
        for row in iter_csv(
            package
            / f"policy_issue_selection_freeze_part_{shard:02d}_of_04.csv.gz"
        ):
            if row["policy_status"] != "SELECTED_PREOUTCOME":
                continue
            records[(190, row["policy_id"])].append(
                _support_record(
                    issue=row["issue"],
                    fold=row["fold"],
                    year=row["year"],
                    identity=row["selected_n7_identity_sha256"],
                    match_ids=json.loads(row["selected_match_ids_json"]),
                )
            )
    for rows in records.values():
        rows.sort(
            key=lambda row: (
                int(str(row["issue"])),
                str(row["fold"]),
                str(row["identity"]),
            )
        )
    return records


def stage3_compatibility_class_registry(
    stage3: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for action in stage3:
        parameters = json.loads(str(action["parameters_json"]))
        grouped[str(parameters["weight_source"])].append(
            str(action["interface_action_key"])
        )
    rows = []
    for weight_source in sorted(grouped):
        actions = sorted(grouped[weight_source])
        rows.append(
            {
                "compatibility_class_key": stage3_compatibility_class_key(
                    weight_source
                ),
                "weight_source": weight_source,
                "weight_registry": (
                    "CONTROL_UNIT_WEIGHT"
                    if weight_source == "NA"
                    else "BJ137_COMPLETE_MATCH_WEIGHT_REGISTRY_V1"
                ),
                "stage3_action_count": len(actions),
                "stage3_action_set_sha256": canonical_hash(actions),
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    if sum(int(row["stage3_action_count"]) for row in rows) != 963:
        raise RuntimeError("Stage-3 compatibility class census drift")
    return rows


def stage1_stage3_coverage_registry(
    stage1: Sequence[Mapping[str, object]],
    registry_rows: Sequence[Mapping[str, object]],
    class_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    match_keys = {
        (str(row["issue"]), str(row["fold"]), str(row["match_id"]))
        for row in registry_rows
    }
    source_records = stage1_support_records()
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
                (str(support["issue"]), str(support["fold"]), match_id)
                in match_keys
                for match_id in support["match_ids"]
            )
        ]
        total = len(supports)
        supported_count = len(supported)
        supported_keys = {
            (str(row["issue"]), str(row["fold"]), str(row["identity"]))
            for row in supported
        }
        supported_folds = sorted({str(row["fold"]) for row in supported})
        supported_years = sorted({str(row["year"]) for row in supported})
        selected_folds = sorted({str(row["fold"]) for row in supports})
        selected_years = sorted({str(row["year"]) for row in supports})
        support_sha = canonical_hash(
            [
                {
                    "issue": row["issue"],
                    "fold": row["fold"],
                    "identity": row["identity"],
                    "match_ids": list(row["match_ids"]),
                    "complete_match_registry": (
                        str(row["issue"]),
                        str(row["fold"]),
                        str(row["identity"]),
                    )
                    in supported_keys,
                }
                for row in supports
            ]
        )
        adequate = (
            total >= MIN_CHRONOLOGICAL_SUPPORT
            and len(selected_folds) >= MIN_CHRONOLOGICAL_FOLDS
        )
        for class_row in class_rows:
            weight_source = str(class_row["weight_source"])
            if action["availability"] != "AVAILABLE":
                status = "STAGE1_UNAVAILABLE_ZERO_FLOW"
                reason = "UPSTREAM_STAGE1_ACTION_UNAVAILABLE"
            elif not adequate:
                status = "INCOMPATIBLE"
                reason = "INSUFFICIENT_CHRONOLOGICAL_STAGE1_SUPPORT"
            elif weight_source == "NA":
                status = "COMPATIBLE"
                reason = "UNIT_WEIGHT_CONTROL_NO_MATCH_REGISTRY_REQUIRED"
            elif supported_count == total:
                status = "COMPATIBLE"
                reason = "COMPLETE_MATCH_WEIGHT_REGISTRY_FULL_COVERAGE"
            else:
                status = "INCOMPATIBLE"
                reason = "INCOMPLETE_PRE_EVENT_WEIGHT_COVERAGE_NO_FALLBACK"
            rows.append(
                {
                    "stage1_interface_action_key": action[
                        "interface_action_key"
                    ],
                    "stage1_upstream_issue": issue,
                    "stage1_source_identity": source_identity,
                    "stage3_compatibility_class_key": class_row[
                        "compatibility_class_key"
                    ],
                    "stage3_weight_source": weight_source,
                    "stage3_action_count": class_row["stage3_action_count"],
                    "selected_output_count": total,
                    "complete_registry_output_count": supported_count,
                    "complete_registry_coverage_fraction": (
                        "" if total == 0 else format(supported_count / total, ".12f")
                    ),
                    "selected_fold_count": len(selected_folds),
                    "selected_year_count": len(selected_years),
                    "selected_folds_json": canonical_json(selected_folds),
                    "selected_years_json": canonical_json(selected_years),
                    "supported_fold_count": len(supported_folds),
                    "supported_year_count": len(supported_years),
                    "supported_folds_json": canonical_json(supported_folds),
                    "supported_years_json": canonical_json(supported_years),
                    "stage1_support_set_sha256": support_sha,
                    "compatibility_status": status,
                    "reason_code": reason,
                    "fallback_rule": "NONE; incompatible pairs are removed before Stage-3 screening and emit no fabricated stake",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    rows.sort(
        key=lambda row: (
            str(row["stage1_interface_action_key"]),
            str(row["stage3_compatibility_class_key"]),
        )
    )
    if len(rows) != 2_469 * 7:
        raise RuntimeError("Stage1×Stage3 normalized compatibility census drift")
    return rows


def stage1_stage3_compatibility_contract(
    class_rows: Sequence[Mapping[str, object]],
    coverage_rows: Sequence[Mapping[str, object]],
    native_reconciliation: Mapping[str, object],
) -> dict[str, object]:
    return {
        "contract": "BJ193_STAGE1_STAGE3_COMPATIBILITY_V1",
        "normalized_join": {
            "stage3_action_to_class": "stage3_compatibility_class_registry.csv",
            "stage1_action_to_class_coverage": "stage1_stage3_coverage_registry.csv.gz",
            "complete_pair_rule": "join Stage-3 action compatibility_class_key to the exact Stage-1 action/class row; this covers every 2,377,647 action pair without denormalized duplication",
            "pair_count": 2_469 * 963,
        },
        "complete_match_weight_registry": {
            "artifact": "stage3_complete_match_weight_registry.csv.gz",
            "source_package": "bj137_gate_a_preoutcome_v2",
            "source_file": "match_vectors.csv",
            "source_file_sha256": MATCH_VECTOR_SHA256,
            "row_count": 47_819,
            "field_mapping": COMPLETE_WEIGHT_SOURCE_MAP,
            "row_identity": "conditional_chain_adapter.complete_match_weight_row_identity",
        },
        "adequacy": {
            "minimum_selected_outputs": MIN_CHRONOLOGICAL_SUPPORT,
            "minimum_folds": MIN_CHRONOLOGICAL_FOLDS,
            "non_na": "requires 100% exact seven-match coverage by the complete-match registry",
            "na": "unit weight needs no registry but still requires chronological Stage-1 support",
        },
        "screen_order": "compatibility_status==COMPATIBLE before Stage-3 outcome screen/model fit/action choice",
        "unsupported": "no silent role-vector lookup, probability substitution, ALLOW_ALL conversion, losing stake, or partial-match fallback",
        "native_137_reconciliation": dict(native_reconciliation),
        "class_count": len(class_rows),
        "coverage_row_count": len(coverage_rows),
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def direction_adapter_contract() -> dict[str, object]:
    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    return {
        "contract": "BJ193_STAGE1_CONDITIONAL_DIRECTION_ADAPTER_V3",
        "module": "conditional_chain_adapter.py",
        "module_sha256": sha256_file(ADAPTER_PATH),
        "adapter_version": "bj193-conditional-chain-adapter-v4",
        "upstream_semantics": {
            "status": "BOUND_REFERENCE_NOT_RENAMED",
            "source": "#190 D_DIRECTION_ONLY is defined only on accepted B0 support",
            "derived_action": "each #193 action is a new Stage-1-conditional identity hash over the adapter, exact #190 policy parameters and support rule",
        },
        "source_bindings": {
            "detector_grid.csv": sha256_file(package / "detector_grid.csv"),
            "estimator_registry.csv": sha256_file(
                package / "estimator_registry.csv"
            ),
            "estimator_match_freeze.csv.gz": sha256_file(
                package / "estimator_match_freeze.csv.gz"
            ),
            "directional_ticket_contract.json": sha256_file(
                package / "directional_ticket_contract.json"
            ),
        },
        "input": {
            "selected_match_ids": "exactly seven unique IDs in immutable Stage-1 order",
            "stage1_output_sha256": "required and copied into every direction output",
            "policy": "one exact detector_grid row; DIAGNOSTIC_UNAVAILABLE stays UNAVAILABLE",
            "estimator_rows": "one exact estimator_match_freeze row per selected match",
            "estimator_identity": "canonical hash of detector/variant, selected source and every immutable estimator component used; UNION/MODEL_AGREEMENT bind both T1 and target-safe consensus identities",
        },
        "estimator_mapping": {
            "FUNDAMENTAL_INDEPENDENT": "fundamental p/delta/z; derived identity binds T1 estimator identity",
            "CALIBRATED_MARKET_ESTIMATOR": "calibrated p/delta/z; derived identity binds target-safe consensus identity",
            "UNION": "larger magnitude per match; exact tie fundamental first; selected source supplies probability; derived identity binds both compared component identities",
            "MODEL_AGREEMENT": "require identical favored and omitted codes; weaker magnitude per match; exact tie fundamental first; selected weaker source supplies probability; derived identity binds both agreement components",
            "LINE_RESIDUAL_MU": "same T1 score-distribution probability and signed line residual; derived identity binds T1 estimator identity",
        },
        "eligibility_order": [
            "exact N7 and complete estimator row lookup",
            "target_safe_consensus AVAILABLE",
            "minimum history",
            "optional broad-market B05_19",
            "optional uncertainty <= 0.12",
            "estimator direction availability",
            "rank all seven by magnitude desc, match_idx asc, numeric match_id asc",
            "frozen K1/K2/K4/ALL threshold on the ranked prefix",
        ],
        "construction": {
            "match_order": "unchanged Stage-1 order",
            "strongest": "first ranked direction metric",
            "delete": "set the strongest leg's most-negative code weight to zero; no other code or match is removed",
            "weights": "exact selected estimator p3/p1/p0 per match, formatted to 12 decimals in output; deleted code zero",
            "protection": "no additional protection beyond frozen base and threshold gates",
            "tie_break": "magnitude desc, match_idx asc, numeric match_id asc; code ties 3 then 1 then 0; source ties fundamental first",
        },
        "zero_flow": {
            "NO_BET": "non-N7, failed base/threshold, or unavailable selected-match direction; zero tickets and stake",
            "UNAVAILABLE": "upstream policy or estimator row unavailable; zero tickets and stake",
            "never": "missing/failed direction is never converted to losing stake or ALLOW_ALL after model choice",
        },
        "forbidden_inputs": sorted(
            load_module(ADAPTER_PATH, "bj193_adapter_contract").FORBIDDEN_INPUT_FIELDS
        ),
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def conditional_builder_contract() -> dict[str, object]:
    adapter = load_module(ADAPTER_PATH, "bj193_adapter_builder_contract")
    return {
        "contract": "BJ193_STAGE2_TO_STAGE3_CONDITIONAL_BUILDER_V4",
        "module": "conditional_chain_adapter.py",
        "module_sha256": sha256_file(ADAPTER_PATH),
        "accepted_allocator_module": "bj145_allocation_engine.py",
        "accepted_allocator_sha256": ALLOCATION_ENGINE_SHA256,
        "stage3_complete_match_weight_source": {
            "source_package": "bj137_gate_a_preoutcome_v2",
            "source_gate_a_manifest_sha256": SOURCES[2].manifest_sha256,
            "source_file": "match_vectors.csv",
            "source_file_sha256": MATCH_VECTOR_SHA256,
            "derived_registry": "stage3_complete_match_weight_registry.csv.gz",
            "weight_source_fields_3_1_0": {
                key: list(value)
                for key, value in adapter.WEIGHT_SOURCE_FIELDS.items()
            },
            "accepted_source_field_mapping": COMPLETE_WEIGHT_SOURCE_MAP,
            "identity_rule": (
                "all seven rows must share exact nonblank issue/fold, carry a "
                "valid complete_match_weight_row_identity, and match the ordered "
                "Stage-1 support by internal match_id; missing row/field or mixed "
                "identity is UNAVAILABLE with zero flow; legacy portfolio-role "
                "rows are reconciliation evidence only and are rejected by the "
                "controlling builder"
            ),
        },
        "input_order": {
            "matches": "exact Stage-2 ordered_match_ids, unchanged from Stage 1",
            "codes": ["3", "1", "0"],
            "tickets": "full seven-leg base-3 ordinal 0..2186",
        },
        "weight_vector": {
            "rule": "for each ordered match/code multiply the bound #137 Stage-3 source weight by the Stage-2 estimator direction weight when the code is allowed, otherwise exact zero; NA control source is unit weight; retain a length-2187 vector with explicit zeros",
            "normalization": "math.fsum raw total; divide each raw weight; apply residual 1-math.fsum to the last positive ordinal",
            "identity": "SHA-256 of canonical 17-digit float strings in ordinal order",
            "zero_support": "NO_BET with zero tickets/stake",
        },
        "mechanisms": {
            "WR_DUPLICATE_STAKE": "accepted #145 inverse-CDF on normalized vector; duplicates retained; zero weights forbidden from realized counts",
            "WOR_DISTINCT": "accepted #145 exponential keys only when M <= positive support; otherwise NO_BET",
            "RESIDUAL_SYSTEMATIC": "accepted #145 Hamilton allocation; repeats allowed on positive support",
            "CAPPED_REPEAT": "accepted #145 capped Hamilton only when M <= positive_support*cap; otherwise NO_BET",
            "DETERMINISTIC_TOP_MASS": "accepted #145 weight-desc/ordinal-asc only when M <= positive support; otherwise NO_BET",
            "FULL_ENUMERATED": "enumerate each positive Stage-2 ticket exactly once; ALLOW_ALL gives 2187, reduced support gives explicit ENUMERATE_UPSTREAM_SUPPORT_FALLBACK",
        },
        "M_semantics": "requested M is the frozen action output, not a rejection gate or budget cap; infeasible distinct/capped action becomes explicit zero-flow rather than selecting zero-weight tickets",
        "accounting": "one realized multiplicity is one independent ¥2 ticket/tax unit; requested stake = 2*sum multiplicities; no aggregation",
        "replay_signature": {
            "rule": "computed internally as SHA-256 over contract, canonical issue, Stage-1 output digest, Stage-2 output digest and derived Stage-3 action digest",
            "caller_selected_signature": False,
            "output_field": "stage3_replay_signature_sha256",
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def direction_adapter_golden_fixture() -> dict[str, object]:
    adapter = load_module(ADAPTER_PATH, "bj193_adapter_direction_golden")
    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    policy_id = "DP_59d1464347f9845f8cd5"
    policy = next(
        row
        for row in read_csv(package / "detector_grid.csv")
        if row["policy_id"] == policy_id
    )
    selected_match_ids = [
        "90622", "90585", "90637", "90608", "90587", "90632", "90646"
    ]
    wanted = set(selected_match_ids)
    estimator_by_match = {
        row["match_id"]: row
        for row in read_csv(package / "estimator_match_freeze.csv.gz")
        if row["match_id"] in wanted
    }
    stage1_sha = canonical_hash(
        {"issue": "190101", "selected_match_ids": selected_match_ids}
    )
    output = adapter.apply_direction_adapter(
        selected_match_ids,
        estimator_by_match,
        policy,
        stage1_output_sha256=stage1_sha,
        adapter_sha256=sha256_file(ADAPTER_PATH),
    )
    if (
        output["status"] != "ACTIVE"
        or output["strongest_match_id"] != "90622"
        or output["omitted_code"] != "0"
        or output["delete_leg_index_zero_based"] != 0
    ):
        raise RuntimeError("conditional direction golden anchor drift")
    reconstructed_190_allocation_input = {
        "issue": "190101",
        "ordered_match_ids": output["ordered_match_ids"],
        "per_leg_probability_source": [
            row["estimator_source"] for row in output["per_match"]
        ],
        "per_leg_p3_p1_p0": [
            row["probability_3_1_0"] for row in output["per_match"]
        ],
        "delete_leg_index_zero_based": output["delete_leg_index_zero_based"],
        "omitted_code": output["omitted_code"],
        "strongest_match_id": output["strongest_match_id"],
        "base3_code_order": ["3", "1", "0"],
        "repeat_rank": "joint log probability desc, base-3 ordinal asc",
    }
    reconstructed_hash = canonical_hash(reconstructed_190_allocation_input)
    accepted_hash = (
        "718d8a51151c07f1bba89c0075953183f7cf09120318514980ac9dcf77151dd2"
    )
    if reconstructed_hash != accepted_hash:
        raise RuntimeError("conditional direction does not reproduce #190 anchor")
    return {
        "contract": "BJ193_DIRECTION_ADAPTER_GOLDEN_V3",
        "source": "#190 exact pre-event DP_59d... issue 190101 selected support",
        "input": {
            "policy_id": policy_id,
            "selected_match_ids": selected_match_ids,
            "stage1_output_sha256": stage1_sha,
            "estimator_row_identity_sha256": canonical_hash(
                [
                    {
                        "match_id": match_id,
                        "t1": estimator_by_match[match_id][
                            "t1_score_estimator_identity_sha256"
                        ],
                        "market": estimator_by_match[match_id][
                            "target_safe_consensus_identity_sha256"
                        ],
                    }
                    for match_id in selected_match_ids
                ]
            ),
        },
        "expected_output": output,
        "accepted_190_joint_allocation_input_sha256": accepted_hash,
        "reconstructed_190_joint_allocation_input_sha256": reconstructed_hash,
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def conditional_builder_golden_vectors(
    registry_rows: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    adapter = load_module(ADAPTER_PATH, "bj193_adapter_builder_golden")
    engine = adapter.load_frozen_allocation_engine(ALLOCATION_ENGINE_PATH)
    allow_all = [[0.52, 0.28, 0.20] for _ in range(7)]
    deleted = [list(row) for row in allow_all]
    deleted[2][2] = 0.0
    weighted = [
        [0.55, 0.30, 0.15], [0.20, 0.35, 0.45], [0.48, 0.22, 0.30],
        [0.33, 0.34, 0.33], [0.62, 0.18, 0.20], [0.27, 0.41, 0.32],
        [0.45, 0.25, 0.30],
    ]
    zero = [list(row) for row in allow_all]
    zero[4] = [0.0, 0.0, 0.0]
    cases = [
        ("ALLOW_ALL_FULL", "FULL_ENUMERATED", allow_all, 2187, "NA", None),
        ("ONE_DELETE_WOR_M64", "WOR_DISTINCT", deleted, 64, "137001", None),
        ("ONE_DELETE_WR_M2187", "WR_DUPLICATE_STAKE", deleted, 2187, "137001", None),
        ("WEIGHTED_RESIDUAL_M64", "RESIDUAL_SYSTEMATIC", weighted, 64, "NA", None),
        ("WEIGHTED_CAPPED_M128_CAP2", "CAPPED_REPEAT", weighted, 128, "NA", 2),
        ("WEIGHTED_TOP_MASS_M64", "DETERMINISTIC_TOP_MASS", weighted, 64, "NA", None),
        ("ZERO_SUPPORT", "FULL_ENUMERATED", zero, 2187, "NA", None),
        ("INSUFFICIENT_WOR_M2187", "WOR_DISTINCT", deleted, 2187, "137001", None),
        ("REDUCED_FULL_FALLBACK", "FULL_ENUMERATED", deleted, 2187, "NA", None),
    ]
    rows = []
    for name, mechanism, weights, m, seed, cap in cases:
        context = {
            "issue": "190101",
            "stage1_output_sha256": canonical_hash(
                {"golden": "stage1", "case": name}
            ),
            "stage2_output_sha256": canonical_hash(
                {"golden": "stage2", "case": name}
            ),
            "derived_stage3_action_sha256": canonical_hash(
                {
                    "mechanism": mechanism,
                    "M": m,
                    "cap": cap,
                    "case": name,
                }
            ),
        }
        result = adapter.allocate_conditional_tickets(
            mechanism,
            weights,
            m,
            allocation_engine=engine,
            **context,
            seed=seed,
            cap=cap,
        )
        result = {key: value for key, value in result.items() if key != "counts"}
        rows.append(
            {
                "case": name,
                "input": {
                    "mechanism": mechanism,
                    "per_match_weight_3_1_0": weights,
                    "M": m,
                    "seed": seed,
                    "cap": cap,
                    **context,
                },
                "expected": result,
            }
        )
    role_rows = []
    first_portfolio = None
    for row in read_csv(ROLE_VECTOR_PATH):
        if first_portfolio is None:
            first_portfolio = row["portfolio_id"]
        if row["portfolio_id"] != first_portfolio:
            break
        role_rows.append(row)
    if len(role_rows) != 7:
        raise RuntimeError("#137 production role-vector golden is not exact N7")
    role_rows.sort(key=lambda row: int(row["selection_rank"]))
    ordered = [row["match_id"] for row in role_rows]
    direction_rows = []
    for index, match_id in enumerate(ordered):
        allowed = ["3", "1", "0"] if index else ["3", "1"]
        direction_rows.append(
            {
                "match_id": match_id,
                "allowed_codes": allowed,
                "direction_weight_3_1_0": (
                    ["0.500000000000", "0.300000000000", "0.000000000000"]
                    if index == 0
                    else ["0.500000000000", "0.300000000000", "0.200000000000"]
                ),
            }
        )
    complete_registry_rows = (
        list(registry_rows)
        if registry_rows is not None
        else complete_match_weight_registry()
    )
    registry = {
        (str(row["issue"]), str(row["fold"]), str(row["match_id"])): row
        for row in complete_registry_rows
    }
    complete_rows = [
        registry[(row["issue"], row["fold"], row["match_id"])]
        for row in role_rows
    ]
    role_by_match = {str(row["match_id"]): row for row in complete_rows}
    mapping_cases = []
    for weight_source in adapter.WEIGHT_SOURCE_FIELDS:
        mapped = adapter.combine_stage2_and_stage3_weights(
            ordered, direction_rows, role_by_match, weight_source
        )
        if mapped["status"] != "ACTIVE":
            raise RuntimeError("#137 complete-match mapping golden failed")
        mapping_cases.append(
            {
                "weight_source": weight_source,
                "expected_output": mapped,
            }
        )
    q_mapping = next(
        row["expected_output"]
        for row in mapping_cases
        if row["weight_source"] == "Q_WEIGHT"
    )
    q_allocation = adapter.allocate_conditional_tickets(
        "WOR_DISTINCT",
        q_mapping["per_match_weight_3_1_0"],
        64,
        allocation_engine=engine,
        issue=role_rows[0]["issue"],
        stage1_output_sha256=canonical_hash(
            {"golden": "role_mapping_stage1", "ordered": ordered}
        ),
        stage2_output_sha256=canonical_hash(
            {"golden": "role_mapping_stage2", "mapped": q_mapping}
        ),
        derived_stage3_action_sha256=canonical_hash(
            {"golden": "role_mapping_stage3", "mechanism": "WOR", "M": 64}
        ),
        seed="137001",
    )
    if q_allocation["status"] != "ACTIVE":
        raise RuntimeError("#137 mapped production allocation golden failed")
    return {
        "contract": "BJ193_CONDITIONAL_BUILDER_GOLDEN_V5",
        "adapter_sha256": sha256_file(ADAPTER_PATH),
        "allocation_engine_sha256": sha256_file(ALLOCATION_ENGINE_PATH),
        "role_vector_source_sha256": sha256_file(ROLE_VECTOR_PATH),
        "complete_match_source_sha256": sha256_file(MATCH_VECTOR_PATH),
        "cases": rows,
        "role_vector_mapping_golden": {
            "source_portfolio_id": first_portfolio,
            "ordered_match_ids": ordered,
            "role_rows": role_rows,
            "complete_match_rows": complete_rows,
            "stage2_direction_rows": direction_rows,
            "mapping_cases": mapping_cases,
            "q_weight_wor_m64_expected": {
                key: value for key, value in q_allocation.items() if key != "counts"
            },
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def stage_feature_projection_rows() -> list[dict[str, object]]:
    base = read_csv(ROOT / "results" / V1_PACKAGE / "feature_contract.csv")
    rows: list[dict[str, object]] = []
    common_transform = (
        "inner-train median impute + explicit missing flag; inner-train q01/q99 "
        "winsor; inner-train population mean/SD z-score (zero SD => 0); refit "
        "only on full outer-train after family selection"
    )
    for stage in ("STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"):
        ordinal = 0
        for source in base:
            ordinal += 1
            rows.append(
                {
                    "stage": stage,
                    "feature_ordinal": ordinal,
                    "projection_field": source["feature"],
                    "source_scope": "COMMON_X_I",
                    "source_field": source["feature"],
                    "dtype": "FLOAT64",
                    "encoding": "NUMERIC_STANDARDIZED_PLUS_MISSING_FLAG",
                    "fit_rule": common_transform,
                    "unknown_rule": "NA",
                    "model_input": True,
                    "audit_binding_only": False,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
        upstream: list[tuple[str, str, str, str, bool]] = []
        if stage in {"STAGE_2_DIRECTION", "STAGE_3_BET"}:
            upstream.extend(
                [
                    ("stage1_selected_match_count", "STAGE1", "selected_match_count", "FLOAT64", True),
                    ("stage1_support_count", "STAGE1", "support_count", "FLOAT64", True),
                    ("stage1_candidate_score_min", "STAGE1_DERIVED", "candidate_scores_json:min", "FLOAT64", True),
                    ("stage1_candidate_score_median", "STAGE1_DERIVED", "candidate_scores_json:median", "FLOAT64", True),
                    ("stage1_candidate_score_max", "STAGE1_DERIVED", "candidate_scores_json:max", "FLOAT64", True),
                    ("stage1_selector_family", "STAGE1", "selector_family", "CATEGORY", True),
                    ("stage1_source_action_identity", "STAGE1", "source_action_identity", "CATEGORY", True),
                    ("stage1_availability", "STAGE1", "availability", "CATEGORY", True),
                    ("stage1_fallback_flag", "STAGE1", "fallback_flag", "BOOLEAN", True),
                    ("stage1_reason_code", "STAGE1", "reason_code", "CATEGORY", True),
                    ("stage1_output_sha256", "STAGE1", "output_sha256", "SHA256", False),
                ]
            )
        if stage == "STAGE_3_BET":
            upstream.extend(
                [
                    ("stage2_direction_status", "STAGE2", "availability", "CATEGORY", True),
                    ("stage2_strongest_magnitude", "STAGE2_DERIVED", "per_match:max(magnitude)", "FLOAT64", True),
                    ("stage2_strongest_abs_z", "STAGE2_DERIVED", "per_match:max-ranked(abs_z)", "FLOAT64", True),
                    ("stage2_omitted_code", "STAGE2", "omitted_code", "CATEGORY", True),
                    ("stage2_delete_leg_index", "STAGE2", "delete_leg_index_zero_based", "FLOAT64", True),
                    ("stage2_positive_ticket_support", "STAGE2", "ticket_support_size", "FLOAT64", True),
                    ("stage2_estimator_source_set", "STAGE2_DERIVED", "per_match:sorted_unique(estimator_source)", "CATEGORY_SET", True),
                    ("stage2_protection_count", "STAGE2_DERIVED", "per_match:sum(protection_flag)", "FLOAT64", True),
                    ("stage2_fallback_flag", "STAGE2", "fallback_flag", "BOOLEAN", True),
                    ("stage2_reason_code", "STAGE2", "reason_code", "CATEGORY", True),
                    ("stage2_output_sha256", "STAGE2", "output_sha256", "SHA256", False),
                ]
            )
        for field, scope, source_field, dtype, model_input in upstream:
            ordinal += 1
            if dtype == "FLOAT64":
                encoding = "NUMERIC_STANDARDIZED_PLUS_MISSING_FLAG"
                fit_rule = common_transform
                unknown = "NA"
            elif dtype == "BOOLEAN":
                encoding = "BOOLEAN_0_1"
                fit_rule = "no fitted transform"
                unknown = "missing => explicit missing indicator and 0 value"
            elif dtype == "SHA256":
                encoding = "AUDIT_BINDING_NOT_MODEL_INPUT"
                fit_rule = "no fitted transform"
                unknown = "missing => fail closed"
            else:
                encoding = "TRAIN_ONLY_LEXICAL_ONE_HOT_WITH_UNKNOWN"
                fit_rule = "categories are sorted lexical values observed in fit partition only; append __UNKNOWN__; no frequency pruning"
                unknown = "unseen/blank => __UNKNOWN__"
            rows.append(
                {
                    "stage": stage,
                    "feature_ordinal": ordinal,
                    "projection_field": field,
                    "source_scope": scope,
                    "source_field": source_field,
                    "dtype": dtype,
                    "encoding": encoding,
                    "fit_rule": fit_rule,
                    "unknown_rule": unknown,
                    "model_input": model_input,
                    "audit_binding_only": not model_input,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    return rows


def feature_projection_hashes() -> dict[str, str]:
    rows = stage_feature_projection_rows()
    return {
        stage: canonical_hash([row for row in rows if row["stage"] == stage])
        for stage in ("STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET")
    }


def screen_actions(
    rows: Sequence[Mapping[str, object]], keep: int
) -> list[dict[str, object]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row["screen_score"]),
            -int(row["active_support"]),
            float(row["native_stake_yuan"]),
            str(row["action_identity"]),
        ),
    )
    return [dict(row) for row in ordered[:keep]]


def select_validation_model(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not rows:
        raise ValueError("no validation models")
    return dict(
        min(
            rows,
            key=lambda row: (
                -float(row["validation_pre_tax_roi"]),
                float(row["max_issue_drawdown_yuan"]),
                float(row["native_stake_yuan"]),
                int(row["complexity_rank"]),
                str(row["model_id"]),
            ),
        )
    )


def select_predicted_action(
    rows: Sequence[Mapping[str, object]], comparator_utility: float
) -> dict[str, object] | None:
    eligible = [
        row
        for row in rows
        if float(row["predicted_utility"]) > float(comparator_utility) + 1e-15
    ]
    if not eligible:
        return None
    return dict(
        min(
            eligible,
            key=lambda row: (
                -float(row["predicted_utility"]),
                float(row["native_stake_yuan"]),
                int(row["complexity_rank"]),
                str(row["action_identity"]),
            ),
        )
    )


def stagewise_learner_execution_contract() -> dict[str, object]:
    projection_hash = feature_projection_hashes()
    return {
        "contract": "BJ193_STAGEWISE_LEARNER_EXECUTION_V3",
        "topology": {
            "kind": "THREE_SEPARATE_STAGE_MODELS_EXECUTED_IN_ORDER",
            "stage_order": ["STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"],
            "model_scope": "one action-specific utility model per retained stage action for every non-prior model family; no joint-action model and no shared multiaction estimator",
            "upstream_training": "Stage-2/3 use honest expanding out-of-fold frozen upstream outputs; full upstream rows/digests are audit-bound and only projection fields marked model_input enter estimators",
            "outer_test": "all three families/transforms/screens/models frozen before first issue of held-out year; no within-year outcome update",
        },
        "feature_projection": {
            "registry": "stage_feature_projection.csv",
            "projection_sha256_by_stage": projection_hash,
            "column_order": "feature_ordinal ascending; each numeric feature followed immediately by its missing indicator; categorical levels lexical with __UNKNOWN__ last",
            "fit_partition": "inner-train during selection; full outer-train only after selected family; never validation/test/full sample",
        },
        "family_implementation": {
            "PRIOR_ONLY_FIXED": "per-action constant = aggregate training net/stake with minimum support 20; blank/unsupported action excluded",
            "BINNED_REGIME_RULE": "per action, evaluate every numeric projection singly; train-only linear-interpolated quantile boundaries for requested bins; leaf prediction aggregate net/stake; require min_leaf; choose feature by training MSE then feature_ordinal",
            "SHALLOW_TREE": "per-action deterministic CART regression; squared error; best split over all numeric/encoded columns; thresholds are adjacent-value midpoints; split tie feature_ordinal then threshold; leaf aggregate net/stake; max_depth/min_leaf from grid",
            "MONOTONE_REGULARIZED_SCORE": "per-action ridge least squares with intercept unpenalized and L2 grid value; projected POOL_VALUE coefficients constrained >=0, UNCERTAINTY_DIVERGENCE constrained <=0, other coefficients unconstrained; active-set coordinate order feature_ordinal; convergence tol 1e-12, max 10000",
            "NEAREST_HISTORICAL_REGIME": "per-action Euclidean distance on transformed model columns; distance tie issue chronological ordinal; k from grid; UNIFORM or 1/max(distance,1e-12) weights; prediction weighted aggregate utility",
        },
        "stage_screen": {
            "STAGE_1_SELECTION": {"keep": 16, "mandatory": "accepted static selector fallback"},
            "STAGE_2_DIRECTION": {"keep": 64, "mandatory": "ALLOW_ALL on exact Stage-1 support"},
            "STAGE_3_BET": {"keep": 64, "mandatory": "ENUMERATE_UPSTREAM_SUPPORT fallback and accepted FULL when definitionally supported"},
            "score": "aggregate training pre-tax net / aggregate training stake; minimum active support 20",
            "order": ["score desc", "active support desc", "native stake asc", "stage action identity lexical"],
            "streaming": "complete pass, exact fixed-size heap using the full order tuple; chunk invariant for 1/17/256/4096; no sampling/adaptive early stop",
        },
        "stage1_stage3_compatibility_gate": {
            "contract": "stage1_stage3_compatibility_contract.json",
            "class_registry": "stage3_compatibility_class_registry.csv",
            "coverage_registry": "stage1_stage3_coverage_registry.csv.gz",
            "screen_order": "join the exact Stage-1 interface action and Stage-3 compatibility class; retain only compatibility_status==COMPATIBLE before any Stage-3 outcome screen, model fit, validation, or action choice",
            "incompatible": "excluded with explicit zero flow; never substitute legacy role-vector weights, unit weights, ALLOW_ALL, partial match weights, or losing stake",
        },
        "validation": {
            "primary": "complete-chain sum selected pre-tax net / sum selected stake; blank when stake zero",
            "tie_order": ["ROI desc", "max issue drawdown yuan asc", "native stake asc", "complexity rank asc", "model_id lexical"],
            "random_state": 193001,
            "randomized_subsampling": False,
        },
        "action_choice": {
            "rule": "highest predicted utility strictly > strongest matched prior-only comparator; otherwise exact stage fallback",
            "tie_order": ["predicted utility desc", "native stake asc", "complexity rank asc", "stage action identity lexical"],
            "availability": "only exact pre-event ACTIVE actions whose Stage1×Stage3 pair is COMPATIBLE; NO_BET remains selectable zero flow only when it is the explicit fallback; UNAVAILABLE and INCOMPATIBLE excluded",
        },
        "targets": {
            "STAGE_1_SELECTION": "utility of selector with ALLOW_ALL and FULL downstream controls",
            "STAGE_2_DIRECTION": "incremental utility vs ALLOW_ALL on identical honest Stage-1 path with enumerate-support downstream control",
            "STAGE_3_BET": "incremental utility vs enumerate-support on identical honest Stage-1/2 path after nuisance-seed averaging",
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def learner_execution_fixture() -> dict[str, object]:
    screen_input = [
        {"action_identity": "B", "screen_score": 0.1, "active_support": 30, "native_stake_yuan": 64},
        {"action_identity": "A", "screen_score": 0.1, "active_support": 30, "native_stake_yuan": 64},
        {"action_identity": "C", "screen_score": 0.1, "active_support": 29, "native_stake_yuan": 32},
    ]
    validation_input = [
        {"model_id": "M2", "validation_pre_tax_roi": 0.02, "max_issue_drawdown_yuan": 100, "native_stake_yuan": 64, "complexity_rank": 1},
        {"model_id": "M1", "validation_pre_tax_roi": 0.02, "max_issue_drawdown_yuan": 100, "native_stake_yuan": 64, "complexity_rank": 1},
    ]
    action_input = [
        {"action_identity": "Y", "predicted_utility": 0.03, "native_stake_yuan": 64, "complexity_rank": 1},
        {"action_identity": "X", "predicted_utility": 0.03, "native_stake_yuan": 64, "complexity_rank": 1},
    ]
    return {
        "contract": "BJ193_STAGEWISE_LEARNER_FIXTURE_V3",
        "screen": {
            "input": screen_input,
            "keep": 2,
            "expected_action_order": [
                row["action_identity"] for row in screen_actions(screen_input, 2)
            ],
        },
        "validation": {
            "input": validation_input,
            "expected_model_id": select_validation_model(validation_input)["model_id"],
        },
        "action_choice": {
            "input": action_input,
            "comparator_utility": 0.0,
            "expected_action_identity": select_predicted_action(action_input, 0.0)["action_identity"],
            "expected_fallback_when_comparator": 0.03,
        },
        "projection_hashes": feature_projection_hashes(),
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def stage_interface_contract() -> dict[str, object]:
    common = [
        "issue", "issue_instance", "cutoff_ts", "public_state_sha256",
        "history_end_issue", "history_end_cutoff_ts", "history_sha256",
        "stage_id", "stage_version", "model_id", "model_sha256",
        "source_action_identity", "availability", "abstention_flag",
        "fallback_flag", "reason_code", "output_sha256",
    ]
    return {
        "contract": "BJ193_THREE_STAGE_INTERFACE_V2",
        "decision_unit": "one canonical complete issue",
        "common_pre_event_state": {
            "symbol": "X_i",
            "history": "H_<i contains only issues before the frozen fold boundary; outer-test outcomes never update any model within that fold",
            "source": "v1 issue_regime_features plus public pre-event stage-specific source fields",
            "required_fields": [
                "issue", "issue_instance", "cutoff_ts", "source_version",
                "source_row_sha256", "public_state_sha256", "missingness_json",
            ],
            "forbidden_fields": [
                "target_result", "final_sp", "winning_sp", "payout", "tax",
                "roi", "settlement", "post_cutoff_message_or_market_evidence",
            ],
        },
        "canonical_digest": {
            "serialization": "UTF-8 JSON; sort_keys=true; separators=(',', ':'); ensure_ascii=true",
            "output_rule": "SHA-256 of the complete stage output with output_sha256 omitted",
            "list_order": "ordered match IDs, outcome code order 3/1/0, ticket base-3 ordinal",
        },
        "stages": {
            "STAGE_1_SELECTION": {
                "function": "theta_selection_i = f_selection(X_i,H_<i)",
                "required_fields": common + [
                    "selector_family", "selector_parameters_json",
                    "selected_match_ids_json", "candidate_scores_json",
                    "selected_match_count", "support_count",
                ],
                "reason_codes": [
                    "MODEL_CHOICE", "PRIOR_ONLY_FALLBACK", "STATIC_FALLBACK",
                    "NO_QUALIFYING_MATCH_SET", "INSUFFICIENT_HISTORY",
                    "SOURCE_UNAVAILABLE",
                ],
            },
            "STAGE_2_DIRECTION": {
                "function": "theta_direction_i = f_direction(X_i,selection_output_i,theta_selection_i,H_<i)",
                "required_upstream": [
                    "stage1_output_sha256", "stage1_selected_match_ids_json",
                ],
                "required_fields": common + [
                    "stage1_output_sha256", "stage1_selected_match_ids_json",
                    "derived_direction_action_sha256", "direction_adapter_version",
                    "direction_adapter_sha256", "upstream_190_policy_id",
                    "ordered_match_ids_json", "per_match_outcome_identity_json",
                    "per_match_outcome_weight_json", "per_match_probability_json",
                    "per_match_value_json", "per_match_estimator_source_json",
                    "per_match_estimator_identity_sha256_json",
                    "per_match_estimator_component_identity_sha256_json",
                    "direction_thresholds_json", "protection_flags_json",
                    "ranked_direction_match_ids_json", "strongest_match_id",
                    "delete_leg_index_zero_based", "omitted_code",
                    "positive_ticket_support_count", "support_count",
                ],
                "support_invariant": "ordered_match_ids_json must equal Stage-1 selected_match_ids_json exactly; Stage 2 may change allowed/weighted outcomes but never match support",
                "reason_codes": [
                    "MODEL_CHOICE", "PRIOR_ONLY_FALLBACK", "ALLOW_ALL_FALLBACK",
                    "PROTECTION_TRIGGERED", "ABSTAIN_DIRECTION",
                    "INSUFFICIENT_HISTORY", "SOURCE_UNAVAILABLE",
                ],
            },
            "STAGE_3_BET": {
                "function": "theta_bet_i = f_bet(X_i,selection_output_i,theta_selection_i,direction_output_i,theta_direction_i,H_<i)",
                "required_upstream": [
                    "stage1_output_sha256", "stage2_output_sha256",
                    "ordered_match_ids_json", "per_match_outcome_identity_json",
                    "per_match_outcome_weight_json",
                ],
                "required_fields": common + [
                    "stage1_output_sha256", "stage2_output_sha256",
                    "derived_direction_action_sha256",
                    "derived_stage3_action_sha256",
                    "stage3_replay_signature_sha256",
                    "stage3_compatibility_class_key",
                    "stage1_stage3_compatibility_status",
                    "stage1_stage3_compatibility_reason_code",
                    "ordered_match_ids_json", "per_match_outcome_identity_json",
                    "per_match_outcome_weight_json", "allocator", "weight_source",
                    "mechanism", "repeat_mode", "cap", "M",
                    "requested_M", "effective_M", "positive_ticket_support_count",
                    "per_ticket_stake_yuan", "requested_ticket_count",
                    "requested_stake_yuan", "ticket_ledger_sha256",
                    "ticket_builder_version", "ticket_builder_sha256",
                    "normalized_ticket_weight_sha256", "allocator_engine_sha256",
                    "builder_status", "builder_reason_code",
                    "exposure_signature_sha256", "support_count",
                ],
                "M_boundary": "M is an output from the exact accepted grid, including 2187 FULL; it is not a budget rejection gate. Distinct/capped mechanisms with insufficient positive capacity are explicit NO_BET; FULL enumerates exact positive upstream support once",
                "reason_codes": [
                    "MODEL_CHOICE", "PRIOR_ONLY_FALLBACK",
                    "ENUMERATE_UPSTREAM_SUPPORT_FALLBACK", "NO_TICKET_SUPPORT",
                    "INSUFFICIENT_HISTORY", "SOURCE_UNAVAILABLE",
                ],
            },
        },
        "status_enum": ["ACTIVE", "NO_BET", "UNAVAILABLE"],
        "zero_flow_rule": "NO_BET and UNAVAILABLE emit zero tickets/stake and remain distinct; unavailable never becomes a losing stake",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def digest_stage_output(row: Mapping[str, object]) -> str:
    payload = {key: value for key, value in row.items() if key != "output_sha256"}
    return canonical_hash(payload)


def validate_chain_trace(trace: Mapping[str, Mapping[str, object]]) -> None:
    stage1 = trace["stage1"]
    stage2 = trace["stage2"]
    stage3 = trace["stage3"]
    for stage in (stage1, stage2, stage3):
        if stage["output_sha256"] != digest_stage_output(stage):
            raise RuntimeError("stage output digest drift")
        if stage["availability"] in {"NO_BET", "UNAVAILABLE"} and int(
            stage.get("requested_ticket_count", 0)
        ) != 0:
            raise RuntimeError("zero-flow stage carries tickets")
    if stage2["stage1_output_sha256"] != stage1["output_sha256"]:
        raise RuntimeError("Stage-2 upstream Stage-1 digest drift")
    if stage3["stage1_output_sha256"] != stage1["output_sha256"]:
        raise RuntimeError("Stage-3 upstream Stage-1 digest drift")
    if stage3["stage2_output_sha256"] != stage2["output_sha256"]:
        raise RuntimeError("Stage-3 upstream Stage-2 digest drift")
    if stage3["derived_direction_action_sha256"] != stage2[
        "derived_direction_action_sha256"
    ]:
        raise RuntimeError("Stage-3 direction-adapter identity drift")
    adapter = load_module(ADAPTER_PATH, "bj193_trace_signature_validator")
    expected_signature = adapter.stage3_replay_signature(
        issue=stage3["issue"],
        stage1_output_sha256=stage1["output_sha256"],
        stage2_output_sha256=stage2["output_sha256"],
        derived_stage3_action_sha256=stage3["derived_stage3_action_sha256"],
    )
    if stage3["stage3_replay_signature_sha256"] != expected_signature:
        raise RuntimeError("Stage-3 replay signature identity drift")
    if stage3["stage1_stage3_compatibility_status"] != "COMPATIBLE":
        raise RuntimeError("Stage-3 trace bypassed compatibility gate")
    if stage2["ordered_match_ids_json"] != stage1["selected_match_ids_json"]:
        raise RuntimeError("Stage-2 replaced Stage-1 match support")
    if stage3["ordered_match_ids_json"] != stage2["ordered_match_ids_json"]:
        raise RuntimeError("Stage-3 replaced upstream match support")
    for field in (
        "per_match_outcome_identity_json", "per_match_outcome_weight_json"
    ):
        if stage3[field] != stage2[field]:
            raise RuntimeError(f"Stage-3 replaced Stage-2 {field}")
    if stage3["builder_status"] in {"NO_BET", "UNAVAILABLE"} and (
        int(stage3["requested_ticket_count"]) != 0
        or float(stage3["requested_stake_yuan"]) != 0
    ):
        raise RuntimeError("zero-flow builder carries economic flow")


def chain_fixture() -> dict[str, object]:
    adapter = load_module(ADAPTER_PATH, "bj193_chain_fixture_adapter")
    common = {
        "issue": "26080",
        "issue_instance": "FIXTURE_26080@PRE_EVENT",
        "cutoff_ts": "2026-08-05T10:00:00+08:00",
        "public_state_sha256": canonical_hash("fixture-public-state"),
        "history_end_issue": "26079",
        "history_end_cutoff_ts": "2026-08-04T10:00:00+08:00",
        "history_sha256": canonical_hash("fixture-history"),
        "stage_version": VERSION,
        "model_id": "PRIOR_ONLY_FIXED_FIXTURE",
        "model_sha256": canonical_hash("fixture-model"),
        "availability": "ACTIVE",
        "abstention_flag": False,
        "fallback_flag": True,
        "reason_code": "PRIOR_ONLY_FALLBACK",
    }
    match_ids = [f"M{i}" for i in range(1, 8)]
    stage1 = {
        **common,
        "stage_id": "STAGE_1_SELECTION",
        "source_action_identity": "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1",
        "selector_family": "S2_COLD_FIRST",
        "selector_parameters_json": canonical_json({"top_k": 1}),
        "selected_match_ids_json": canonical_json(match_ids),
        "candidate_scores_json": canonical_json({match_id: index / 10 for index, match_id in enumerate(match_ids)}),
        "selected_match_count": 7,
        "support_count": 7,
    }
    stage1["output_sha256"] = digest_stage_output(stage1)
    stage2 = {
        **common,
        "stage_id": "STAGE_2_DIRECTION",
        "source_action_identity": "B0_BEST_FULL",
        "stage1_output_sha256": stage1["output_sha256"],
        "stage1_selected_match_ids_json": stage1["selected_match_ids_json"],
        "derived_direction_action_sha256": canonical_hash(
            {"adapter": "STATIC_ALLOW_ALL", "stage1": stage1["output_sha256"]}
        ),
        "direction_adapter_version": "STATIC_ALLOW_ALL_CONTROL_V1",
        "direction_adapter_sha256": sha256_file(ADAPTER_PATH),
        "upstream_190_policy_id": "NA",
        "ordered_match_ids_json": stage1["selected_match_ids_json"],
        "per_match_outcome_identity_json": canonical_json({match_id: ["3", "1", "0"] for match_id in match_ids}),
        "per_match_outcome_weight_json": canonical_json({match_id: ["1", "1", "1"] for match_id in match_ids}),
        "per_match_probability_json": canonical_json({match_id: ["0.34", "0.33", "0.33"] for match_id in match_ids}),
        "per_match_value_json": canonical_json({match_id: ["NA", "NA", "NA"] for match_id in match_ids}),
        "per_match_estimator_source_json": canonical_json(
            {match_id: "STATIC_ALLOW_ALL" for match_id in match_ids}
        ),
        "per_match_estimator_identity_sha256_json": canonical_json(
            {match_id: canonical_hash(["STATIC_ALLOW_ALL", match_id]) for match_id in match_ids}
        ),
        "per_match_estimator_component_identity_sha256_json": canonical_json(
            {match_id: {} for match_id in match_ids}
        ),
        "direction_thresholds_json": canonical_json({"rule": "ALLOW_ALL"}),
        "protection_flags_json": canonical_json({match_id: False for match_id in match_ids}),
        "ranked_direction_match_ids_json": canonical_json(match_ids),
        "strongest_match_id": "",
        "delete_leg_index_zero_based": "NA",
        "omitted_code": "",
        "positive_ticket_support_count": 2187,
        "support_count": 7,
    }
    stage2["output_sha256"] = digest_stage_output(stage2)
    derived_stage3_action_sha256 = canonical_hash(
        {
            "source_action_identity": "FULL_ENUMERATED_M2187",
            "weight_source": "NA",
            "mechanism": "FULL_ENUMERATED",
            "M": 2187,
        }
    )
    stage3 = {
        **common,
        "stage_id": "STAGE_3_BET",
        "source_action_identity": "FULL_ENUMERATED_M2187",
        "stage1_output_sha256": stage1["output_sha256"],
        "stage2_output_sha256": stage2["output_sha256"],
        "derived_direction_action_sha256": stage2[
            "derived_direction_action_sha256"
        ],
        "derived_stage3_action_sha256": derived_stage3_action_sha256,
        "stage3_replay_signature_sha256": adapter.stage3_replay_signature(
            issue=common["issue"],
            stage1_output_sha256=stage1["output_sha256"],
            stage2_output_sha256=stage2["output_sha256"],
            derived_stage3_action_sha256=derived_stage3_action_sha256,
        ),
        "stage3_compatibility_class_key": stage3_compatibility_class_key("NA"),
        "stage1_stage3_compatibility_status": "COMPATIBLE",
        "stage1_stage3_compatibility_reason_code": (
            "UNIT_WEIGHT_CONTROL_NO_MATCH_REGISTRY_REQUIRED"
        ),
        "ordered_match_ids_json": stage2["ordered_match_ids_json"],
        "per_match_outcome_identity_json": stage2["per_match_outcome_identity_json"],
        "per_match_outcome_weight_json": stage2["per_match_outcome_weight_json"],
        "allocator": "FULL_ENUMERATED",
        "weight_source": "NA",
        "mechanism": "FULL_ENUMERATED",
        "repeat_mode": "NOT_APPLICABLE",
        "cap": "NA",
        "M": 2187,
        "requested_M": 2187,
        "effective_M": 2187,
        "positive_ticket_support_count": 2187,
        "per_ticket_stake_yuan": 2,
        "requested_ticket_count": 2187,
        "requested_stake_yuan": 4374,
        "ticket_ledger_sha256": canonical_hash(list(range(2187))),
        "ticket_builder_version": "BJ193_STAGE2_TO_STAGE3_BUILDER_V4",
        "ticket_builder_sha256": sha256_file(ADAPTER_PATH),
        "normalized_ticket_weight_sha256": canonical_hash(
            [format(1 / 2187, ".17g")] * 2187
        ),
        "allocator_engine_sha256": ALLOCATION_ENGINE_SHA256,
        "builder_status": "ACTIVE",
        "builder_reason_code": "FULL_ALLOW_ALL",
        "exposure_signature_sha256": canonical_hash({"match_ids": match_ids, "codes": "310"}),
        "support_count": 7,
    }
    stage3["output_sha256"] = digest_stage_output(stage3)
    trace = {"stage1": stage1, "stage2": stage2, "stage3": stage3}
    validate_chain_trace(trace)
    return {
        "contract": "BJ193_CHAIN_INTERFACE_FIXTURE_V2",
        "outcome_access": False,
        "trace": trace,
        "final_trace_sha256": canonical_hash(trace),
        "expected": {
            "stage1_to_stage2_bound": True,
            "stage1_and_stage2_to_stage3_bound": True,
            "match_support_preserved": True,
            "ticket_count": 2187,
            "requested_stake_yuan": 4374,
        },
    }


def stage_training_rows() -> list[dict[str, object]]:
    projection_hash = feature_projection_hashes()
    common = {
        "minimum_history": "60 prior canonical issues and >=2 prior calendar years",
        "minimum_action_support": 20,
        "nested_fit": "inner-train transforms/models; prior-year validation chooses family; selected family refit on full outer-train; entire outer-test year remains untouched",
        "training_upstream_rule": "downstream training uses expanding chronological out-of-fold upstream outputs generated with H_<j only, never in-sample or oracle upstream choices",
        "test_update_rule": "no model, transform, screen, rank, or fallback update from any outer-test outcome within the held-out year",
        "pre_tax_primary": True,
        "model_topology": "one action-specific utility model per retained stage action; three separately fit stage models; no flattened joint-action or shared multiaction estimator",
        "screen_order": "screen_score desc; active_support desc; native_stake_yuan asc; stage action identity lexical",
        "validation_tie_order": "ROI desc; max issue drawdown yuan asc; native stake asc; complexity rank asc; model_id lexical",
        "action_tie_order": "predicted utility desc; native stake asc; complexity rank asc; stage action identity lexical",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }
    return [
        {
            "stage": "STAGE_1_SELECTION",
            "target": "prior-issue seed-aggregated pre-tax utility of each exact selector with static ALLOW_ALL direction and FULL_ENUMERATED downstream control",
            "loss": "unweighted MSE of active prior-issue utility; validation controls realized selected-path pre-tax ROI and holding tie-break",
            "support_mask": "exact selector defined, seven selected matches, canonical prior outcome available, and static Stage-2/3 controls definitionally supported; NO_BET explicit, UNAVAILABLE excluded",
            "prior_only_fallback": "accepted #134/#167 BEST_FULL selector S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1",
            "screen": "rank all available Stage-1 actions on inner/outer training only; retain exact top 16 plus fallback; no early stop",
            "upstream_inputs": "X_i,H_<i only",
            "feature_projection_sha256": projection_hash["STAGE_1_SELECTION"],
            **common,
        },
        {
            "stage": "STAGE_2_DIRECTION",
            "target": "conditional incremental prior-issue pre-tax utility of each direction action versus ALLOW_ALL, holding the honest Stage-1 output and static enumerate-upstream-support Stage-3 control fixed",
            "loss": "unweighted MSE of conditional utility/lift on matched active prior issues; validation controls conditional selected-path pre-tax lift and holding tie-break",
            "support_mask": "exact honest Stage-1 selected match IDs preserved, direction estimates available for all seven matches, and static Stage-3 control supported; NO_BET explicit, UNAVAILABLE excluded",
            "prior_only_fallback": "B0_BEST_FULL / ALLOW_ALL outcome codes on exact Stage-1 support",
            "screen": "rank every causally AVAILABLE #190 direction action on conditional inner/outer training support; retain exact top 64 plus fallback; no early stop",
            "upstream_inputs": "X_i,H_<i plus immutable Stage-1 output and digest",
            "feature_projection_sha256": projection_hash["STAGE_2_DIRECTION"],
            **common,
        },
        {
            "stage": "STAGE_3_BET",
            "target": "conditional prior-issue seed-aggregated pre-tax utility of each accepted allocator/repeat/M action given honest Stage-1 and Stage-2 outputs",
            "loss": "unweighted MSE of conditional utility/lift on matched active prior issues; validation controls conditional selected-path pre-tax lift and holding tie-break",
            "support_mask": "exact honest Stage-1/2 output digests, complete required nuisance-seed ensemble, and reproducible ticket ledger; NO_BET explicit, any missing replicate makes action UNAVAILABLE",
            "prior_only_fallback": "enumerate the exact upstream Stage-2 allowed ticket support; M equals that support size",
            "screen": "rank all 963 seed-agnostic Stage-3 actions after nuisance-seed averaging; retain exact top 64 plus fallback; no early stop",
            "upstream_inputs": "X_i,H_<i plus immutable Stage-1 and Stage-2 outputs/digests",
            "feature_projection_sha256": projection_hash["STAGE_3_BET"],
            **common,
        },
    ]


def stage_model_grid() -> list[dict[str, object]]:
    base = read_csv(ROOT / "results" / V1_PACKAGE / "model_family_grid.csv")
    learner = stagewise_learner_execution_contract()
    projection_hash = learner["feature_projection"]["projection_sha256_by_stage"]
    rows = []
    for stage in ("STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"):
        for row in base:
            rows.append(
                {
                    "stage": stage,
                    "stage_model_id": f"{stage}::{row['model_id']}",
                    "source_model_id": row["model_id"],
                    "family": row["family"],
                    "parameters_json": row["parameters_json"],
                    "complexity_rank": row["complexity_rank"],
                    "feature_fit": row["feature_fit"],
                    "hyperparameter_selection": row["hyperparameter_selection"],
                    "action_selection": row["action_selection"],
                    "prior_only_fallback": row["family"] == "PRIOR_ONLY_FIXED",
                    "model_topology": "ONE_ACTION_SPECIFIC_UTILITY_MODEL_PER_RETAINED_STAGE_ACTION",
                    "feature_projection_sha256": projection_hash[stage],
                    "transform_spec": learner["feature_projection"]["column_order"]
                    + "; "
                    + learner["feature_projection"]["fit_partition"],
                    "estimator_spec": learner["family_implementation"][
                        row["family"]
                    ],
                    "stage_screen_spec": canonical_json(
                        learner["stage_screen"][stage]
                    ),
                    "screen_order": canonical_json(
                        learner["stage_screen"]["order"]
                    ),
                    "validation_tie_order": canonical_json(
                        learner["validation"]["tie_order"]
                    ),
                    "action_tie_order": canonical_json(
                        learner["action_choice"]["tie_order"]
                    ),
                    "random_state": learner["validation"]["random_state"],
                    "upstream_interface": (
                        "X_i,H_<i" if stage == "STAGE_1_SELECTION"
                        else "X_i,H_<i,Stage-1 output"
                        if stage == "STAGE_2_DIRECTION"
                        else "X_i,H_<i,Stage-1 output,Stage-2 output"
                    ),
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    if len(rows) != 90 or sum(bool(row["prior_only_fallback"]) for row in rows) != 3:
        raise RuntimeError("#193 stage model-grid drift")
    return rows


def chronology_contract() -> dict[str, object]:
    v1 = ROOT / "results" / V1_PACKAGE
    folds = read_csv(v1 / "chronological_nested_folds.csv")
    return {
        "contract": "BJ193_STAGEWISE_NESTED_CHRONOLOGY_V2",
        "frozen_fold_file": f"{V1_PACKAGE}/chronological_nested_folds.csv",
        "frozen_fold_file_sha256": sha256_file(v1 / "chronological_nested_folds.csv"),
        "outer_folds": [row["outer_fold"] for row in folds],
        "outer_fold_count": len(folds),
        "frozen_folds": folds,
        "stage_order": ["STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"],
        "inner_training_upstream_outputs": "for each training issue j, generate every upstream output as an out-of-fold expanding chronological fit restricted to H_<j; never train a downstream stage on in-sample or realized-best upstream actions",
        "inner_validation": "freeze Stage-1 then Stage-2 then Stage-3 outputs; score complete chain on prior-year validation; no validation outcome enters any fit or screen",
        "outer_refit": "after choosing each stage family, refit transforms/screens/models using full outer-train and honest cross-fitted upstream outputs",
        "outer_test": "freeze all three model families before the first held-out-year issue; do not update from any outcome in that outer-test year; make the three decisions in order at each issue cutoff",
        "minimum_history": "each stage independently falls back when fewer than 60 prior canonical issues, fewer than two years, or fewer than 20 active rows for the stage action",
        "seed_rule": "aggregate the exact accepted nuisance-seed ensemble before Stage-3 screen, fit, choice, oracle, regret, or promotion; never select seed or sum seed stakes",
        "oracle_rule": "Tier O may choose stage actions from realized outcomes only after causal chain settlement and only for ceiling/regret; never an input to any Tier-C stage",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def attribution_rows() -> list[dict[str, object]]:
    return [
        {
            "ordinal": 1,
            "control_id": "ALL_STATIC",
            "stage1": "STATIC_BEST_FULL selector",
            "stage2": "ALLOW_ALL outcome codes",
            "stage3": "FULL_ENUMERATED exact upstream support",
            "incremental_comparator": "NA",
            "attribution": "controlling static baseline",
        },
        {
            "ordinal": 2,
            "control_id": "DYNAMIC_SELECTION_ONLY",
            "stage1": "dynamic f_selection",
            "stage2": "ALLOW_ALL outcome codes",
            "stage3": "FULL_ENUMERATED exact upstream support",
            "incremental_comparator": "ALL_STATIC",
            "attribution": "Stage-1 lift",
        },
        {
            "ordinal": 3,
            "control_id": "DYNAMIC_SELECTION_DIRECTION",
            "stage1": "dynamic f_selection",
            "stage2": "dynamic f_direction conditional on immutable Stage-1 output",
            "stage3": "FULL_ENUMERATED exact upstream direction support",
            "incremental_comparator": "DYNAMIC_SELECTION_ONLY",
            "attribution": "Stage-2 incremental lift conditional on Stage 1",
        },
        {
            "ordinal": 4,
            "control_id": "FULL_DYNAMIC_CHAIN",
            "stage1": "dynamic f_selection",
            "stage2": "dynamic f_direction conditional on immutable Stage-1 output",
            "stage3": "dynamic f_bet conditional on immutable Stage-1/2 outputs",
            "incremental_comparator": "DYNAMIC_SELECTION_DIRECTION",
            "attribution": "Stage-3 incremental lift and end-to-end chain",
        },
    ]


def output_contract() -> dict[str, object]:
    return {
        "contract": "BJ193_CHAIN_GATE_B_OUTPUT_SCHEMA_V2",
        "raw": {
            "stage1_selection_output.csv.gz": stage_interface_contract()["stages"]["STAGE_1_SELECTION"]["required_fields"],
            "stage2_direction_output.csv.gz": stage_interface_contract()["stages"]["STAGE_2_DIRECTION"]["required_fields"],
            "stage3_bet_output.csv.gz": stage_interface_contract()["stages"]["STAGE_3_BET"]["required_fields"],
            "issue_chain_decision_trace.csv.gz": [
                "issue", "issue_instance", "cutoff_ts",
                "public_input_sources_json", "public_state_sha256",
                "history_end_issue", "history_end_cutoff_ts", "history_sha256",
                "stage1_model_id", "stage1_model_version",
                "stage1_source_action_identity", "stage1_output_sha256",
                "stage1_availability", "stage1_fallback", "stage1_reason_code",
                "stage2_model_id", "stage2_model_version",
                "stage2_source_action_identity", "stage2_derived_direction_action_sha256",
                "stage2_direction_adapter_sha256", "stage2_output_sha256",
                "stage2_availability", "stage2_fallback", "stage2_reason_code",
                "stage3_model_id", "stage3_model_version",
                "stage3_source_action_identity", "stage3_derived_action_sha256",
                "stage3_replay_signature_sha256",
                "stage3_compatibility_class_key",
                "stage1_stage3_compatibility_status",
                "stage1_stage3_compatibility_reason_code",
                "stage3_output_sha256",
                "stage3_availability", "stage3_fallback", "stage3_reason_code",
                "ticket_builder_version", "ticket_builder_sha256",
                "normalized_ticket_weight_sha256", "allocator_engine_sha256",
                "builder_status", "builder_reason_code",
                "final_ticket_ledger_sha256", "requested_ticket_count",
                "requested_stake_yuan", "exposure_signature_sha256",
                "chain_trace_sha256", "availability", "fallback_path",
                "reason_codes_json",
            ],
            "final_ticket_ledger.csv.gz": [
                "issue", "stage3_output_sha256", "ticket_ordinal",
                "ordered_outcome_codes", "multiplicity", "unit_stake_yuan",
                "ticket_sha256",
            ],
        },
        "stage_receipts": [
            "stage_model_selection_receipt.csv",
            "stage_action_screen_receipt.csv.gz",
            "stage_support_census.csv",
            "stage_fallback_census.csv",
            "stage_choice_frequency.csv",
        ],
        "incremental_science": [
            "incremental_attribution_summary.csv",
            "native_and_strict_common_performance.csv",
            "oracle_ceiling_and_stage_regret.csv.gz",
            "failure_attribution.csv",
            "handoff_dynamic_sleeves.csv",
        ],
        "holding": [
            "issue_equity_timeseries.csv.gz", "streak_metrics.csv",
            "rolling_loss_windows.csv", "drawdown_episodes.csv",
            "recovery_summary.csv", "holding_feasibility_scorecard.csv",
        ],
        "stability": [
            "year_fold_loyo.csv", "bootstrap_paired_20000.csv",
            "ex_largest_issue_year.csv", "payout_concentration.csv",
            "within_seed_dispersion.csv",
        ],
        "chart_sources": [
            "stage1_selector_choice_by_regime.csv",
            "stage2_direction_choice_by_regime.csv",
            "stage3_allocator_M_choice_by_regime.csv",
            "incremental_roi_holding_bridge.csv",
            "chain_equity_drawdown.csv.gz", "stage_regret_decomposition.csv",
            "feature_partial_dependence.csv.gz", "complete_dynamic_M_curves.csv.gz",
        ],
        "support_views": {
            "native": "each control on its exact frozen availability; NO_BET explicit zero flow",
            "strict_common": "same canonical issue rows where all four matched controls are not UNAVAILABLE; NO_BET retained",
        },
        "gate_a_executable_bindings": {
            "direction_adapter": "direction_adapter_contract.json + direction_adapter_golden_fixture.json + conditional_chain_adapter.py",
            "ticket_builder": "conditional_builder_contract.json + conditional_builder_golden_vectors.json + byte-bound bj145_allocation_engine.py",
            "stagewise_learner": "stagewise_learner_execution_contract.json + stage_feature_projection.csv + learner_execution_fixture.json",
            "stage1_stage3_compatibility": "stage3_complete_match_weight_registry.csv.gz + stage3_compatibility_class_registry.csv + stage1_stage3_coverage_registry.csv.gz + stage1_stage3_compatibility_contract.json + native_137_weight_reconciliation.json",
        },
        "economics": "pre-tax ROI controls; tax is reference-only and applied per exact ¥2 ticket without aggregation",
        "holding_unit": "chronologically ordered canonical issue; v1 holding contract and fixture remain byte-bound",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def seed_aggregation_contract() -> dict[str, object]:
    source = ROOT / "results" / V1_PACKAGE / "action_learning_execution_contract.json"
    return {
        "contract": "BJ193_STAGE3_NUISANCE_SEED_AGGREGATION_V2",
        "source_file": f"{V1_PACKAGE}/action_learning_execution_contract.json",
        "source_file_sha256": sha256_file(source),
        "selection_identity": "namespace + selector_factor_id + causal_allocation_factor_id; seed and replay row are forbidden",
        "required_replicates": "exact frozen_seed_set_sha256 and replay_row_set_sha256 from every Stage-3 catalog row",
        "availability": "if any required replicate is missing/unavailable, the entire issue-action is UNAVAILABLE; never convert it to losing stake",
        "economics": "arithmetic mean replicate stake/gross/tax/net represents one randomized strategy; never sum seed stake as purchased exposure",
        "ordering": "exact numeric seed then replay row identity before accumulation",
        "ranking_boundary": "average before every Stage-3 screen, target, fit, choice, oracle, regret, bootstrap, and promotion decision",
        "within_seed_reporting": "replicate ROI distribution/SD/MCSE/quantiles/positive fraction is diagnostic only and never a selectable action dimension",
        "tax": "each exact ¥2 ticket is an independent tax unit; no ticket/issue/policy aggregation",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def decision_trace_schema() -> dict[str, object]:
    output = output_contract()
    return {
        "contract": "BJ193_END_TO_END_DECISION_TRACE_V2",
        "decision_unit": "one canonical issue at one explicit public pre-event cutoff",
        "fields": output["raw"]["issue_chain_decision_trace.csv.gz"],
        "stage_payloads": {
            "stage1": "stage1_selection_output.csv.gz",
            "stage2": "stage2_direction_output.csv.gz",
            "stage3": "stage3_bet_output.csv.gz",
            "ticket_ledger": "final_ticket_ledger.csv.gz",
        },
        "integrity": [
            "public_state_sha256 binds every public pre-event source row/version and missingness flag",
            "Stage-2 row binds exact Stage-1 output_sha256 and ordered selected match IDs",
            "Stage-2 row binds its derived conditional action identity, adapter hash and every selected-match estimator identity/source",
            "Stage-3 row binds exact Stage-1 and Stage-2 output_sha256 plus derived direction identity, outcome identities/weights, normalized full-ordinal vector and accepted allocator hash",
            "Stage-3 row binds a canonical internal replay signature over issue, ordered Stage-1 output digest, Stage-2 output digest and derived Stage-3 action; no caller-selected RNG namespace exists",
            "Stage-3 row binds the normalized Stage1×Stage3 compatibility class/status/reason before any screen or economic flow",
            "chain_trace_sha256 binds the three complete stage outputs and final ticket ledger SHA-256",
            "final ticket ledger must be byte-reproducible from Stage-3 output, frozen builder version/hash and ordered base-3 ticket rule",
        ],
        "fallback": "availability, abstention, fallback and reason code are explicit at every stage; NO_BET and UNAVAILABLE remain distinct zero-flow states",
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def incremental_reporting_contract() -> dict[str, object]:
    return {
        "contract": "BJ193_STAGEWISE_INCREMENTAL_REPORTING_V2",
        "contrasts": [
            {
                "stage": "STAGE_1_SELECTION",
                "candidate": "DYNAMIC_SELECTION_ONLY",
                "comparator": "ALL_STATIC",
                "interpretation": "selection lift with direction and bet construction static",
            },
            {
                "stage": "STAGE_2_DIRECTION",
                "candidate": "DYNAMIC_SELECTION_DIRECTION",
                "comparator": "DYNAMIC_SELECTION_ONLY",
                "interpretation": "direction lift conditional on the identical dynamic Stage-1 path",
            },
            {
                "stage": "STAGE_3_BET",
                "candidate": "FULL_DYNAMIC_CHAIN",
                "comparator": "DYNAMIC_SELECTION_DIRECTION",
                "interpretation": "allocator/repeat/M lift conditional on identical Stage-1/2 paths",
            },
            {
                "stage": "END_TO_END",
                "candidate": "FULL_DYNAMIC_CHAIN",
                "comparator": "ALL_STATIC",
                "interpretation": "complete causal chain versus controlling static baseline",
            },
        ],
        "metrics": [
            "support", "stake_yuan", "pre_tax_roi", "tax_adjusted_roi",
            "hit_rate", "payout_hhi", "largest_issue_share", "turnover",
            "max_loss_streak_calendar", "max_loss_streak_active",
            "rolling_5_10_20_loss_probability", "max_drawdown_yuan",
            "max_drawdown_pct", "drawdown_duration", "time_under_water",
            "recovery_time",
        ],
        "stability": "paired 20,000 issue bootstrap; YEAR/FOLD/LOYO; ex-largest issue/year; payout concentration; same draw indices for every matched contrast",
        "decision": "a causal sleeve must beat the strongest matched prior/static comparator, survive exclusions, avoid one-payout dependence, and not have unacceptable holding deterioration",
        "strict_ev": "request independent EV only if a causal candidate is materially positive/promotable; oracle positivity never qualifies",
        "parent_192": "no sleeve or portfolio allocation authority until #193 Gate B is PI accepted and the native graph unblocks #192",
    }


def write_readme(path: Path, counts: Mapping[str, int]) -> None:
    path.write_text(
        f"""# #193 Gate-A v2 — chained per-issue interface amendment

This package amends, but does not replace or mutate, the accepted
`{V1_PACKAGE}` lineage.  It freezes three separately parameterized decisions:
match selection, outcome direction, and ticket construction.  No target
outcome or Gate-B settlement payload is opened.

Stage 2 actions are explicitly derived Stage-1-conditional adapters; they are
not renamed #190 B0-only actions. Stage 3 actions bind accepted #167 parameters
to the exact Stage-2 mask/weight-to-ordinal builder and byte-bound #145 engine.
The complete #137 match-vector registry supplies hash-bound pre-event weights
for every supported #127/#134 N7. A normalized Stage1×Stage3 registry screens
all {counts['stage1_stage3_pairs']:,} action pairs before learning: incompatible
#190/non-NA pairs are explicit zero-flow and never fall back to partial, unit,
or fabricated weights. The allocator replay signature is derived internally
from the issue and complete upstream/action digests.
The stagewise learner registry fixes projection columns, encoding, per-action
topology, screening and every validation/action tie.

Catalog census:

- Stage 1 selection actions: {counts['stage1']:,}
- Stage 2 direction actions: {counts['stage2']:,}
- Stage 3 seed-agnostic allocator/M actions: {counts['stage3']:,}
- Complete pre-event Stage-3 match-weight rows: {counts['complete_match_weights']:,}
- Normalized Stage1×Stage3 coverage rows/classes: {counts['compatibility_coverage']:,}/{counts['compatibility_classes']:,}
- stage-specific model configurations: {counts['models']:,}
- required matched attribution controls: 4

Downstream stages consume immutable upstream outputs and digests.  Their
training inputs are chronologically honest upstream predictions, not in-sample
or realized-best choices.  Seed remains a nuisance replicate and M remains an
output from the accepted grid, not a budget gate.

`SHA256SUMS.json` binds exact committed transport bytes and the recorded
runtime. `PORTABLE_SHA256SUMS.json` plus `CONTENT_IDENTITY.json` bind canonical
decompressed gzip content, so semantic replay is portable across compliant
gzip implementations even when compressed bytes differ.

Status: ready for PI review, no Gate-B, betting, production, or #192 authority.
""",
        encoding="utf-8",
    )


def publish(output: Path) -> None:
    source_rows = verify_sources()
    if sha256_file(ALLOCATION_ENGINE_PATH) != ALLOCATION_ENGINE_SHA256:
        raise RuntimeError("accepted #145 allocation engine drift")
    stage1 = stage1_catalog()
    stage2 = stage2_catalog()
    stage3 = stage3_catalog()
    complete_weights = complete_match_weight_registry()
    native_reconciliation = native_137_weight_reconciliation(complete_weights)
    compatibility_classes = stage3_compatibility_class_registry(stage3)
    compatibility_coverage = stage1_stage3_coverage_registry(
        stage1, complete_weights, compatibility_classes
    )
    compatibility_contract = stage1_stage3_compatibility_contract(
        compatibility_classes, compatibility_coverage, native_reconciliation
    )
    models = stage_model_grid()
    fixture = chain_fixture()
    counts = {
        "stage1": len(stage1),
        "stage2": len(stage2),
        "stage3": len(stage3),
        "models": len(models),
        "complete_match_weights": len(complete_weights),
        "compatibility_classes": len(compatibility_classes),
        "compatibility_coverage": len(compatibility_coverage),
        "stage1_stage3_pairs": sum(
            int(row["stage3_action_count"])
            for row in compatibility_coverage
        ),
        "compatible_coverage_rows": sum(
            row["compatibility_status"] == "COMPATIBLE"
            for row in compatibility_coverage
        ),
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError(f"refusing to replace immutable package: {output}")
    stage = output.with_name(f"{output.name}.stage-{uuid.uuid4().hex}")
    stage.mkdir()
    try:
        write_csv(stage / "source_binding.csv", list(source_rows[0]), source_rows)
        write_gzip(stage / "stage1_selection_catalog.csv.gz", CATALOG_FIELDS, stage1)
        write_gzip(stage / "stage2_direction_catalog.csv.gz", CATALOG_FIELDS, stage2)
        write_gzip(stage / "stage3_bet_catalog.csv.gz", CATALOG_FIELDS, stage3)
        write_gzip(
            stage / "stage3_complete_match_weight_registry.csv.gz",
            COMPLETE_MATCH_WEIGHT_FIELDS,
            complete_weights,
        )
        write_csv(
            stage / "stage3_compatibility_class_registry.csv",
            list(compatibility_classes[0]),
            compatibility_classes,
        )
        write_gzip(
            stage / "stage1_stage3_coverage_registry.csv.gz",
            list(compatibility_coverage[0]),
            compatibility_coverage,
        )
        write_json(
            stage / "stage1_stage3_compatibility_contract.json",
            compatibility_contract,
        )
        write_json(
            stage / "native_137_weight_reconciliation.json",
            native_reconciliation,
        )
        training = stage_training_rows()
        write_csv(stage / "stage_training_contract.csv", list(training[0]), training)
        write_csv(stage / "stage_model_grid.csv", list(models[0]), models)
        projection = stage_feature_projection_rows()
        write_csv(
            stage / "stage_feature_projection.csv",
            list(projection[0]),
            projection,
        )
        attribution = attribution_rows()
        for row in attribution:
            row.update(
                {
                    "support": "native plus strict common across all four controls; NO_BET retained; UNAVAILABLE excluded only from strict common",
                    "pre_tax_primary": True,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
        write_csv(stage / "attribution_control_registry.csv", list(attribution[0]), attribution)
        write_json(stage / "stage_interface_contract.json", stage_interface_contract())
        write_json(
            stage / "direction_adapter_contract.json",
            direction_adapter_contract(),
        )
        write_json(
            stage / "direction_adapter_golden_fixture.json",
            direction_adapter_golden_fixture(),
        )
        write_json(
            stage / "conditional_builder_contract.json",
            conditional_builder_contract(),
        )
        write_json(
            stage / "conditional_builder_golden_vectors.json",
            conditional_builder_golden_vectors(complete_weights),
        )
        write_json(
            stage / "stagewise_learner_execution_contract.json",
            stagewise_learner_execution_contract(),
        )
        write_json(
            stage / "learner_execution_fixture.json",
            learner_execution_fixture(),
        )
        write_json(stage / "stagewise_chronology_contract.json", chronology_contract())
        write_json(stage / "seed_aggregation_contract.json", seed_aggregation_contract())
        write_json(stage / "decision_trace_schema.json", decision_trace_schema())
        write_json(stage / "chain_decision_trace_fixture.json", fixture)
        write_json(stage / "gate_b_output_schema_contract.json", output_contract())
        write_json(
            stage / "incremental_reporting_contract.json",
            incremental_reporting_contract(),
        )
        v1_manifest = json.loads(
            (ROOT / "results" / V1_PACKAGE / "SHA256SUMS.json").read_text()
        )
        lineage = {
            "contract": CONTRACT,
            "version": VERSION,
            "v1": {
                "package": V1_PACKAGE,
                "manifest_sha256": V1_MANIFEST_SHA256,
                "content_identity_sha256": V1_CONTENT_SHA256,
                "action_stream_sha256": V1_ACTION_STREAM_SHA256,
                "payload_count": len(v1_manifest),
                "immutable_status": "ACCEPTED_LINEAGE_UNCHANGED",
                "superseded_scope_only": "one-model-per-joint-action topology; all sources/features/chronology/seed/path-risk definitions remain bound",
            },
            "v2_amendment": "three separately parameterized stage interfaces; derived Stage-1-conditional direction identities; hash-bound complete-match Stage-3 weight registry plus normalized Stage1×Stage3 compatibility gate with no fallback; internally derived replay signature; exact Stage-2-to-ticket-vector allocator builder; executable stagewise feature/topology/screen/tie contract; portable decompressed-content identity; honest upstream training outputs; decision trace; matched incremental controls",
            "outcome_access": False,
            "gate_b_authorized": False,
        }
        write_json(stage / "lineage_binding.json", lineage)
        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "issue": 193,
            "parent_issue": 192,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_INTERFACE_AMENDMENT",
            "status": "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY",
            "outcome_access": False,
            "gate_b_authorized": False,
            "production_authority": False,
            "parent_192_authority": False,
            "v1_lineage": lineage["v1"],
            "denominator": {
                "canonical_issue_count": 344,
                "stage_count": 3,
                "stage1_action_count": counts["stage1"],
                "stage2_action_count": counts["stage2"],
                "stage2_available_action_count": sum(
                    row["availability"] == "AVAILABLE" for row in stage2
                ),
                "stage3_seed_agnostic_action_count": counts["stage3"],
                "stage3_complete_match_weight_row_count": counts[
                    "complete_match_weights"
                ],
                "stage3_compatibility_class_count": counts[
                    "compatibility_classes"
                ],
                "stage1_stage3_coverage_row_count": counts[
                    "compatibility_coverage"
                ],
                "stage1_stage3_pair_count": counts["stage1_stage3_pairs"],
                "compatible_coverage_row_count": counts[
                    "compatible_coverage_rows"
                ],
                "stage_model_grid_count": counts["models"],
                "stage_feature_projection_row_count": len(projection),
                "model_grid_count_per_stage": 30,
                "required_attribution_control_count": 4,
                "source_package_count": len(source_rows),
                "outer_fold_count": 5,
            },
            "interfaces": [
                "f_selection(X_i,H_<i)",
                "f_direction(X_i,selection_output_i,theta_selection_i,H_<i)",
                "f_bet(X_i,selection_output_i,theta_selection_i,direction_output_i,theta_direction_i,H_<i)",
            ],
            "seed_rule": "exact accepted seeds are nuisance replicates averaged before Stage-3 screen/fit/choice; never summed purchased exposure",
            "M_rule": "exact accepted M grid including FULL=2187; M is an output, never a budget rejection gate",
            "outcome_boundary": OUTCOME_BOUNDARY,
            "portable_identity_rule": "CONTENT_IDENTITY and PORTABLE_SHA256SUMS hash decompressed gzip payload content; byte SHA256SUMS separately binds the committed transport/runtime bytes",
        }
        write_json(stage / "gate_a_card.json", card)
        write_readme(stage / "README.md", counts)
        shutil.copy2(Path(__file__).resolve(), stage / "freeze_runner.py")
        shutil.copy2(ADAPTER_PATH, stage / "conditional_chain_adapter.py")
        shutil.copy2(ALLOCATION_ENGINE_PATH, stage / "bj145_allocation_engine.py")
        runtime_binding = {
            "contract": "BJ193_TRANSPORT_RUNTIME_BINDING_V3",
            "python_implementation": sys.implementation.name,
            "python_version": sys.version,
            "zlib_compile_version": zlib.ZLIB_VERSION,
            "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
            "gzip_transport": "RFC1952; filename empty; mtime=0; compresslevel=9",
            "scope": "byte SHA256SUMS transport receipt only; excluded from portable semantic identity",
        }
        write_json(stage / "runtime_transport_binding.json", runtime_binding)

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
            "identity_rule": "SHA-256 over canonical decompressed payload bytes for .gz and raw bytes otherwise; excludes runtime transport binding and identity/manifest files",
            "portable_manifest_sha256": portable_manifest_sha,
            "controls": {
                "outcome_access": False,
                "gate_b_authorized": False,
                "v1_manifest_sha256": V1_MANIFEST_SHA256,
                "v1_content_identity_sha256": V1_CONTENT_SHA256,
                "v1_action_stream_sha256": V1_ACTION_STREAM_SHA256,
                **counts,
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
        # Final self-audit before the only mutation of the target name.
        for name, expected in manifest.items():
            if sha256_file(stage / name) != expected:
                raise RuntimeError(f"staged payload drift: {name}")
        os.replace(stage, output)
    except BaseException:
        if stage.exists():
            interrupted = stage.with_name(stage.name + ".failed")
            if not interrupted.exists():
                os.replace(stage, interrupted)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    publish(args.output)


if __name__ == "__main__":
    main()
