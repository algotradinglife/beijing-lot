"""Immutable, outcome-unexposed Gate-A package builder for Issue #204."""

from __future__ import annotations

from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import pandas as pd

from unified_tensor.contract import FEATURE_NAMES
from unified_tensor.inference import TensorContractError, load_issue_tensors

from .contract import (
    CONTRACT_VERSION,
    CV_VALIDATION_YEARS,
    DEVELOPMENT_YEARS,
    EMBARGO_START_YEAR,
    FALLBACK_RULE,
    MARKET_BASELINE_FEATURE,
    METRICS,
    MODEL_FAMILIES,
    MODEL_FEATURES,
    RETROSPECTIVE_TEST_YEAR,
    SEEDS,
    SOURCE_PACKAGE,
    UPSTREAM_CONTRACT_VERSION,
)


class GateAError(RuntimeError):
    """Raised if an input boundary or frozen Gate-A output is invalid."""


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8", newline="\n")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _package_source_manifest(package: Path) -> dict[str, Any]:
    manifest_path = package / "SHA256SUMS.json"
    if not manifest_path.is_file():
        raise GateAError("#203 source package SHA256SUMS.json is absent")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise GateAError("#203 source manifest is not JSON") from exc
    if not isinstance(manifest, dict):
        raise GateAError("#203 source manifest is invalid")
    return manifest


def _validate_source(package: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Verify #203 inference through its public outcome-unexposed loader."""

    if package.name != "bj203_causal_tensor_v2":
        raise GateAError("Gate A only accepts the frozen #203 v2 source package")
    try:
        # This validates the complete inference manifest without importing the
        # label loader.  One issue keeps the bounded Gate-A validation small.
        tensors = load_issue_tensors(package, issues=("190101",))
    except TensorContractError as exc:
        raise GateAError(f"#203 inference verification failed: {exc}") from exc
    if len(tensors) != 1:
        raise GateAError("#203 source sentinel issue is unavailable")
    inference = package / "inference"
    identity = pd.read_parquet(inference / "cell_identity.parquet")
    if set(MODEL_FEATURES).difference(FEATURE_NAMES):
        raise GateAError("frozen model schema requests a non-#203 feature")
    return identity, _package_source_manifest(package)


def _split_rows(identity: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "issue_instance", "issue", "year", "issue_order",
        "feature_cutoff_ts_utc", "kickoff_ts_utc", "split",
    ]
    matches = (
        identity.loc[:, columns]
        .drop_duplicates("issue_instance")
        .sort_values(["year", "issue_order", "issue_instance"], kind="mergesort")
        .reset_index(drop=True)
    )
    matches["year"] = pd.to_numeric(matches["year"], errors="raise").astype(int)
    if not matches["issue_instance"].is_unique:
        raise GateAError("#203 issue identity is not unique")

    def role(year: int) -> str:
        if year in DEVELOPMENT_YEARS:
            return "DEVELOPMENT"
        if year == RETROSPECTIVE_TEST_YEAR:
            return "RETROSPECTIVE_TEST_LOCKED"
        if year >= EMBARGO_START_YEAR:
            return "EMBARGOED_FOR_210"
        raise GateAError(f"unexpected source year {year}")

    matches["role"] = matches["year"].map(role)
    matches["labels_permitted_gate_a"] = False
    matches["labels_permitted_gate_b"] = matches["role"].eq("RETROSPECTIVE_TEST_LOCKED")
    matches["feature_namespace"] = "outcome_unexposed_inference"
    return matches


def _cv_manifest(splits: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for validation_year in CV_VALIDATION_YEARS:
        train_years = [year for year in DEVELOPMENT_YEARS if year < validation_year]
        if len(train_years) < 2:
            raise GateAError("expanding CV requires at least two prior years")
        rows.append({
            "fold_id": f"EXPANDING_OOS_{validation_year}",
            "train_years": ";".join(map(str, train_years)),
            "validation_year": validation_year,
            "test_year": RETROSPECTIVE_TEST_YEAR,
            "test_labels_opened": False,
            "selection_rule": "select only from development expanding folds",
        })
    return pd.DataFrame(rows)


def _environment() -> dict[str, str]:
    packages = ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "matplotlib")
    return {
        package: importlib.metadata.version(package)
        for package in packages
    }


def _build_card(source: Path, source_manifest: dict[str, Any], splits: pd.DataFrame) -> dict[str, Any]:
    development = splits.loc[splits["role"].eq("DEVELOPMENT")]
    test = splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED")]
    embargoed = splits.loc[splits["role"].eq("EMBARGOED_FOR_210")]
    return {
        "issue": 204,
        "stage": "GATE_A_OUTCOME_UNEXPOSED_PREREGISTRATION",
        "contract_version": CONTRACT_VERSION,
        "source": {
            "package": SOURCE_PACKAGE,
            "package_sha256s": digest(source / "SHA256SUMS.json"),
            "inference_manifest_sha256": digest(source / "inference" / "MANIFEST.json"),
            "source_manifest_files": len(source_manifest),
            "source_contract": UPSTREAM_CONTRACT_VERSION,
            "labels_opened": False,
        },
        "chronology": {
            "development_years": list(DEVELOPMENT_YEARS),
            "retrospective_test_year": RETROSPECTIVE_TEST_YEAR,
            "test_boundary": "2024-01-01 through the exact issue preceding #203's 2025-04 embargo",
            "embargoed_start_year": EMBARGO_START_YEAR,
            "embargoed_issue_count": int(len(embargoed)),
            "development_issue_count": int(len(development)),
            "retrospective_test_issue_count": int(len(test)),
            "cv_validation_years": list(CV_VALIDATION_YEARS),
        },
        "schema": {
            "ragged_shape": "X_i[J_i,3,F]",
            "outcome_axis": ["3", "1", "0"],
            "model_features": list(MODEL_FEATURES),
            "mask_features": list(MODEL_FEATURES),
            "market_baseline_feature": MARKET_BASELINE_FEATURE,
            "sp_target": "pre-event predicted_final_sp only; no observed/final SP feature",
        },
        "models": list(MODEL_FAMILIES),
        "fallback": FALLBACK_RULE,
        "metrics": list(METRICS),
        "seeds": list(SEEDS),
        "environment": _environment(),
        "test_opening_rule": "The 2024 label namespace may be opened exactly once only by a Gate-B runner after this Gate-A package is accepted unchanged.",
        "promotion_authorized": False,
        "scope": "Historical exploratory PoC only; no ticket, ROI, betting, release, production, #205, or #210 action.",
    }


def _readme(card: dict[str, Any]) -> str:
    chronology = card["chronology"]
    return f"""# #204 Gate A — market-anchored residual model preregistration

This is an immutable **outcome-unexposed** Track-A contract.  It verifies and
uses only the #203 inference namespace.  It does not import, open, copy or
emit development or retrospective settlement labels.

* Development: {chronology['development_years']}
* Frozen one-shot retrospective test: {chronology['retrospective_test_year']}
* Embargoed for #210: {chronology['embargoed_start_year']} onward
* Candidate models: market-only, logistic residual, shallow gradient residual,
  then a set-context residual only if the controls justify it.

The hard action gate is `{FALLBACK_RULE['rule_id']}`: an incomplete, nonfinite,
out-of-distribution or failed-calibration row reproduces the frozen market
baseline where it is valid, otherwise it is `NO_BET_FROZEN`.

No historical result authorizes betting, production, release or downstream
#205 work.  Gate B requires PI acceptance of this exact package.
"""


def _replay_markdown() -> str:
    return """# Deterministic Gate-A replay

Run from the repository root with the pinned existing environment:

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py verify \\
  --package results/bj204_gate_a_preoutcome_v1
PYTHONPATH=src $PY scripts/execute_bj204_notebook.py

# Detached rebuild: use a new, empty directory.
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py freeze \\
  --source results/bj203_causal_tensor_v2 --output <new-empty-directory>
```

The Gate-A builder validates only #203's `inference/` namespace.  It never
imports `unified_tensor.settlement_labels` and never opens 2024 test labels.
"""


def _write_manifest(output: Path) -> dict[str, str]:
    files = {
        path.relative_to(output).as_posix(): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}
    }
    write_json(output / "SHA256SUMS.json", files)
    content = sha256(canonical_json(files).encode("utf-8")).hexdigest()
    write_json(output / "CONTENT_IDENTITY.json", {"sha256": content})
    return files


def build_package(output: str | Path, *, source_package: str | Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise GateAError(f"refusing to replace output package: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source_package).resolve()
    identity, source_manifest = _validate_source(source)
    splits = _split_rows(identity)
    cv = _cv_manifest(splits)
    card = _build_card(source, source_manifest, splits)
    write_csv(output / "split_manifest.csv", splits)
    write_csv(output / "cv_manifest.csv", cv)
    write_json(output / "freeze_card.json", card)
    write_json(output / "inference_schema.json", card["schema"])
    write_json(output / "model_config.json", {
        "contract_version": CONTRACT_VERSION,
        "models": card["models"],
        "fallback": card["fallback"],
        "metrics": card["metrics"],
        "seeds": card["seeds"],
        "environment": card["environment"],
    })
    write_json(output / "source_binding.json", card["source"])
    (output / "README.md").write_text(_readme(card), encoding="utf-8", newline="\n")
    (output / "REPLAY.md").write_text(_replay_markdown(), encoding="utf-8", newline="\n")
    files = _write_manifest(output)
    return {
        "contract_version": CONTRACT_VERSION,
        "package": output.name,
        "files": len(files),
        "development_issues": int(splits["role"].eq("DEVELOPMENT").sum()),
        "retrospective_test_issues": int(splits["role"].eq("RETROSPECTIVE_TEST_LOCKED").sum()),
        "embargoed_issues": int(splits["role"].eq("EMBARGOED_FOR_210").sum()),
        "status": "GATE_A_OUTCOME_UNEXPOSED_PASS",
    }


def verify_package(package: str | Path) -> dict[str, Any]:
    root = Path(package)
    try:
        card = json.loads((root / "freeze_card.json").read_text(encoding="utf-8"))
        sums = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))
        content = json.loads((root / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateAError("Gate-A package metadata is invalid") from exc
    if card.get("contract_version") != CONTRACT_VERSION:
        raise GateAError("Gate-A contract version drift")
    if card.get("source", {}).get("labels_opened") is not False:
        raise GateAError("Gate-A must not open labels")
    actual = {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}
    }
    if actual != sums:
        raise GateAError("Gate-A payload manifest mismatch")
    if content != {"sha256": sha256(canonical_json(sums).encode("utf-8")).hexdigest()}:
        raise GateAError("Gate-A content identity mismatch")
    splits = pd.read_csv(root / "split_manifest.csv", dtype={"issue": str})
    if bool(
        splits["labels_permitted_gate_a"].astype(str).str.lower().eq("true").any()
    ):
        raise GateAError("Gate-A split manifest permits labels")
    if set(splits.loc[splits["role"].eq("DEVELOPMENT"), "year"].astype(int)) != set(DEVELOPMENT_YEARS):
        raise GateAError("development chronology drift")
    if set(splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "year"].astype(int)) != {RETROSPECTIVE_TEST_YEAR}:
        raise GateAError("retrospective test chronology drift")
    if not bool(splits.loc[splits["role"].eq("EMBARGOED_FOR_210"), "year"].astype(int).ge(EMBARGO_START_YEAR).all()):
        raise GateAError("embargo chronology drift")
    return {"contract_version": CONTRACT_VERSION, "files": len(actual), "status": "PASS"}
