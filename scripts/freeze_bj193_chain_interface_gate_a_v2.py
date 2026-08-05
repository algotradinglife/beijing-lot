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
import json
import os
import shutil
import uuid
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
        ("sampler_plan.csv", "n7_role_vectors.csv.gz"),
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


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> None:
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as binary:
        with __import__("io").TextIOWrapper(binary, newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


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
    "preserved_source_identity",
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
) -> dict[str, object]:
    return {
        "stage": stage,
        "interface_action_key": interface_key(stage, package, source_file, identity),
        "upstream_issue": issue,
        "source_package": package,
        "source_file": source_file,
        "source_identity_field": identity_field,
        "source_identity": identity,
        "parameters_json": canonical_json(parameters),
        "availability": availability,
        "scientific_role": role,
        "preserved_source_identity": True,
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
        params = {
            key: value
            for key, value in source.items()
            if key not in {"policy_id", "outcome_boundary"}
        }
        params.update(
            {
                "direction_construction_source_identity": "D_DIRECTION_ONLY",
                "direction_rule": arms["D_DIRECTION_ONLY"]["direction_rule"],
                "support_rule": "apply only to the exact ordered Stage-1 match IDs; never replace, reorder, add, or remove Stage-1 matches",
            }
        )
        rows.append(
            catalog_row(
                "STAGE_2_DIRECTION", 190, package, "detector_grid.csv",
                "policy_id", identity, params, source["availability"],
                "ACCEPTED_INDEPENDENT_DIVERGENCE_DIRECTION_RULE",
            )
        )
    rows.sort(key=lambda row: str(row["interface_action_key"]))
    if len(rows) != 2_425 or len({row["interface_action_key"] for row in rows}) != len(rows):
        raise RuntimeError("#193 Stage-2 catalog census drift")
    return rows


def stage3_catalog() -> list[dict[str, object]]:
    v1 = ROOT / "results" / V1_PACKAGE / "causal_allocation_catalog.csv"
    rows: list[dict[str, object]] = []
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
        rows.append(
            catalog_row(
                "STAGE_3_BET", 167, V1_PACKAGE,
                "causal_allocation_catalog.csv", "causal_allocation_factor_id",
                identity, params, "AVAILABLE", "ACCEPTED_ALLOCATOR_REPEAT_M_ACTION",
            )
        )
    rows.sort(key=lambda row: str(row["interface_action_key"]))
    if len(rows) != 963 or len({row["interface_action_key"] for row in rows}) != len(rows):
        raise RuntimeError("#193 Stage-3 catalog census drift")
    return rows


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
                    "ordered_match_ids_json", "per_match_outcome_identity_json",
                    "per_match_outcome_weight_json", "per_match_probability_json",
                    "per_match_value_json",
                    "direction_thresholds_json", "protection_flags_json",
                    "support_count",
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
                    "ordered_match_ids_json", "per_match_outcome_identity_json",
                    "per_match_outcome_weight_json", "allocator", "weight_source",
                    "mechanism", "repeat_mode", "cap", "M",
                    "per_ticket_stake_yuan", "requested_ticket_count",
                    "requested_stake_yuan", "ticket_ledger_sha256",
                    "ticket_builder_version", "ticket_builder_sha256",
                    "exposure_signature_sha256", "support_count",
                ],
                "M_boundary": "M is an output from the exact accepted grid, including 2187 FULL; it is not a budget rejection gate and has no new arbitrary maximum",
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
    if stage2["ordered_match_ids_json"] != stage1["selected_match_ids_json"]:
        raise RuntimeError("Stage-2 replaced Stage-1 match support")
    if stage3["ordered_match_ids_json"] != stage2["ordered_match_ids_json"]:
        raise RuntimeError("Stage-3 replaced upstream match support")
    for field in (
        "per_match_outcome_identity_json", "per_match_outcome_weight_json"
    ):
        if stage3[field] != stage2[field]:
            raise RuntimeError(f"Stage-3 replaced Stage-2 {field}")


def chain_fixture() -> dict[str, object]:
    common = {
        "issue": "FIXTURE_26080",
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
        "ordered_match_ids_json": stage1["selected_match_ids_json"],
        "per_match_outcome_identity_json": canonical_json({match_id: ["3", "1", "0"] for match_id in match_ids}),
        "per_match_outcome_weight_json": canonical_json({match_id: ["1", "1", "1"] for match_id in match_ids}),
        "per_match_probability_json": canonical_json({match_id: ["0.34", "0.33", "0.33"] for match_id in match_ids}),
        "per_match_value_json": canonical_json({match_id: ["NA", "NA", "NA"] for match_id in match_ids}),
        "direction_thresholds_json": canonical_json({"rule": "ALLOW_ALL"}),
        "protection_flags_json": canonical_json({match_id: False for match_id in match_ids}),
        "support_count": 7,
    }
    stage2["output_sha256"] = digest_stage_output(stage2)
    stage3 = {
        **common,
        "stage_id": "STAGE_3_BET",
        "source_action_identity": "FULL_ENUMERATED_M2187",
        "stage1_output_sha256": stage1["output_sha256"],
        "stage2_output_sha256": stage2["output_sha256"],
        "ordered_match_ids_json": stage2["ordered_match_ids_json"],
        "per_match_outcome_identity_json": stage2["per_match_outcome_identity_json"],
        "per_match_outcome_weight_json": stage2["per_match_outcome_weight_json"],
        "allocator": "FULL_ENUMERATED",
        "weight_source": "NA",
        "mechanism": "FULL_ENUMERATED",
        "repeat_mode": "NOT_APPLICABLE",
        "cap": "NA",
        "M": 2187,
        "per_ticket_stake_yuan": 2,
        "requested_ticket_count": 2187,
        "requested_stake_yuan": 4374,
        "ticket_ledger_sha256": canonical_hash(list(range(2187))),
        "ticket_builder_version": "FROZEN_FULL_ENUMERATED_FIXTURE_V1",
        "ticket_builder_sha256": canonical_hash("fixture-ticket-builder"),
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
    common = {
        "minimum_history": "60 prior canonical issues and >=2 prior calendar years",
        "minimum_action_support": 20,
        "nested_fit": "inner-train transforms/models; prior-year validation chooses family; selected family refit on full outer-train; entire outer-test year remains untouched",
        "training_upstream_rule": "downstream training uses expanding chronological out-of-fold upstream outputs generated with H_<j only, never in-sample or oracle upstream choices",
        "test_update_rule": "no model, transform, screen, rank, or fallback update from any outer-test outcome within the held-out year",
        "pre_tax_primary": True,
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
            **common,
        },
    ]


def stage_model_grid() -> list[dict[str, object]]:
    base = read_csv(ROOT / "results" / V1_PACKAGE / "model_family_grid.csv")
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
                "stage2_source_action_identity", "stage2_output_sha256",
                "stage2_availability", "stage2_fallback", "stage2_reason_code",
                "stage3_model_id", "stage3_model_version",
                "stage3_source_action_identity", "stage3_output_sha256",
                "stage3_availability", "stage3_fallback", "stage3_reason_code",
                "ticket_builder_version", "ticket_builder_sha256",
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
            "Stage-3 row binds exact Stage-1 and Stage-2 output_sha256 plus outcome identities/weights",
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

Catalog census:

- Stage 1 selection actions: {counts['stage1']:,}
- Stage 2 direction actions: {counts['stage2']:,}
- Stage 3 seed-agnostic allocator/M actions: {counts['stage3']:,}
- stage-specific model configurations: {counts['models']:,}
- required matched attribution controls: 4

Downstream stages consume immutable upstream outputs and digests.  Their
training inputs are chronologically honest upstream predictions, not in-sample
or realized-best choices.  Seed remains a nuisance replicate and M remains an
output from the accepted grid, not a budget gate.

Status: ready for PI review, no Gate-B, betting, production, or #192 authority.
""",
        encoding="utf-8",
    )


def publish(output: Path) -> None:
    source_rows = verify_sources()
    stage1 = stage1_catalog()
    stage2 = stage2_catalog()
    stage3 = stage3_catalog()
    models = stage_model_grid()
    fixture = chain_fixture()
    counts = {
        "stage1": len(stage1),
        "stage2": len(stage2),
        "stage3": len(stage3),
        "models": len(models),
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
        training = stage_training_rows()
        write_csv(stage / "stage_training_contract.csv", list(training[0]), training)
        write_csv(stage / "stage_model_grid.csv", list(models[0]), models)
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
            "v2_amendment": "three separately parameterized stage interfaces, conditional targets/support/fallbacks, honest upstream training outputs, decision trace, and matched incremental controls",
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
                "stage_model_grid_count": counts["models"],
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
        }
        write_json(stage / "gate_a_card.json", card)
        write_readme(stage / "README.md", counts)
        shutil.copy2(Path(__file__).resolve(), stage / "freeze_runner.py")

        payloads = {
            str(path.relative_to(stage)): sha256_file(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        }
        content = {
            "contract": CONTRACT,
            "version": VERSION,
            "controls": {
                "outcome_access": False,
                "gate_b_authorized": False,
                "v1_manifest_sha256": V1_MANIFEST_SHA256,
                "v1_content_identity_sha256": V1_CONTENT_SHA256,
                "v1_action_stream_sha256": V1_ACTION_STREAM_SHA256,
                **counts,
            },
            "payloads": payloads,
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
