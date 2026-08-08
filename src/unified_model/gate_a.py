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
FULL_3SP_IDENTITY_COLUMNS = ("expect", "match_no", "match_uid")
PCLOSE_COLUMNS = (
    "match_id", "issue", "p_close_3", "p_close_1", "p_close_0", "beidan_hcap",
)
BRIDGE_ISSUE_RANGE = (24011, 25042)
BRIDGE_OUTLIER_MAX_ABS_DELTA = 0.10
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
    if "predicted_final_sp" not in FEATURE_NAMES:
        raise GateAError("#203 source lacks the declared pre-event SP input")
    identity = pd.read_parquet(
        package / "inference" / "cell_identity.parquet",
        columns=["cell_join_key", "issue_instance", "issue", "year", "issue_order",
                 "match_id", "match_idx", "outcome_code", "feature_cutoff_ts_utc", "kickoff_ts_utc"],
    )
    return identity, _package_source_manifest(package)


def _read_history_rows(history_source: Path, ranges: tuple[tuple[int, int], ...]) -> pd.DataFrame:
    """Read an explicit allow-list of pre-event proxy columns only.

    The history database contains outcome fields, but this query does not
    select, predicate on, or derive any of them.  It is therefore safe for
    Gate A while honestly grading the retained odds as retrospective proxies.
    """

    if not history_source.is_file():
        raise GateAError(f"history proxy source is absent: {history_source}")
    if history_source.suffix.lower() == ".csv":
        frame = pd.read_csv(history_source, usecols=list(HISTORY_COLUMNS))
        issue_numbers = pd.to_numeric(frame["issue"], errors="raise")
        allowed = np.zeros(len(frame), dtype=bool)
        for lower, upper in ranges:
            allowed |= issue_numbers.between(lower, upper).to_numpy()
        frame = frame.loc[allowed].copy()
    else:
        where = " OR ".join(
            f"(CAST(issue AS INTEGER) BETWEEN {lower} AND {upper})"
            for lower, upper in ranges
        )
        query = (
            "SELECT issue, match_idx, league, kickoff_ts, handicap_line, "
            "avg_eu_home, avg_eu_draw, avg_eu_away FROM historical_matches WHERE " + where
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
    return frame.sort_values(["issue_num", "match_idx"], kind="mergesort").reset_index(drop=True)


def _read_history_proxy(history_source: Path) -> pd.DataFrame:
    history = _read_history_rows(history_source, RETROSPECTIVE_TEST_RANGES)
    if not history["issue_num"].map(_is_test_issue).all():
        raise GateAError("history proxy escaped frozen test ranges")
    return history


def _read_full_3sp_identity(full_3sp_source: Path) -> pd.DataFrame:
    """Read only the official-source identity namespace, never targets."""

    if not full_3sp_source.is_file():
        raise GateAError(f"full-3SP identity source is absent: {full_3sp_source}")
    frame = pd.read_csv(full_3sp_source, usecols=list(FULL_3SP_IDENTITY_COLUMNS))
    if tuple(frame.columns) != FULL_3SP_IDENTITY_COLUMNS:
        raise GateAError("full-3SP identity schema drift")
    frame["expect"] = frame["expect"].astype(str)
    frame["match_no"] = pd.to_numeric(frame["match_no"], errors="raise").astype(int)
    frame["match_uid"] = pd.to_numeric(frame["match_uid"], errors="raise").astype("Int64")
    frame["issue_num"] = _issue_number(frame["expect"])
    if bool(frame[["expect", "match_no"]].duplicated().any()):
        raise GateAError("full-3SP identity keys are not unique")
    return frame


def _read_pclose_proxy(
    pclose_source: Path, issue_range: tuple[int, int] | None = None, *, allow_duplicate_match_id: bool = False,
) -> pd.DataFrame:
    """Read only pre-event market-reference fields from the frozen bridge source."""

    if not pclose_source.is_file():
        raise GateAError(f"p_close bridge source is absent: {pclose_source}")
    if pclose_source.suffix.lower() == ".csv":
        frame = pd.read_csv(pclose_source, usecols=list(PCLOSE_COLUMNS))
        if issue_range is not None:
            issue_numbers = pd.to_numeric(frame["issue"], errors="raise")
            frame = frame.loc[issue_numbers.between(*issue_range)].copy()
    else:
        query = "SELECT match_id, issue, p_close_3, p_close_1, p_close_0, beidan_hcap FROM matches"
        params: tuple[int, int] = ()
        if issue_range is not None:
            query += " WHERE CAST(issue AS INTEGER) BETWEEN ? AND ?"
            params = issue_range
        with sqlite3.connect(f"file:{pclose_source.resolve()}?mode=ro", uri=True) as connection:
            frame = pd.read_sql_query(query, connection, params=params)
    if tuple(frame.columns) != PCLOSE_COLUMNS:
        raise GateAError("p_close bridge schema drift")
    frame["match_id"] = frame["match_id"].astype(str)
    frame["issue"] = frame["issue"].astype(str)
    if not allow_duplicate_match_id and bool(frame["match_id"].duplicated().any()):
        raise GateAError("p_close match_uid bridge is not unique")
    return frame


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


def _test_identity_reconciliation(history: pd.DataFrame, full_3sp_identity: pd.DataFrame) -> pd.DataFrame:
    """Freeze test-set alignment using identifiers only, never target values."""

    target = full_3sp_identity.loc[
        full_3sp_identity["issue_num"].map(_is_test_issue),
        ["expect", "match_no", "match_uid"],
    ].copy()
    result = history[["issue", "match_idx"]].merge(
        target,
        left_on=["issue", "match_idx"], right_on=["expect", "match_no"],
        how="left", validate="one_to_one",
    )
    result["official_target_identity_available"] = result["match_uid"].notna()
    result["target_identity_reason"] = np.where(
        result["official_target_identity_available"],
        "MATCHED_OFFICIAL_3SP_TARGET_NOT_OPENED",
        "HISTORY_ONLY_NO_OFFICIAL_3SP_TARGET",
    )
    result["labels_opened"] = False
    result["target_quality_mask"] = SP_TARGET["quality_mask"]
    result = result.drop(columns=["expect", "match_no"])
    if len(result) != 16990:
        raise GateAError("test identity reconciliation history census drift")
    if int(result["official_target_identity_available"].sum()) != 16853:
        raise GateAError("test identity reconciliation target census drift")
    return result.sort_values(["issue", "match_idx"], key=lambda s: _issue_number(s) if s.name == "issue" else s,
                              kind="mergesort").reset_index(drop=True)


def _market_bridge(
    history_source: Path, full_3sp_identity: pd.DataFrame, pclose_source: Path
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Freeze the source bridge without reading settlement columns.

    ``match_uid`` is obtained from the CSV's identity-only projection and is
    used to join the historical average-EU source to the pre-event p_close
    source.  Team/league names are never used as join keys.
    """

    history = _read_history_rows(history_source, (BRIDGE_ISSUE_RANGE,))
    target = full_3sp_identity.loc[
        full_3sp_identity["issue_num"].between(*BRIDGE_ISSUE_RANGE),
        ["expect", "match_no", "match_uid"],
    ]
    joined = history.merge(
        target, left_on=["issue", "match_idx"], right_on=["expect", "match_no"],
        how="left", validate="one_to_one",
    )
    joined = joined.loc[joined["match_uid"].notna()].copy()
    joined["match_uid"] = joined["match_uid"].astype(int).astype(str)
    pclose = _read_pclose_proxy(pclose_source, BRIDGE_ISSUE_RANGE)
    joined = joined.merge(
        pclose, left_on="match_uid", right_on="match_id", how="left",
        validate="one_to_one", suffixes=("", "_pclose"),
    )
    odds = joined[["avg_eu_home", "avg_eu_draw", "avg_eu_away"]].apply(pd.to_numeric, errors="coerce")
    inverse = 1.0 / odds
    historical_complete = odds.gt(0).all(axis=1) & np.isfinite(inverse).all(axis=1)
    normalized = inverse.div(inverse.sum(axis=1).where(historical_complete), axis=0)
    pclose_values = joined[["p_close_3", "p_close_1", "p_close_0"]].apply(pd.to_numeric, errors="coerce")
    pclose_complete = pclose_values.notna().all(axis=1) & np.isfinite(pclose_values).all(axis=1)
    comparable = historical_complete & pclose_complete
    bridge = pd.DataFrame({
        "issue": joined["issue"].astype(str), "match_idx": joined["match_idx"].astype(int),
        "match_uid": joined["match_uid"], "history_source_grade": PROXY_GRADE,
        "p_close_source_grade": "RETROSPECTIVE_PROXY_REFERENCE",
        "market_probability_3": normalized.iloc[:, 0],
        "market_probability_1": normalized.iloc[:, 1],
        "market_probability_0": normalized.iloc[:, 2],
        "p_close_3": pclose_values.iloc[:, 0], "p_close_1": pclose_values.iloc[:, 1],
        "p_close_0": pclose_values.iloc[:, 2],
        "handicap_line_history": joined["handicap_line"],
        "handicap_line_p_close": joined["beidan_hcap"],
        "historical_market_complete": historical_complete,
        "p_close_complete": pclose_complete,
    })
    deltas = np.abs(
        bridge[["market_probability_3", "market_probability_1", "market_probability_0"]].to_numpy()
        - bridge[["p_close_3", "p_close_1", "p_close_0"]].to_numpy()
    )
    bridge["max_abs_probability_delta"] = np.where(comparable, deltas.max(axis=1), np.nan)
    bridge["bridge_outlier_gt_005"] = bridge["max_abs_probability_delta"].gt(0.05)
    bridge["bridge_outlier_gt_010"] = bridge["max_abs_probability_delta"].gt(BRIDGE_OUTLIER_MAX_ABS_DELTA)
    bridge["bridge_fallback_reason"] = np.select(
        [~bridge["historical_market_complete"], ~bridge["p_close_complete"], bridge["bridge_outlier_gt_010"]],
        ["NO_BET_FROZEN_HISTORY_MARKET_MISSING", "HISTORY_PROXY_ONLY_PCLOSE_REFERENCE_MISSING",
         "HISTORY_PROXY_RETAINED_PCLOSE_NOT_SUBSTITUTED_OUTLIER"],
        default="BRIDGE_COMPARABLE",
    )
    observed = bridge.loc[comparable]
    if len(observed) != 20837:
        raise GateAError("market bridge complete-support census drift")
    correlations = [float(np.corrcoef(
        observed[f"market_probability_{code}"], observed[f"p_close_{code}"]
    )[0, 1]) for code in ("3", "1", "0")]
    summary = {
        "issue_range": list(BRIDGE_ISSUE_RANGE),
        "join_key": "history.issue+history.match_idx -> official_identity.expect+match_no -> match_uid -> p_close.match_id",
        "history_rows": int(len(history)),
        "official_identity_matched_rows": int(len(joined)),
        "history_without_official_identity_rows": int(len(history) - len(joined)),
        "p_close_match_rows": int(bridge["p_close_complete"].sum()),
        "complete_comparable_rows": int(len(observed)),
        "mean_absolute_error": float(np.abs(
            observed[["market_probability_3", "market_probability_1", "market_probability_0"]].to_numpy()
            - observed[["p_close_3", "p_close_1", "p_close_0"]].to_numpy()
        ).mean()),
        "outcome_correlations": dict(zip(("3", "1", "0"), correlations, strict=True)),
        "max_delta_gt_005_rows": int(observed["bridge_outlier_gt_005"].sum()),
        "max_delta_gt_010_rows": int(observed["bridge_outlier_gt_010"].sum()),
        "handicap_exact_rows": int((
            observed["handicap_line_history"] == observed["handicap_line_p_close"]
        ).sum()),
        "labels_opened": False,
        "outlier_policy": "do not substitute p_close; retain normalized average-EU proxy with explicit source grade",
        "missing_policy": "missing history triplet -> NO_BET_FROZEN; missing p_close reference -> history-proxy-only grade",
    }
    return bridge.sort_values(["issue", "match_idx"], key=lambda s: _issue_number(s) if s.name == "issue" else s,
                               kind="mergesort").reset_index(drop=True), summary


COMMON_FEATURES = MODEL_FEATURES


def _development_registry(identity: pd.DataFrame, *, strict_census: bool = True) -> pd.DataFrame:
    """Select the frozen chronological registry; never compare raw issue ids."""

    matches = identity.drop_duplicates(["issue_instance", "match_id", "match_idx"]).copy()
    matches["year"] = pd.to_numeric(matches["year"], errors="raise").astype(int)
    matches["issue_num"] = pd.to_numeric(matches["issue"], errors="raise").astype(int)
    keep = matches["year"].lt(2025) | (
        matches["year"].eq(2025) & matches["issue_num"].le(DEVELOPMENT_ISSUE_MAX)
    )
    result = matches.loc[keep].sort_values(["year", "issue_order", "issue_instance", "match_idx"], kind="mergesort")
    expected = {2019: 55, 2020: 44, 2021: 58, 2022: 58, 2023: 55, 2024: 59, 2025: 15}
    actual = result.drop_duplicates("issue_instance").groupby("year").size().to_dict()
    if strict_census and (actual != expected or result["issue_instance"].nunique() != 344):
        raise GateAError(f"development chronology registry drift: {actual}")
    return result.reset_index(drop=True)


def _common_adapter(
    source: Path, identity: pd.DataFrame, history: pd.DataFrame,
    full_identity: pd.DataFrame, pclose_source: Path, *, strict_census: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Materialize one outcome-unexposed M×3 feature/mask schema for both sides."""

    development = _development_registry(identity, strict_census=strict_census)
    full = full_identity[["expect", "match_no", "match_uid"]].copy()
    dev = development.merge(
        full, left_on=["issue", "match_idx"], right_on=["expect", "match_no"],
        how="left", validate="one_to_one",
    )
    dev["match_uid_key"] = dev["match_uid"].astype("Int64").astype(str)
    pclose = _read_pclose_proxy(pclose_source, allow_duplicate_match_id=True).rename(columns={"match_id": "pclose_match_uid"})
    pclose["pclose_match_uid"] = pclose["pclose_match_uid"].astype(str)
    # The raw archive has one documented duplicate key; deterministic first-row
    # retention is frozen here rather than permitting an accidental one-to-many join.
    duplicate_census = pclose.groupby("pclose_match_uid", sort=True).size().rename("source_rows").reset_index()
    duplicate_census = duplicate_census.loc[duplicate_census["source_rows"].gt(1)].copy()
    duplicate_census["resolution"] = "FIRST_SOURCE_ROW_BY_SQLITE_ROW_ORDER"
    pclose = pclose.drop_duplicates("pclose_match_uid", keep="first")
    # The p_close issue field is evidence of the source query, but the frozen
    # development chronology always comes from #203's issue registry.
    pclose = pclose.drop(columns=["issue"])
    dev = dev.merge(pclose, left_on="match_uid_key", right_on="pclose_match_uid", how="left", validate="many_to_one")
    pclose_complete = dev[["p_close_3", "p_close_1", "p_close_0"]].notna().all(axis=1)
    if strict_census and (len(dev) != 102245 or int(pclose_complete.sum()) != 101029):
        raise GateAError("development p_close adapter support drift")

    test = history.copy()
    odds = test[["avg_eu_home", "avg_eu_draw", "avg_eu_away"]].apply(pd.to_numeric, errors="coerce")
    inverse = 1.0 / odds
    test_complete = odds.gt(0).all(axis=1) & np.isfinite(inverse).all(axis=1)
    normalized = inverse.div(inverse.sum(axis=1).where(test_complete), axis=0)
    if strict_census and (len(test) != 16990 or int(test_complete.sum()) != 16968):
        raise GateAError("test average-EU adapter support drift")

    # Optional input retains the declared semantic without treating it as a target.
    values = pd.read_parquet(source / "inference" / "feature_values.parquet", columns=["cell_join_key", "predicted_final_sp"])
    pred = identity[["cell_join_key", "issue", "match_id", "match_idx", "outcome_code"]].merge(values, on="cell_join_key")
    pred = pred.loc[pred["issue"].astype(str).isin(dev["issue"].astype(str))]
    dev_base = dev.rename(columns={"issue": "issue_key"}).copy()
    dev_base["issue"] = dev_base["issue_key"].astype(str)
    test_base = test.copy()
    # Issue chronology is authoritative even when an archival kickoff value is
    # absent; the two frozen blocks are 2025 and 2026 respectively.
    test_base["year"] = np.where(test_base["issue_num"].le(25125), 2025, 2026).astype(int)
    test_base["issue_instance"] = "RETROSPECTIVE_PROXY_" + test_base["issue"].astype(str)

    rows: list[pd.DataFrame] = []
    masks: list[pd.DataFrame] = []
    for code, dev_col, test_col in (("3", "p_close_3", 0), ("1", "p_close_1", 1), ("0", "p_close_0", 2)):
        d = pd.DataFrame({
            "issue": dev_base["issue"], "issue_instance": dev_base["issue_instance"],
            "year": dev_base["year"], "issue_order": dev_base["issue_order"],
            "match_idx": dev_base["match_idx"], "outcome_code": code,
            "market_probability": dev_base[dev_col], "native_handicap_line": dev_base["beidan_hcap"],
            "source_is_pclose": 1.0, "source_is_average_eu": 0.0,
            "market_proxy_complete": pclose_complete.astype(float),
            "source_grade": "RETROSPECTIVE_PROXY_PCLOSE", "role": "DEVELOPMENT_CV",
        })
        p = pred.loc[pred["outcome_code"].astype(str).eq(code), ["issue", "match_idx", "predicted_final_sp"]].copy()
        p["issue"] = p["issue"].astype(str)
        d = d.merge(p, on=["issue", "match_idx"], how="left", validate="one_to_one")
        t = pd.DataFrame({
            "issue": test_base["issue"].astype(str), "issue_instance": test_base["issue_instance"],
            "year": test_base["year"], "issue_order": np.nan, "match_idx": test_base["match_idx"],
            "outcome_code": code, "market_probability": normalized.iloc[:, test_col],
            "native_handicap_line": test_base["handicap_line"], "source_is_pclose": 0.0,
            "source_is_average_eu": 1.0, "market_proxy_complete": test_complete.astype(float),
            "source_grade": PROXY_GRADE, "role": "RETROSPECTIVE_TEST_LOCKED",
            "predicted_final_sp": np.nan,
        })
        for part in (d, t):
            part["cell_key"] = (
                part["issue"].astype(str) + ":" + part["match_idx"].astype(str) + ":" + part["outcome_code"]
            )
            rows.append(part)
            mask = part[["cell_key"]].copy()
            mask["market_probability"] = part["market_probability"].notna()
            mask["native_handicap_line"] = part["native_handicap_line"].notna()
            mask["source_is_pclose"] = True
            mask["source_is_average_eu"] = True
            mask["market_proxy_complete"] = True
            mask["predicted_final_sp_input"] = part["predicted_final_sp"].notna()
            masks.append(mask)
    features = pd.concat(rows, ignore_index=True).rename(columns={"predicted_final_sp": "predicted_final_sp_input"})
    features = features[["cell_key", "issue", "issue_instance", "year", "issue_order", "match_idx", "outcome_code", "role", "source_grade", *COMMON_FEATURES]]
    features = features.sort_values(["role", "year", "issue", "match_idx", "outcome_code"], kind="mergesort").reset_index(drop=True)
    feature_masks = pd.concat(masks, ignore_index=True).sort_values("cell_key", kind="mergesort").reset_index(drop=True)
    registry = pd.concat([
        dev_base.assign(role="DEVELOPMENT_CV", source_grade="RETROSPECTIVE_PROXY_PCLOSE", market_proxy_complete=pclose_complete),
        test_base.assign(role="RETROSPECTIVE_TEST_LOCKED", source_grade=PROXY_GRADE, market_proxy_complete=test_complete),
    ], ignore_index=True, sort=False)
    registry = registry[["issue", "issue_instance", "year", "issue_order", "match_idx", "role", "source_grade", "market_proxy_complete"]]
    coverage = registry.groupby(["role", "source_grade", "year"], dropna=False, sort=True).agg(
        issues=("issue", "nunique"), matches=("issue", "size"), complete_market_rows=("market_proxy_complete", "sum")
    ).reset_index()
    coverage["fallback_no_bet_rows"] = coverage["matches"] - coverage["complete_market_rows"]
    coverage["common_schema_coverage"] = coverage["complete_market_rows"] / coverage["matches"]
    return features, feature_masks, registry, coverage, duplicate_census


def load_common_issue(package: str | Path, issue: str) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """Load either development or test issue through the same common M×3 interface."""

    root = Path(package)
    features = pd.read_parquet(root / "common_cell_features.parquet")
    masks = pd.read_parquet(root / "common_cell_masks.parquet")
    selected = features.loc[features["issue"].astype(str).eq(str(issue))].copy()
    if selected.empty:
        raise GateAError(f"common adapter issue is absent: {issue}")
    selected = selected.sort_values(["match_idx", "outcome_code"], kind="mergesort")
    if len(selected) % 3 or set(selected["outcome_code"].unique()) != {"3", "1", "0"}:
        raise GateAError("common adapter does not form M×3")
    aligned_masks = masks.set_index("cell_key").loc[selected["cell_key"]]
    values = selected.loc[:, list(COMMON_FEATURES)].to_numpy(dtype=float).reshape(-1, 3, len(COMMON_FEATURES))
    mask_values = aligned_masks.loc[:, list(COMMON_FEATURES)].to_numpy(dtype=bool).reshape(-1, 3, len(COMMON_FEATURES))
    return values, mask_values, COMMON_FEATURES


def _common_field_coverage(features: pd.DataFrame, masks: pd.DataFrame) -> pd.DataFrame:
    """Long-form field/outcome completeness audit for the common M×3 interface."""

    joined = features[["cell_key", "role", "source_grade", "year", "outcome_code"]].merge(
        masks, on="cell_key", how="left", validate="one_to_one",
    )
    long = joined.melt(
        id_vars=["role", "source_grade", "year", "outcome_code"],
        value_vars=list(COMMON_FEATURES), var_name="feature", value_name="available",
    )
    result = long.groupby(
        ["role", "source_grade", "year", "outcome_code", "feature"], sort=True,
    ).agg(cells=("available", "size"), available_cells=("available", "sum")).reset_index()
    result["missing_cells"] = result["cells"] - result["available_cells"]
    result["coverage"] = result["available_cells"] / result["cells"]
    return result


def _common_probability_validity(features: pd.DataFrame, masks: pd.DataFrame) -> pd.DataFrame:
    """Audit full probability-triplet, handicap, and SP-input eligibility."""

    identity_columns = ["issue", "match_idx", "role", "source_grade", "year"]
    joined = features[[*identity_columns, "outcome_code", "cell_key", "market_probability"]].merge(
        masks[["cell_key", "market_probability", "native_handicap_line", "predicted_final_sp_input"]],
        on="cell_key", how="left", validate="one_to_one", suffixes=("", "_mask"),
    )
    market = joined.pivot(index=identity_columns, columns="outcome_code", values="market_probability")
    market_mask = joined.pivot(index=identity_columns, columns="outcome_code", values="market_probability_mask")
    handicap_mask = joined.pivot(index=identity_columns, columns="outcome_code", values="native_handicap_line")
    sp_input_mask = joined.pivot(index=identity_columns, columns="outcome_code", values="predicted_final_sp_input")
    expected = ["3", "1", "0"]
    market = market.reindex(columns=expected)
    market_mask = market_mask.reindex(columns=expected).fillna(False).astype(bool)
    handicap_mask = handicap_mask.reindex(columns=expected).fillna(False).astype(bool)
    sp_input_mask = sp_input_mask.reindex(columns=expected).fillna(False).astype(bool)
    values = market.to_numpy(dtype=float)
    valid_market = (
        market_mask.all(axis=1).to_numpy() & np.isfinite(values).all(axis=1)
        & (values > 0).all(axis=1) & (np.abs(values.sum(axis=1) - 1.0) <= 2e-6)
    )
    detail = market.reset_index()[identity_columns]
    detail["market_triplet_valid"] = valid_market
    detail["handicap_complete"] = handicap_mask.all(axis=1).to_numpy()
    detail["predicted_sp_input_complete"] = sp_input_mask.all(axis=1).to_numpy()
    return detail.groupby(["role", "source_grade", "year"], sort=True).agg(
        matches=("issue", "size"),
        market_triplet_valid_rows=("market_triplet_valid", "sum"),
        fallback_no_bet_rows=("market_triplet_valid", lambda values: int((~values).sum())),
        handicap_complete_rows=("handicap_complete", "sum"),
        predicted_sp_input_complete_rows=("predicted_sp_input_complete", "sum"),
    ).reset_index()


def _issue_reconciliation(
    identity: pd.DataFrame, development: pd.DataFrame, history: pd.DataFrame,
    proxy: pd.DataFrame, test_identities: pd.DataFrame,
) -> pd.DataFrame:
    """Publish source identity and missing-source reasons for every frozen issue."""

    inference = identity.copy()
    inference["issue"] = inference["issue"].astype(str)
    inference["issue_num"] = _issue_number(inference["issue"])
    inference_counts = inference.groupby("issue", sort=True).size().rename("inference_cell_rows")
    history_counts = history.groupby("issue", sort=True).size().rename("history_rows")
    proxy_counts = proxy.groupby("issue", sort=True)["market_proxy_complete"].sum().rename("complete_proxy_rows")
    target_counts = test_identities.groupby("issue", sort=True)["official_target_identity_available"].sum()
    development_issues = set(development["issue"].astype(str).unique())
    issues = sorted(set(history_counts.index) | development_issues, key=int)
    rows: list[dict[str, Any]] = []
    for issue in issues:
        issue_num = int(issue)
        historical = int(history_counts.get(issue, 0))
        if issue in development_issues:
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
            "official_3sp_target_identity_rows": int(target_counts.get(issue, 0)),
            "history_only_no_target_rows": int(historical - target_counts.get(issue, 0)),
            "complete_proxy_rows": int(proxy_counts.get(issue, 0)),
            "inference_cell_rows": int(inference_counts.get(issue, 0)),
            "source_status": source_status,
            "missing_reason": missing_reason,
            "labels_opened": False,
            "target_quality_mask": SP_TARGET["quality_mask"],
        })
    result = pd.DataFrame(rows)
    test_rows = result["role"].eq("RETROSPECTIVE_TEST_LOCKED")
    if int(result.loc[test_rows, "history_rows"].sum()) != 16990:
        raise GateAError("frozen 75-issue retrospective history census drift")
    if int(result[test_rows].shape[0]) != 75:
        raise GateAError("frozen retrospective issue census drift")
    if int(result.loc[test_rows, "official_3sp_target_identity_rows"].sum()) != 16853:
        raise GateAError("frozen retrospective target identity census drift")
    return result


def _split_rows(development: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
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
        "year": np.where(test["issue_num"].le(25125), 2025, 2026).astype(int),
        "issue_order": np.arange(len(matches), len(matches) + len(test), dtype=int),
        "feature_cutoff_ts_utc": pd.NA,
        "kickoff_ts_utc": test["kickoff_ts"],
        "role": "RETROSPECTIVE_TEST_LOCKED",
        "labels_permitted_gate_a": False,
        "labels_permitted_gate_b": True,
        "feature_namespace": "retrospective_proxy_outcome_unexposed",
    })
    result = pd.concat([matches, test_rows], ignore_index=True)
    if int(matches["issue"].nunique()) != 344:
        raise GateAError("development split issue census drift")
    if not result["labels_permitted_gate_a"].eq(False).all():
        raise GateAError("Gate A split leaks labels")
    return result


def _development_target_identity_reconciliation(
    development: pd.DataFrame, full_3sp_identity: pd.DataFrame,
) -> pd.DataFrame:
    """Bind 25041/25042 target *identities* inside supervised development.

    Gate A may verify only that official target identities exist.  It never
    reads target values, result codes, or update timestamps.
    """

    scope = development.loc[
        development["issue"].astype(str).isin(("25041", "25042")),
        ["issue", "issue_instance", "year", "issue_order", "match_idx"],
    ].copy()
    target = full_3sp_identity.loc[
        full_3sp_identity["expect"].astype(str).isin(("25041", "25042")),
        ["expect", "match_no", "match_uid"],
    ]
    result = scope.merge(
        target, left_on=["issue", "match_idx"], right_on=["expect", "match_no"],
        how="left", validate="one_to_one",
    ).drop(columns=["expect", "match_no"])
    result["official_target_identity_available"] = result["match_uid"].notna()
    result["target_identity_reason"] = np.where(
        result["official_target_identity_available"],
        "MATCHED_OFFICIAL_3SP_TARGET_NOT_OPENED",
        "DEVELOPMENT_INFERENCE_IDENTITY_WITHOUT_OFFICIAL_3SP_TARGET",
    )
    result["labels_opened"] = False
    result["target_quality_mask"] = SP_TARGET["quality_mask"]
    if len(result) != 1024 or int(result["official_target_identity_available"].sum()) != 1021:
        raise GateAError("25041/25042 development target identity census drift")
    return result.sort_values(["issue", "match_idx"], key=lambda s: _issue_number(s) if s.name == "issue" else s,
                              kind="mergesort").reset_index(drop=True)


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
    full_3sp_source: Path,
    pclose_source: Path,
    splits: pd.DataFrame,
    reconciliation: pd.DataFrame,
    coverage: pd.DataFrame,
    common_coverage: pd.DataFrame,
    common_validity: pd.DataFrame,
    development_targets: pd.DataFrame,
    bridge_summary: dict[str, Any],
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
            "official_3sp_identity_source": "data/raw/beidan_full_3sp.csv",
            "official_3sp_identity_sha256": digest(full_3sp_source),
            "official_3sp_identity_columns_allowlist": list(FULL_3SP_IDENTITY_COLUMNS),
            "p_close_bridge_source": "data/beidan_features.db",
            "p_close_bridge_sha256": digest(pclose_source),
            "p_close_columns_allowlist": list(PCLOSE_COLUMNS),
            "full_replay_source_location_contract": (
                "freeze requires explicit --history-source, --full-3sp-identity-source, "
                "and --pclose-source paths; no parent-worktree discovery is permitted"
            ),
            "labels_opened": False,
        },
        "chronology": {
            "development_cv_through_issue": DEVELOPMENT_ISSUE_MAX,
            "retrospective_test_issue_ranges": [list(item) for item in RETROSPECTIVE_TEST_RANGES],
            "reserve_for_210_from_issue": RESERVE_ISSUE_MIN,
            "development_issue_count": int(development["issue"].nunique()),
            "development_match_count": int(common_coverage.loc[
                common_coverage["role"].eq("DEVELOPMENT_CV"), "matches"
            ].sum()),
            "retrospective_test_issue_count": int(test["issue"].nunique()),
            "retrospective_test_history_rows": int(reconciliation.loc[
                reconciliation["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "history_rows"
            ].sum()),
            "cv_validation_years": list(CV_VALIDATION_YEARS),
            "development_target_identity_scope": "25041-25042",
            "development_target_identity_rows": int(len(development_targets)),
            "development_target_identity_available_rows": int(development_targets["official_target_identity_available"].sum()),
        },
        "schema": {
            "ragged_shape": "X_i[J_i,3,F]",
            "outcome_axis": ["3", "1", "0"],
            "model_features": list(MODEL_FEATURES),
            "mask_features": list(MODEL_FEATURES),
            "market_baseline_feature": MARKET_BASELINE_FEATURE,
            "predicted_final_sp_semantics": "outcome-unexposed pre-event proxy input only",
            "sp_target": SP_TARGET,
            "common_adapter": {
                "feature_table": "common_cell_features.parquet",
                "mask_table": "common_cell_masks.parquet",
                "registry_table": "common_issue_registry.csv",
                "coverage_table": "common_schema_coverage_by_period.csv",
                "field_coverage_table": "common_schema_field_coverage.csv",
                "probability_validity_table": "common_probability_validity.csv",
                "development_source_grade": "RETROSPECTIVE_PROXY_PCLOSE",
                "test_source_grade": PROXY_GRADE,
                "by_period": common_coverage.to_dict(orient="records"),
                "probability_validity_by_period": common_validity.to_dict(orient="records"),
            },
        },
        "proxy_panel": {
            "grade": PROXY_GRADE,
            "coverage_file": "proxy_coverage_by_period.csv",
            "panel_file": "retrospective_proxy_panel.csv",
            "baseline_model_fallback_coverage": coverage.to_dict(orient="records"),
            "limitation": "retrospective proxy only; no source timestamp proves a live pre-event capture",
        },
        "market_source_bridge": {
            "table": "market_proxy_pclose_bridge.csv",
            "summary": "market_proxy_pclose_bridge_summary.json",
            "summary_values": bridge_summary,
            "transform": "normalized_inverse(avg_eu_home,avg_eu_draw,avg_eu_away)",
            "source_grade": PROXY_GRADE,
            "outlier_max_abs_probability_delta": BRIDGE_OUTLIER_MAX_ABS_DELTA,
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
    return f"""# #204 Gate A v4 — market-anchored residual model preregistration

This immutable package is **outcome-unexposed**.  It uses the #203 inference
namespace only for development/CV through issue `{chronology['development_cv_through_issue']}`.
The one-shot retrospective window is `25043–25125` plus `26011–26049`; it is
represented by a clearly graded `{PROXY_GRADE}` market panel.  Issues `26051+`
remain reserved for #210.

The common `X_i[J_i,3,F]` adapter is materialized for both development and
test in `common_cell_features.parquet` plus `common_cell_masks.parquet`.
Development uses the identity-bridged p_close proxy; the test side uses
normalized average-EU. Source-grade fields and coverage tables make that
transition explicit. `predicted_final_sp_input` is a pre-event proxy input,
not a target. The supervised
SP target is the official 3/1/0 final-SP vector under
`{SP_TARGET['quality_mask']}` and is not opened here.  The target-only census
records the known post-kickoff update prevalence precisely to prevent a
retrospective proxy from being misrepresented as a live capture.

`market_proxy_pclose_bridge.csv` freezes the normalized-inverse-average-EU to
`p_close` source transition on 20,837 complete historical overlaps. It joins
only `issue + match_idx` and official `match_uid` identifiers, retains source
grades, publishes the delta distribution, and never treats the vendors as
byte-identical. Missing/reference-outlier handling is preregistered in the
bridge summary; no official result or SP value is read.

The hard action gate is `{FALLBACK_RULE['rule_id']}`: an incomplete/nonfinite
proxy row uses a valid frozen market vector if one exists; otherwise it is
`NO_BET_FROZEN`.  Gate B requires PI acceptance of this exact package.
"""


def _replay_markdown() -> str:
    return """# Deterministic Gate-A v4 replay

Run from the repository root with the pinned existing environment.  The
history source is read-only and queried with the documented eight-column
pre-event allow-list; no official-SP or result field is selected.

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py verify \\
  --package results/bj204_gate_a_preoutcome_v4

PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py freeze \\
  --source results/bj203_causal_tensor_v2 \\
  --history-source data/beidan_history.db \\
  --full-3sp-identity-source data/raw/beidan_full_3sp.csv \\
  --pclose-source data/beidan_features.db --output <new-empty-directory>

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
    output: str | Path, *, source_package: str | Path, history_source: str | Path,
    full_3sp_identity_source: str | Path, pclose_source: str | Path,
) -> dict[str, Any]:
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise GateAError(f"refusing to replace output package: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source_package).resolve()
    history_path = Path(history_source).resolve()
    full_3sp_path = Path(full_3sp_identity_source).resolve()
    pclose_path = Path(pclose_source).resolve()
    identity, source_manifest = _validate_source(source)
    history = _read_history_proxy(history_path)
    full_3sp_identity = _read_full_3sp_identity(full_3sp_path)
    development = _development_registry(identity)
    proxy = _proxy_panel(history)
    test_identities = _test_identity_reconciliation(history, full_3sp_identity)
    development_targets = _development_target_identity_reconciliation(development, full_3sp_identity)
    common_features, common_masks, common_registry, common_coverage, pclose_duplicates = _common_adapter(
        source, identity, history, full_3sp_identity, pclose_path,
    )
    common_field_coverage = _common_field_coverage(common_features, common_masks)
    common_validity = _common_probability_validity(common_features, common_masks)
    reconciliation = _issue_reconciliation(identity, development, history, proxy, test_identities)
    bridge, bridge_summary = _market_bridge(history_path, full_3sp_identity, pclose_path)
    splits = _split_rows(development, history)
    cv = _cv_manifest(splits)
    coverage = _coverage(proxy)
    card = _build_card(
        source, source_manifest, history_path, full_3sp_path, pclose_path, splits,
        reconciliation, coverage, common_coverage, common_validity, development_targets, bridge_summary,
    )
    write_csv(output / "split_manifest.csv", splits)
    write_csv(output / "cv_manifest.csv", cv)
    write_csv(output / "identity_reconciliation.csv", reconciliation)
    write_csv(output / "test_identity_reconciliation.csv", test_identities)
    write_csv(output / "development_target_identity_reconciliation.csv", development_targets)
    write_csv(output / "retrospective_proxy_panel.csv", proxy)
    write_csv(output / "proxy_coverage_by_period.csv", coverage)
    common_features.to_parquet(output / "common_cell_features.parquet", index=False)
    common_masks.to_parquet(output / "common_cell_masks.parquet", index=False)
    write_csv(output / "common_issue_registry.csv", common_registry)
    write_csv(output / "common_schema_coverage_by_period.csv", common_coverage)
    write_csv(output / "common_schema_field_coverage.csv", common_field_coverage)
    write_csv(output / "common_probability_validity.csv", common_validity)
    write_csv(output / "pclose_duplicate_resolution.csv", pclose_duplicates)
    write_csv(output / "market_proxy_pclose_bridge.csv", bridge)
    write_json(output / "market_proxy_pclose_bridge_summary.json", bridge_summary)
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
        "development_matches": int(len(development)),
        "retrospective_test_issues": int(splits.loc[splits["role"].eq("RETROSPECTIVE_TEST_LOCKED"), "issue"].nunique()),
        "target_bearing_test_identities": int(test_identities["official_target_identity_available"].sum()),
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
    development = splits.loc[splits["role"].eq("DEVELOPMENT_CV")]
    yearly = development.groupby("year")["issue"].nunique().to_dict()
    if yearly != {2019: 55, 2020: 44, 2021: 58, 2022: 58, 2023: 55, 2024: 59, 2025: 15}:
        raise GateAError("development chronology registry drift")
    if test["issue"].nunique() != 75 or not test["issue"].astype(int).map(_is_test_issue).all():
        raise GateAError("retrospective test chronology drift")
    reconciliation = pd.read_csv(root / "identity_reconciliation.csv", dtype={"issue": str})
    test_reconciliation = reconciliation.loc[reconciliation["role"].eq("RETROSPECTIVE_TEST_LOCKED")]
    if len(test_reconciliation) != 75 or int(test_reconciliation["history_rows"].sum()) != 16990:
        raise GateAError("retrospective source reconciliation drift")
    if int(test_reconciliation["official_3sp_target_identity_rows"].sum()) != 16853:
        raise GateAError("retrospective target identity reconciliation drift")
    test_identities = pd.read_csv(root / "test_identity_reconciliation.csv", dtype={"issue": str})
    if len(test_identities) != 16990 or int(test_identities["official_target_identity_available"].sum()) != 16853:
        raise GateAError("test identity detail reconciliation drift")
    development_targets = pd.read_csv(root / "development_target_identity_reconciliation.csv", dtype={"issue": str})
    if len(development_targets) != 1024 or int(development_targets["official_target_identity_available"].sum()) != 1021:
        raise GateAError("development target identity reconciliation drift")
    features = pd.read_parquet(root / "common_cell_features.parquet")
    masks = pd.read_parquet(root / "common_cell_masks.parquet")
    if list(features.columns[-len(COMMON_FEATURES):]) != list(COMMON_FEATURES) or len(features) != len(masks):
        raise GateAError("common M×3 schema drift")
    if features.groupby(["issue", "match_idx"]).size().ne(3).any():
        raise GateAError("common M×3 outcome cardinality drift")
    validity = pd.read_csv(root / "common_probability_validity.csv")
    if int(validity["market_triplet_valid_rows"].sum()) != 101029 + 16968:
        raise GateAError("common market triplet validity drift")
    bridge_summary = json.loads((root / "market_proxy_pclose_bridge_summary.json").read_text(encoding="utf-8"))
    if bridge_summary.get("complete_comparable_rows") != 20837:
        raise GateAError("market bridge support census drift")
    quality = pd.read_csv(root / "target_only_quality_mask.csv")
    if quality["official_3sp_rows"].tolist() != [11314, 5539]:
        raise GateAError("target-only official-SP census drift")
    return {"contract_version": CONTRACT_VERSION, "files": len(actual), "status": "PASS"}
