"""Issue #208: evidence verifier + tamper self-tests (REQ-E06).

The verifier independently recomputes key invariants from the immutable
package and fails closed on any inconsistency. Tamper tests attack the
PRODUCTION entry points: mutated settlement fields, self-consistent ledger
edits, manifest forgery with unlisted payloads, and forged provenance must
all FAIL against the production verifier (not against a string check).

REWORK v2 (D4):
- manifest: full coverage — every file in the package must be listed in
  SHA256SUMS.json (except SHA256SUMS.json itself and the receipt); any
  unlisted payload file is a failure.
- provenance: verified against the trusted upstream hashes, not by checking
  for a "FORGED" prefix.
- capital accounting: start at ¥100,000, integer ¥2 units, requested/funded/K
  consistency, no top-up, post = pre - funded + payout for every path.
- N/K semantics: the verifier now takes K and checks exactly K ticket rows per
  issue (the old function never received K).
- outcome isolation: a REAL 2024 label-mutation invariance check (fitted
  parameter invariance), not just a forbidden-name constant test.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd

from .contract import (
    CONTRACT_VERSION,
    EMBARGOED_SPLITS,
    INCUMBENT_K,
    INCUMBENT_LANE,
    INCUMBENT_N,
    INITIAL_BANKROLL_YUAN,
    TICKET_STAKE_YUAN,
)
from .features import STATE_FEATURE_NAMES


class VerifyError(RuntimeError):
    """Raised when verification fails."""


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


# Only the manifest itself is excluded: it cannot contain its own digest and
# is externally bound by the exact Git review SHA.  Every other delivered
# byte, including receipt.sha256, must be covered by the manifest.
MANIFEST_EXCLUDED = {"SHA256SUMS.json"}


def manifest(package: Path, files: list[Path]) -> dict[str, str]:
    """Map relative path (posix) -> sha256 for each artifact file.

    REWORK v2 (D1): keys are RELATIVE to the package root so nested artifacts
    (e.g. models/fold1_mlp.joblib) are covered; the old basename-only mapping
    lost subdirectory entries.
    """
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in files
    }


def verify_manifest(package: Path, manifest_json: dict[str, str]) -> list[str]:
    """Full-coverage manifest verification.

    REWORK v2 (D4): (1) every listed relative path exists and hashes match;
    (2) every file under the package root (except SHA256SUMS.json and the
    receipt) is listed — an unlisted payload is a failure.
    """
    failures: list[str] = []
    for name, expected in manifest_json.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name == "SHA256SUMS.json":
            failures.append(f"invalid manifest artifact path {name}")
            continue
        path = package / name
        if path.is_symlink():
            failures.append(f"manifest artifact is a symlink: {name}")
            continue
        if not path.is_file():
            failures.append(f"missing artifact {name}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"hash mismatch {name}: {actual} != {expected}")
    on_disk: set[str] = set()
    for path in package.rglob("*"):
        relative = path.relative_to(package).as_posix()
        if path.is_symlink():
            failures.append(f"package contains symlink: {relative}")
        if path.is_file() and relative not in MANIFEST_EXCLUDED:
            on_disk.add(relative)
    unlisted = sorted(on_disk - set(manifest_json))
    if unlisted:
        failures.append(f"unlisted payload files: {unlisted}")
    return failures


def _handoff_ref_in_package(package: Path, ref: str) -> Path | None:
    """Map a repo-root-relative handoff ref (results/issue-208/...) into the
    package tree, tolerating a staging or temp package directory name.

    The handoff serializes canonical post-publication paths (e.g.
    `results/issue-208/SHA256SUMS.json`).  Verification runs on the staging
    tree before atomic rename AND on the final package afterwards, so the ref
    is resolved relative to the package root by stripping the canonical
    package-name segment.  Temp copies used by the tamper suite carry the same
    relative layout, so the same resolution applies there.
    """
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return None
    parts = ref_path.parts
    # The package may currently be a unique staging/EV temp directory.  The
    # handoff itself always names the canonical published package.
    if "issue-208" in parts:
        sub = Path(*parts[parts.index("issue-208") + 1:])
        return package / sub
    return package / ref_path


def verify_handoff_paths(package: Path) -> list[str]:
    """Every #209 handoff artifact path must resolve inside the published
    package and must never reference the staging directory (`.staging`).

    REWORK v3.1 (PI narrow durability REJECT 2026-08-15): the v3 handoff
    serialized `results/issue-208.staging/SHA256SUMS.json` because
    `_build_handoff` received the staging output path.  This verifier runs on
    both the staging tree (pre-rename) and the final package (post-rename) and
    fails closed if any handoff path points at `.staging` or does not resolve
    after publication.
    """
    failures: list[str] = []
    handoff_path = package / "handoff_209.json"
    if not handoff_path.exists():
        return ["missing handoff_209.json"]
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    refs: list[tuple[str, str]] = []
    if "package_manifest" in handoff:
        refs.append(("package_manifest", str(handoff["package_manifest"])))
    if "model_file" in handoff:
        refs.append(("model_file", str(handoff["model_file"])))
    for field, ref in refs:
        if ".staging" in ref:
            failures.append(
                f"handoff {field} references staging path: {ref}"
            )
            continue
        target = _handoff_ref_in_package(package, ref)
        if target is None:
            failures.append(f"handoff {field} path not under package root: {ref}")
            continue
        if not target.exists():
            failures.append(
                f"handoff {field} does not resolve after publish: {ref}"
            )
    return failures


def verify_receipt(package: Path) -> list[str]:
    """Require the canonical one-line method receipt.

    Exact bytes matter: append, duplicate-line and alternate-name variants
    are rejected even if one valid-looking line remains.
    """
    failures: list[str] = []
    receipt = package / "receipt.sha256"
    method = package / "method.yaml"
    if not receipt.exists():
        return ["missing receipt.sha256"]
    if not method.exists():
        return ["missing method.yaml for receipt check"]
    expected = sha256_file(method)
    expected_text = f"{expected}  method.yaml\n"
    try:
        text = receipt.read_text(encoding="utf-8")
    except Exception as exc:
        return [f"invalid receipt.sha256: {exc}"]
    if text != expected_text:
        failures.append("receipt.sha256 is not the canonical method binding")
    return failures


def verify_schema(frame: pd.DataFrame, required: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for column, dtype in required.items():
        if column not in frame.columns:
            failures.append(f"missing column {column}")
            continue
        if dtype == "any":
            continue
        if dtype in {"numeric", "float", "int"}:
            if not pd.api.types.is_numeric_dtype(frame[column]):
                failures.append(f"column {column} not numeric")
            elif dtype == "int" and not pd.api.types.is_integer_dtype(frame[column]):
                # Nullable integer columns may be represented as floats after
                # parquet round-trips; accept only if all present values are
                # mathematically integral.
                values = frame[column].dropna().to_numpy(dtype=float)
                if not np.allclose(values, np.round(values), atol=1e-9):
                    failures.append(f"column {column} not integral")
        elif dtype == "bool":
            if not pd.api.types.is_bool_dtype(frame[column]):
                failures.append(f"column {column} not boolean")
        elif dtype == "str":
            non_null = frame[column].dropna()
            if not non_null.map(lambda value: isinstance(value, str)).all():
                failures.append(f"column {column} not string")
    return failures


def verify_package_schema(package: Path, schema: dict[str, Any]) -> list[str]:
    """Apply declared columns, keys, domains and JSON contracts.

    Auxiliary frames may retain the compact ``{column: dtype}`` form.  The
    decision/capital/#209 frames use the richer contract form with explicit
    columns, non-null fields, primary keys, domains and unit declarations.
    """
    failures: list[str] = []
    frames = schema.get("frames")
    if not isinstance(frames, dict) or not frames:
        return ["schema.json has no decision-critical frames"]
    on_disk_frames = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.suffix in {".csv", ".parquet"}
    }
    if set(frames) != on_disk_frames:
        missing = sorted(on_disk_frames - set(frames))
        stale = sorted(set(frames) - on_disk_frames)
        if missing:
            failures.append(f"schema omits data frames: {missing}")
        if stale:
            failures.append(f"schema declares missing data frames: {stale}")
    critical_frames = {
        "census.csv",
        "eligibility.csv",
        "issue_capital_ledger.parquet",
        "decision_rows_all.parquet",
        "dynamic_control_decisions.parquet",
        "path_holding_metrics.parquet",
        "label_surface_fit.parquet",
        "ticket_economics.parquet",
        "incumbent_paths.parquet",
        "training_frame_all.parquet",
        "validation_frame_all.parquet",
        "chronology_blocks.parquet",
        "decision_ticket_identities.parquet",
    }
    absent_critical = critical_frames - set(frames)
    if absent_critical:
        failures.append(
            f"schema missing critical frames: {sorted(absent_critical)}"
        )
    for name, contract in frames.items():
        if not isinstance(contract, dict):
            failures.append(f"invalid frame schema: {name}")
            continue
        required = contract.get("columns", contract)
        if not isinstance(required, dict) or not required:
            failures.append(f"frame schema has no columns: {name}")
            continue
        path = package / name
        if not path.exists():
            failures.append(f"schema target missing: {name}")
            continue
        try:
            frame = (
                pd.read_parquet(path)
                if path.suffix == ".parquet"
                else pd.read_csv(path)
            )
        except Exception as exc:
            failures.append(f"schema target unreadable {name}: {exc}")
            continue
        declared_columns = set(required)
        if declared_columns != set(frame.columns):
            failures.append(
                f"{name}: declared columns do not exactly match published columns"
            )
        diagnostic_only = contract.get("diagnostic_only")
        if not isinstance(diagnostic_only, bool):
            failures.append(f"{name}: diagnostic_only must be explicit boolean")
        elif name in critical_frames and diagnostic_only:
            failures.append(f"{name}: critical frame marked diagnostic-only")
        failures.extend(
            f"{name}: {failure}"
            for failure in verify_schema(frame, required)
        )
        non_null = contract.get("non_null", [])
        for column in non_null:
            if column not in frame.columns:
                failures.append(f"{name}: non-null column missing {column}")
            elif frame[column].isna().any():
                failures.append(f"{name}: null values in {column}")
        primary_key = contract.get("primary_key", [])
        if primary_key:
            missing = [column for column in primary_key if column not in frame]
            if missing:
                failures.append(f"{name}: primary-key columns missing {missing}")
            elif frame.loc[:, primary_key].isna().any(axis=None):
                failures.append(f"{name}: null value in primary key {primary_key}")
            elif frame.duplicated(primary_key).any():
                failures.append(f"{name}: duplicate primary key {primary_key}")
        for column, allowed in contract.get("domains", {}).items():
            if column not in frame.columns:
                failures.append(f"{name}: domain column missing {column}")
                continue
            observed = set(frame[column].dropna().tolist())
            unexpected = observed - set(allowed)
            if unexpected:
                failures.append(
                    f"{name}: values outside {column} domain: "
                    f"{sorted(map(str, unexpected))[:5]}"
                )
        for column, unit in contract.get("units", {}).items():
            if column not in frame.columns:
                failures.append(f"{name}: unit column missing {column}")
            if not isinstance(unit, str) or not unit.strip():
                failures.append(f"{name}: invalid unit declaration for {column}")

    json_contracts = schema.get("json_artifacts", {})
    if not isinstance(json_contracts, dict):
        failures.append("json_artifacts must be an object")
        json_contracts = {}
    on_disk_json = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*.json")
        if path.relative_to(package).as_posix()
        not in {"SHA256SUMS.json", "schema.json"}
    }
    if set(json_contracts) != on_disk_json:
        missing = sorted(on_disk_json - set(json_contracts))
        stale = sorted(set(json_contracts) - on_disk_json)
        if missing:
            failures.append(f"schema omits JSON artifacts: {missing}")
        if stale:
            failures.append(f"schema declares missing JSON artifacts: {stale}")
    for name, contract in json_contracts.items():
        path = package / name
        if not path.exists():
            failures.append(f"JSON schema target missing: {name}")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"JSON schema target unreadable {name}: {exc}")
            continue
        if not isinstance(contract.get("diagnostic_only"), bool):
            failures.append(f"{name}: JSON diagnostic_only must be explicit")
        for key in contract.get("required_keys", []):
            current: Any = value
            for part in str(key).split("."):
                if not isinstance(current, dict) or part not in current:
                    failures.append(f"{name}: missing required key {key}")
                    break
                current = current[part]

    binary_contracts = schema.get("binary_artifacts", {})
    if not isinstance(binary_contracts, dict):
        failures.append("binary_artifacts must be an object")
        binary_contracts = {}
    on_disk_binary = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*.joblib")
    }
    if set(binary_contracts) != on_disk_binary:
        failures.append("binary artifact inventory mismatch")
    for name in binary_contracts:
        if not (package / name).is_file():
            failures.append(f"binary artifact missing: {name}")

    identity = schema.get("manifest_identity", {})
    if not isinstance(identity, dict) or identity.get(
        "all_delivered_bytes_except_manifest_are_hashed"
    ) is not True:
        failures.append("schema does not declare complete manifest coverage")

    required_relationships = {
        "capital_conservation",
        "ticket_bundle_n_k",
        "payout_exactly_once",
        "handoff_resolves_post_publish",
        "chronological_issue_block_isolation",
        "issue_level_path_metrics",
        "dynamic_restricted_argmax",
        "complete_code_binding_set",
        "training_state_source_binding",
    }
    observed_relationships = {
        str(row.get("name"))
        for row in schema.get("relationships", [])
        if isinstance(row, dict) and row.get("production_verifier")
    }
    missing_relationships = required_relationships - observed_relationships
    if missing_relationships:
        failures.append(
            f"schema missing verified relationships: {sorted(missing_relationships)}"
        )
    return failures


def verify_completion(package: Path) -> list[str]:
    path = package / "COMPLETED.json"
    if not path.exists():
        return ["missing COMPLETED.json"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid COMPLETED.json: {exc}"]
    if value.get("status") != "COMPLETED":
        return [f"completion status is {value.get('status')!r}, not COMPLETED"]
    return []


def verify_req_evidence(
    decision: dict[str, Any], package: Path | None = None
) -> list[str]:
    """Require one concrete producer evidence row for REQ-208-01..09.

    The immutable package binds the producing code commit and file evidence.
    The exact final PR HEAD remains external by necessity (a Git commit cannot
    contain its own hash) and is supplied by the handoff/EV verdict.
    """
    failures: list[str] = []
    rows = decision.get("req_evidence")
    if not isinstance(rows, list):
        return ["decision.json missing req_evidence rows"]
    expected = {f"REQ-208-{index:02d}" for index in range(1, 10)}
    observed = {str(row.get("req")) for row in rows if isinstance(row, dict)}
    if observed != expected:
        failures.append(
            f"REQ evidence rows mismatch: missing={sorted(expected-observed)} "
            f"extra={sorted(observed-expected)}"
        )
    for row in rows:
        if not isinstance(row, dict):
            failures.append("REQ evidence row is not an object")
            continue
        if row.get("status") != "PASS":
            failures.append(f"{row.get('req')} producer status is not PASS")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            failures.append(f"{row.get('req')} has no evidence paths")
        elif package is not None:
            for relative in evidence:
                if not (package / str(relative)).exists():
                    failures.append(
                        f"{row.get('req')} evidence path missing: {relative}"
                    )
    code_commit = str(decision.get("producer_code_commit", ""))
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        failures.append("decision producer_code_commit is not a full SHA")
    return failures


def _model_numerical_payload(model: object) -> dict[str, object]:
    steps = getattr(model, "named_steps", {})
    scaler = steps.get("standardscaler")
    estimator = steps.get("mlpregressor")
    if estimator is None:
        estimator = steps.get("mlpclassifier")
    if estimator is None:
        estimator = steps.get("ridge")
    payload: dict[str, object] = {
        "pipeline_steps": list(steps),
        "estimator_type": type(estimator).__name__ if estimator is not None else None,
    }
    if scaler is not None:
        payload["scaler_mean"] = np.asarray(scaler.mean_, dtype=float).tolist()
        payload["scaler_scale"] = np.asarray(scaler.scale_, dtype=float).tolist()
    if estimator is not None:
        if hasattr(estimator, "coefs_"):
            payload["coefs"] = [
                np.asarray(value, dtype=float).tolist()
                for value in estimator.coefs_
            ]
            payload["intercepts"] = [
                np.asarray(value, dtype=float).tolist()
                for value in estimator.intercepts_
            ]
        if hasattr(estimator, "coef_"):
            payload["coef"] = np.asarray(estimator.coef_, dtype=float).tolist()
            payload["intercept"] = np.asarray(
                estimator.intercept_, dtype=float
            ).tolist()
        if hasattr(estimator, "classes_"):
            payload["classes"] = np.asarray(estimator.classes_).tolist()
        if getattr(estimator, "n_iter_", None) is not None:
            payload["n_iter"] = int(estimator.n_iter_)
    return payload


def _scaler_numerical_payload(scaler: object) -> dict[str, object]:
    return {
        "type": type(scaler).__name__,
        "mean": np.asarray(scaler.mean_, dtype=float).tolist(),
        "scale": np.asarray(scaler.scale_, dtype=float).tolist(),
        "n_features_in": int(scaler.n_features_in_),
    }


def verify_holdout_mutation_receipt(package: Path) -> list[str]:
    path = package / "holdout_mutation_receipt.json"
    if not path.exists():
        return ["missing holdout_mutation_receipt.json"]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid holdout mutation receipt: {exc}"]
    failures: list[str] = []
    if receipt.get("probe") != "ACTUAL_TERMINAL_FOLD_REFIT_AFTER_LOCKED_TEST_LABEL_MUTATION":
        failures.append("holdout receipt is not an actual-refit probe")
    if int(receipt.get("mutated_rows", 0)) <= 0:
        failures.append("holdout receipt mutated no rows")
    if receipt.get("baseline_signature_sha256") != receipt.get("mutated_signature_sha256"):
        failures.append("holdout mutation changed fitted signature")
    for key in ("baseline_signature_sha256", "mutated_signature_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt.get(key, ""))) is None:
            failures.append(f"holdout receipt {key} is not SHA-256")
    if receipt.get("all_fitted_objects_and_decisions_invariant") is not True:
        failures.append("holdout receipt does not attest full fitted-state invariance")
    payloads: dict[str, dict[str, Any]] = {}
    for side in ("baseline", "mutated"):
        file_key = f"{side}_payload_file"
        ref = receipt.get(file_key)
        if not isinstance(ref, str) or Path(ref).is_absolute() or ".." in Path(ref).parts:
            failures.append(f"holdout receipt has invalid {file_key}")
            continue
        payload_path = package / ref
        if not payload_path.exists():
            failures.append(f"holdout payload missing: {ref}")
            continue
        try:
            payloads[side] = json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append(f"holdout payload unreadable {ref}: {exc}")
            continue
        encoded = json.dumps(
            payloads[side],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        actual = hashlib.sha256(encoded).hexdigest()
        if actual != receipt.get(f"{side}_signature_sha256"):
            failures.append(f"holdout {side} payload/signature mismatch")
    if set(payloads) == {"baseline", "mutated"}:
        if payloads["baseline"] != payloads["mutated"]:
            failures.append("holdout baseline/mutated fitted payloads differ")
        baseline = payloads["baseline"]
        train_issues = set(map(str, baseline.get("training_issues", [])))
        validation_issues = set(map(str, baseline.get("validation_issues", [])))
        if not train_issues or not validation_issues:
            failures.append("holdout payload lacks fit/validation issue blocks")
        elif train_issues & validation_issues:
            failures.append("holdout payload fit/validation issues overlap")
        fitted = baseline.get("fitted_objects")
        expected_keys = {
            "ticket_ranker", "primary_mlp", "ridge", "best_fixed",
            "restricted_mlps", "ood", "diagnostic_mlp",
        }
        if not isinstance(fitted, dict) or set(fitted) != expected_keys:
            failures.append("holdout payload fitted-object inventory incomplete")
            fitted = {}
        inventory_path = package / "fitted_object_inventory.json"
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            if inventory.get("terminal_fold") != "fold2":
                failures.append("published fitted-object inventory fold mismatch")
            if inventory.get("fitted_objects") != fitted:
                failures.append("holdout payload does not bind fitted-object inventory")
        except Exception as exc:
            failures.append(f"fitted-object inventory binding failed: {exc}")

        # Bind every fitted numerical object to a separately delivered model
        # artifact.  This prevents a self-consistent receipt/inventory rewrite
        # from silently replacing Ridge or a restricted control.
        try:
            import joblib

            model_targets = {
                "ticket_ranker": ("models/fold2_ranker.joblib", fitted.get("ticket_ranker")),
                "primary_mlp": ("models/fold2_mlp.joblib", (fitted.get("primary_mlp") or {}).get("model")),
                "ridge": ("models/fold2_ridge.joblib", (fitted.get("ridge") or {}).get("model")),
                "diagnostic_mlp": ("models/fold2_diagnostic_mlp.joblib", (fitted.get("diagnostic_mlp") or {}).get("model")),
            }
            for name, (relative, expected_payload) in model_targets.items():
                target = package / relative
                if not target.exists():
                    failures.append(f"fitted-object artifact missing: {relative}")
                    continue
                if _model_numerical_payload(joblib.load(target)) != expected_payload:
                    failures.append(f"fitted-object artifact mismatch: {name}")
            restricted = fitted.get("restricted_mlps") or {}
            expected_restricted = {
                "dynamic_n_fixed_k8_lane",
                "fixed_n7_dynamic_k",
                "dynamic_nk_fixed_generator",
            }
            if set(restricted) != expected_restricted:
                failures.append("restricted fitted-object inventory incomplete")
            for name in sorted(expected_restricted):
                target = package / f"models/fold2_{name}.joblib"
                expected_payload = (restricted.get(name) or {}).get("model")
                if not target.exists():
                    failures.append(f"restricted model artifact missing: {name}")
                elif _model_numerical_payload(joblib.load(target)) != expected_payload:
                    failures.append(f"restricted model artifact mismatch: {name}")
            ood_target = package / "models/fold2_ood_scaler.joblib"
            if not ood_target.exists():
                failures.append("OOD scaler artifact missing")
            elif _scaler_numerical_payload(joblib.load(ood_target)) != (
                (fitted.get("ood") or {}).get("scaler")
            ):
                failures.append("OOD scaler artifact mismatch")
        except Exception as exc:
            failures.append(f"fitted-object artifact binding failed: {exc}")

        training_path = package / "training_frame_all.parquet"
        if training_path.exists() and fitted:
            training = pd.read_parquet(training_path)
            fold2 = training.loc[
                training["fold"].eq("fold2")
                & training["training_role"].eq("FIT")
            ]
            expected_fixed = str(
                fold2.groupby("action_key")["y_lift"].median().idxmax()
            )
            if (fitted.get("best_fixed") or {}).get("fixed_action_key") != expected_fixed:
                failures.append("best-fixed fitted object disagrees with training primitive")
        decisions_path = package / "decision_rows_all.parquet"
        if decisions_path.exists():
            decisions = pd.read_parquet(decisions_path)
            terminal = decisions.loc[decisions["split"].eq("CV_2023")].copy()
            actual_decisions = [
                {
                    "issue": str(row["issue"]),
                    "prior_bankroll_yuan": float(row["prior_bankroll_yuan"]),
                    "action_key": str(row["action_key"]),
                    "decision_trace_json": str(row["decision_trace_json"]),
                }
                for _, row in terminal.sort_values("issue").iterrows()
            ]
            expected_decisions = sorted(
                baseline.get("decisions", []),
                key=lambda row: str(row.get("issue", "")),
            )
            if actual_decisions != expected_decisions:
                failures.append("holdout payload does not bind terminal decisions")
        else:
            failures.append("holdout decision binding target missing")
    return failures


def verify_chronology(package: Path) -> list[str]:
    """Verify fit/validation issue blocks are disjoint and chronological."""
    failures: list[str] = []
    paths = {
        "fit": package / "training_frame_all.parquet",
        "validation": package / "validation_frame_all.parquet",
        "blocks": package / "chronology_blocks.parquet",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return [f"chronology artifacts missing: {missing}"]
    fit = pd.read_parquet(paths["fit"])
    validation = pd.read_parquet(paths["validation"])
    blocks = pd.read_parquet(paths["blocks"])
    for frame_name, frame, role in (
        ("fit", fit, "FIT"),
        ("validation", validation, "VALIDATION"),
    ):
        for column in ("fold", "issue", "training_role"):
            if column not in frame:
                failures.append(f"{frame_name} frame missing {column}")
        if "training_role" in frame and not frame["training_role"].eq(role).all():
            failures.append(f"{frame_name} frame has wrong training_role")
    required_block_columns = {
        "fold", "issue", "role", "used_by_q_fit",
        "used_by_ranker_fit", "used_by_ood_fit",
    }
    if not required_block_columns.issubset(blocks.columns):
        failures.append("chronology block receipt missing required columns")
        return failures
    for fold in sorted(set(fit.get("fold", [])) | set(validation.get("fold", []))):
        fit_issues = set(
            fit.loc[fit["fold"].eq(fold), "issue"].astype(str)
        )
        val_issues = set(
            validation.loc[validation["fold"].eq(fold), "issue"].astype(str)
        )
        if not fit_issues or not val_issues:
            failures.append(f"{fold} has empty fit or validation issue block")
            continue
        overlap = fit_issues & val_issues
        if overlap:
            failures.append(f"{fold} fit/validation overlap: {sorted(overlap)[:5]}")
        if max(fit_issues) >= min(val_issues):
            failures.append(f"{fold} issue blocks are not chronological")
        fold_blocks = blocks.loc[blocks["fold"].eq(fold)].copy()
        declared_fit = set(
            fold_blocks.loc[fold_blocks["role"].eq("FIT"), "issue"].astype(str)
        )
        declared_val = set(
            fold_blocks.loc[
                fold_blocks["role"].eq("VALIDATION"), "issue"
            ].astype(str)
        )
        if declared_fit != fit_issues or declared_val != val_issues:
            failures.append(f"{fold} chronology receipt/frame mismatch")
        fit_flags = fold_blocks[fold_blocks["role"].eq("FIT")]
        val_flags = fold_blocks[fold_blocks["role"].eq("VALIDATION")]
        for column in ("used_by_q_fit", "used_by_ranker_fit", "used_by_ood_fit"):
            if not fit_flags[column].eq(True).all():  # noqa: E712
                failures.append(f"{fold} fit rows not enabled for {column}")
            if not val_flags[column].eq(False).all():  # noqa: E712
                failures.append(f"{fold} validation rows entered {column}")
    return failures


def _independent_prior_state(
    incumbent: pd.DataFrame, split: str, issue: str
) -> dict[str, float]:
    """Independent causal lag-state reconstruction for verification.

    This intentionally does not call the production feature constructor.  A
    verifier that shares the same helper would accept a training/inference
    bug whenever both sides are wrong in the same way.
    """
    prior = incumbent.loc[
        incumbent["split"].astype(str).eq(str(split))
        & (incumbent["issue"].astype(str) < str(issue))
    ].sort_values("issue")
    if prior.empty:
        return {
            "prior_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_trail5_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_trail10_bankroll_yuan": INITIAL_BANKROLL_YUAN,
            "prior_running_drawdown_pct": 0.0,
            "prior_consecutive_losses": 0.0,
        }
    posts = prior["post_issue_bankroll_yuan"].to_numpy(dtype=float)
    bankroll = float(posts[-1])
    peak = float(max(INITIAL_BANKROLL_YUAN, float(np.max(posts))))
    losses = 0
    net = (
        prior["gross_payout_yuan"].to_numpy(dtype=float)
        - prior["funded_stake_yuan"].to_numpy(dtype=float)
    )
    for value in net[::-1]:
        if value < 0:
            losses += 1
        else:
            break
    return {
        "prior_bankroll_yuan": bankroll,
        "prior_trail5_bankroll_yuan": (
            float(posts[-5]) if len(posts) >= 5 else INITIAL_BANKROLL_YUAN
        ),
        "prior_trail10_bankroll_yuan": (
            float(posts[-10]) if len(posts) >= 10 else INITIAL_BANKROLL_YUAN
        ),
        "prior_running_drawdown_pct": (
            (peak - bankroll) / peak if peak else 0.0
        ),
        "prior_consecutive_losses": float(losses),
    }


def verify_state_semantics(package: Path) -> list[str]:
    """REWORK v4 (EV D3): source-derived binding of critical training-state
    evidence.

    A legal re-manifest attack — shift `prior_running_drawdown_pct` in
    `training_frame_all.parquet`, regenerate a valid SHA256SUMS.json — passes
    hash-only verification because the manifest only proves intra-package
    self-consistency.  This verifier recomputes the five path-dependent state
    features (prior_bankroll_yuan, trail5/trail10 bankroll, running drawdown
    with the time-zero ¥100,000 anchor, economic loss streak) from the frozen
    incumbent source (`incumbent_paths.parquet`, itself bound to the #207
    CONTROLLING identities and payout economics) and fails closed when the
    published training/validation frames diverge.  It additionally binds the
    fitted model's scaler mean for the drawdown feature to the recomputed
    training-frame mean, so a re-manifested frame cannot be silently
    substituted without the model metadata also matching.
    """
    failures: list[str] = []
    incumbent_path = package / "incumbent_paths.parquet"
    if not incumbent_path.exists():
        return ["missing incumbent_paths.parquet for state semantics"]
    incumbent = pd.read_parquet(incumbent_path)

    # Recompute the source-derived prior state for every (split, issue) the
    # frames could legally carry.  This is independent of any frame bytes.
    recomputed: dict[tuple[str, str], dict[str, float]] = {}
    for split, group in incumbent.groupby("split", sort=False):
        split_str = str(split)
        for issue in group["issue"].astype(str):
            recomputed[(split_str, issue)] = _independent_prior_state(
                incumbent, split_str, issue
            )

    path_features = (
        "prior_bankroll_yuan",
        "prior_trail5_bankroll_yuan",
        "prior_trail10_bankroll_yuan",
        "prior_running_drawdown_pct",
        "prior_consecutive_losses",
    )
    for frame_name in (
        "training_frame_all.parquet",
        "validation_frame_all.parquet",
    ):
        frame_path = package / frame_name
        if not frame_path.exists():
            failures.append(f"missing {frame_name} for state semantics")
            continue
        frame = pd.read_parquet(frame_path)
        missing = [
            column for column in ("split", "issue", *path_features)
            if column not in frame.columns
        ]
        if missing:
            failures.append(f"{frame_name} missing state columns: {missing}")
            continue
        for (split, issue), group in frame.groupby(
            ["split", "issue"], sort=False
        ):
            key = (str(split), str(issue))
            expected = recomputed.get(key)
            if expected is None:
                failures.append(
                    f"{frame_name} state key {key} has no source-derived prior"
                )
                continue
            row = group.iloc[0]
            for feature in path_features:
                observed = float(row[feature])
                wanted = float(expected[feature])
                if not np.isclose(observed, wanted, rtol=1e-9, atol=1e-9):
                    failures.append(
                        f"{frame_name} {key} {feature} = {observed} "
                        f"but source-derived value = {wanted}"
                    )

    # Model↔training binding: the fitted MLP scaler mean for the drawdown
    # feature must equal the recomputed training-frame mean on FIT rows.
    handoff_path = package / "handoff_209.json"
    if not handoff_path.exists():
        failures.append("missing handoff_209.json for state semantics")
        return failures
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    model_payload = handoff.get("model") or {}
    scaler_mean = model_payload.get("scaler_mean")
    if not isinstance(scaler_mean, list) or len(scaler_mean) != len(STATE_FEATURE_NAMES) + 4:
        failures.append("handoff model scaler_mean missing or malformed")
        return failures
    drawdown_idx = STATE_FEATURE_NAMES.index("prior_running_drawdown_pct")
    training = pd.read_parquet(package / "training_frame_all.parquet")
    # The #209 handoff model is the fold2 MLP, so the binding uses the fold2
    # FIT rows only (fold1 FIT rows never entered the fold2 scaler).
    fit_rows = training[
        training.get("fold", pd.Series(dtype=str)).eq("fold2")
        & training.get("training_role", pd.Series(dtype=str)).eq("FIT")
    ]
    if fit_rows.empty:
        failures.append("training frame has no fold2 FIT rows for scaler binding")
        return failures
    fit_mean = float(fit_rows["prior_running_drawdown_pct"].mean())
    scaler_value = float(scaler_mean[drawdown_idx])
    if not np.isclose(fit_mean, scaler_value, rtol=1e-6, atol=1e-6):
        failures.append(
            f"model scaler drawdown mean {scaler_value} != "
            f"training fold2 FIT drawdown mean {fit_mean}"
        )
    return failures


def _independent_recovery_episodes(
    posts: np.ndarray, initial: float
) -> dict[str, float]:
    """REWORK v4 (EV D2): INDEPENDENT episode recomputation for the verifier.

    Deliberately implemented from primitives here (not via production
    `summarize_path`) so a semantic bug in the production summary cannot be
    rubber-stamped by a verifier that calls the same function.  Returns the
    completed-recovery episode count, the longest COMPLETED underwater
    duration, the right-censored (open) underwater duration at path end, and
    total underwater issues.  A terminal underwater episode that never
    recovers is an open episode, never a completed recovery.
    """
    running_peak = np.maximum.accumulate(
        np.concatenate(([initial], posts))
    )[1:]
    underwater = running_peak > posts
    total_underwater = int(np.count_nonzero(underwater))
    completed_durations: list[int] = []
    current = 0
    in_episode = False
    events = 0
    for i in range(len(posts)):
        if underwater[i]:
            current += 1
            in_episode = True
        else:
            if in_episode and i > 0 and posts[i] >= running_peak[i]:
                events += 1
                completed_durations.append(current)
            in_episode = False
            current = 0
    open_duration = current if in_episode else 0
    return {
        "time_under_water_issues": float(total_underwater),
        "recovery_issues": float(events),
        "max_recovery_issues": float(max(completed_durations, default=0)),
        "open_underwater_issues": float(open_duration),
    }


def verify_path_metrics(
    ledger: pd.DataFrame,
    holding: pd.DataFrame,
) -> list[str]:
    """Recompute issue-level and aggregate path metrics from primitives.

    REWORK v4 (EV D2): the recovery/time-under-water episode semantics are
    recomputed here with the INDEPENDENT `_independent_recovery_episodes`
    primitive implementation, never by calling production `summarize_path`.
    This closes the blind spot where the verifier and the producer shared the
    same right-censoring semantic error.
    """
    from .replay import (
        materialize_issue_path_metrics,
        path_holding_metrics,
        summarize_path,
    )

    failures: list[str] = []
    if ledger.empty or holding.empty:
        return ["path metric artifacts are empty"]
    required_issue_columns = {
        "drawdown_pct", "consecutive_losses", "mean_pairwise_overlap",
        "ticket_hhi", "repeat_exposure",
    }
    missing = required_issue_columns - set(ledger.columns)
    if missing:
        return [f"capital ledger missing path metrics: {sorted(missing)}"]
    for column in required_issue_columns:
        if ledger[column].isna().any():
            failures.append(f"capital ledger has null {column}")
    expected_keys: set[tuple[str, str]] = set()
    for (split, policy), group in ledger.groupby(["split", "policy"], sort=False):
        group = group.sort_values(["year", "issue"], kind="mergesort")
        expected_keys.add((str(split), str(policy)))
        recomputed = materialize_issue_path_metrics(group)
        for column in ("drawdown_pct", "consecutive_losses"):
            observed = group[column].to_numpy(dtype=float)
            expected = recomputed[column].to_numpy(dtype=float)
            if not np.allclose(observed, expected, atol=1e-9):
                failures.append(
                    f"{split}/{policy} issue-level {column} mismatch"
                )
        summary = {**summarize_path(group), **path_holding_metrics(group)}
        # REWORK v4 (EV D2): independently recompute the episode semantics and
        # compare against BOTH the production summary and the published row.
        posts = group["post_issue_bankroll_yuan"].to_numpy(dtype=float)
        initial = float(group.iloc[0]["pre_issue_bankroll_yuan"])
        independent = _independent_recovery_episodes(posts, initial)
        for key, expected in independent.items():
            if not np.isclose(
                float(summary.get(key, float("nan"))),
                expected,
                atol=1e-9,
                equal_nan=True,
            ):
                failures.append(
                    f"{split}/{policy} production summary {key} disagrees "
                    f"with independent episode recomputation"
                )
        row = holding[
            holding["split"].astype(str).eq(str(split))
            & holding["policy"].astype(str).eq(str(policy))
        ]
        if len(row) != 1:
            failures.append(f"{split}/{policy} holding summary cardinality != 1")
            continue
        for key, expected in summary.items():
            if key not in row.columns:
                failures.append(f"holding summary missing {key}")
                continue
            observed = row.iloc[0][key]
            if isinstance(expected, (bool, np.bool_)):
                if bool(observed) != bool(expected):
                    failures.append(f"{split}/{policy} holding {key} mismatch")
            elif not np.isclose(float(observed), float(expected), equal_nan=True):
                failures.append(f"{split}/{policy} holding {key} mismatch")
    observed_keys = set(
        zip(holding["split"].astype(str), holding["policy"].astype(str))
    )
    if observed_keys != expected_keys:
        failures.append("holding summary path inventory mismatch")
    return failures


def _candidate_from_action_key(action_key: str) -> dict[str, object]:
    parts = str(action_key).split("/")
    if len(parts) != 4:
        raise VerifyError(f"invalid candidate action key: {action_key}")
    return {
        "policy": "LEARNED_MLP_Q",
        "n": int(parts[0][1:]),
        "k": int(parts[1][1:]),
        "lane": parts[2],
        "capital": parts[3],
    }


def _incumbent_candidate(*, reason: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "policy": "FROZEN_N7_INCUMBENT",
        "n": INCUMBENT_N,
        "k": INCUMBENT_K,
        "lane": INCUMBENT_LANE,
        "capital": "NATIVE_2_YUAN",
    }
    if reason:
        value["reason"] = (
            "selection rule found no eligible learned row; freeze N7 incumbent"
        )
    return value


def verify_selection_authority(package: Path) -> list[str]:
    """Independently rebuild terminal selection and bind it to #209 handoff."""
    failures: list[str] = []
    try:
        selection = json.loads(
            (package / "selection.json").read_text(encoding="utf-8")
        )
        handoff = json.loads(
            (package / "handoff_209.json").read_text(encoding="utf-8")
        )
        incumbent = pd.read_parquet(package / "incumbent_paths.parquet")
    except Exception as exc:
        return [f"selection authority inputs unreadable: {exc}"]

    fold_specs = (("fold1", "CV_2022"), ("fold2", "CV_2023"))
    expected_rows: list[dict[str, object]] = []
    learned_drawdowns: list[float] = []
    for fold, split in fold_specs:
        path_file = package / f"path_learned_{fold}.parquet"
        if not path_file.exists():
            failures.append(f"selection primitive missing: {path_file.name}")
            continue
        learned = pd.read_parquet(path_file).sort_values("issue")
        frozen = incumbent.loc[
            incumbent["split"].astype(str).eq(split)
        ].sort_values("issue")
        if learned.empty or frozen.empty:
            failures.append(f"selection primitive empty: {fold}/{split}")
            continue
        learned_end = float(learned.iloc[-1]["post_issue_bankroll_yuan"])
        incumbent_end = float(frozen.iloc[-1]["post_issue_bankroll_yuan"])
        expected_rows.append({
            "fold": fold,
            "test_split": split,
            "learned_end": learned_end,
            "frozen_incumbent_end": incumbent_end,
            "matched_lift": learned_end - incumbent_end,
        })
        learned_drawdowns.append(float(learned["drawdown_pct"].max()))

    if len(expected_rows) != len(fold_specs):
        return failures
    lifts = np.asarray([float(row["matched_lift"]) for row in expected_rows])
    median_lift = float(np.median(lifts))
    positive = int(np.sum(lifts > 0))
    rule1 = bool(
        np.isfinite(lifts).all()
        and all(float(row["learned_end"]) > 0 for row in expected_rows)
    )
    rule2 = bool(np.isfinite(median_lift) and median_lift > 0)
    rule3 = positive == len(expected_rows)
    eligible = bool(rule1 and rule2 and rule3)
    expected_scalars = {
        "rule1_valid_replay_complete_support_no_ruin": rule1,
        "rule2_positive_median_lift": rule2,
        "rule3_positive_on_all_constructible_folds": rule3,
        "eligible": eligible,
        "median_matched_lift_yuan": median_lift,
        "positive_fold_count": positive,
        "constructible_fold_count": len(expected_rows),
        "worst_fold_matched_lift_yuan": float(np.min(lifts)),
        "max_drawdown_pct": float(max(learned_drawdowns)),
    }
    for key, expected in expected_scalars.items():
        observed = selection.get(key)
        if isinstance(expected, bool):
            if observed is not expected:
                failures.append(f"selection {key} mismatch")
        else:
            try:
                matches = np.isclose(
                    float(observed), float(expected), equal_nan=True
                )
            except (TypeError, ValueError):
                matches = False
            if not matches:
                failures.append(f"selection {key} mismatch")

    observed_rows = selection.get("matched_lift_by_fold")
    if not isinstance(observed_rows, list) or len(observed_rows) != len(expected_rows):
        failures.append("selection fold primitive inventory mismatch")
    else:
        by_fold = {str(row.get("fold")): row for row in observed_rows}
        for expected in expected_rows:
            observed = by_fold.get(str(expected["fold"]))
            if observed is None:
                failures.append(f"selection missing {expected['fold']}")
                continue
            for key in ("test_split", "learned_end", "frozen_incumbent_end", "matched_lift"):
                if key == "test_split":
                    if observed.get(key) != expected[key]:
                        failures.append(f"selection {expected['fold']} {key} mismatch")
                else:
                    try:
                        matches = np.isclose(
                            float(observed.get(key)),
                            float(expected[key]),
                            equal_nan=True,
                        )
                    except (TypeError, ValueError):
                        matches = False
                    if not matches:
                        failures.append(
                            f"selection {expected['fold']} {key} mismatch"
                        )

    if eligible:
        terminal = pd.read_parquet(package / "decision_rows_all.parquet")
        frequency = terminal.loc[
            terminal["split"].eq("CV_2023"), "action_key"
        ].value_counts()
        expected_candidate = _candidate_from_action_key(str(frequency.index[0]))
        expected_frozen = expected_candidate
    else:
        expected_candidate = _incumbent_candidate(reason=True)
        expected_frozen = _incumbent_candidate()
    if selection.get("candidate") != expected_candidate:
        failures.append("selection candidate disagrees with decisive primitives")
    if selection.get("frozen_candidate") != expected_frozen:
        failures.append("selection frozen_candidate disagrees with eligibility")
    if handoff.get("candidate") != expected_frozen:
        failures.append("handoff candidate disagrees with selection")
    if handoff.get("fallback") != _incumbent_candidate():
        failures.append("handoff fallback is not frozen incumbent")

    try:
        inventory = json.loads(
            (package / "fitted_object_inventory.json").read_text(encoding="utf-8")
        )["fitted_objects"]["primary_mlp"]
        model = handoff.get("model") or {}
        for key in (
            "model_kind", "fixed_action_key", "fitted_action_keys",
            "residual_rmse", "validation_rmse", "fit_issue_count",
            "validation_issue_count",
        ):
            if model.get(key) != inventory.get(key):
                failures.append(f"handoff model {key} disagrees with fitted inventory")
        numerical = inventory.get("model") or {}
        if model.get("scaler_mean") != numerical.get("scaler_mean"):
            failures.append("handoff model scaler_mean disagrees with inventory")
        if model.get("scaler_scale") != numerical.get("scaler_scale"):
            failures.append("handoff model scaler_scale disagrees with inventory")
    except Exception as exc:
        failures.append(f"handoff fitted-model relation unreadable: {exc}")
    return failures


def verify_handoff_contract(package: Path) -> list[str]:
    """Validate the minimal label-blind #209 inference contract."""
    failures = verify_handoff_paths(package)
    if failures:
        return failures
    handoff = json.loads((package / "handoff_209.json").read_text(encoding="utf-8"))
    for key in (
        "fit_boundary", "candidate", "fallback", "model", "model_file",
        "contract_version", "package_manifest", "label_blind_replay",
    ):
        if key not in handoff:
            failures.append(f"handoff missing {key}")
    boundary = handoff.get("fit_boundary", {})
    if boundary.get("2024_opened") is not False:
        failures.append("handoff does not keep 2024 closed")
    if handoff.get("contract_version") != CONTRACT_VERSION:
        failures.append("handoff contract version mismatch")
    if handoff.get("handoff_version") != "bj208-handoff-for-209-v7":
        failures.append("handoff version is not v7")
    model_ref = handoff.get("model_file")
    if model_ref:
        target = _handoff_ref_in_package(package, str(model_ref))
        if target is None or not target.exists():
            failures.append(f"handoff model file unresolved: {model_ref}")
    return failures


def verify_dynamic_control_decisions(frame: pd.DataFrame) -> list[str]:
    """Restricted dynamic controls must be scored per issue from causal state."""
    failures: list[str] = []
    required_policies = {
        "dynamic_n_fixed_k8_lane",
        "fixed_n7_dynamic_k",
        "dynamic_nk_fixed_generator",
    }
    if frame.empty:
        return ["empty dynamic control decision table"]
    if set(frame["policy"].unique()) != required_policies:
        failures.append("dynamic control table does not contain exactly three controls")
    for policy, group in frame.groupby("policy"):
        traces: list[dict[str, Any]] = []
        for raw in group["decision_trace_json"]:
            try:
                traces.append(json.loads(raw))
            except Exception:
                failures.append(f"{policy} has invalid decision trace JSON")
                break
        if traces and any(
            trace.get("control_semantics")
            != "PER_ISSUE_CAUSAL_STATE_CONDITIONED"
            for trace in traces
        ):
            failures.append(f"{policy} is not marked state-conditioned")
        score_signatures = {
            json.dumps(trace.get("scores", {}), sort_keys=True)
            for trace in traces
            if trace.get("scores")
        }
        if len(group) > 1 and len(score_signatures) < 2:
            failures.append(f"{policy} scores do not respond to issue state")
        for (_, row), trace in zip(group.iterrows(), traces):
            scores = trace.get("scores")
            if not isinstance(scores, dict) or not scores:
                failures.append(f"{policy} has empty score map")
                continue
            try:
                expected_key = max(scores, key=lambda key: float(scores[key]))
            except Exception:
                failures.append(f"{policy} has invalid score values")
                continue
            chosen = str(row["action_key"])
            if chosen != expected_key or trace.get("action_key") != expected_key:
                failures.append(f"{policy} chosen action is not score argmax")
            match = re.fullmatch(
                r"N(?P<n>\d+)/K(?P<k>\d+)/(?P<lane>[^/]+)/(?P<capital>[^/]+)",
                chosen,
            )
            if match is None:
                failures.append(f"{policy} has malformed action key")
                continue
            n = int(match.group("n"))
            k = int(match.group("k"))
            if match.group("lane") != "MARKET_WOR" or match.group("capital") != "NATIVE_2_YUAN":
                failures.append(f"{policy} action outside frozen lane/capital")
            if policy == "dynamic_n_fixed_k8_lane" and k != 8:
                failures.append(f"{policy} chose K{k}, expected fixed K8")
            if policy == "fixed_n7_dynamic_k" and n != 7:
                failures.append(f"{policy} chose N{n}, expected fixed N7")
    return failures


def verify_capital_accounting(ledger: pd.DataFrame) -> list[str]:
    """post = pre - funded + payout; integer ¥2 funding; path continuity.

    REWORK v2 (D4): additionally checks every path starts at the frozen
    ¥100,000 initial bankroll, funded stake is an integer multiple of ¥2,
    funded <= pre (no leverage / no top-up), and no negative/NaN values.
    """
    failures: list[str] = []
    if ledger.empty:
        return ["empty capital ledger"]
    required_numeric = (
        "pre_issue_bankroll_yuan",
        "funded_stake_yuan",
        "gross_payout_yuan",
        "post_issue_bankroll_yuan",
    )
    for column in required_numeric:
        if column not in ledger.columns:
            failures.append(f"capital ledger missing {column}")
            return failures
        if not np.isfinite(ledger[column].to_numpy(dtype=float)).all():
            failures.append(f"capital ledger {column} contains NaN/Inf")
    expected = (
        ledger["pre_issue_bankroll_yuan"]
        - ledger["funded_stake_yuan"]
        + ledger["gross_payout_yuan"]
    )
    mismatch = ~np.isclose(expected, ledger["post_issue_bankroll_yuan"], atol=1e-6)
    if mismatch.any():
        failures.append(
            f"capital conservation violated on {int(mismatch.sum())} rows"
        )
    if (ledger["funded_stake_yuan"] < 0).any():
        failures.append("negative funded stake")
    if (ledger["gross_payout_yuan"] < 0).any():
        failures.append("negative payout")
    if (ledger["pre_issue_bankroll_yuan"] < 0).any():
        failures.append("negative pre-issue bankroll")
    # Integer ¥2 funding units (native ¥2 per ticket; active = integer units).
    funded = ledger["funded_stake_yuan"].to_numpy(dtype=float)
    if not np.allclose(funded / TICKET_STAKE_YUAN, np.round(funded / TICKET_STAKE_YUAN), atol=1e-9):
        failures.append("funded stake is not an integer multiple of ¥2")
    # No leverage: funded must never exceed pre (and never exceed requested).
    if "requested_stake_yuan" in ledger.columns:
        over_req = ledger["funded_stake_yuan"] > ledger["requested_stake_yuan"] + 1e-6
        if over_req.any():
            failures.append(
                f"funded exceeds requested on {int(over_req.sum())} rows"
            )
        active = ledger[ledger.get("capital", pd.Series(index=ledger.index, dtype=object)).eq("SIMPLE_ACTIVE")]
        if not active.empty:
            expected_request = active["pre_issue_bankroll_yuan"] * 0.01
            bad_request = ~np.isclose(
                active["requested_stake_yuan"], expected_request, atol=1e-6
            )
            if bad_request.any():
                failures.append(
                    f"SIMPLE_ACTIVE requested stake mismatch on {int(bad_request.sum())} rows"
                )
            unfundable_execution = (
                active["pre_issue_bankroll_yuan"].lt(200.0 - 1e-9)
                & active["funded_stake_yuan"].gt(0.0)
            )
            if unfundable_execution.any():
                failures.append("SIMPLE_ACTIVE executed below ¥200 minimum bankroll")
    over_pre = ledger["funded_stake_yuan"] > ledger["pre_issue_bankroll_yuan"] + 1e-6
    if over_pre.any():
        failures.append(f"funded exceeds pre-issue bankroll on {int(over_pre.sum())} rows")
    # Path continuity: within each (split, policy) path the next issue's pre
    # must equal the prior issue's post (no top-up, no leakage).
    path_keys = [c for c in ("split", "policy") if c in ledger.columns]
    if path_keys:
        try:
            for _, group in ledger.groupby(path_keys, sort=False):
                group = group.sort_values("issue")
                posts = group["post_issue_bankroll_yuan"].to_numpy(dtype=float)
                pres = group["pre_issue_bankroll_yuan"].to_numpy(dtype=float)
                if len(posts) > 1:
                    continuity = ~np.isclose(posts[:-1], pres[1:], atol=1e-6)
                    if continuity.any():
                        failures.append(
                            f"path continuity broken on {int(continuity.sum())} row boundary"
                        )
                        break
        except Exception as exc:  # pragma: no cover
            failures.append(f"path continuity check failed: {exc}")
    # Every path starts at the frozen ¥100,000 initial bankroll.
    if path_keys:
        for _, group in ledger.groupby(path_keys, sort=False):
            group = group.sort_values("issue")
            first = float(group.iloc[0]["pre_issue_bankroll_yuan"])
            if not np.isclose(first, INITIAL_BANKROLL_YUAN, atol=1e-6):
                failures.append(
                    f"path {group.iloc[0].get('policy', '?')} starts at {first}, "
                    f"not {INITIAL_BANKROLL_YUAN}"
                )
                break
    return failures


def verify_no_embargoed_split(frame: pd.DataFrame, split_col: str = "split") -> list[str]:
    if split_col not in frame.columns:
        return [f"missing split column {split_col}"]
    present = set(frame[split_col].unique())
    overlap = present & set(EMBARGOED_SPLITS)
    if overlap:
        return [f"embargoed split present: {sorted(overlap)}"]
    return []


def verify_no_2024_issue(frame: pd.DataFrame) -> list[str]:
    if "issue" not in frame.columns:
        return []
    issues = frame["issue"].astype(str)
    if issues.str.startswith("24").any():
        return ["2024 issue found in #208 artifact"]
    return []


def verify_nk_semantics(ticket_rows: pd.DataFrame, k: int | None = None) -> list[str]:
    """Every ticket has exactly N distinct matches; K is ticket count.

    REWORK v2 (D4): the function now receives K and checks that exactly K
    ticket rows exist per issue for each issued bundle (rows carry 'k' or a
    caller-provided K).  The old verifier never received K and accepted a
    single ticket.
    """
    failures: list[str] = []
    if ticket_rows.empty:
        return ["empty ticket table"]
    # Per-bundle K check: rows are grouped by (issue, lane, seed) if present,
    # else the caller-provided k applies to the whole table.
    group_cols = [
        c for c in ("split", "issue", "n", "k", "lane", "seed")
        if c in ticket_rows.columns
    ]
    if group_cols:
        for _, group in ticket_rows.groupby(group_cols, sort=False):
            row_k = int(group["k"].iloc[0]) if "k" in group.columns else (
                k if k is not None else len(group)
            )
            if len(group) != row_k:
                failures.append(
                    f"bundle has {len(group)} tickets but K={row_k}"
                )
                break
    elif k is not None:
        if len(ticket_rows) != k:
            failures.append(f"ticket table has {len(ticket_rows)} rows but K={k}")
    semantic_keys: dict[int, tuple[tuple[int, str], ...]] = {}
    for row_index, row in ticket_rows.iterrows():
        n = int(row["n"])
        matches = [int(x) for x in str(row["match_indices"]).split("|")]
        outcomes = str(row["outcomes"]).split("|")
        if len(matches) != n:
            failures.append(f"ticket {row['ticket_identity']} has {len(matches)} matches != N={n}")
            break
        if len(set(matches)) != n:
            failures.append(f"ticket {row['ticket_identity']} has duplicate matches")
            break
        if len(outcomes) != n:
            failures.append(f"ticket {row['ticket_identity']} outcome count mismatch")
            break
        if not set(outcomes).issubset({"3", "1", "0"}):
            failures.append(f"ticket {row['ticket_identity']} has invalid outcome code")
            break
        paired_legs = tuple(sorted(zip(matches, outcomes, strict=True)))
        semantic_keys[row_index] = paired_legs
        if "issue" in ticket_rows.columns:
            payload = "|".join(
                f"{row['issue']}:{match_idx}:{outcome}"
                for match_idx, outcome in paired_legs
            )
            expected_identity = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if str(row["ticket_identity"]) != expected_identity:
                failures.append(
                    f"ticket {row['ticket_identity']} is not canonical for paired legs"
                )
                break
    if failures:
        return failures

    # Only the explicit with-replacement lane may repeat a semantic ticket.
    # WOR and deterministic top-K lanes operate over unique unordered parlays,
    # so a leg-order alias is a contract failure even if its stored hash differs.
    if group_cols and "lane" in ticket_rows.columns:
        for group_key, group in ticket_rows.groupby(group_cols, sort=False):
            lane = str(group["lane"].iloc[0])
            if lane == "MARKET_WR":
                continue
            keys = [semantic_keys[index] for index in group.index]
            if len(set(keys)) != len(keys):
                failures.append(
                    f"bundle {group_key} contains semantic duplicate tickets in {lane}"
                )
                break
    return failures


def verify_provenance(provenance: dict[str, Any]) -> list[str]:
    """Validate provenance against the trusted upstream identity.

    REWORK v2 (D4): provenance must carry the frozen upstream hashes and
    contract version.  A forged provenance fails because the fields do not
    match the trusted constants (not because a string starts with 'FORGED').
    """
    from .contract import (
        UPSTREAM_207_MANIFEST_SHA256,
        UPSTREAM_207_SHA,
        VALUE_MATRIX_SHA256,
    )

    failures: list[str] = []
    expected = {
        "version": CONTRACT_VERSION,
        "source_issue_207_sha": UPSTREAM_207_SHA,
        "source_issue_207_manifest_sha256": UPSTREAM_207_MANIFEST_SHA256,
        "source_value_matrix_sha256": VALUE_MATRIX_SHA256,
    }
    for key, value in expected.items():
        if provenance.get(key) != value:
            failures.append(f"provenance {key} mismatch: {provenance.get(key)}")
    if "label_boundary" not in provenance or "2024" not in str(provenance.get("label_boundary", "")):
        failures.append("provenance label_boundary must state 2024 embargo")
    return failures


def verify_code_bindings(provenance: dict[str, Any], root: Path) -> list[str]:
    """Bind the decision to its executable code/config and environment lock."""
    failures: list[str] = []
    bindings = provenance.get("code_bindings")
    if not isinstance(bindings, dict) or not bindings:
        return ["provenance missing code_bindings"]
    expected_paths = {
        "method.yaml",
        "requirements.txt",
        "scripts/run_bj208_policy.py",
        *(
            path.relative_to(root).as_posix()
            for path in sorted((root / "src/parlay_policy").glob("*.py"))
        ),
    }
    if set(map(str, bindings)) != expected_paths:
        missing = sorted(expected_paths - set(map(str, bindings)))
        extra = sorted(set(map(str, bindings)) - expected_paths)
        if missing:
            failures.append(f"code bindings omit expected files: {missing}")
        if extra:
            failures.append(f"code bindings contain unexpected files: {extra}")
    for relative, expected in bindings.items():
        path = root / str(relative)
        if not path.exists():
            failures.append(f"bound code missing: {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"bound code hash mismatch: {relative}")
    environment = provenance.get("environment")
    if not isinstance(environment, dict):
        failures.append("provenance missing environment lock")
    else:
        payload = json.dumps(
            environment, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != provenance.get("environment_lock_sha256"):
            failures.append("environment lock hash mismatch")
    commit = str(provenance.get("producer_code_commit", ""))
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        failures.append("provenance producer_code_commit is not a full SHA")
    return failures


def verify_2024_mutation_invariance(
    fit_fn: Any,
    value_matrix_path: Path,
    *,
    fit_kwargs: dict[str, Any] | None = None,
) -> list[str]:
    """REQ-208-03: mutating 2024 labels cannot change any fitted parameter.

    REWORK v2 (D4): this is a REAL invariance check.  The pipeline is fitted
    on a copy of the value matrix with 2024 realized_outcome/official SP
    mutated; fitted parameters (model weights or fixed-action choice) must be
    byte-identical because #208 never reads 2024 rows.

    fit_fn(pipeline_frame) -> fitted_params_hash (str).  The check loads the
    original value matrix, fits, then fits again on a 2024-mutated copy and
    compares hashes.
    """
    if fit_fn is None:
        return ["2024 mutation invariance requires a fit_fn"]
    frame = pd.read_parquet(value_matrix_path)
    baseline = fit_fn(frame, **(fit_kwargs or {}))
    mutated = frame.copy()
    mask_2024 = mutated["issue"].astype(str).str.startswith("24")
    if mask_2024.any():
        mutated.loc[mask_2024, "realized_outcome"] = ~mutated.loc[
            mask_2024, "realized_outcome"
        ].astype(bool)
        mutated.loc[mask_2024, "official_final_sp_label"] = (
            mutated.loc[mask_2024, "official_final_sp_label"] * 1.5
        )
    after = fit_fn(mutated, **(fit_kwargs or {}))
    if baseline != after:
        return ["2024 label mutation changed fitted parameters"]
    return []


# --- REWORK v3 (PI payout-economics) verifier --------------------------------

# Beijing ticket payout coefficient — applied exactly once per winning N-fold
# ticket.  Never divided out, never per leg, never compounded as 0.65^N.
_PAYOUT_COEFFICIENT = 0.65
_PAYOUT_REL_TOL = 1e-6


def _official_sp_for_ticket(
    panels: dict[tuple[str, str], Any],
    split: str,
    issue: str,
    match_indices: str,
    outcomes: str,
) -> float:
    """Product of official final SP for a ticket's (match, outcome) legs.

    Recomputed independently from the frozen value-matrix panels so the
    verifier does not trust the worker's `pre_tax_gross_multiple` field.
    """
    panel = panels.get((str(split), str(issue)))
    if panel is None:
        raise VerifyError(f"payout-economics panel missing: {split}/{issue}")
    immutable_match_ids = [int(x) for x in str(match_indices).split("|")]
    out_rank = {"3": 0, "1": 1, "0": 2}
    oidx = [out_rank[o] for o in str(outcomes).split("|")]
    if len(immutable_match_ids) != len(oidx):
        raise VerifyError("ticket leg count mismatch in payout-economics")
    row_by_match_id = {
        int(match_idx): row_index
        for row_index, match_idx in enumerate(panel.match_idx)
    }
    try:
        row_indices = [row_by_match_id[match_idx] for match_idx in immutable_match_ids]
    except KeyError as exc:
        raise VerifyError(
            f"payout-economics unknown immutable match id: {exc.args[0]}"
        ) from exc
    sp = panel.official_sp[
        np.asarray(row_indices, dtype=int), np.asarray(oidx, dtype=int)
    ]
    return float(np.prod(sp))


def verify_payout_economics(
    package: Path,
    panels: dict[tuple[str, str], Any],
    upstream_tickets: pd.DataFrame,
    ledger: pd.DataFrame | None = None,
) -> list[str]:
    """REWORK v3 (PI payout-economics) production-entry verifier.

    Independent checks that the Beijing payout coefficient 0.65 is applied
    EXACTLY ONCE per winning N-fold ticket and never divided out:

    1. `ticket_economics.parquet` per-ticket pre_tax_gross_multiple must equal
       0.65 * prod(official_sp) for hit rows (0.0 for miss rows).  This
       detects BOTH omission (multiple == prod(SP)) AND compounding
       (multiple == 0.65^N * prod(SP)).
    2. `incumbent_paths.parquet` gross_payout_yuan must equal the frozen
       CONTROLLING tickets' sum(realized_gross) * ¥2 (realized_gross already
       includes 0.65 exactly once).  This detects division-out (payout
       inflated by /0.65).
    3. The consolidated ledger's FROZEN_INCUMBENT_207 rows must match the
       incumbent_paths rows (binding consistency).
    """
    failures: list[str] = []

    # 1. Per-ticket economics from the immutable package.
    econ_path = package / "ticket_economics.parquet"
    if not econ_path.exists():
        failures.append("missing ticket_economics.parquet for payout economics")
        return failures
    econ = pd.read_parquet(econ_path)
    if econ.empty:
        failures.append("empty ticket_economics.parquet")
        return failures
    checked = 0
    for _, row in econ.iterrows():
        try:
            sp_prod = _official_sp_for_ticket(
                panels,
                str(row["split"]),
                str(row["issue"]),
                str(row["match_indices"]),
                str(row["outcomes"]),
            )
        except VerifyError as exc:
            failures.append(str(exc))
            continue
        hit = bool(row["realized_hit"])
        if hit:
            expected = _PAYOUT_COEFFICIENT * sp_prod
            actual = float(row["pre_tax_gross_multiple"])
            if not np.isclose(actual, expected, rtol=_PAYOUT_REL_TOL, atol=1e-9):
                failures.append(
                    f"payout coefficient violation ticket {str(row['ticket_identity'])} "
                    f"{row['split']}/{row['issue']}: multiple={actual:.6f} "
                    f"expected 0.65*prod(SP)={expected:.6f} (prod(SP)={sp_prod:.6f})"
                )
                if len(failures) >= 5:
                    break
        else:
            actual = float(row["pre_tax_gross_multiple"])
            if not np.isclose(actual, 0.0, atol=1e-9):
                failures.append(
                    f"miss ticket {str(row['ticket_identity'])} has nonzero multiple "
                    f"{actual}"
                )
        checked += 1
    if checked == 0:
        failures.append("ticket_economics had no rows with official SP available")

    # 2. Incumbent path payout vs frozen CONTROLLING realized_gross.
    inc_path = package / "incumbent_paths.parquet"
    if not inc_path.exists():
        failures.append("missing incumbent_paths.parquet")
    else:
        incumbent = pd.read_parquet(inc_path)
        if "source" in incumbent.columns:
            reconstructed = incumbent[
                incumbent["source"].str.startswith(
                    "RECONSTRUCTED_CORRECTED_ECONOMICS"
                )
            ]
        else:
            reconstructed = incumbent
        for _, row in reconstructed.iterrows():
            tickets = upstream_tickets[
                (upstream_tickets["split"] == row["split"])
                & (upstream_tickets["issue"] == row["issue"])
                & (upstream_tickets["panel_role"] == "CONTROLLING")
                & (upstream_tickets["policy"] == "MARKET_WOR")
                & (upstream_tickets["k"] == 8)
            ]
            if tickets.empty:
                failures.append(
                    f"incumbent reconstruction missing CONTROLLING tickets "
                    f"{row['split']}/{row['issue']}"
                )
                continue
            expected_payout = float(
                tickets["realized_gross"].fillna(0.0).sum() * 2.0
            )
            actual_payout = float(row["gross_payout_yuan"])
            if not np.isclose(
                actual_payout, expected_payout, rtol=_PAYOUT_REL_TOL, atol=1e-6
            ):
                failures.append(
                    f"incumbent payout division-out at {row['split']}/{row['issue']}: "
                    f"payout={actual_payout:.4f} expected "
                    f"sum(realized_gross)*2={expected_payout:.4f}"
                )
                if len(failures) >= 5:
                    break

    # 3. FROZEN_INCUMBENT_207 ledger rows must equal incumbent_paths.
    if ledger is not None and not ledger.empty:
        if "source" in ledger.columns:
            frozen_rows = ledger[ledger["source"] == "FROZEN_INCUMBENT_207"]
            if not frozen_rows.empty:
                inc_path2 = package / "incumbent_paths.parquet"
                if inc_path2.exists():
                    incumbent = pd.read_parquet(inc_path2)
                    for _, row in frozen_rows.iterrows():
                        sub = incumbent[
                            (incumbent["split"] == row["split"])
                            & (incumbent["issue"] == row["issue"])
                        ]
                        if sub.empty:
                            continue
                        if not np.isclose(
                            float(sub.iloc[0]["gross_payout_yuan"]),
                            float(row["gross_payout_yuan"]),
                            rtol=_PAYOUT_REL_TOL, atol=1e-6,
                        ):
                            failures.append(
                                f"FROZEN_INCUMBENT_207 ledger row {row['split']}/"
                                f"{row['issue']} does not match incumbent_paths"
                            )
                            break
    return failures


# --- tamper attacks (attack the PRODUCTION verifier) ------------------------


def tamper_mutate_settlement(ledger_path: Path) -> None:
    """Attack 1: mutate a realized settlement field (payout)."""
    frame = pd.read_parquet(ledger_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    frame.loc[frame.index[0], "gross_payout_yuan"] = (
        float(frame.loc[frame.index[0], "gross_payout_yuan"]) + 12345.0
    )
    frame.to_parquet(ledger_path, index=False)


def tamper_self_consistent_ledger(ledger_path: Path) -> None:
    """Attack 2: change a ledger row but keep the accounting equation true."""
    frame = pd.read_parquet(ledger_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    idx = frame.index[0]
    pre = float(frame.loc[idx, "pre_issue_bankroll_yuan"])
    funded = float(frame.loc[idx, "funded_stake_yuan"])
    payout = float(frame.loc[idx, "gross_payout_yuan"])
    post = pre - funded + payout
    frame.loc[idx, "pre_issue_bankroll_yuan"] = pre + 100.0
    frame.loc[idx, "post_issue_bankroll_yuan"] = post + 100.0
    frame.to_parquet(ledger_path, index=False)


def tamper_forge_manifest(manifest_path: Path, package: Path) -> None:
    """Attack 3: rewrite the manifest to claim tampered hashes are valid AND
    hide an unlisted payload."""
    frame_names = [
        path.relative_to(package).as_posix()
        for path in sorted(package.rglob("*.parquet"))
    ]
    forged: dict[str, str] = {}
    for name in frame_names:
        forged[name] = "0" * 64
    # Also declare a payload that is NOT on disk (claims coverage of a file
    # that does not exist) — coverage must catch the missing file.
    forged["ghost_payload.parquet"] = "0" * 64
    _json(manifest_path, forged)


def tamper_forge_source_trace(trace_path: Path) -> None:
    """Attack 4: rewrite provenance/source trace with forged identity + hash."""
    if not trace_path.exists():
        raise VerifyError("tamper target missing")
    value = json.loads(trace_path.read_text(encoding="utf-8"))
    value["source_identity"] = "FORGED_TRACE_00000000000000000000000000000000"
    value["source_issue_207_manifest_sha256"] = "0" * 64
    value["source_value_matrix_sha256"] = "0" * 64
    _json(trace_path, value)


def tamper_omit_payout_coefficient(econ_path: Path) -> None:
    """Attack 5 (REWORK v3): drop the 0.65 coefficient from a hit ticket.

    Sets a winning ticket's pre_tax_gross_multiple to the raw product(SP)
    (the superseded omission defect).  The payout-economics verifier must
    recompute 0.65*prod(SP) and FAIL the tampered multiple.
    """
    frame = pd.read_parquet(econ_path)
    hits = frame[frame["realized_hit"] == True]  # noqa: E712
    if hits.empty:
        raise VerifyError("tamper target has no hit ticket")
    idx = hits.index[0]
    # raw product(SP) = pre_tax_gross_multiple / 0.65 (omission).
    frame.loc[idx, "pre_tax_gross_multiple"] = (
        float(frame.loc[idx, "pre_tax_gross_multiple"]) / _PAYOUT_COEFFICIENT
    )
    frame.to_parquet(econ_path, index=False)


def tamper_divide_out_payout(incumbent_paths_path: Path) -> None:
    """Attack 6 (REWORK v3): divide the payout coefficient back out.

    Inflates an incumbent issue's gross_payout_yuan by /0.65 (the superseded
    division-out defect: pre-tax = realized_gross / 0.65).  The verifier must
    recompute payout = sum(realized_gross)*2 and FAIL.  The mutated row is a
    NONZERO-payout issue (a zero-payout row would make /0.65 a no-op).
    """
    frame = pd.read_parquet(incumbent_paths_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    nonzero = frame[frame["gross_payout_yuan"] > 1e-9]
    if nonzero.empty:
        raise VerifyError("tamper target has no nonzero incumbent payout")
    idx = nonzero.index[0]
    frame.loc[idx, "gross_payout_yuan"] = (
        float(frame.loc[idx, "gross_payout_yuan"]) / _PAYOUT_COEFFICIENT
    )
    frame.to_parquet(incumbent_paths_path, index=False)


def tamper_compound_coefficient(econ_path: Path, n: int = 4) -> None:
    """Attack 7 (REWORK v3): compound the coefficient per leg (0.65^N).

    Sets a winning ticket's pre_tax_gross_multiple to 0.65^N * prod(SP)
    (the superseded per-leg compounding defect).  The verifier must recompute
    0.65*prod(SP) (coefficient exactly once) and FAIL the 0.65^N multiple.
    """
    frame = pd.read_parquet(econ_path)
    hits = frame[frame["realized_hit"] == True]  # noqa: E712
    if hits.empty:
        raise VerifyError("tamper target has no hit ticket")
    idx = hits.index[0]
    # 0.65^N * prod(SP) = (0.65^N)/0.65 * (0.65*prod(SP)) = 0.65^(N-1)*multiple.
    frame.loc[idx, "pre_tax_gross_multiple"] = (
        float(frame.loc[idx, "pre_tax_gross_multiple"])
        * (_PAYOUT_COEFFICIENT ** (n - 1))
    )
    frame.to_parquet(econ_path, index=False)


def tamper_handoff_staging_path(handoff_path: Path) -> None:
    """Attack 8 (REWORK v3.1): rewrite handoff_209.json to point package_manifest
    at the transient staging directory.

    The v3 defect serialized `results/issue-208.staging/SHA256SUMS.json`
    because `_build_handoff` received the staging output path.  A handoff that
    references `.staging` must FAIL `verify_handoff_paths` (and therefore the
    production package verifier) even though the path is a valid relative
    string — the staging directory does not exist after atomic publication.
    """
    if not handoff_path.exists():
        raise VerifyError("tamper target missing")
    value = json.loads(handoff_path.read_text(encoding="utf-8"))
    value["package_manifest"] = "results/issue-208.staging/SHA256SUMS.json"
    _json(handoff_path, value)


def tamper_completion_status(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value["status"] = "IN_PROGRESS"
    _json(path, value)


def tamper_empty_schema(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value["frames"] = {}
    _json(path, value)


def tamper_drop_bundle_ticket(path: Path) -> None:
    frame = pd.read_parquet(path)
    if frame.empty:
        raise VerifyError("ticket tamper target empty")
    keys = ["split", "issue", "n", "k", "lane", "seed"]
    first_key = tuple(frame.iloc[0][key] for key in keys)
    mask = np.logical_and.reduce(
        [frame[key].eq(value).to_numpy() for key, value in zip(keys, first_key)]
    )
    indices = frame.index[mask]
    if len(indices) < 2:
        raise VerifyError("ticket tamper bundle too small")
    frame = frame.drop(indices[0])
    frame.to_parquet(path, index=False)


def tamper_semantic_ticket_alias(path: Path) -> None:
    """Replace one WOR/top-K row with an order-only alias of another row."""
    frame = pd.read_parquet(path)
    keys = ["split", "issue", "n", "k", "lane", "seed"]
    candidates = frame[~frame["lane"].eq("MARKET_WR")]
    target_indices: list[int] | None = None
    for _, group in candidates.groupby(keys, sort=False):
        if len(group) >= 2:
            target_indices = list(group.index[:2])
            break
    if target_indices is None:
        raise VerifyError("ticket alias tamper needs a non-WR bundle")
    source_index, target_index = target_indices
    source = frame.loc[source_index]
    matches = str(source["match_indices"]).split("|")
    outcomes = str(source["outcomes"]).split("|")
    reversed_pairs = list(reversed(list(zip(matches, outcomes, strict=True))))
    frame.loc[target_index, "match_indices"] = "|".join(
        match_idx for match_idx, _ in reversed_pairs
    )
    frame.loc[target_index, "outcomes"] = "|".join(
        outcome for _, outcome in reversed_pairs
    )
    noncanonical_payload = "|".join(
        f"{source['issue']}:{match_idx}:{outcome}"
        for match_idx, outcome in reversed_pairs
    )
    frame.loc[target_index, "ticket_identity"] = hashlib.sha256(
        noncanonical_payload.encode("utf-8")
    ).hexdigest()
    frame.to_parquet(path, index=False)


def tamper_req_evidence(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value["req_evidence"] = value.get("req_evidence", [])[1:]
    _json(path, value)


def tamper_dynamic_control_semantics(path: Path) -> None:
    frame = pd.read_parquet(path)
    if frame.empty:
        raise VerifyError("dynamic control tamper target empty")
    trace = json.loads(frame.loc[frame.index[0], "decision_trace_json"])
    trace["control_semantics"] = "GLOBAL_MEDIAN_FIXED_CELL"
    frame.loc[frame.index[0], "decision_trace_json"] = json.dumps(
        trace, ensure_ascii=False
    )
    frame.to_parquet(path, index=False)


def tamper_dynamic_control_non_argmax(path: Path) -> None:
    frame = pd.read_parquet(path)
    trace = json.loads(frame.loc[frame.index[0], "decision_trace_json"])
    scores = trace.get("scores", {})
    if len(scores) < 2:
        raise VerifyError("dynamic control tamper needs two scored actions")
    chosen = min(scores, key=lambda key: float(scores[key]))
    frame.loc[frame.index[0], "action_key"] = chosen
    trace["action_key"] = chosen
    frame.loc[frame.index[0], "decision_trace_json"] = json.dumps(
        trace, ensure_ascii=False
    )
    frame.to_parquet(path, index=False)


def tamper_zero_issue_drawdown(path: Path) -> None:
    frame = pd.read_parquet(path)
    frame["drawdown_pct"] = 0.0
    frame.to_parquet(path, index=False)


def tamper_holding_summary(path: Path) -> None:
    frame = pd.read_parquet(path)
    if frame.empty:
        raise VerifyError("holding summary tamper target empty")
    frame.loc[frame.index[0], "ending_capital_yuan"] = (
        float(frame.loc[frame.index[0], "ending_capital_yuan"]) + 123.0
    )
    if "rolling5_loss_prob" in frame:
        frame.loc[frame.index[0], "rolling5_loss_prob"] = 0.987654
    frame.to_parquet(path, index=False)


def tamper_omit_code_binding(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    bindings = value.get("code_bindings", {})
    if not bindings:
        raise VerifyError("code binding tamper target empty")
    bindings.pop(next(iter(bindings)))
    _json(path, value)


def tamper_holdout_state_shift(frame_path: Path) -> None:
    """REWORK v4 (EV D3) attack: shift `prior_running_drawdown_pct` in the
    training frame by +0.5 and let the attacker regenerate a legal manifest.

    Hash-only verification passes (intra-package self-consistency), so the
    production `verify_state_semantics` must fail closed on the source-derived
    recomputation and the model-scaler binding.
    """
    frame = pd.read_parquet(frame_path)
    if "prior_running_drawdown_pct" not in frame.columns:
        raise VerifyError("training frame missing prior_running_drawdown_pct")
    frame["prior_running_drawdown_pct"] = (
        frame["prior_running_drawdown_pct"].astype(float) + 0.5
    )
    frame.to_parquet(frame_path, index=False)


def tamper_receipt_append(path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("UNBOUND-DELIVERED-BYTES\n")


def tamper_receipt_rewrite(path: Path) -> None:
    path.write_text(f"{'0' * 64}  method.yaml\n", encoding="utf-8")


def tamper_receipt_duplicate(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text + text, encoding="utf-8")


def tamper_forge_holdout_attestation(package: Path) -> None:
    receipt_path = package / "holdout_mutation_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    forged = {
        "training_issues": ["FORGED_FIT"],
        "validation_issues": ["FORGED_VALIDATION"],
        "policy": {},
        "decisions": [],
    }
    encoded = json.dumps(
        forged, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = hashlib.sha256(encoded).hexdigest()
    for side in ("baseline", "mutated"):
        ref = str(receipt[f"{side}_payload_file"])
        _json(package / ref, forged)
        receipt[f"{side}_signature_sha256"] = signature
    receipt["mutated_rows"] = 1
    receipt["all_fitted_objects_and_decisions_invariant"] = True
    _json(receipt_path, receipt)


def tamper_false_promotion(package: Path) -> None:
    selection_path = package / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    for row in selection.get("matched_lift_by_fold", []):
        row["matched_lift"] = 999_999.0
        row["learned_end"] = float(row.get("frozen_incumbent_end", 0.0)) + 999_999.0
    selection.update({
        "median_matched_lift_yuan": 999_999.0,
        "worst_fold_matched_lift_yuan": 999_999.0,
        "positive_fold_count": 2,
        "rule1_valid_replay_complete_support_no_ruin": True,
        "rule2_positive_median_lift": True,
        "rule3_positive_on_all_constructible_folds": True,
        "eligible": True,
    })
    forged = {
        "policy": "LEARNED_MLP_Q",
        "n": 9,
        "k": 32,
        "lane": "LEARNED_MLP",
        "capital": "SIMPLE_ACTIVE",
    }
    selection["candidate"] = forged
    selection["frozen_candidate"] = forged
    _json(selection_path, selection)
    handoff_path = package / "handoff_209.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["candidate"] = forged
    _json(handoff_path, handoff)


def tamper_nested_manifest_name(package: Path) -> None:
    target = package / "models" / "SHA256SUMS.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _json(target, {"unbound": "payload"})


def _rewrite_manifest_for_tamper(package: Path) -> None:
    artifacts = sorted(
        path for path in package.rglob("*")
        if path.is_file()
        and path.relative_to(package).as_posix() not in MANIFEST_EXCLUDED
    )
    _json(package / "SHA256SUMS.json", manifest(package, artifacts))


def run_tamper_suite(package: Path, verify_package_fn: Any) -> list[dict[str, Any]]:
    """Run the REQ-E06 tamper attacks against the PRODUCTION package verifier.

    REWORK v2 (D4): each attack copies the package to a temp dir, mutates the
    copy, then runs the FULL production verifier (verify_package_fn) on the
    copy.  The attack is DETECTED iff the full verifier returns failures.
    This replaces the old per-function probes that could be fooled by
    unlisted payloads / FORGED-prefix checks.
    """
    import shutil
    import tempfile

    results: list[dict[str, Any]] = []

    def _run_attack(
        name: str, mutate_fn: Any, *, re_manifest: bool = True
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            # Full recursive copy (staging tree includes models/ subdir).
            for item in package.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(package)
                    dest = work / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
            mutate_fn(work)
            if re_manifest:
                _rewrite_manifest_for_tamper(work)
            failures = verify_package_fn(work)
            results.append(
                {
                    "attack": name,
                    "detected": bool(failures),
                    "failures": failures[:5],
                }
            )

    _run_attack(
        "mutate_settlement",
        lambda target: tamper_mutate_settlement(
            target / "issue_capital_ledger.parquet"
        ),
    )
    _run_attack(
        "self_consistent_ledger",
        lambda target: tamper_self_consistent_ledger(
            target / "issue_capital_ledger.parquet"
        ),
    )
    _run_attack(
        "forge_manifest",
        lambda target: tamper_forge_manifest(
            target / "SHA256SUMS.json", target
        ),
        re_manifest=False,
    )
    _run_attack(
        "forge_source_trace",
        lambda target: tamper_forge_source_trace(target / "provenance.json"),
    )
    _run_attack(
        "omit_payout_coefficient",
        lambda target: tamper_omit_payout_coefficient(
            target / "ticket_economics.parquet"
        ),
    )
    _run_attack(
        "divide_out_payout",
        lambda target: tamper_divide_out_payout(
            target / "incumbent_paths.parquet"
        ),
    )
    _run_attack(
        "compound_coefficient_0_65_n",
        lambda target: tamper_compound_coefficient(
            target / "ticket_economics.parquet", n=4
        ),
    )
    _run_attack(
        "handoff_staging_path",
        lambda target: tamper_handoff_staging_path(target / "handoff_209.json"),
    )
    _run_attack(
        "completion_not_complete",
        lambda target: tamper_completion_status(target / "COMPLETED.json"),
    )
    _run_attack(
        "empty_decision_schema",
        lambda target: tamper_empty_schema(target / "schema.json"),
    )
    _run_attack(
        "drop_ticket_from_bundle",
        lambda target: tamper_drop_bundle_ticket(
            target / "ticket_economics.parquet"
        ),
    )
    _run_attack(
        "semantic_ticket_order_alias",
        lambda target: tamper_semantic_ticket_alias(
            target / "ticket_economics.parquet"
        ),
    )
    _run_attack(
        "remove_req_evidence",
        lambda target: tamper_req_evidence(target / "decision.json"),
    )
    _run_attack(
        "dynamic_control_globalized",
        lambda target: tamper_dynamic_control_semantics(
            target / "dynamic_control_decisions.parquet"
        ),
    )
    _run_attack(
        "dynamic_control_non_argmax",
        lambda target: tamper_dynamic_control_non_argmax(
            target / "dynamic_control_decisions.parquet"
        ),
    )
    _run_attack(
        "zero_issue_drawdown",
        lambda target: tamper_zero_issue_drawdown(
            target / "issue_capital_ledger.parquet"
        ),
    )
    _run_attack(
        "holding_summary_forgery",
        lambda target: tamper_holding_summary(
            target / "path_holding_metrics.parquet"
        ),
    )
    _run_attack(
        "omit_code_binding",
        lambda target: tamper_omit_code_binding(target / "provenance.json"),
    )
    _run_attack(
        "receipt_append",
        lambda target: tamper_receipt_append(target / "receipt.sha256"),
    )
    _run_attack(
        "receipt_rewrite",
        lambda target: tamper_receipt_rewrite(target / "receipt.sha256"),
    )
    _run_attack(
        "receipt_duplicate_line",
        lambda target: tamper_receipt_duplicate(target / "receipt.sha256"),
    )
    _run_attack(
        "receipt_delete",
        lambda target: (target / "receipt.sha256").unlink(),
    )
    _run_attack(
        "forged_holdout_attestation",
        tamper_forge_holdout_attestation,
    )
    _run_attack(
        "training_state_drawdown_shift",
        lambda target: tamper_holdout_state_shift(
            target / "training_frame_all.parquet"
        ),
    )
    _run_attack(
        "false_terminal_promotion",
        tamper_false_promotion,
    )
    _run_attack(
        "nested_manifest_name_escape",
        tamper_nested_manifest_name,
        re_manifest=False,
    )
    return results


__all__ = [
    "MANIFEST_EXCLUDED", "VerifyError", "manifest", "run_tamper_suite",
    "sha256_file", "tamper_forge_manifest", "tamper_forge_source_trace",
    "tamper_mutate_settlement", "tamper_self_consistent_ledger",
    "tamper_omit_payout_coefficient", "tamper_divide_out_payout",
    "tamper_compound_coefficient", "tamper_handoff_staging_path",
    "tamper_completion_status", "tamper_drop_bundle_ticket",
    "tamper_semantic_ticket_alias",
    "tamper_dynamic_control_semantics", "tamper_empty_schema",
    "tamper_holdout_state_shift", "tamper_req_evidence",
    "verify_2024_mutation_invariance", "verify_capital_accounting",
    "verify_code_bindings", "verify_completion", "verify_dynamic_control_decisions",
    "verify_chronology",
    "verify_handoff_contract", "verify_handoff_paths",
    "verify_holdout_mutation_receipt", "verify_manifest",
    "verify_nk_semantics", "verify_package_schema", "verify_path_metrics",
    "verify_req_evidence", "verify_selection_authority",
    "verify_no_2024_issue", "verify_no_embargoed_split",
    "verify_payout_economics", "verify_provenance", "verify_receipt",
    "verify_schema", "verify_state_semantics",
]
