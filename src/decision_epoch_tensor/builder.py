"""Build and verify the #214 causal decision-epoch capability package."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from unified_tensor.builder import (
    _load_inputs,
    _prepare_matches,
    verify_package as verify_upstream_package,
)

from .contract import (
    ACTIVATION_UTC,
    COHORTS,
    CONTRACT_VERSION,
    CORE_FEATURES,
    EPOCH_RULES,
    FEATURE_DICTIONARY,
    FEATURE_NAMES,
    OUTCOME_ORDER,
    REPRESENTATIVE_GATE,
    SOURCE_TIMEZONE,
    UPSTREAM_CONTRACT_VERSION,
    epoch_cell_key,
    epoch_id,
)
from .loader import load_epoch_tensors


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_PACKAGE = ROOT / "results/bj203_causal_tensor_v2"
ENVIRONMENT_LOCK = ROOT / "requirements.txt"
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "f05e02404a91bb63d2a40c55bbe572964cf681057df72f7c69c6145c4c78572d"
)

SOURCE_FILES = (
    "base_match_capability.parquet",
    "live_match_identity.parquet",
    "selected_market_observations.parquet",
    "selected_eligibility_observations.parquet",
    "segment_windows.parquet",
    "source_freeze.json",
)


class DecisionEpochBuildError(RuntimeError):
    """Raised when #214 evidence cannot be built or verified safely."""


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


def write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=True,
        write_statistics=True,
        version="2.6",
        data_page_version="2.0",
        row_group_size=65_536,
    )


def _sqlite_snapshot(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise DecisionEpochBuildError(f"source database is unavailable: {database}")
    connection = sqlite3.connect(
        f"{database.expanduser().resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _utc_text(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _hkt_naive_to_utc(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, format="mixed", errors="raise")
    if parsed.dt.tz is not None:
        localized = parsed.dt.tz_convert("UTC")
    else:
        localized = parsed.dt.tz_localize(
            SOURCE_TIMEZONE,
            ambiguous="raise",
            nonexistent="raise",
        ).dt.tz_convert("UTC")
    return localized.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _numeric(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.replace("", np.nan), errors="coerce")


def _complete_triplet(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    selected = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")
    return selected.notna().all(axis=1) & selected.gt(1.0).all(axis=1)


def _complete_probability_triplet(
    frame: pd.DataFrame,
    columns: Iterable[str],
) -> pd.Series:
    selected = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")
    return (
        selected.notna().all(axis=1)
        & selected.ge(0.0).all(axis=1)
        & selected.le(1.0).all(axis=1)
        & selected.sum(axis=1).sub(1.0).abs().le(1e-5)
    )


def _base_match_capability(upstream: Path) -> pd.DataFrame:
    receipt = verify_upstream_package(upstream)
    if receipt.get("contract_version") != UPSTREAM_CONTRACT_VERSION:
        raise DecisionEpochBuildError("unexpected #203 upstream contract")
    estimator, census, predictions, extension, heldout = _load_inputs(
        None,
        upstream / "sources/unavailable_match_identity.parquet",
        heldout_identity_extension=(
            upstream / "sources/heldout_match_identity.parquet"
        ),
    )
    matches, _league, _team, _breadth = _prepare_matches(
        estimator,
        census,
        predictions,
        extension,
        heldout,
    )
    matches["match_position_fraction"] = (
        matches.groupby("issue", sort=False).cumcount()
        / np.maximum(
            matches.groupby("issue", sort=False)["match_id"].transform("size") - 1,
            1,
        )
    )
    base = matches.loc[
        :,
        [
            "match_id",
            "issue",
            "match_idx",
            "year",
            "kickoff_ts_utc",
            "feature_cutoff_ts_utc",
            "identity_observed_ts_utc",
            "identity_timing_status",
            "identity_source",
            "native_handicap_line",
            "league_index",
            "home_team_index",
            "away_team_index",
            "match_position_fraction",
            "calibrated_p3",
            "calibrated_p1",
            "calibrated_p0",
            "euro_1h_odds3",
            "euro_1h_odds1",
            "euro_1h_odds0",
            "predicted_sp3",
            "predicted_sp1",
            "predicted_sp0",
        ],
    ].copy()
    base["cohort"] = np.where(
        matches["split"].eq("development"),
        "development",
        "historical_model_unseen",
    )
    base["named_calibrated_present"] = _complete_probability_triplet(
        base, ("calibrated_p3", "calibrated_p1", "calibrated_p0")
    )
    base["named_euro_present"] = _complete_triplet(
        base, ("euro_1h_odds3", "euro_1h_odds1", "euro_1h_odds0")
    )
    base["named_predicted_sp_present"] = _complete_triplet(
        base, ("predicted_sp3", "predicted_sp1", "predicted_sp0")
    )
    base = base.drop(
        columns=[
            "calibrated_p3",
            "calibrated_p1",
            "calibrated_p0",
            "euro_1h_odds3",
            "euro_1h_odds1",
            "euro_1h_odds0",
            "predicted_sp3",
            "predicted_sp1",
            "predicted_sp0",
        ]
    )
    base["match_idx"] = base["match_idx"].astype("int32")
    base["year"] = base["year"].astype("int16")
    base["native_handicap_line"] = pd.to_numeric(
        base["native_handicap_line"], errors="coerce"
    )
    return base.sort_values(
        ["feature_cutoff_ts_utc", "issue", "match_idx", "match_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _extract_live_sources(
    live_database: Path,
    market_database: Path,
    *,
    source_freeze_cutoff_utc: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cutoff = pd.Timestamp(source_freeze_cutoff_utc)
    if cutoff.tzinfo is None:
        raise DecisionEpochBuildError("source freeze cutoff must include timezone")
    cutoff_text = cutoff.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    with closing(_sqlite_snapshot(live_database)) as connection:
        match_rows = connection.execute(
            """
            SELECT CAST(match_id AS TEXT) AS match_id,
                   CAST(issue AS TEXT) AS issue,
                   CAST(match_idx AS INTEGER) AS match_idx,
                   kickoff_ts, created_ts, handicap_line
              FROM matches
             WHERE CAST(issue AS INTEGER) >= 26051
             ORDER BY CAST(issue AS INTEGER), match_idx, match_id
            """
        ).fetchall()
        snapshot_rows = connection.execute(
            """
            SELECT id, CAST(match_id AS TEXT) AS match_id, snapshot_ts,
                   sp_3, sp_1, sp_0, eu_h, eu_d, eu_a, source
              FROM snapshots
             WHERE snapshot_ts <= ?
             ORDER BY snapshot_ts, match_id, id
            """,
            (cutoff_text,),
        ).fetchall()
        live_schema = "\n".join(
            str(row[0])
            for row in connection.execute(
                """
                SELECT sql FROM sqlite_master
                 WHERE type='table' AND name IN ('matches','snapshots')
                 ORDER BY name
                """
            )
        )
    with closing(_sqlite_snapshot(market_database)) as connection:
        eligibility_rows = connection.execute(
            """
            SELECT CAST(issue AS TEXT) AS issue,
                   CAST(row_idx AS INTEGER) AS match_idx,
                   COALESCE(match_id,'') AS match_id,
                   fetched_at_utc, source_updated_at_hkt,
                   sale_status, parlay_allowed, capture_classification,
                   source_attribute, publication_status
              FROM live_market_sp_snapshots
             WHERE playid=34 AND outcome_code='3'
               AND fetched_at_utc <= ?
             ORDER BY fetched_at_utc, issue, row_idx, match_id
            """,
            (cutoff_text,),
        ).fetchall()
        window_rows = connection.execute(
            """
            SELECT CAST(issue AS TEXT) AS issue,
                   CAST(segment_idx AS INTEGER) AS segment_idx,
                   freeze_at, manual_frozen_at, match_indices_json
              FROM segment_decision_windows
             ORDER BY CAST(issue AS INTEGER), segment_idx
            """
        ).fetchall()
        market_schema = "\n".join(
            str(row[0])
            for row in connection.execute(
                """
                SELECT sql FROM sqlite_master
                 WHERE type='table'
                   AND name IN ('live_market_sp_snapshots','segment_decision_windows')
                 ORDER BY name
                """
            )
        )
    matches = pd.DataFrame([dict(row) for row in match_rows])
    snapshots = pd.DataFrame([dict(row) for row in snapshot_rows])
    eligibility = pd.DataFrame([dict(row) for row in eligibility_rows])
    windows = pd.DataFrame([dict(row) for row in window_rows])
    if matches.empty or snapshots.empty:
        raise DecisionEpochBuildError("live timestamped source is empty")
    matches["kickoff_ts_utc"] = _hkt_naive_to_utc(matches["kickoff_ts"])
    matches["identity_observed_ts_utc"] = _utc_text(matches["created_ts"])
    matches["year"] = pd.to_datetime(
        matches["kickoff_ts_utc"], utc=True
    ).dt.year.astype("int16")
    matches["cohort"] = np.where(
        pd.to_numeric(matches["issue"], errors="raise").le(26082),
        "post_203_operational_observational",
        "prospective_post_activation",
    )
    matches["feature_cutoff_ts_utc"] = matches.groupby("issue", sort=False)[
        "identity_observed_ts_utc"
    ].transform("max")
    matches["identity_timing_status"] = "TIMESTAMPED_IDENTITY_ONLY"
    matches["identity_source"] = "beidan_live.matches"
    matches["league_index"] = np.nan
    matches["home_team_index"] = np.nan
    matches["away_team_index"] = np.nan
    matches["match_position_fraction"] = (
        matches.groupby("issue", sort=False).cumcount()
        / np.maximum(matches.groupby("issue", sort=False)["match_id"].transform("size") - 1, 1)
    )
    matches["named_calibrated_present"] = False
    matches["named_euro_present"] = False
    matches["named_predicted_sp_present"] = False
    live_match_columns = [
        "match_id",
        "issue",
        "match_idx",
        "year",
        "kickoff_ts_utc",
        "feature_cutoff_ts_utc",
        "identity_observed_ts_utc",
        "identity_timing_status",
        "identity_source",
        "handicap_line",
        "league_index",
        "home_team_index",
        "away_team_index",
        "match_position_fraction",
        "cohort",
        "named_calibrated_present",
        "named_euro_present",
        "named_predicted_sp_present",
    ]
    matches = matches.loc[:, live_match_columns].rename(
        columns={"handicap_line": "native_handicap_line"}
    )
    snapshots["snapshot_ts_utc"] = _utc_text(snapshots["snapshot_ts"])
    snapshots = snapshots.drop(columns="snapshot_ts")
    if not eligibility.empty:
        eligibility["fetched_at_utc"] = _utc_text(eligibility["fetched_at_utc"])
        eligibility["source_updated_at_utc"] = pd.to_datetime(
            eligibility["source_updated_at_hkt"],
            format="mixed",
            utc=True,
            errors="coerce",
        ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        eligibility["source_updated_at_utc"] = pd.Series(dtype="object")
    if not windows.empty:
        effective = windows["manual_frozen_at"].replace("", np.nan).fillna(
            windows["freeze_at"]
        )
        windows["decision_epoch_utc"] = _hkt_naive_to_utc(effective)
    metadata = {
        "source_freeze_cutoff_utc": cutoff_text,
        "activation_utc": ACTIVATION_UTC,
        "logical_sources": {
            "beidan_live": ["matches", "snapshots"],
            "500_bjdc": [
                "live_market_sp_snapshots(playid=34,outcome_code=3)",
                "segment_decision_windows",
            ],
        },
        "prohibited_tables_not_read": [
            "beidan_live.settlements",
            "500_bjdc.matches result/final fields",
            "multimarket_settlement_truth",
        ],
        "runtime_input_census": {
            "live_matches": len(matches),
            "live_snapshots": len(snapshots),
            "eligibility_observations": len(eligibility),
            "segment_windows": len(windows),
        },
        "runtime_schema_sha256": {
            "beidan_live": sha256(live_schema.encode("utf-8")).hexdigest(),
            "500_bjdc": sha256(market_schema.encode("utf-8")).hexdigest(),
        },
    }
    return matches, snapshots, eligibility, windows, metadata


def _source_row_sha256(row: pd.Series) -> str:
    fields = (
        row.get("market_snapshot_id", ""),
        row.get("match_id", ""),
        row.get("market_observed_ts_utc", ""),
        row.get("sp_3", ""),
        row.get("sp_1", ""),
        row.get("sp_0", ""),
        row.get("eu_h", ""),
        row.get("eu_d", ""),
        row.get("eu_a", ""),
        row.get("market_source", ""),
    )
    return sha256("|".join(str(value) for value in fields).encode("utf-8")).hexdigest()


def _denominator_sha256(values: list[int]) -> str:
    return sha256(
        ",".join(str(value) for value in values).encode("utf-8")
    ).hexdigest()


def _epoch_family(
    matches: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    source_freeze_cutoff_utc: str,
) -> pd.DataFrame:
    source_cutoff = pd.Timestamp(source_freeze_cutoff_utc)
    activation = pd.Timestamp(ACTIVATION_UTC)
    rule_order = {rule: index for index, rule in enumerate(EPOCH_RULES)}
    records: list[dict[str, Any]] = []
    for issue, scoped in matches.groupby("issue", sort=False):
        scoped = scoped.sort_values(
            ["kickoff_ts_utc", "match_idx", "match_id"], kind="mergesort"
        )
        cohort = str(scoped.iloc[0]["cohort"])
        kickoffs = pd.to_datetime(scoped["kickoff_ts_utc"], utc=True)
        denominator = sorted(scoped["match_idx"].astype(int).tolist())
        if cohort == "prospective_post_activation":
            issue_start = activation
        else:
            issue_start = pd.Timestamp(scoped.iloc[0]["feature_cutoff_ts_utc"])
        anchors = {
            "FIRST": kickoffs.iloc[0],
            "MEDIAN": kickoffs.iloc[(len(kickoffs) - 1) // 2],
            "LAST": kickoffs.iloc[-1],
        }
        candidates: list[tuple[str, pd.Timestamp, str, int | None, list[int]]] = [
            ("ISSUE_START", issue_start, "bj203_feature_cutoff", None, denominator)
        ]
        for name, timestamp in anchors.items():
            candidates.extend(
                [
                    (
                        f"{name}_KICKOFF_MINUS_10H",
                        timestamp - pd.Timedelta(hours=10),
                        "schedule_anchor",
                        None,
                        denominator,
                    ),
                    (
                        f"{name}_KICKOFF_MINUS_1H",
                        timestamp - pd.Timedelta(hours=1),
                        "schedule_anchor",
                        None,
                        denominator,
                    ),
                ]
            )
        scoped_windows = windows[windows["issue"].astype(str).eq(str(issue))]
        for window in scoped_windows.sort_values("segment_idx").itertuples(index=False):
            members = sorted(int(value) for value in json.loads(window.match_indices_json))
            candidates.append(
                (
                    "PUBLISHED_SEGMENT_FREEZE",
                    pd.Timestamp(window.decision_epoch_utc),
                    "segment_decision_windows",
                    int(window.segment_idx),
                    members,
                )
            )
        if cohort == "prospective_post_activation":
            candidates.append(
                (
                    "PROSPECTIVE_ACTIVATION",
                    activation,
                    "github_issue_214_activation",
                    None,
                    denominator,
                )
            )
        candidates.sort(
            key=lambda item: (
                item[1],
                rule_order[item[0]],
                item[3] if item[3] is not None else -1,
            )
        )
        for ordinal, (rule, epoch, source, segment_idx, members) in enumerate(
            candidates
        ):
            epoch = epoch.tz_localize("UTC") if epoch.tzinfo is None else epoch.tz_convert("UTC")
            epoch_text = epoch.strftime("%Y-%m-%dT%H:%M:%SZ")
            if cohort == "prospective_post_activation" and epoch < activation:
                evaluation = "PRE_ACTIVATION_UNSUPPORTED"
            elif epoch > source_cutoff:
                evaluation = "FUTURE_NOT_OBSERVED_AT_SOURCE_FREEZE"
            else:
                evaluation = "EVALUATED"
            records.append(
                {
                    "epoch_id": epoch_id(str(issue), rule, epoch_text, ordinal),
                    "issue": str(issue),
                    "cohort": cohort,
                    "epoch_rule": rule,
                    "epoch_ordinal": ordinal,
                    "decision_epoch_utc": epoch_text,
                    "source_freeze_cutoff_utc": source_freeze_cutoff_utc,
                    "evaluation_status": evaluation,
                    "epoch_source": source,
                    "segment_idx": segment_idx,
                    "denominator_match_indices_json": json.dumps(
                        members, separators=(",", ":")
                    ),
                    "denominator_sha256": _denominator_sha256(members),
                }
            )
    epochs = pd.DataFrame(records).sort_values(
        ["decision_epoch_utc", "issue", "epoch_rule", "epoch_ordinal"],
        kind="mergesort",
    ).reset_index(drop=True)
    if not bool(epochs["cohort"].isin(COHORTS).all()) or not bool(
        epochs["epoch_rule"].isin(EPOCH_RULES).all()
    ):
        raise DecisionEpochBuildError("generated epoch family violates contract")
    return epochs


def _roster_cross_join(matches: pd.DataFrame, epochs: pd.DataFrame) -> pd.DataFrame:
    grouped = {issue: frame for issue, frame in matches.groupby("issue", sort=False)}
    frames: list[pd.DataFrame] = []
    for epoch in epochs.itertuples(index=False):
        scoped = grouped[str(epoch.issue)]
        members = set(json.loads(epoch.denominator_match_indices_json))
        scoped = scoped[scoped["match_idx"].astype(int).isin(members)].copy()
        scoped.insert(0, "epoch_id", str(epoch.epoch_id))
        scoped["epoch_rule"] = str(epoch.epoch_rule)
        scoped["decision_epoch_utc"] = str(epoch.decision_epoch_utc)
        scoped["evaluation_status"] = str(epoch.evaluation_status)
        frames.append(scoped)
    roster = pd.concat(frames, ignore_index=True)
    decision = pd.to_datetime(roster["decision_epoch_utc"], utc=True)
    cutoff = pd.to_datetime(roster["feature_cutoff_ts_utc"], utc=True)
    observed = pd.to_datetime(
        roster["identity_observed_ts_utc"].replace("", pd.NA),
        utc=True,
        errors="coerce",
    )
    timing = roster["identity_timing_status"].astype(str)
    roster["identity_known_at_epoch"] = np.where(
        timing.eq("CUTOFF_BOUND_IDENTITY"),
        decision.ge(cutoff),
        np.where(
            timing.eq("TIMESTAMPED_IDENTITY_ONLY"),
            observed.notna() & observed.le(decision),
            False,
        ),
    ).astype(bool)
    roster["not_started_at_epoch"] = pd.to_datetime(
        roster["kickoff_ts_utc"], utc=True
    ).gt(decision)
    roster["candidate_roster"] = (
        roster["evaluation_status"].eq("EVALUATED")
        & roster["identity_known_at_epoch"]
        & roster["not_started_at_epoch"]
    )
    roster["_row_order"] = np.arange(len(roster), dtype=np.int64)
    return roster


def _merge_latest_market(
    roster: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    renamed = snapshots.rename(
        columns={
            "id": "market_snapshot_id",
            "snapshot_ts_utc": "market_observed_ts_utc",
            "source": "market_source",
        }
    ).copy()
    renamed["_market_time"] = pd.to_datetime(
        renamed["market_observed_ts_utc"], utc=True
    )
    left = roster.copy()
    left["_epoch_time"] = pd.to_datetime(left["decision_epoch_utc"], utc=True)
    left = left.sort_values(["_epoch_time", "match_id"], kind="mergesort")
    renamed = renamed.sort_values(
        ["_market_time", "match_id", "market_snapshot_id"], kind="mergesort"
    )
    merged = pd.merge_asof(
        left,
        renamed,
        left_on="_epoch_time",
        right_on="_market_time",
        by="match_id",
        direction="backward",
        allow_exact_matches=True,
    )
    return merged.sort_values("_row_order", kind="mergesort").reset_index(drop=True)


def _merge_latest_eligibility(
    roster: pd.DataFrame,
    eligibility: pd.DataFrame,
) -> pd.DataFrame:
    if eligibility.empty:
        for column in (
            "eligibility_match_id",
            "eligibility_observed_ts_utc",
            "source_updated_at_utc",
            "sale_status",
            "parlay_allowed",
            "capture_classification",
            "source_attribute",
            "publication_status",
        ):
            roster[column] = ""
        return roster
    right = eligibility.rename(
        columns={
            "match_id": "eligibility_match_id",
            "fetched_at_utc": "eligibility_observed_ts_utc",
        }
    ).copy()
    right = right.sort_values(
        [
            "eligibility_observed_ts_utc",
            "issue",
            "match_idx",
            "eligibility_match_id",
            "source_attribute",
        ],
        kind="mergesort",
    ).drop_duplicates(
        ["issue", "match_idx", "eligibility_observed_ts_utc"], keep="last"
    )
    right["_eligibility_time"] = pd.to_datetime(
        right["eligibility_observed_ts_utc"], utc=True
    )
    left = roster.copy()
    left["_epoch_time"] = pd.to_datetime(left["decision_epoch_utc"], utc=True)
    left = left.sort_values(
        ["_epoch_time", "issue", "match_idx"], kind="mergesort"
    )
    right = right.sort_values(
        ["_eligibility_time", "issue", "match_idx"], kind="mergesort"
    )
    merged = pd.merge_asof(
        left,
        right,
        left_on="_epoch_time",
        right_on="_eligibility_time",
        by=["issue", "match_idx"],
        direction="backward",
        allow_exact_matches=True,
    )
    return merged.sort_values("_row_order", kind="mergesort").reset_index(drop=True)


def _rejection_reason(row: pd.Series) -> str:
    reasons: list[str] = []
    if row["evaluation_status"] != "EVALUATED":
        reasons.append(str(row["evaluation_status"]))
    if not bool(row["identity_known_at_epoch"]):
        reasons.append("IDENTITY_NOT_TIMESTAMPED_AT_EPOCH")
    if not bool(row["not_started_at_epoch"]):
        reasons.append("MATCH_ALREADY_STARTED")
    if str(row.get("sale_status") or "") != "open":
        reasons.append("SALE_OPEN_NOT_VERIFIED")
    if str(row.get("parlay_allowed") or "") != "allowed":
        reasons.append("PARLAY_ALLOWED_NOT_VERIFIED")
    if not bool(row["market_clock_safe"]):
        reasons.append("CAUSAL_MARKET_SNAPSHOT_UNAVAILABLE")
    elif not bool(row["core_market_sp_complete"]):
        reasons.append("CORE_EURO_BJ_SP_INCOMPLETE")
    return ";".join(reasons) if reasons else "INCLUDED"


def _strict_inference_tables(
    roster: pd.DataFrame,
    epochs: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    strict = roster[roster["strict_complete_eligible_match"]].copy()
    strict = strict.sort_values(
        ["epoch_id", "match_idx", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    roster_columns = [
        "epoch_id",
        "issue",
        "cohort",
        "match_id",
        "match_idx",
        "decision_epoch_utc",
        "kickoff_ts_utc",
        "identity_observed_ts_utc",
        "sale_status",
        "parlay_allowed",
        "eligibility_observed_ts_utc",
        "market_observed_ts_utc",
        "source_row_sha256",
    ]
    strict_roster = strict.reindex(columns=roster_columns).copy()
    identity_columns = [
        "cell_join_key",
        "epoch_id",
        "issue",
        "cohort",
        "epoch_rule",
        "decision_epoch_utc",
        "match_id",
        "match_idx",
        "match_order",
        "kickoff_ts_utc",
        "outcome_code",
        "outcome_order",
    ]
    if strict.empty:
        identity = pd.DataFrame(columns=identity_columns)
        values = pd.DataFrame(columns=["cell_join_key", *FEATURE_NAMES])
        masks = pd.DataFrame(columns=["cell_join_key", *FEATURE_NAMES])
        for feature in FEATURE_NAMES:
            values[feature] = values[feature].astype("float32")
            masks[feature] = masks[feature].astype(bool)
        return {
            "epoch_identity": epochs.copy(),
            "roster": strict_roster,
            "cell_identity": identity,
            "feature_values": values,
            "feature_masks": masks,
        }

    strict["match_order"] = strict.groupby("epoch_id", sort=False).cumcount()
    cells = strict.loc[strict.index.repeat(len(OUTCOME_ORDER))].reset_index(drop=True)
    cells["outcome_code"] = np.tile(OUTCOME_ORDER, len(strict))
    cells["outcome_order"] = np.tile(
        np.arange(len(OUTCOME_ORDER), dtype=np.int8), len(strict)
    )
    cells["cell_join_key"] = [
        epoch_cell_key(str(epoch), str(match), str(outcome))
        for epoch, match, outcome in zip(
            cells["epoch_id"],
            cells["match_id"],
            cells["outcome_code"],
            strict=True,
        )
    ]
    identity = cells.loc[:, identity_columns].copy()
    values = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    for feature in FEATURE_NAMES:
        values[feature] = np.nan
    values["outcome_code_numeric"] = pd.to_numeric(cells["outcome_code"])
    outcome_sources = {
        "3": ("sp_3", "eu_h", 0),
        "1": ("sp_1", "eu_d", 1),
        "0": ("sp_0", "eu_a", 2),
    }
    for code, (sp_column, euro_column, position) in outcome_sources.items():
        selected = cells["outcome_code"].eq(code)
        values.loc[selected, "bj_sp_snapshot"] = pd.to_numeric(
            cells.loc[selected, sp_column], errors="coerce"
        )
        values.loc[selected, "euro_1h_odds"] = pd.to_numeric(
            cells.loc[selected, euro_column], errors="coerce"
        )
        values.loc[selected, "devig_euro_probability"] = cells.loc[
            selected, f"devig_p{code}"
        ]
    decision = pd.to_datetime(cells["decision_epoch_utc"], utc=True)
    observed = pd.to_datetime(cells["market_observed_ts_utc"], utc=True)
    kickoff = pd.to_datetime(cells["kickoff_ts_utc"], utc=True)
    values["bj_sp_snapshot_age_minutes"] = (
        decision - observed
    ).dt.total_seconds() / 60.0
    values["native_handicap_line"] = pd.to_numeric(
        cells["native_handicap_line"], errors="coerce"
    )
    values["league_index"] = pd.to_numeric(
        cells["league_index"], errors="coerce"
    )
    values["home_team_index"] = pd.to_numeric(
        cells["home_team_index"], errors="coerce"
    )
    values["away_team_index"] = pd.to_numeric(
        cells["away_team_index"], errors="coerce"
    )
    values["kickoff_delay_hours"] = (
        kickoff - decision
    ).dt.total_seconds() / 3600.0
    values["match_position_fraction"] = pd.to_numeric(
        cells["match_position_fraction"], errors="coerce"
    )
    values["calendar_year"] = pd.to_numeric(cells["year"], errors="coerce")
    for feature in FEATURE_NAMES:
        values[feature] = values[feature].astype("float32")
    masks = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    for feature in FEATURE_NAMES:
        masks[feature] = np.isfinite(values[feature].to_numpy(dtype=np.float64))
        values.loc[~masks[feature], feature] = np.nan
    return {
        "epoch_identity": epochs.copy(),
        "roster": strict_roster,
        "cell_identity": identity,
        "feature_values": values,
        "feature_masks": masks,
    }


def _coverage_tables(
    roster: pd.DataFrame,
    epochs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    grouped = roster.groupby("epoch_id", sort=False)
    epoch_diagnostics = grouped.agg(
        issue=("issue", "first"),
        cohort=("cohort", "first"),
        epoch_rule=("epoch_rule", "first"),
        decision_epoch_utc=("decision_epoch_utc", "first"),
        evaluation_status=("evaluation_status", "first"),
        denominator_matches=("match_id", "size"),
        identity_known_matches=("identity_known_at_epoch", "sum"),
        not_started_matches=("not_started_at_epoch", "sum"),
        candidate_matches=("candidate_roster", "sum"),
        causal_market_matches=("market_clock_safe", "sum"),
        causal_core_complete_matches=("core_market_sp_complete", "sum"),
        eligibility_clock_safe_matches=("eligibility_clock_safe", "sum"),
        sale_open_matches=("sale_open_verified", "sum"),
        parlay_allowed_matches=("parlay_allowed_verified", "sum"),
        strict_complete_eligible_matches=("strict_complete_eligible_match", "sum"),
        named_euro_rows=("named_euro_present", "sum"),
        named_predicted_sp_rows=("named_predicted_sp_present", "sum"),
        post_epoch_market_violations=("post_epoch_market_violation", "sum"),
        started_match_violations=("started_match_in_strict_roster", "sum"),
    ).reset_index()
    epoch_diagnostics["n7_gate_pass"] = epoch_diagnostics[
        "strict_complete_eligible_matches"
    ].ge(REPRESENTATIVE_GATE.minimum_complete_matches_per_epoch)
    epoch_diagnostics["potential_core_rate"] = np.where(
        epoch_diagnostics["candidate_matches"].gt(0),
        epoch_diagnostics["causal_core_complete_matches"]
        / epoch_diagnostics["candidate_matches"],
        0.0,
    )
    epoch_diagnostics["strict_core_rate"] = np.where(
        epoch_diagnostics["candidate_matches"].gt(0),
        epoch_diagnostics["strict_complete_eligible_matches"]
        / epoch_diagnostics["candidate_matches"],
        0.0,
    )
    coverage = (
        epoch_diagnostics.groupby(["cohort", "epoch_rule"], sort=True)
        .agg(
            issues=("issue", "nunique"),
            epochs=("epoch_id", "size"),
            evaluated_epochs=(
                "evaluation_status",
                lambda values: int(values.eq("EVALUATED").sum()),
            ),
            candidate_matches=("candidate_matches", "sum"),
            causal_core_complete_matches=("causal_core_complete_matches", "sum"),
            strict_complete_eligible_matches=(
                "strict_complete_eligible_matches",
                "sum",
            ),
            n7_passing_epochs=("n7_gate_pass", "sum"),
        )
        .reset_index()
    )
    coverage["potential_core_rate"] = np.where(
        coverage["candidate_matches"].gt(0),
        coverage["causal_core_complete_matches"] / coverage["candidate_matches"],
        0.0,
    )
    coverage["strict_core_rate"] = np.where(
        coverage["candidate_matches"].gt(0),
        coverage["strict_complete_eligible_matches"]
        / coverage["candidate_matches"],
        0.0,
    )
    coverage["n7_epoch_pass_rate"] = np.where(
        coverage["evaluated_epochs"].gt(0),
        coverage["n7_passing_epochs"] / coverage["evaluated_epochs"],
        0.0,
    )
    required_cohorts = (
        "development",
        "historical_model_unseen",
        "prospective_post_activation",
    )
    gate_rows: list[dict[str, Any]] = []
    minimum_issues = {
        "development": REPRESENTATIVE_GATE.minimum_evaluated_issues_development,
        "historical_model_unseen": (
            REPRESENTATIVE_GATE.minimum_evaluated_issues_historical_model_unseen
        ),
        "prospective_post_activation": (
            REPRESENTATIVE_GATE.minimum_evaluated_issues_prospective_post_activation
        ),
    }
    for cohort in required_cohorts:
        scoped = epoch_diagnostics[
            epoch_diagnostics["cohort"].eq(cohort)
            & epoch_diagnostics["evaluation_status"].eq("EVALUATED")
        ]
        candidate = int(scoped["candidate_matches"].sum())
        strict = int(scoped["strict_complete_eligible_matches"].sum())
        issue_count = int(scoped["issue"].nunique())
        epoch_count = len(scoped)
        n7_pass = int(scoped["n7_gate_pass"].sum())
        pass_rate = n7_pass / epoch_count if epoch_count else 0.0
        core_rate = strict / candidate if candidate else 0.0
        cohort_pass = (
            issue_count >= minimum_issues[cohort]
            and pass_rate >= REPRESENTATIVE_GATE.minimum_epoch_pass_rate
            and core_rate >= REPRESENTATIVE_GATE.minimum_core_cell_coverage
        )
        gate_rows.append(
            {
                "cohort": cohort,
                "evaluated_issues": issue_count,
                "required_issues": minimum_issues[cohort],
                "evaluated_epochs": epoch_count,
                "n7_passing_epochs": n7_pass,
                "n7_epoch_pass_rate": pass_rate,
                "required_epoch_pass_rate": (
                    REPRESENTATIVE_GATE.minimum_epoch_pass_rate
                ),
                "candidate_matches": candidate,
                "strict_complete_eligible_matches": strict,
                "strict_core_coverage": core_rate,
                "required_core_coverage": (
                    REPRESENTATIVE_GATE.minimum_core_cell_coverage
                ),
                "cohort_gate_pass": cohort_pass,
            }
        )
    gate = pd.DataFrame(gate_rows)
    violations = {
        "post_epoch_market_observations": int(
            roster["post_epoch_market_violation"].sum()
        ),
        "started_matches_in_strict_roster": int(
            roster["started_match_in_strict_roster"].sum()
        ),
        "heldout_outcome_columns": 0,
    }
    ready = bool(gate["cohort_gate_pass"].all()) and not any(violations.values())
    decision = {
        "disposition": (
            "READY_FOR_204" if ready else "BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT"
        ),
        "gate_id": REPRESENTATIVE_GATE.gate_id,
        "gate": REPRESENTATIVE_GATE.as_dict(),
        "cohort_results": gate.to_dict(orient="records"),
        "violations": violations,
        "blocking_facts": [] if ready else [
            "No source supplies verified p34 sale-open and parlay-allowed state at decision epochs.",
            "Historical named 1h/10h fields lack observation timestamps and remain diagnostic-only.",
            "The prospective post-activation cohort has fewer than two evaluated issues.",
        ],
        "authority": (
            "Data capability only; no model training, betting, ROI, release or "
            "execution authority. #204 remains blocked until PI accepts READY_FOR_204."
        ),
    }
    return epoch_diagnostics, coverage, gate, decision


def _assemble_frames(
    base_matches: pd.DataFrame,
    live_matches: pd.DataFrame,
    market_observations: pd.DataFrame,
    eligibility_observations: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    source_freeze_cutoff_utc: str,
) -> dict[str, Any]:
    extra = live_matches[
        ~live_matches["match_id"].astype(str).isin(base_matches["match_id"].astype(str))
    ].copy()
    matches = pd.concat([base_matches, extra], ignore_index=True, sort=False)
    matches = matches.sort_values(
        ["feature_cutoff_ts_utc", "issue", "match_idx", "match_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    if matches["match_id"].duplicated().any():
        raise DecisionEpochBuildError("match identity is not unique")
    epochs = _epoch_family(
        matches,
        windows,
        source_freeze_cutoff_utc=source_freeze_cutoff_utc,
    )
    roster = _roster_cross_join(matches, epochs)
    roster = _merge_latest_market(roster, market_observations)
    roster = _merge_latest_eligibility(roster, eligibility_observations)
    decision_time = pd.to_datetime(roster["decision_epoch_utc"], utc=True)
    market_time = pd.to_datetime(
        roster["market_observed_ts_utc"], utc=True, errors="coerce"
    )
    eligibility_time = pd.to_datetime(
        roster["eligibility_observed_ts_utc"], utc=True, errors="coerce"
    )
    source_time = pd.to_datetime(
        roster["source_updated_at_utc"], utc=True, errors="coerce"
    )
    roster["post_epoch_market_violation"] = market_time.gt(decision_time).fillna(False)
    roster["market_clock_safe"] = market_time.notna() & market_time.le(decision_time)
    roster["eligibility_clock_safe"] = (
        eligibility_time.notna()
        & eligibility_time.le(decision_time)
        & source_time.notna()
        & source_time.le(decision_time)
    )
    eligibility_id = roster["eligibility_match_id"].fillna("").astype(str)
    roster["eligibility_identity_safe"] = eligibility_id.eq("") | eligibility_id.eq(
        roster["match_id"].astype(str)
    )
    roster["sale_status"] = roster["sale_status"].fillna("").astype(str).str.lower()
    roster["parlay_allowed"] = (
        roster["parlay_allowed"].fillna("").astype(str).str.lower()
    )
    roster["sale_open_verified"] = (
        roster["eligibility_clock_safe"]
        & roster["eligibility_identity_safe"]
        & roster["sale_status"].eq("open")
    )
    roster["parlay_allowed_verified"] = (
        roster["eligibility_clock_safe"]
        & roster["eligibility_identity_safe"]
        & roster["parlay_allowed"].isin({"allowed", "true", "yes"})
    )
    roster.loc[roster["parlay_allowed_verified"], "parlay_allowed"] = "allowed"
    roster["bj_sp_complete"] = _complete_triplet(roster, ("sp_3", "sp_1", "sp_0"))
    roster["euro_complete"] = _complete_triplet(roster, ("eu_h", "eu_d", "eu_a"))
    odds = roster.loc[:, ["eu_h", "eu_d", "eu_a"]].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype=float)
    inverse = np.full_like(odds, np.nan)
    valid = np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)
    inverse[valid] = 1.0 / odds[valid]
    devig = np.full_like(odds, np.nan)
    devig[valid] = inverse[valid] / inverse[valid].sum(axis=1, keepdims=True)
    roster[["devig_p3", "devig_p1", "devig_p0"]] = devig
    roster["core_market_sp_complete"] = (
        roster["candidate_roster"]
        & roster["market_clock_safe"]
        & roster["bj_sp_complete"]
        & roster["euro_complete"]
    )
    roster["strict_complete_eligible_match"] = (
        roster["core_market_sp_complete"]
        & roster["sale_open_verified"]
        & roster["parlay_allowed_verified"]
    )
    roster["started_match_in_strict_roster"] = (
        roster["strict_complete_eligible_match"]
        & ~roster["not_started_at_epoch"]
    )
    roster["source_row_sha256"] = ""
    selected_market = roster["market_snapshot_id"].notna()
    roster.loc[selected_market, "source_row_sha256"] = roster.loc[
        selected_market
    ].apply(_source_row_sha256, axis=1)
    roster["rejection_reason"] = roster.apply(_rejection_reason, axis=1)
    inference = _strict_inference_tables(roster, epochs)
    epoch_diagnostics, coverage, gate, decision = _coverage_tables(roster, epochs)
    selected_market_ids = set(
        roster.loc[selected_market, "market_snapshot_id"].astype("int64")
    )
    selected_market_sources = market_observations[
        market_observations["id"].astype("int64").isin(selected_market_ids)
    ].copy()
    eligibility_keys = set(
        zip(
            roster["issue"].astype(str),
            roster["match_idx"].astype(int),
            roster["eligibility_observed_ts_utc"].fillna("").astype(str),
            strict=False,
        )
    )
    eligibility_keys.discard(("", 0, ""))
    selected_eligibility = eligibility_observations[
        [
            (str(row.issue), int(row.match_idx), str(row.fetched_at_utc))
            in eligibility_keys
            for row in eligibility_observations.itertuples(index=False)
        ]
    ].copy()
    roster_public_columns = [
        "epoch_id",
        "issue",
        "cohort",
        "epoch_rule",
        "decision_epoch_utc",
        "evaluation_status",
        "match_id",
        "match_idx",
        "kickoff_ts_utc",
        "identity_observed_ts_utc",
        "identity_timing_status",
        "identity_known_at_epoch",
        "not_started_at_epoch",
        "candidate_roster",
        "market_snapshot_id",
        "market_observed_ts_utc",
        "market_source",
        "market_clock_safe",
        "eligibility_observed_ts_utc",
        "source_updated_at_utc",
        "sale_status",
        "parlay_allowed",
        "capture_classification",
        "eligibility_clock_safe",
        "eligibility_identity_safe",
        "bj_sp_complete",
        "euro_complete",
        "core_market_sp_complete",
        "sale_open_verified",
        "parlay_allowed_verified",
        "strict_complete_eligible_match",
        "named_calibrated_present",
        "named_euro_present",
        "named_predicted_sp_present",
        "source_row_sha256",
        "rejection_reason",
    ]
    roster_public = roster.reindex(columns=roster_public_columns).copy()
    return {
        "matches": matches,
        "epochs": epochs,
        "roster_capability": roster_public,
        "selected_market_sources": selected_market_sources,
        "selected_eligibility_sources": selected_eligibility,
        "inference": inference,
        "epoch_diagnostics": epoch_diagnostics,
        "coverage": coverage,
        "gate": gate,
        "decision": decision,
    }


def _namespace_manifest(directory: Path, namespace: str) -> dict[str, Any]:
    files = {
        path.relative_to(directory).as_posix(): digest(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "namespace": namespace,
        "files": files,
    }
    write_json(directory / "MANIFEST.json", manifest)
    return manifest


def _implementation_hashes() -> dict[str, str]:
    paths = {
        "builder": Path(__file__),
        "contract": Path(__file__).with_name("contract.py"),
        "loader": Path(__file__).with_name("loader.py"),
        "cli": ROOT / "scripts/build_bj214_decision_epoch_tensor.py",
        "notebook_executor": ROOT / "scripts/execute_bj214_notebook.py",
        "environment_lock": ENVIRONMENT_LOCK,
    }
    return {name: digest(path) for name, path in paths.items()}


def _source_dictionary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "logical_source": "bj203_causal_tensor_v2",
                "fields": "identity, schedule, static feature capability",
                "timestamp_rule": "preserve #203 identity timing status",
                "provenance_grade": "IMMUTABLE_PACKAGE",
                "admissible_use": "identity and named-field presence diagnostics",
                "limitation": "named 1h/10h fields lack observation clocks for #214",
            },
            {
                "logical_source": "beidan_live.snapshots",
                "fields": "timestamped p34 BJ SP and EURO odds",
                "timestamp_rule": "snapshot_ts_utc <= decision_epoch_utc",
                "provenance_grade": "TIMESTAMPED_APPEND_ONLY_NO_RAW_BUNDLE",
                "admissible_use": "potential causal market/SP coverage",
                "limitation": "source=merged; no sale/parlay evidence",
            },
            {
                "logical_source": "500_bjdc.live_market_sp_snapshots:p34",
                "fields": "sale/parlay/capture classification",
                "timestamp_rule": (
                    "fetched_at_utc and source_updated_at_utc <= decision_epoch_utc"
                ),
                "provenance_grade": "TIMESTAMPED_UNPUBLISHED_NO_CAPTURE_BATCH",
                "admissible_use": "eligibility evidence only when explicit",
                "limitation": "all frozen p34 rows report unknown/unknown",
            },
            {
                "logical_source": "500_bjdc.segment_decision_windows",
                "fields": "published operational segment epochs and membership",
                "timestamp_rule": "manual_frozen_at else freeze_at",
                "provenance_grade": "PUBLISHED_OPERATIONAL_CONTRACT",
                "admissible_use": "epoch identity and denominator",
                "limitation": "available only for recent operational issues",
            },
        ]
    )


def _feature_dictionary() -> pd.DataFrame:
    frame = pd.DataFrame(FEATURE_DICTIONARY)
    frame.insert(0, "feature_order", np.arange(len(frame), dtype=np.int16))
    frame["decision_epoch_capability"] = "STATIC_OR_UNSUPPORTED"
    frame.loc[
        frame["name"].isin(CORE_FEATURES), "decision_epoch_capability"
    ] = "TIMESTAMPED_LIVE_WHERE_AVAILABLE"
    frame.loc[
        frame["name"].isin(
            {
                "calibrated_market_probability",
                "predicted_final_sp",
            }
        ),
        "decision_epoch_capability",
    ] = "UNSUPPORTED_WITHOUT_OBSERVATION_TIMESTAMP"
    frame.loc[
        frame["name"].isin(
            {
                "outcome_code_numeric",
                "native_handicap_line",
                "league_index",
                "home_team_index",
                "away_team_index",
                "kickoff_delay_hours",
                "match_position_fraction",
                "calendar_year",
            }
        ),
        "decision_epoch_capability",
    ] = "IDENTITY_STATIC_WHEN_STRICT_ROSTER_ELIGIBLE"
    return frame


def _load_frozen_sources(source_directory: Path) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    directory = source_directory.expanduser().resolve()
    manifest_path = directory / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DecisionEpochBuildError("invalid frozen source manifest") from exc
    if (
        manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("namespace") != "frozen_source_whitelists"
        or set(manifest.get("files", {})) != set(SOURCE_FILES)
    ):
        raise DecisionEpochBuildError("frozen source namespace drift")
    paths = list(directory.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise DecisionEpochBuildError("frozen source namespace contains a symlink")
    actual = {
        path.relative_to(directory).as_posix()
        for path in paths
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if actual != set(SOURCE_FILES):
        raise DecisionEpochBuildError("frozen source file census drift")
    for relative, expected in manifest["files"].items():
        if digest(directory / relative) != expected:
            raise DecisionEpochBuildError(f"frozen source hash mismatch: {relative}")
    if (
        EXPECTED_SOURCE_MANIFEST_SHA256
        and digest(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256
    ):
        raise DecisionEpochBuildError("frozen source identity differs from exact lock")
    metadata = json.loads((directory / "source_freeze.json").read_text(encoding="utf-8"))
    return (
        pd.read_parquet(directory / "base_match_capability.parquet"),
        pd.read_parquet(directory / "live_match_identity.parquet"),
        pd.read_parquet(directory / "selected_market_observations.parquet"),
        pd.read_parquet(directory / "selected_eligibility_observations.parquet"),
        pd.read_parquet(directory / "segment_windows.parquet"),
        metadata,
    )


def _write_frozen_sources(
    directory: Path,
    *,
    base_matches: pd.DataFrame,
    live_matches: pd.DataFrame,
    selected_market: pd.DataFrame,
    selected_eligibility: pd.DataFrame,
    windows: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    write_parquet(directory / "base_match_capability.parquet", base_matches)
    write_parquet(directory / "live_match_identity.parquet", live_matches)
    write_parquet(
        directory / "selected_market_observations.parquet", selected_market
    )
    write_parquet(
        directory / "selected_eligibility_observations.parquet",
        selected_eligibility,
    )
    write_parquet(directory / "segment_windows.parquet", windows)
    metadata = {
        **metadata,
        "frozen_source_census": {
            "base_matches": len(base_matches),
            "live_matches": len(live_matches),
            "selected_market_observations": len(selected_market),
            "selected_eligibility_observations": len(selected_eligibility),
            "segment_windows": len(windows),
        },
        "upstream_package": {
            "contract_version": UPSTREAM_CONTRACT_VERSION,
            "manifest_sha256": digest(UPSTREAM_PACKAGE / "MANIFEST.json"),
            "sha256sums_sha256": digest(UPSTREAM_PACKAGE / "SHA256SUMS.json"),
        },
        "outcome_namespace_read": False,
    }
    write_json(directory / "source_freeze.json", metadata)
    _namespace_manifest(directory, "frozen_source_whitelists")


def _write_analysis_figure(coverage: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    plotted = coverage[
        coverage["epoch_rule"].isin(
            {
                "ISSUE_START",
                "MEDIAN_KICKOFF_MINUS_10H",
                "MEDIAN_KICKOFF_MINUS_1H",
                "PUBLISHED_SEGMENT_FREEZE",
                "PROSPECTIVE_ACTIVATION",
            }
        )
    ].copy()
    plotted["label"] = plotted["cohort"] + "\n" + plotted["epoch_rule"]
    figure, axis = plt.subplots(figsize=(12, 6), constrained_layout=True)
    positions = np.arange(len(plotted), dtype=float)
    axis.bar(
        positions - 0.18,
        plotted["potential_core_rate"],
        width=0.36,
        label="timestamped EURO+BJ-SP potential",
    )
    axis.bar(
        positions + 0.18,
        plotted["strict_core_rate"],
        width=0.36,
        label="strict sale+parlay eligible",
    )
    axis.axhline(
        REPRESENTATIVE_GATE.minimum_core_cell_coverage,
        color="black",
        linestyle="--",
        linewidth=1,
        label="predeclared support threshold",
    )
    axis.set_ylim(0, 1.05)
    axis.set_ylabel("matched causal core coverage")
    axis.set_xticks(positions, plotted["label"], rotation=65, ha="right", fontsize=7)
    axis.set_title("#214 decision-epoch market/SP capability")
    axis.legend(loc="upper left")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150, metadata={"Software": "matplotlib"})
    plt.close(figure)


def _decision_report(decision: dict[str, Any]) -> str:
    rows = decision["cohort_results"]
    lines = [
        "# #214 decision-epoch market/SP capability",
        "",
        f"Disposition: **{decision['disposition']}**.",
        "",
        "| cohort | evaluated issues | evaluated epochs | N7 epoch pass rate | strict core coverage | gate |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {cohort} | {evaluated_issues} / {required_issues} | "
            "{evaluated_epochs} | {n7_epoch_pass_rate:.2%} | "
            "{strict_core_coverage:.2%} | {gate} |".format(
                **row,
                gate="PASS" if row["cohort_gate_pass"] else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            "The package distinguishes timestamped price availability from strict ticket eligibility. "
            "p34 price observations exist, but the frozen source exposes neither verified sale-open "
            "nor parlay-allowed state. Named historical 1h/10h fields are diagnostic-only because "
            "they do not carry observation timestamps.",
            "",
            "#204 remains blocked. A future Data capability must capture p34 sale/parlay state and "
            "immutable raw provenance at the same decision epochs, then satisfy the predeclared gate. "
            "This negative result grants no model, betting, ROI, release or execution authority.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_package_outputs(output: Path, assembled: dict[str, Any]) -> None:
    inference = output / "inference"
    audit = output / "audit"
    analysis = output / "analysis"
    inference.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)
    analysis.mkdir(parents=True, exist_ok=True)
    for name, frame in assembled["inference"].items():
        write_parquet(inference / f"{name}.parquet", frame)
    _namespace_manifest(inference, "decision_epoch_outcome_unexposed_inference")
    write_parquet(audit / "roster_capability.parquet", assembled["roster_capability"])
    write_csv(audit / "epoch_roster_diagnostics.csv", assembled["epoch_diagnostics"])
    write_csv(audit / "coverage_by_cohort_rule.csv", assembled["coverage"])
    write_csv(audit / "representative_support_gate.csv", assembled["gate"])
    rejections = (
        assembled["roster_capability"]
        .groupby(
            ["cohort", "epoch_rule", "rejection_reason"],
            sort=True,
            dropna=False,
        )
        .size()
        .rename("match_epoch_rows")
        .reset_index()
    )
    write_csv(audit / "rejection_summary.csv", rejections)
    source_census = pd.DataFrame(
        [
            {"artifact": "epochs", "rows": len(assembled["epochs"])},
            {
                "artifact": "roster_capability",
                "rows": len(assembled["roster_capability"]),
            },
            {
                "artifact": "strict_roster",
                "rows": len(assembled["inference"]["roster"]),
            },
            {
                "artifact": "strict_cells",
                "rows": len(assembled["inference"]["cell_identity"]),
            },
            {
                "artifact": "selected_market_sources",
                "rows": len(assembled["selected_market_sources"]),
            },
            {
                "artifact": "selected_eligibility_sources",
                "rows": len(assembled["selected_eligibility_sources"]),
            },
        ]
    )
    write_csv(audit / "source_census.csv", source_census)
    write_csv(output / "feature_dictionary.csv", _feature_dictionary())
    write_csv(output / "source_dictionary.csv", _source_dictionary())
    write_json(output / "representative_support_gate.json", REPRESENTATIVE_GATE.as_dict())
    write_json(analysis / "decision.json", assembled["decision"])
    (analysis / "DECISION_REPORT.md").write_text(
        _decision_report(assembled["decision"]), encoding="utf-8", newline="\n"
    )
    _write_analysis_figure(
        assembled["coverage"], analysis / "decision_epoch_coverage.png"
    )
    schema = {
        "contract_version": CONTRACT_VERSION,
        "upstream_contract_version": UPSTREAM_CONTRACT_VERSION,
        "object": "X_i,t[J_i,t x 3 x F]",
        "outcome_order": list(OUTCOME_ORDER),
        "feature_order": list(FEATURE_NAMES),
        "epoch_rules": list(EPOCH_RULES),
        "cohorts": list(COHORTS),
        "strict_roster_definition": (
            "identity observed by t AND kickoff after t AND sale_status=open "
            "AND parlay_allowed=allowed AND complete timestamped 3-way EURO/BJ SP"
        ),
        "masked_value": "NaN with mask=false",
        "labels": "PHYSICALLY_ABSENT",
    }
    write_json(output / "schema.json", schema)
    data_card = f"""# #214 causal decision-epoch tensor

Contract: `{CONTRACT_VERSION}`. Upstream: `{UPSTREAM_CONTRACT_VERSION}`.

The operative interface is `X_{{i,t}}[J_{{i,t}} x 3 x F]`. Epochs are fixed from
issue cutoffs, schedule-only first/median/last kickoff anchors, published segment
windows, and the prospective activation timestamp. Outcomes never choose an epoch.

`J_{{i,t}}` is strict: identity must be observed by `t`, kickoff must follow `t`,
sale must be explicitly open, parlay permission explicitly allowed, and all three
timestamped EURO and Beijing SP values must be complete. Unknown is not allowed.

Historical named 1h/10h fields are retained only as presence diagnostics because
they lack observation timestamps. They are not unmasked by this package. The
retrospective held-out cohort preserves the #203 model-unseen/label-embargoed claim;
it is not described as organization-wide untouched. The prospective cohort begins
at `{ACTIVATION_UTC}` and contains no outcome namespace.

Disposition: **{assembled['decision']['disposition']}**. #204 remains blocked unless
PI accepts `READY_FOR_204`. This package trains no model, ranks no bet, computes no
ROI, and grants no release or execution authority.
"""
    (output / "DATA_CARD.md").write_text(data_card, encoding="utf-8", newline="\n")
    replay = """# Deterministic replay

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py verify \\
  --package results/bj214_decision_epoch_tensor_v1

PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py replay \\
  --source-package results/bj214_decision_epoch_tensor_v1 \\
  --output <new-empty-directory>

PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py compare \\
  --frozen results/bj214_decision_epoch_tensor_v1 \\
  --replay <new-empty-directory>

PYTHONPATH=src $PY scripts/execute_bj214_notebook.py
```

Replay reads only the locked source namespace embedded in the package. It never
opens runtime databases or any settlement/result table.
"""
    (output / "REPLAY.md").write_text(replay, encoding="utf-8", newline="\n")
    root_manifest = {
        "contract_version": CONTRACT_VERSION,
        "upstream_contract_version": UPSTREAM_CONTRACT_VERSION,
        "source_manifest_sha256": digest(output / "sources/MANIFEST.json"),
        "inference_manifest_sha256": digest(inference / "MANIFEST.json"),
        "implementation_hashes": _implementation_hashes(),
        "decision_sha256": digest(analysis / "decision.json"),
        "decision_report_sha256": digest(analysis / "DECISION_REPORT.md"),
        "disposition": assembled["decision"]["disposition"],
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "authority": {
            "model_training": False,
            "betting": False,
            "roi": False,
            "release": False,
            "execution": False,
        },
        "census": {
            "epochs": len(assembled["epochs"]),
            "roster_capability_rows": len(assembled["roster_capability"]),
            "strict_roster_rows": len(assembled["inference"]["roster"]),
            "strict_cells": len(assembled["inference"]["cell_identity"]),
        },
    }
    write_json(output / "MANIFEST.json", root_manifest)
    sums = {
        path.relative_to(output).as_posix(): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    write_json(output / "SHA256SUMS.json", sums)


def build_package(
    output: Path,
    *,
    live_database: Path | None = None,
    market_database: Path | None = None,
    source_package: Path | None = None,
    source_freeze_cutoff_utc: str | None = None,
) -> dict[str, Any]:
    output = output.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise DecisionEpochBuildError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    source_dir = output / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    if source_package is not None:
        frozen_source_dir = source_package.expanduser().resolve() / "sources"
        _load_frozen_sources(frozen_source_dir)
        for name in (*SOURCE_FILES, "MANIFEST.json"):
            shutil.copyfile(frozen_source_dir / name, source_dir / name)
    else:
        if live_database is None or market_database is None:
            raise DecisionEpochBuildError("runtime build requires both source databases")
        cutoff = source_freeze_cutoff_utc or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        base = _base_match_capability(UPSTREAM_PACKAGE)
        live, market, eligibility, windows, metadata = _extract_live_sources(
            live_database,
            market_database,
            source_freeze_cutoff_utc=cutoff,
        )
        initial = _assemble_frames(
            base,
            live,
            market,
            eligibility,
            windows,
            source_freeze_cutoff_utc=cutoff,
        )
        _write_frozen_sources(
            source_dir,
            base_matches=base,
            live_matches=live,
            selected_market=initial["selected_market_sources"],
            selected_eligibility=initial["selected_eligibility_sources"],
            windows=windows,
            metadata=metadata,
        )
    base, live, market, eligibility, windows, metadata = _load_frozen_sources(
        source_dir
    )
    assembled = _assemble_frames(
        base,
        live,
        market,
        eligibility,
        windows,
        source_freeze_cutoff_utc=str(metadata["source_freeze_cutoff_utc"]),
    )
    _write_package_outputs(output, assembled)
    return verify_package(output)


def _root_file_hashes(output: Path) -> dict[str, str]:
    return {
        path.relative_to(output).as_posix(): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def _assert_frame_exact(actual: pd.DataFrame, expected: pd.DataFrame, name: str) -> None:
    try:
        pd.testing.assert_frame_equal(
            actual,
            expected,
            check_dtype=True,
            check_exact=True,
            check_like=False,
        )
    except AssertionError as exc:
        raise DecisionEpochBuildError(f"source-bound {name} drift") from exc


def _verify_source_bound_outputs(output: Path) -> dict[str, Any]:
    base, live, market, eligibility, windows, metadata = _load_frozen_sources(
        output / "sources"
    )
    expected = _assemble_frames(
        base,
        live,
        market,
        eligibility,
        windows,
        source_freeze_cutoff_utc=str(metadata["source_freeze_cutoff_utc"]),
    )
    for name, frame in expected["inference"].items():
        _assert_frame_exact(
            pd.read_parquet(output / f"inference/{name}.parquet"),
            frame,
            f"inference/{name}",
        )
    _assert_frame_exact(
        pd.read_parquet(output / "audit/roster_capability.parquet"),
        expected["roster_capability"],
        "roster capability",
    )
    for relative, frame in (
        ("audit/epoch_roster_diagnostics.csv", expected["epoch_diagnostics"]),
        ("audit/coverage_by_cohort_rule.csv", expected["coverage"]),
        ("audit/representative_support_gate.csv", expected["gate"]),
    ):
        actual = pd.read_csv(output / relative, keep_default_na=False)
        expected_csv = pd.read_csv(
            StringIO(frame.to_csv(index=False, lineterminator="\n", float_format="%.12g")),
            keep_default_na=False,
        )
        _assert_frame_exact(actual, expected_csv, relative)
    actual_decision = json.loads(
        (output / "analysis/decision.json").read_text(encoding="utf-8")
    )
    if actual_decision != expected["decision"]:
        raise DecisionEpochBuildError("source-bound decision drift")
    if (output / "analysis/DECISION_REPORT.md").read_text(
        encoding="utf-8"
    ) != _decision_report(expected["decision"]):
        raise DecisionEpochBuildError("source-bound decision report drift")
    return expected["decision"]


def verify_package(output: Path) -> dict[str, Any]:
    output = output.expanduser().resolve()
    if output.is_symlink() or not output.is_dir():
        raise DecisionEpochBuildError("package root is unavailable or a symlink")
    paths = list(output.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise DecisionEpochBuildError("package must not contain symlinks")
    try:
        sums = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
        manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DecisionEpochBuildError("invalid package manifest") from exc
    if not isinstance(sums, dict) or set(sums) != set(_root_file_hashes(output)):
        raise DecisionEpochBuildError("root package file census drift")
    for relative, expected_hash in sums.items():
        if digest(output / relative) != expected_hash:
            raise DecisionEpochBuildError(f"package hash mismatch: {relative}")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise DecisionEpochBuildError("root contract version drift")
    if manifest.get("upstream_contract_version") != UPSTREAM_CONTRACT_VERSION:
        raise DecisionEpochBuildError("upstream contract version drift")
    source_hash = digest(output / "sources/MANIFEST.json")
    if manifest.get("source_manifest_sha256") != source_hash:
        raise DecisionEpochBuildError("root source identity drift")
    if EXPECTED_SOURCE_MANIFEST_SHA256 and source_hash != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise DecisionEpochBuildError("source identity differs from exact package lock")
    if manifest.get("inference_manifest_sha256") != digest(
        output / "inference/MANIFEST.json"
    ):
        raise DecisionEpochBuildError("inference namespace identity drift")
    if manifest.get("implementation_hashes") != _implementation_hashes():
        raise DecisionEpochBuildError("implementation identity drift")
    if manifest.get("decision_sha256") != digest(output / "analysis/decision.json"):
        raise DecisionEpochBuildError("decision identity drift")
    if manifest.get("decision_report_sha256") != digest(
        output / "analysis/DECISION_REPORT.md"
    ):
        raise DecisionEpochBuildError("decision report identity drift")
    tensors = load_epoch_tensors(output)
    decision = _verify_source_bound_outputs(output)
    roster_rows = sum(len(tensor.match_ids) for tensor in tensors)
    cells = roster_rows * len(OUTCOME_ORDER)
    expected_census = {
        "epochs": len(tensors),
        "roster_capability_rows": len(
            pd.read_parquet(output / "audit/roster_capability.parquet")
        ),
        "strict_roster_rows": roster_rows,
        "strict_cells": cells,
    }
    if manifest.get("census") != expected_census:
        raise DecisionEpochBuildError("root census drift")
    return {
        "contract_version": CONTRACT_VERSION,
        "disposition": decision["disposition"],
        "epochs": len(tensors),
        "strict_roster_rows": roster_rows,
        "strict_cells": cells,
        "features": len(FEATURE_NAMES),
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "source_manifest_sha256": source_hash,
        "status": "PASS",
    }


def compare_packages(frozen: Path, replay: Path) -> dict[str, Any]:
    left = verify_package(frozen)
    right = verify_package(replay)
    left_files = _root_file_hashes(frozen.expanduser().resolve())
    right_files = _root_file_hashes(replay.expanduser().resolve())
    if left_files != right_files:
        differing = sorted(
            name for name in set(left_files) | set(right_files)
            if left_files.get(name) != right_files.get(name)
        )
        raise DecisionEpochBuildError(
            f"deterministic replay differs: {', '.join(differing)}"
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "files": len(left_files),
        "source_manifest_sha256": left["source_manifest_sha256"],
        "status": "PASS_IDENTICAL",
        "replay_status": right["status"],
    }
