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
    INITIAL_BANKROLL_YUAN,
    TICKET_STAKE_YUAN,
)


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
        path = package / name
        if not path.exists():
            failures.append(f"missing artifact {name}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"hash mismatch {name}: {actual} != {expected}")
    on_disk = {
        p.relative_to(package).as_posix()
        for p in package.rglob("*")
        if p.is_file() and p.name not in MANIFEST_EXCLUDED
    }
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
        if path.name not in {"SHA256SUMS.json", "schema.json"}
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
    if receipt.get("model_weights_scaler_fixed_choice_ood_and_decisions_invariant") is not True:
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
        # Bind the attested terminal model to the actual #209 model bytes by
        # comparing fitted numerical state, not joblib serialization bytes.
        model_path = package / "models/fold2_mlp.joblib"
        if not model_path.exists():
            failures.append("holdout model binding target missing")
        else:
            try:
                import joblib

                model = joblib.load(model_path)
                steps = getattr(model, "named_steps", {})
                scaler = steps.get("standardscaler")
                estimator = steps.get("mlpregressor")
                model_payload = {
                    "scaler_mean": np.asarray(scaler.mean_, dtype=float).tolist(),
                    "scaler_scale": np.asarray(scaler.scale_, dtype=float).tolist(),
                    "coefs": [
                        np.asarray(value, dtype=float).tolist()
                        for value in estimator.coefs_
                    ],
                    "intercepts": [
                        np.asarray(value, dtype=float).tolist()
                        for value in estimator.intercepts_
                    ],
                    "n_iter": int(estimator.n_iter_),
                }
                if baseline.get("policy") != model_payload:
                    failures.append("holdout payload does not bind fold2 model")
            except Exception as exc:
                failures.append(f"holdout model binding failed: {exc}")
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


def verify_path_metrics(
    ledger: pd.DataFrame,
    holding: pd.DataFrame,
) -> list[str]:
    """Recompute issue-level and aggregate path metrics from primitives."""
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
    if handoff.get("handoff_version") != "bj208-handoff-for-209-v5":
        failures.append("handoff version is not v5")
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
    for _, row in ticket_rows.iterrows():
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
    idx = [int(x) for x in str(match_indices).split("|")]
    out_rank = {"3": 0, "1": 1, "0": 2}
    oidx = [out_rank[o] for o in str(outcomes).split("|")]
    if len(idx) != len(oidx):
        raise VerifyError("ticket leg count mismatch in payout-economics")
    sp = panel.official_sp[np.asarray(idx, dtype=int), np.asarray(oidx, dtype=int)]
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
    receipt["model_weights_scaler_fixed_choice_ood_and_decisions_invariant"] = True
    _json(receipt_path, receipt)


def _rewrite_manifest_for_tamper(package: Path) -> None:
    artifacts = sorted(
        path for path in package.rglob("*")
        if path.is_file() and path.name not in MANIFEST_EXCLUDED
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
    return results


__all__ = [
    "MANIFEST_EXCLUDED", "VerifyError", "manifest", "run_tamper_suite",
    "sha256_file", "tamper_forge_manifest", "tamper_forge_source_trace",
    "tamper_mutate_settlement", "tamper_self_consistent_ledger",
    "tamper_omit_payout_coefficient", "tamper_divide_out_payout",
    "tamper_compound_coefficient", "tamper_handoff_staging_path",
    "tamper_completion_status", "tamper_drop_bundle_ticket",
    "tamper_dynamic_control_semantics", "tamper_empty_schema",
    "tamper_req_evidence",
    "verify_2024_mutation_invariance", "verify_capital_accounting",
    "verify_code_bindings", "verify_completion", "verify_dynamic_control_decisions",
    "verify_chronology",
    "verify_handoff_contract", "verify_handoff_paths",
    "verify_holdout_mutation_receipt", "verify_manifest",
    "verify_nk_semantics", "verify_package_schema", "verify_path_metrics",
    "verify_req_evidence",
    "verify_no_2024_issue", "verify_no_embargoed_split",
    "verify_payout_economics", "verify_provenance", "verify_receipt",
    "verify_schema",
]
