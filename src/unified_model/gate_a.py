"""Immutable, outcome-unexposed Gate-A package builder for Issue #204."""

from __future__ import annotations

from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np
import pandas as pd

from unified_tensor.contract import FEATURE_NAMES
from unified_tensor.inference import TensorContractError, load_issue_tensors

from .contract import (
    CONTRACT_VERSION,
    CV_VALIDATION_YEARS,
    DEVELOPMENT_ISSUE_MAX,
    FALLBACK_RULE,
    MARKET_BASELINE_FEATURE,
    METRICS,
    MODEL_FAMILIES,
    MODEL_FEATURES,
    PROXY_GRADE,
    RESERVE_ISSUE_MIN,
    RETROSPECTIVE_TEST_RANGES,
    SEEDS,
    SOURCE_PACKAGE,
    SP_TARGET,
    UPSTREAM_CONTRACT_VERSION,
)


class GateAError(RuntimeError):
    """Raised if an input boundary or frozen Gate-A output is invalid."""


HISTORY_COLUMNS = (
    "issue", "match_idx", "league", "kickoff_ts", "handicap_line",
    "avg_eu_home", "avg_eu_draw", "avg_eu_away",
)
LABEL_ONLY_QUALITY = (
    # Counts are source-census metadata independently supplied by the PI.  They
    # are deliberately not read from the official settlement source in Gate A.
    {"period": "25043-25125", "history_rows": 11382, "official_3sp_rows": 11314,
     "post_kickoff_updates": 8247},
    {"period": "26011-26049", "history_rows": 5608, "official_3sp_rows": 5539,
     "post_kickoff_updates": 4516},
)


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


def _issue_number(values: pd.Series) -> pd.Series:
    parsed = pd.to_numeric(values.astype(str), errors="raise").astype(int)
    if (parsed <= 0).any():
        raise GateAError("issue identity must be a positive integer")
    return parsed


def _is_test_issue(issue: int) -> bool:
    return any(lower <= issue <= upper for lower, upper in RETROSPECTIVE_TEST_RANGES)


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
    """Verify only the public #203 inference namespace, never labels."""

    if package.name != "bj203_causal_tensor_v2":
        raise GateAError("Gate A only accepts the frozen #203 v2 source package")
    try:
        tensors = load_issue_tensors(package, issues=("190101",))
    except TensorContractError as exc:
        raise GateAError(f"#203 inference verification failed: {exc}") from exc
    if len(tensors) != 1:
        raise GateAError("#203 source sentinel issue is unavailable")
    if set(MODEL_FEATURES).difference(FEATURE_NAMES):
        raise GateAError("frozen model schema requests a non-#203 feature")
    identity = pd.read_parquet(
        package / "inference" / "cell_identity.parquet",
        columns=["issue_instance", "issue", "year", "issue_order",
                 "feature_cutoff_ts_utc", "kickoff_ts_utc"],
    )
    return identity, _package_source_manifest(package)


def _read_history_proxy(history_source: Path) -> pd.DataFrame:
    """Read an explicit allow-list of pre-event proxy columns only.

    The history database contains outcome fields, but this query does not
    select, predicate on, or derive any of them.  It is therefore safe for
    Gate A while honestly grading the retained odds as retrospective proxies.
    """

    if not history_source.is_file():
        raise GateAError(f"history proxy source is absent: {history_source}")
    ranges = " OR ".join(
        f"(CAST(issue AS INTEGER) BETWEEN {lower} AND {upper})"
        for lower, upper in RETROSPECTIVE_TEST_RANGES
    )
    query = (
        "SELECT issue, match_idx, league, kickoff_ts, handicap_line, "
        "avg_eu_home, avg_eu_draw, avg_eu_away FROM historical_matches WHERE " + ranges
    )
    with sqlite3.connect(f"file:{history_source.resolve()}?mode=ro", uri=True) as connection:
        frame = pd.read_sql_query(query, connection)
    if tuple(frame.columns) != HISTORY_COLUMNS:
        raise GateAError("history proxy schema drift")
    frame["issue"] = frame["issue"].astype(str)
    frame["issue_num"] = _issue_number(frame["issue"])
    frame["match_idx"] = pd.to_numeric(frame["match_idx"], errors="raise").astype(int)
    if bool(frame[["issue", "match_idx"]].duplicated().any()):
        raise GateAError("history proxy identities are not unique")
    if not frame["issue_num"].map(_is_test_issue).all():
        raise GateAError("history proxy escaped frozen test ranges")
    return frame.sort_values(["issue_num", "match_idx"], kind="mergesort").reset_index(drop=True)


def _proxy_panel(history: pd.DataFrame) -> pd.DataFrame:
    values = history.loc[:, list(HISTORY_COLUMNS)].copy()
    odds = values[["avg_eu_home", "avg_eu_draw", "avg_eu_away"]].apply(
        pd.to_numeric, errors="coerce"
    )
    inverse = 1.0 / odds
    complete = odds.gt(0).all(axis=1) & np.isfinite(inverse).all(axis=1)
    normalizer = inverse.sum(axis=1)
    probabilities = inverse.div(normalizer.where(complete), axis=0)
    values["source_grade"] = PROXY_GRADE
    values["market_proxy_complete"] = complete.astype(bool)
    values["baseline_proxy_eligible"] = complete.astype(bool)
    values["model_proxy_eligible"] = complete.astype(bool)
    values["fallback_no_bet"] = (~complete).astype(bool)
    values["proxy_probability_3"] = probabilities.iloc[:, 0]
    values["proxy_probability_1"] = probabilities.iloc[:, 1]
    values["proxy_probability_0"] = probabilities.iloc[:, 2]
    values["target_available_gate_a"] = False
    values["target_quality_mask"] = SP_TARGET["quality_mask"]
    return values


def _issue_reconciliation(identity: pd.DataFrame, history: pd.DataFrame, proxy: pd.DataFrame) -> pd.DataFrame:
    """Publish source identity and missing-source reasons for every frozen issue."""

    inference = identity.copy()
    inference["issue"] = inference["issue"].astype(str)
    inference["issue_num"] = _issue_number(inference["issue"])
    inference_counts = inference.groupby("issue", sort=True).size().rename("inference_cell_rows")
    history_counts = history.groupby("issue", sort=True).size().rename("history_rows")
    proxy_counts = proxy.groupby("issue", sort=True)["market_proxy_complete"].sum().rename("complete_proxy_rows")
    issues = sorted(set(history_counts.index) | set(
        inference.loc[inference["issue_num"].le(DEVELOPMENT_ISSUE_MAX), "issue"].unique()
    ), key=int)
    rows: list[dict[str, Any]] = []
    for issue in issues:
        issue_num = int(issue)
        historical = int(history_counts.get(issue, 0))
        if issue_num <= DEVELOPMENT_ISSUE_MAX:
            role = "DEVELOPMENT_CV"
            source_status = "UPSTREAM_203_INFERENCE"
            missing_reason = ""
        elif _is_test_issue(issue_num):
            role = "RETROSPECTIVE_TEST_LOCKED"
            source_status = "RETROSPECTIVE_PROXY_HISTORY"
            if issue_num <= 25125:
                missing_reason = "UPSTREAM_203_INFERENCE_ABSENT; HISTORY_PROXY_ONLY"
            else:
                missing_reason = "RETROSPECTIVE_PROXY_REQUIRED; INFERENCE_AUXILIARY_ONLY"
        else:  # Defensive; the issue union above must not produce this branch.
            raise GateAError(f"reconciliation issue outside frozen boundary: {issue}")
        rows.append({
            "issue": issue,
            "role": role,
            "history_rows": historical,
            "complete_proxy_rows": int(proxy_counts.get(issue, 0)),
            "inference_cell_rows": int(inference_counts.get(issue, 0)),
            "source_status": source_status,
            "missing_reason": missing_reason,
            "labels_opened": False,
            "target_quality_mask": SP_TARGET["quality_mask"],
        })
    result = pd.DataFrame(rows)
    if int(result.loc[result["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "history_rows"].sum()) != 16990:
        raise GateAError("frozen 75-issue retrospective history census drift")
    if int(result["role"].eq("RETROSPECTIVE_TEST_LOCKED").sum()) != 75:
        raise GateAError("frozen retrospective issue census drift")
    return result


def _split_rows(identity: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    inference = identity.copy()
    inference["issue"] = inference["issue"].astype(str)
    inference["issue_num"] = _issue_number(inference["issue"])
    development = inference.loc[inference["issue_num"].le(DEVELOPMENT_ISSUE_MAX)].copy()
    matches = (
        development.loc[:, ["issue_instance", "issue", "year", "issue_order",
                            "feature_cutoff_ts_utc", "kickoff_ts_utc"]]
        .drop_duplicates("issue_instance")
        .sort_values(["issue_order", "issue_instance"], kind="mergesort")
        .reset_index(drop=True)
    )
    if not matches["issue_instance"].is_unique:
        raise GateAError("#203 issue identity is not unique")
    matches["role"] = "DEVELOPMENT_CV"
    matches["labels_permitted_gate_a"] = False
    matches["labels_permitted_gate_b"] = False
    matches["feature_namespace"] = "outcome_unexposed_inference"
    test = (
        history[["issue", "issue_num", "kickoff_ts"]].drop_duplicates("issue")
        .sort_values("issue_num", kind="mergesort")
        .reset_index(drop=True)
    )
    test_rows = pd.DataFrame({
        "issue_instance": "RETROSPECTIVE_PROXY_" + test["issue"].astype(str),
        "issue": test["issue"].astype(str),
        "year": pd.to_datetime(test["kickoff_ts"], errors="coerce", utc=True).dt.year.astype("Int64"),
        "issue_order": np.arange(len(matches), len(matches) + len(test), dtype=int),
        "feature_cutoff_ts_utc": pd.NA,
        "kickoff_ts_utc": test["kickoff_ts"],
        "role": "RETROSPECTIVE_TEST_LOCKED",
        "labels_permitted_gate_a": False,
        "labels_permitted_gate_b": True,
        "feature_namespace": "retrospective_proxy_outcome_unexposed",
    })
    result = pd.concat([matches, test_rows], ignore_index=True)
    if not result["labels_permitted_gate_a"].eq(False).all():
        raise GateAError("Gate A split leaks labels")
    return result


def _cv_manifest(splits: pd.DataFrame) -> pd.DataFrame:
    development = splits.loc[splits["role"].eq("DEVELOPMENT_CV")].copy()
    years = sorted(pd.to_numeric(development["year"], errors="raise").astype(int).unique())
    rows: list[dict[str, Any]] = []
    for validation_year in CV_VALIDATION_YEARS:
        train_years = [year for year in years if year < validation_year]
        if len(train_years) < 2 or validation_year not in years:
            continue
        rows.append({
            "fold_id": f"EXPANDING_OOS_{validation_year}",
            "train_years": ";".join(map(str, train_years)),
            "validation_year": validation_year,
            "test_issue_boundary": "25043-26049",
            "test_labels_opened": False,
            "selection_rule": "select only from development expanding folds through issue 25042",
        })
    if not rows:
        raise GateAError("no valid development expanding folds")
    return pd.DataFrame(rows)


def _environment() -> dict[str, str]:
    packages = ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "matplotlib")
    return {package: importlib.metadata.version(package) for package in packages}


def _coverage(proxy: pd.DataFrame) -> pd.DataFrame:
    proxy = proxy.copy()
    issue_num = _issue_number(proxy["issue"])
    period = np.where(issue_num.le(25125), "25043-25125", "26011-26049")
    proxy["period"] = period
    result = (
        proxy.groupby("period", sort=True)
        .agg(
            issues=("issue", "nunique"),
            rows=("issue", "size"),
            baseline_proxy_rows=("baseline_proxy_eligible", "sum"),
            model_proxy_rows=("model_proxy_eligible", "sum"),
            fallback_no_bet_rows=("fallback_no_bet", "sum"),
        )
        .reset_index()
    )
    for prefix in ("baseline_proxy", "model_proxy", "fallback_no_bet"):
        result[f"{prefix}_coverage"] = result[f"{prefix}_rows"] / result["rows"]
    result["source_grade"] = PROXY_GRADE
    result["labels_opened"] = False
    return result


def _build_card(
    source: Path,
    source_manifest: dict[str, Any],
    history_source: Path,
    splits: pd.DataFrame,
    reconciliation: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, Any]:
    development = splits.loc[splits["role"].eq("DEVELOPMENT_CV")]
    test = splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED")]
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
            "history_proxy_source": "data/beidan_history.db",
            "history_proxy_sha256": digest(history_source),
            "history_proxy_columns_allowlist": list(HISTORY_COLUMNS),
            "labels_opened": False,
        },
        "chronology": {
            "development_cv_through_issue": DEVELOPMENT_ISSUE_MAX,
            "retrospective_test_issue_ranges": [list(item) for item in RETROSPECTIVE_TEST_RANGES],
            "reserve_for_210_from_issue": RESERVE_ISSUE_MIN,
            "development_issue_count": int(development["issue"].nunique()),
            "retrospective_test_issue_count": int(test["issue"].nunique()),
            "retrospective_test_history_rows": int(reconciliation.loc[
                reconciliation["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "history_rows"
            ].sum()),
            "cv_validation_years": list(CV_VALIDATION_YEARS),
        },
        "schema": {
            "ragged_shape": "X_i[J_i,3,F]",
            "outcome_axis": ["3", "1", "0"],
            "model_features": list(MODEL_FEATURES),
            "mask_features": list(MODEL_FEATURES),
            "market_baseline_feature": MARKET_BASELINE_FEATURE,
            "predicted_final_sp_semantics": "outcome-unexposed pre-event proxy input only",
            "sp_target": SP_TARGET,
        },
        "proxy_panel": {
            "grade": PROXY_GRADE,
            "coverage_file": "proxy_coverage_by_period.csv",
            "panel_file": "retrospective_proxy_panel.csv",
            "baseline_model_fallback_coverage": coverage.to_dict(orient="records"),
            "limitation": "retrospective proxy only; no source timestamp proves a live pre-event capture",
        },
        "target_only_quality": {
            "file": "target_only_quality_mask.csv",
            "rows": list(LABEL_ONLY_QUALITY),
            "rule": "official final-SP values and update timestamps are never read in Gate A",
        },
        "models": list(MODEL_FAMILIES),
        "fallback": FALLBACK_RULE,
        "metrics": list(METRICS),
        "seeds": list(SEEDS),
        "environment": _environment(),
        "test_opening_rule": "The 25043-26049 target namespace may be opened exactly once only by a Gate-B runner after PI accepts this exact package unchanged.",
        "promotion_authorized": False,
        "scope": "Historical exploratory PoC only; no ticket, ROI, betting, release, production, #205, or #210 action.",
    }


def _readme(card: dict[str, Any]) -> str:
    chronology = card["chronology"]
    return f"""# #204 Gate A v2 — market-anchored residual model preregistration

This immutable package is **outcome-unexposed**.  It uses the #203 inference
namespace only for development/CV through issue `{chronology['development_cv_through_issue']}`.
The one-shot retrospective window is `25043–25125` plus `26011–26049`; it is
represented by a clearly graded `{PROXY_GRADE}` market panel.  Issues `26051+`
remain reserved for #210.

`predicted_final_sp` is a pre-event proxy input, not a target.  The supervised
SP target is the official 3/1/0 final-SP vector under
`{SP_TARGET['quality_mask']}` and is not opened here.  The target-only census
records the known post-kickoff update prevalence precisely to prevent a
retrospective proxy from being misrepresented as a live capture.

The hard action gate is `{FALLBACK_RULE['rule_id']}`: an incomplete/nonfinite
proxy row uses a valid frozen market vector if one exists; otherwise it is
`NO_BET_FROZEN`.  Gate B requires PI acceptance of this exact package.
"""


def _replay_markdown() -> str:
    return """# Deterministic Gate-A v2 replay

Run from the repository root with the pinned existing environment.  The
history source is read-only and queried with the documented eight-column
pre-event allow-list; no official-SP or result field is selected.

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py verify \\
  --package results/bj204_gate_a_preoutcome_v2

PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py freeze \\
  --source results/bj203_causal_tensor_v2 \\
  --history-source data/beidan_history.db --output <new-empty-directory>

PYTHONPATH=src $PY scripts/execute_bj204_notebook.py
```

The package and notebook never import `unified_tensor.settlement_labels` and
never read target values, target timestamps, results, or winning SP.
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


def build_package(
    output: str | Path, *, source_package: str | Path, history_source: str | Path
) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise GateAError(f"refusing to replace output package: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source_package).resolve()
    history_path = Path(history_source).resolve()
    identity, source_manifest = _validate_source(source)
    history = _read_history_proxy(history_path)
    proxy = _proxy_panel(history)
    reconciliation = _issue_reconciliation(identity, history, proxy)
    splits = _split_rows(identity, history)
    cv = _cv_manifest(splits)
    coverage = _coverage(proxy)
    card = _build_card(source, source_manifest, history_path, splits, reconciliation, coverage)
    write_csv(output / "split_manifest.csv", splits)
    write_csv(output / "cv_manifest.csv", cv)
    write_csv(output / "identity_reconciliation.csv", reconciliation)
    write_csv(output / "retrospective_proxy_panel.csv", proxy)
    write_csv(output / "proxy_coverage_by_period.csv", coverage)
    write_csv(output / "target_only_quality_mask.csv", pd.DataFrame(LABEL_ONLY_QUALITY))
    write_json(output / "freeze_card.json", card)
    write_json(output / "inference_schema.json", card["schema"])
    write_json(output / "model_config.json", {
        "contract_version": CONTRACT_VERSION,
        "models": card["models"], "fallback": card["fallback"],
        "metrics": card["metrics"], "seeds": card["seeds"],
        "environment": card["environment"],
    })
    write_json(output / "source_binding.json", card["source"])
    (output / "README.md").write_text(_readme(card), encoding="utf-8", newline="\n")
    (output / "REPLAY.md").write_text(_replay_markdown(), encoding="utf-8", newline="\n")
    files = _write_manifest(output)
    return {
        "contract_version": CONTRACT_VERSION, "package": output.name, "files": len(files),
        "development_issues": int(splits.loc[splits["role"].eq("DEVELOPMENT_CV"), "issue"].nunique()),
        "retrospective_test_issues": int(splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "issue"].nunique()),
        "reserve_from_issue": RESERVE_ISSUE_MIN,
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
    if not splits["labels_permitted_gate_a"].astype(str).str.lower().eq("false").all():
        raise GateAError("Gate-A split manifest permits labels")
    test = splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED")]
    if test["issue"].nunique() != 75 or not test["issue"].astype(int).map(_is_test_issue).all():
        raise GateAError("retrospective test chronology drift")
    reconciliation = pd.read_csv(root / "identity_reconciliation.csv", dtype={"issue": str})
    test_reconciliation = reconciliation.loc[reconciliation["role"].eq("RETROSPECTIVE_TEST_LOCKED")]
    if len(test_reconciliation) != 75 or int(test_reconciliation["history_rows"].sum()) != 16990:
        raise GateAError("retrospective source reconciliation drift")
    quality = pd.read_csv(root / "target_only_quality_mask.csv")
    if quality["official_3sp_rows"].tolist() != [11314, 5539]:
        raise GateAError("target-only official-SP census drift")
    return {"contract_version": CONTRACT_VERSION, "files": len(actual), "status": "PASS"}
