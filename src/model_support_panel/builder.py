"""Build and verify the outcome-blind Issue #216 evidence package."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .contract import (
    ADMISSIBLE_SOURCE_COLUMNS,
    CONTRACT_VERSION,
    EXCLUDED_SOURCE_CLASSES,
    OUTCOME_ORDER,
    PROHIBITED_NAMESPACES,
    PROSPECTIVE_ACTIVATION_UTC,
    REPRESENTATIVE_EPOCH_RULE,
    SOURCE_BOUNDARY_PREREGISTERED_AT_UTC,
    SOURCE_TIMEZONE,
    SUPPORT_GATE,
    UPSTREAM_CONTRACT_VERSION,
    chronological_role,
)


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_LOCK = ROOT / "requirements.txt"
SOURCE_BOUNDARY_COMMIT = "23db9d207b2b1d98772f18ae0762a904cb64e9d2"
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "ad1060fdee801277b00e6a40c5e28722d9df8fae025e163c4c15ed7b0d32f76b"
)

FORBIDDEN_INFERENCE_PARTS = (
    "result",
    "score",
    "settlement",
    "winning",
    "official",
    "final_",
    "payout",
    "profit",
    "roi",
    "hit",
    "label",
)


class ModelSupportBuildError(RuntimeError):
    """Raised when the #216 package cannot be built or verified safely."""


def _inventory_exclusion_reason(logical_name: str) -> str:
    reasons = {
        "500_bjdc": EXCLUDED_SOURCE_CLASSES["500_live_p34_sp_only"],
        "xlsm_canonical": EXCLUDED_SOURCE_CLASSES["xlsm_named_snapshots"],
        "modeling_plus": EXCLUDED_SOURCE_CLASSES["xlsm_named_snapshots"],
        "nowscore_update": EXCLUDED_SOURCE_CLASSES["xlsm_named_snapshots"],
        "history_proxy": EXCLUDED_SOURCE_CLASSES["history_average_or_final_odds"],
        "feature_proxy": EXCLUDED_SOURCE_CLASSES["feature_open_close_proxies"],
    }
    return reasons.get(
        logical_name,
        "schema inventoried without reading values; source is outside the frozen v1 boundary",
    )


def _normalize_source_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["logical_source"] = result["logical_source"].astype(str)
    result["exclusion_reason"] = np.where(
        result["classification"].eq("ADMITTED_TIMESTAMPED_SAME_ROW_CORE"),
        "",
        result["logical_source"].map(_inventory_exclusion_reason),
    )
    columns = [
        "logical_source",
        "filename",
        "bytes",
        "table_name",
        "schema_sha256",
        "value_rows_read",
        "classification",
        "exclusion_reason",
    ]
    return result.loc[:, columns].sort_values(
        ["logical_source", "table_name"], kind="mergesort"
    ).reset_index(drop=True)


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
        raise ModelSupportBuildError(f"source database unavailable: {database}")
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
        converted = parsed.dt.tz_convert("UTC")
    else:
        converted = parsed.dt.tz_localize(
            SOURCE_TIMEZONE,
            ambiguous="raise",
            nonexistent="raise",
        ).dt.tz_convert("UTC")
    return converted.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _schema_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT name, sql
          FROM sqlite_master
         WHERE type='table'
         ORDER BY name
        """
    ).fetchall()


def _inventory_database(logical_name: str, database: Path) -> list[dict[str, Any]]:
    """Inventory schema only; never select table values."""

    with closing(_sqlite_snapshot(database)) as connection:
        rows = _schema_rows(connection)
    reason = _inventory_exclusion_reason(logical_name)
    return [
        {
            "logical_source": logical_name,
            "filename": database.name,
            "bytes": database.stat().st_size,
            "table_name": str(row["name"]),
            "schema_sha256": sha256(str(row["sql"]).encode("utf-8")).hexdigest(),
            "value_rows_read": 0,
            "classification": "SCHEMA_ONLY_EXCLUDED_SOURCE",
            "exclusion_reason": reason,
        }
        for row in rows
    ]


def _extract_runtime_source(
    live_database: Path,
    *,
    source_freeze_cutoff_utc: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cutoff = pd.Timestamp(source_freeze_cutoff_utc)
    if cutoff.tzinfo is None:
        raise ModelSupportBuildError("source freeze cutoff must include a timezone")
    cutoff_text = cutoff.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    with closing(_sqlite_snapshot(live_database)) as connection:
        available: dict[str, set[str]] = {}
        for table in ("matches", "snapshots"):
            available[table] = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            expected = set(ADMISSIBLE_SOURCE_COLUMNS[f"beidan_live.{table}"])
            missing = sorted(expected - available[table])
            if missing:
                raise ModelSupportBuildError(
                    f"beidan_live.{table} missing required columns: {missing}"
                )
        match_rows = connection.execute(
            """
            SELECT match_id, issue, match_idx, kickoff_ts, created_ts,
                   handicap_line
              FROM matches
             WHERE created_ts <= ?
             ORDER BY CAST(issue AS INTEGER), match_idx, match_id
            """,
            (cutoff_text,),
        ).fetchall()
        snapshot_rows = connection.execute(
            """
            SELECT id, match_id, snapshot_ts, sp_3, sp_1, sp_0,
                   eu_h, eu_d, eu_a, source
              FROM snapshots
             WHERE snapshot_ts <= ?
             ORDER BY snapshot_ts, match_id, id
            """,
            (cutoff_text,),
        ).fetchall()
        admitted_schema = "\n".join(
            str(row["sql"])
            for row in _schema_rows(connection)
            if row["name"] in {"matches", "snapshots"}
        )
    matches = pd.DataFrame([dict(row) for row in match_rows])
    snapshots = pd.DataFrame([dict(row) for row in snapshot_rows])
    if matches.empty or snapshots.empty:
        raise ModelSupportBuildError("admissible live source is empty")
    matches["match_id"] = matches["match_id"].astype(str)
    matches["issue"] = matches["issue"].astype(str)
    matches["match_idx"] = pd.to_numeric(matches["match_idx"], errors="raise").astype(
        "int32"
    )
    matches["kickoff_ts_utc"] = _hkt_naive_to_utc(matches.pop("kickoff_ts"))
    matches["identity_observed_ts_utc"] = _utc_text(matches.pop("created_ts"))
    matches["handicap_line"] = pd.to_numeric(
        matches["handicap_line"], errors="coerce"
    )
    snapshots["match_id"] = snapshots["match_id"].astype(str)
    snapshots["market_observed_ts_utc"] = _utc_text(snapshots.pop("snapshot_ts"))
    metadata = {
        "logical_source": "beidan_live",
        "filename": live_database.name,
        "bytes_at_read": live_database.stat().st_size,
        "schema_sha256": sha256(admitted_schema.encode("utf-8")).hexdigest(),
        "source_freeze_cutoff_utc": cutoff_text,
        "runtime_matches_read": len(matches),
        "runtime_snapshots_read": len(snapshots),
        "outcome_namespace_read": False,
    }
    return matches, snapshots, metadata


def _row_digest(values: Iterable[object]) -> str:
    return sha256(
        "|".join("" if pd.isna(value) else str(value) for value in values).encode(
            "utf-8"
        )
    ).hexdigest()


def _complete_triplet(frame: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    values = frame.loc[:, list(columns)].apply(pd.to_numeric, errors="coerce")
    return values.notna().all(axis=1) & np.isfinite(values).all(axis=1) & values.gt(
        1.0
    ).all(axis=1)


def _epoch_id(issue: str, decision_epoch_utc: str) -> str:
    return _row_digest(
        (CONTRACT_VERSION, issue, REPRESENTATIVE_EPOCH_RULE, decision_epoch_utc)
    )


def _panel_row_id(epoch_id: str, match_id: str, outcome_code: str) -> str:
    return _row_digest((CONTRACT_VERSION, epoch_id, match_id, outcome_code))


def assemble_panel(
    matches: pd.DataFrame,
    snapshots: pd.DataFrame,
    *,
    source_freeze_cutoff_utc: str,
) -> dict[str, Any]:
    """Create the controlling issue audit and feature panel from frozen rows."""

    required_matches = {
        "match_id",
        "issue",
        "match_idx",
        "kickoff_ts_utc",
        "identity_observed_ts_utc",
        "handicap_line",
    }
    required_snapshots = {
        "id",
        "match_id",
        "market_observed_ts_utc",
        "sp_3",
        "sp_1",
        "sp_0",
        "eu_h",
        "eu_d",
        "eu_a",
        "source",
    }
    if not required_matches.issubset(matches.columns):
        raise ModelSupportBuildError("frozen match source violates the contract")
    if not required_snapshots.issubset(snapshots.columns):
        raise ModelSupportBuildError("frozen snapshot source violates the contract")
    matches = matches.copy()
    snapshots = snapshots.copy()
    matches["match_id"] = matches["match_id"].astype(str)
    matches["issue"] = matches["issue"].astype(str)
    snapshots["match_id"] = snapshots["match_id"].astype(str)
    if matches["match_id"].duplicated().any():
        raise ModelSupportBuildError("duplicate match identity")
    cutoff = pd.Timestamp(source_freeze_cutoff_utc)
    if cutoff.tzinfo is None:
        raise ModelSupportBuildError("source freeze cutoff must include timezone")
    cutoff = cutoff.tz_convert("UTC")
    snapshot_time = pd.to_datetime(
        snapshots["market_observed_ts_utc"], utc=True, errors="raise"
    )
    if snapshot_time.gt(cutoff).any():
        raise ModelSupportBuildError("frozen source contains post-cutoff snapshot")
    records: list[dict[str, Any]] = []
    selected_source_parts: list[pd.DataFrame] = []
    candidate_parts: list[pd.DataFrame] = []
    for issue, scoped in matches.groupby("issue", sort=False):
        scoped = scoped.sort_values(
            ["kickoff_ts_utc", "match_idx", "match_id"], kind="mergesort"
        )
        kickoffs = pd.to_datetime(scoped["kickoff_ts_utc"], utc=True, errors="raise")
        anchor = kickoffs.iloc[(len(scoped) - 1) // 2]
        epoch = anchor - pd.Timedelta(hours=10)
        epoch_text = epoch.strftime("%Y-%m-%dT%H:%M:%SZ")
        identity_time = pd.to_datetime(
            scoped["identity_observed_ts_utc"], utc=True, errors="raise"
        )
        candidate_mask = identity_time.le(epoch) & kickoffs.gt(epoch)
        candidates = scoped.loc[candidate_mask].copy()
        candidates["epoch_id"] = _epoch_id(str(issue), epoch_text)
        candidates["decision_epoch_utc"] = epoch_text
        candidates["issue_evaluation_status"] = (
            "EVALUATED" if epoch <= cutoff else "FUTURE_AT_SOURCE_FREEZE"
        )
        candidates["identity_known_at_epoch"] = True
        candidates["not_started_at_epoch"] = True
        if epoch <= cutoff and not candidates.empty:
            scoped_snapshots = snapshots[
                snapshots["match_id"].isin(candidates["match_id"])
                & pd.to_datetime(
                    snapshots["market_observed_ts_utc"], utc=True, errors="raise"
                ).le(epoch)
            ].sort_values(
                ["market_observed_ts_utc", "id", "match_id"], kind="mergesort"
            )
            latest = scoped_snapshots.groupby("match_id", sort=False).tail(1)
            selected_source_parts.append(latest.copy())
            candidates = candidates.merge(
                latest,
                on="match_id",
                how="left",
                validate="one_to_one",
            )
        else:
            for column in required_snapshots - {"match_id"}:
                candidates[column] = np.nan
        market_time = pd.to_datetime(
            candidates["market_observed_ts_utc"], utc=True, errors="coerce"
        )
        candidates["market_clock_safe"] = market_time.notna() & market_time.le(epoch)
        candidates["snapshot_age_hours"] = (
            epoch - market_time
        ).dt.total_seconds() / 3600.0
        candidates["bj_sp_complete"] = _complete_triplet(
            candidates, ("sp_3", "sp_1", "sp_0")
        )
        candidates["euro_complete"] = _complete_triplet(
            candidates, ("eu_h", "eu_d", "eu_a")
        )
        candidates["core_complete"] = (
            candidates["market_clock_safe"]
            & candidates["bj_sp_complete"]
            & candidates["euro_complete"]
        )
        candidate_parts.append(candidates)
        candidate_count = len(candidates) if epoch <= cutoff else 0
        core_count = (
            int(candidates["core_complete"].sum()) if epoch <= cutoff else 0
        )
        denominator = sorted(scoped["match_idx"].astype(int).tolist())
        records.append(
            {
                "epoch_id": _epoch_id(str(issue), epoch_text),
                "issue": str(issue),
                "decision_epoch_utc": epoch_text,
                "source_freeze_cutoff_utc": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "representative_epoch_rule": REPRESENTATIVE_EPOCH_RULE,
                "evaluation_status": (
                    "EVALUATED" if epoch <= cutoff else "FUTURE_AT_SOURCE_FREEZE"
                ),
                "denominator_matches": len(scoped),
                "denominator_sha256": _row_digest(denominator),
                "candidate_matches": candidate_count,
                "timestamped_snapshot_matches": (
                    int(candidates["market_clock_safe"].sum())
                    if epoch <= cutoff
                    else 0
                ),
                "core_complete_matches": core_count,
                "core_match_coverage": (
                    core_count / candidate_count if candidate_count else 0.0
                ),
                "n7_issue_pass": core_count
                >= SUPPORT_GATE.minimum_complete_matches_per_issue_epoch,
                "eligible_issue_epoch": bool(epoch <= cutoff and candidate_count > 0),
                "prospective_after_activation": bool(
                    epoch >= pd.Timestamp(PROSPECTIVE_ACTIVATION_UTC)
                ),
            }
        )
    issue_support = pd.DataFrame(records).sort_values(
        ["decision_epoch_utc", "issue"], kind="mergesort"
    ).reset_index(drop=True)
    issue_support["chronological_position"] = -1
    issue_support["chronological_role"] = "not_eligible"
    eligible_index = issue_support.index[issue_support["eligible_issue_epoch"]]
    for position, index in enumerate(eligible_index):
        issue_support.loc[index, "chronological_position"] = position
        issue_support.loc[index, "chronological_role"] = chronological_role(position)
    candidate_roster = (
        pd.concat(candidate_parts, ignore_index=True, sort=False)
        if candidate_parts
        else pd.DataFrame()
    )
    role_lookup = issue_support.set_index("issue")[
        ["chronological_position", "chronological_role", "eligible_issue_epoch"]
    ]
    candidate_roster = candidate_roster.join(role_lookup, on="issue")
    admitted = candidate_roster[
        candidate_roster["eligible_issue_epoch"]
        & candidate_roster["core_complete"]
    ].copy()
    feature_rows: list[dict[str, Any]] = []
    for row in admitted.itertuples(index=False):
        euro_values = np.array([row.eu_h, row.eu_d, row.eu_a], dtype=float)
        probabilities = (1.0 / euro_values) / np.sum(1.0 / euro_values)
        sp_values = (row.sp_3, row.sp_1, row.sp_0)
        euro_odds = (row.eu_h, row.eu_d, row.eu_a)
        for order, outcome_code in enumerate(OUTCOME_ORDER):
            feature_rows.append(
                {
                    "panel_row_id": _panel_row_id(
                        str(row.epoch_id), str(row.match_id), outcome_code
                    ),
                    "epoch_id": str(row.epoch_id),
                    "issue": str(row.issue),
                    "chronological_position": int(row.chronological_position),
                    "chronological_role": str(row.chronological_role),
                    "match_id": str(row.match_id),
                    "match_idx": int(row.match_idx),
                    "outcome_code": outcome_code,
                    "outcome_order": order,
                    "decision_epoch_utc": str(row.decision_epoch_utc),
                    "kickoff_ts_utc": str(row.kickoff_ts_utc),
                    "identity_observed_ts_utc": str(row.identity_observed_ts_utc),
                    "market_observed_ts_utc": str(row.market_observed_ts_utc),
                    "snapshot_age_hours": float(row.snapshot_age_hours),
                    "market_snapshot_id": int(row.id),
                    "market_source": str(row.source),
                    "handicap_line": float(row.handicap_line)
                    if pd.notna(row.handicap_line)
                    else np.nan,
                    "bj_sp": float(sp_values[order]),
                    "euro_odds": float(euro_odds[order]),
                    "devig_euro_probability": float(probabilities[order]),
                    "core_complete": True,
                }
            )
    panel = pd.DataFrame(feature_rows)
    if not panel.empty:
        panel = panel.sort_values(
            ["chronological_position", "match_idx", "match_id", "outcome_order"],
            kind="mergesort",
        ).reset_index(drop=True)
    selected_source = (
        pd.concat(selected_source_parts, ignore_index=True, sort=False)
        .drop_duplicates(subset=["id", "match_id"], keep="last")
        .sort_values(["market_observed_ts_utc", "match_id", "id"], kind="mergesort")
        .reset_index(drop=True)
        if selected_source_parts
        else snapshots.iloc[0:0].copy()
    )
    return {
        "issue_support": issue_support,
        "candidate_roster": candidate_roster,
        "panel": panel,
        "selected_source": selected_source,
    }


def _coverage_by_role(issue_support: pd.DataFrame) -> pd.DataFrame:
    required = {
        "development": SUPPORT_GATE.minimum_development_issues,
        "chronological_evaluation": (
            SUPPORT_GATE.minimum_chronological_evaluation_issues
        ),
        "prospective_confirmation": (
            SUPPORT_GATE.minimum_prospective_confirmation_issues
        ),
    }
    rows: list[dict[str, Any]] = []
    for role, minimum in required.items():
        scoped = issue_support[issue_support["chronological_role"].eq(role)]
        issues = len(scoped)
        candidates = int(scoped["candidate_matches"].sum())
        complete = int(scoped["core_complete_matches"].sum())
        n7_pass = int(scoped["n7_issue_pass"].sum())
        n7_rate = n7_pass / issues if issues else 0.0
        coverage = complete / candidates if candidates else 0.0
        rows.append(
            {
                "chronological_role": role,
                "evaluated_issues": issues,
                "required_issues": minimum,
                "candidate_matches": candidates,
                "core_complete_matches": complete,
                "core_match_coverage": coverage,
                "required_core_match_coverage": (
                    SUPPORT_GATE.minimum_core_match_coverage
                ),
                "n7_passing_issues": n7_pass,
                "n7_issue_pass_rate": n7_rate,
                "required_n7_issue_pass_rate": (
                    SUPPORT_GATE.minimum_n7_issue_pass_rate
                ),
                "role_gate_pass": bool(
                    issues >= minimum
                    and n7_rate >= SUPPORT_GATE.minimum_n7_issue_pass_rate
                    and coverage >= SUPPORT_GATE.minimum_core_match_coverage
                ),
            }
        )
    return pd.DataFrame(rows)


def _decision(issue_support: pd.DataFrame, coverage: pd.DataFrame) -> dict[str, Any]:
    eligible = issue_support[issue_support["eligible_issue_epoch"]]
    eligible_count = len(eligible)
    needed_development = max(
        SUPPORT_GATE.minimum_development_issues - eligible_count, 0
    )
    needed_full = max(SUPPORT_GATE.minimum_total_issues - eligible_count, 0)
    violations = {
        "post_epoch_market_observations": 0,
        "started_matches_in_admitted_panel": 0,
        "duplicate_panel_rows": 0,
        "outcome_namespace_reads": 0,
    }
    ready = bool(coverage["role_gate_pass"].all() and not any(violations.values()))
    return {
        "contract_version": CONTRACT_VERSION,
        "representative_epoch_rule": REPRESENTATIVE_EPOCH_RULE,
        "source_boundary_preregistered_at_utc": (
            SOURCE_BOUNDARY_PREREGISTERED_AT_UTC
        ),
        "source_boundary_commit": SOURCE_BOUNDARY_COMMIT,
        "support_gate": SUPPORT_GATE.as_dict(),
        "model_ready_for_204": ready,
        "disposition": (
            "READY_FOR_204_REVIEW"
            if ready
            else "BLOCKED_ACCUMULATE_CAUSAL_SUPPORT"
        ),
        "role_results": coverage.to_dict(orient="records"),
        "accumulation": {
            "eligible_issue_epochs": eligible_count,
            "issues_needed_before_development_horizon": needed_development,
            "issues_needed_before_full_readiness_horizon": needed_full,
            "next_measurable_condition": (
                "At least 37 chronologically assigned eligible issue epochs, with "
                "each required role meeting the frozen 80% N7 and 80% core "
                "coverage thresholds."
            ),
        },
        "violations": violations,
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "ticket_operability_metadata": "NON_CONTROLLING_NOT_READ",
        "authority": (
            "Data support only. No model training, betting, ROI, release or "
            "execution authority; #204 remains blocked until PI accepts a positive handoff."
        ),
    }


def _namespace_manifest(namespace: Path, namespace_name: str) -> dict[str, Any]:
    files = {
        str(path.relative_to(namespace)): {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in sorted(namespace.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "namespace": namespace_name,
        "files": files,
    }
    write_json(namespace / "MANIFEST.json", manifest)
    return manifest


def _root_checksums(package: Path) -> dict[str, dict[str, Any]]:
    return {
        str(path.relative_to(package)): {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def _write_reports(
    package: Path,
    *,
    decision: Mapping[str, Any],
    source_freeze: Mapping[str, Any],
) -> None:
    accumulation = decision["accumulation"]
    package.joinpath("DATA_CARD.md").write_text(
        "\n".join(
            [
                "# #216 causal p34 model-support panel",
                "",
                f"Contract: `{CONTRACT_VERSION}`. Upstream contract: `{UPSTREAM_CONTRACT_VERSION}`.",
                "",
                f"Controlling rule: `{REPRESENTATIVE_EPOCH_RULE}`. Only same-row,",
                "timestamped three-way Beijing SP and EURO observations at or before the",
                "decision epoch enter the panel. Outcome and settlement namespaces are absent.",
                "Sale/parlay metadata is non-controlling and was not read.",
                "",
                f"Disposition: **{decision['disposition']}**.",
                f"Eligible issue epochs: **{accumulation['eligible_issue_epochs']}**;",
                f"additional issues before development horizon: **{accumulation['issues_needed_before_development_horizon']}**;",
                f"additional issues before full readiness horizon: **{accumulation['issues_needed_before_full_readiness_horizon']}**.",
                "",
                "This data package does not train a model and grants no betting, ROI, release",
                "or execution authority. #204 remains blocked until PI accepts a positive handoff.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    package.joinpath("REPLAY.md").write_text(
        "\n".join(
            [
                "# Deterministic replay",
                "",
                "```bash",
                "PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python",
                "PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py verify \\",
                "  --package results/bj216_model_support_panel_v1",
                "PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py replay \\",
                "  --source-package results/bj216_model_support_panel_v1 --output <new-empty-directory>",
                "PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py compare \\",
                "  --frozen results/bj216_model_support_panel_v1 --replay <new-empty-directory>",
                "```",
                "",
                "Replay reads only the frozen source namespace and never opens a runtime or",
                "outcome/settlement database.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    package.joinpath("analysis/DECISION_REPORT.md").write_text(
        "\n".join(
            [
                "# #216 decision report",
                "",
                f"- Source freeze: `{source_freeze['source_freeze_cutoff_utc']}`",
                f"- Representative rule: `{REPRESENTATIVE_EPOCH_RULE}`",
                f"- Eligible issue epochs: `{accumulation['eligible_issue_epochs']}`",
                f"- Development deficit: `{accumulation['issues_needed_before_development_horizon']}` issues",
                f"- Full readiness deficit: `{accumulation['issues_needed_before_full_readiness_horizon']}` issues",
                f"- `model_ready_for_204`: `{str(decision['model_ready_for_204']).lower()}`",
                f"- Disposition: `{decision['disposition']}`",
                "",
                "Unsupported historical named snapshots were not relabeled or backfilled.",
                "Outcome labels remain physically separate. #204 remains blocked unless PI",
                "accepts a future positive support handoff.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def _build_from_frozen_sources(
    package: Path,
    *,
    source_matches: pd.DataFrame,
    source_snapshots: pd.DataFrame,
    source_freeze: dict[str, Any],
    source_inventory: pd.DataFrame,
) -> dict[str, Any]:
    source_freeze = dict(source_freeze)
    source_inventory = _normalize_source_inventory(source_inventory)
    assembled = assemble_panel(
        source_matches,
        source_snapshots,
        source_freeze_cutoff_utc=str(source_freeze["source_freeze_cutoff_utc"]),
    )
    issue_support = assembled["issue_support"]
    candidate_roster = assembled["candidate_roster"]
    panel = assembled["panel"]
    selected_source = assembled["selected_source"]
    source_freeze["frozen_source_census"] = {
        "matches": len(source_matches),
        "selected_snapshots": len(selected_source),
    }
    coverage = _coverage_by_role(issue_support)
    decision = _decision(issue_support, coverage)
    sources = package / "sources"
    audit = package / "audit"
    inference = package / "inference"
    analysis = package / "analysis"
    for directory in (sources, audit, inference, analysis):
        directory.mkdir(parents=True, exist_ok=True)
    write_parquet(sources / "matches.parquet", source_matches)
    write_parquet(sources / "selected_snapshots.parquet", selected_source)
    write_json(sources / "source_freeze.json", source_freeze)
    write_csv(sources / "source_inventory.csv", source_inventory)
    source_manifest = _namespace_manifest(sources, "outcome_blind_frozen_sources")
    write_csv(audit / "issue_support.csv", issue_support)
    write_csv(audit / "coverage_by_role.csv", coverage)
    write_parquet(audit / "candidate_roster.parquet", candidate_roster)
    write_parquet(inference / "model_support_panel.parquet", panel)
    write_parquet(
        inference / "issue_epochs.parquet",
        issue_support.loc[
            :,
            [
                "epoch_id",
                "issue",
                "decision_epoch_utc",
                "chronological_position",
                "chronological_role",
                "eligible_issue_epoch",
            ],
        ],
    )
    _namespace_manifest(inference, "outcome_unexposed_model_support")
    write_json(analysis / "decision.json", decision)
    _write_reports(package, decision=decision, source_freeze=source_freeze)
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "upstream_contract_version": UPSTREAM_CONTRACT_VERSION,
        "source_boundary_commit": SOURCE_BOUNDARY_COMMIT,
        "source_manifest_sha256": digest(sources / "MANIFEST.json"),
        "environment_lock_sha256": digest(ENVIRONMENT_LOCK),
        "representative_epoch_rule": REPRESENTATIVE_EPOCH_RULE,
        "disposition": decision["disposition"],
        "model_ready_for_204": decision["model_ready_for_204"],
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "panel_rows": len(panel),
        "eligible_issue_epochs": int(
            issue_support["eligible_issue_epoch"].sum()
        ),
        "source_manifest": source_manifest,
    }
    write_json(package / "MANIFEST.json", manifest)
    write_json(package / "SHA256SUMS.json", _root_checksums(package))
    return verify_package(package)


def build_package(
    package: Path,
    *,
    live_database: Path | None = None,
    source_freeze_cutoff_utc: str | None = None,
    inventory_databases: Mapping[str, Path] | None = None,
    source_package: Path | None = None,
) -> dict[str, Any]:
    package = package.expanduser().resolve()
    if any(package.iterdir()) if package.exists() else False:
        raise ModelSupportBuildError("output package must be empty")
    package.mkdir(parents=True, exist_ok=True)
    if source_package is not None:
        source_package = source_package.expanduser().resolve()
        verify_package(source_package)
        source_matches = pd.read_parquet(source_package / "sources/matches.parquet")
        source_snapshots = pd.read_parquet(
            source_package / "sources/selected_snapshots.parquet"
        )
        source_freeze = json.loads(
            (source_package / "sources/source_freeze.json").read_text(
                encoding="utf-8"
            )
        )
        source_inventory = pd.read_csv(
            source_package / "sources/source_inventory.csv",
            dtype={"logical_source": str},
        )
        return _build_from_frozen_sources(
            package,
            source_matches=source_matches,
            source_snapshots=source_snapshots,
            source_freeze=source_freeze,
            source_inventory=source_inventory,
        )
    if live_database is None or source_freeze_cutoff_utc is None:
        raise ModelSupportBuildError("runtime build requires live database and cutoff")
    source_matches, runtime_snapshots, runtime = _extract_runtime_source(
        live_database,
        source_freeze_cutoff_utc=source_freeze_cutoff_utc,
    )
    inventory_rows = [
        {
            "logical_source": "beidan_live",
            "filename": live_database.name,
            "bytes": live_database.stat().st_size,
            "table_name": "matches+snapshots(admissible columns only)",
            "schema_sha256": runtime["schema_sha256"],
            "value_rows_read": runtime["runtime_matches_read"]
            + runtime["runtime_snapshots_read"],
            "classification": "ADMITTED_TIMESTAMPED_SAME_ROW_CORE",
            "exclusion_reason": "",
        }
    ]
    for logical_name, database in sorted((inventory_databases or {}).items()):
        inventory_rows.extend(_inventory_database(logical_name, database))
    source_inventory = pd.DataFrame(inventory_rows)
    source_freeze = {
        **runtime,
        "contract_version": CONTRACT_VERSION,
        "source_boundary_preregistered_at_utc": (
            SOURCE_BOUNDARY_PREREGISTERED_AT_UTC
        ),
        "source_boundary_commit": SOURCE_BOUNDARY_COMMIT,
        "representative_epoch_rule": REPRESENTATIVE_EPOCH_RULE,
        "admissible_source_columns": {
            key: list(value) for key, value in ADMISSIBLE_SOURCE_COLUMNS.items()
        },
        "excluded_source_classes": EXCLUDED_SOURCE_CLASSES,
        "prohibited_namespaces": list(PROHIBITED_NAMESPACES),
        "outcome_namespace_read": False,
    }
    return _build_from_frozen_sources(
        package,
        source_matches=source_matches,
        source_snapshots=runtime_snapshots,
        source_freeze=source_freeze,
        source_inventory=source_inventory,
    )


def _verify_checksums(package: Path) -> None:
    sums_path = package / "SHA256SUMS.json"
    if not sums_path.is_file():
        raise ModelSupportBuildError("missing SHA256SUMS.json")
    expected = json.loads(sums_path.read_text(encoding="utf-8"))
    actual = _root_checksums(package)
    if expected != actual:
        raise ModelSupportBuildError("package checksum manifest mismatch")


def _verify_namespace(namespace: Path, expected_name: str) -> None:
    manifest_path = namespace / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ModelSupportBuildError("namespace contract mismatch")
    if manifest.get("namespace") != expected_name:
        raise ModelSupportBuildError("namespace identity mismatch")
    files = {
        str(path.relative_to(namespace)): {
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for path in sorted(namespace.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if manifest.get("files") != files:
        raise ModelSupportBuildError("namespace manifest mismatch")


def verify_package(package: Path) -> dict[str, Any]:
    package = package.expanduser().resolve()
    _verify_checksums(package)
    _verify_namespace(package / "sources", "outcome_blind_frozen_sources")
    _verify_namespace(package / "inference", "outcome_unexposed_model_support")
    if (package / "labels").exists():
        raise ModelSupportBuildError("outcome label namespace must be absent")
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    decision = json.loads(
        (package / "analysis/decision.json").read_text(encoding="utf-8")
    )
    source_freeze = json.loads(
        (package / "sources/source_freeze.json").read_text(encoding="utf-8")
    )
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise ModelSupportBuildError("root contract mismatch")
    if manifest.get("source_boundary_commit") != SOURCE_BOUNDARY_COMMIT:
        raise ModelSupportBuildError("source boundary commit mismatch")
    if manifest.get("source_manifest_sha256") != digest(
        package / "sources/MANIFEST.json"
    ):
        raise ModelSupportBuildError("source manifest lock mismatch")
    if manifest.get("source_manifest_sha256") != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ModelSupportBuildError(
            "source identity differs from exact package lock"
        )
    if manifest.get("environment_lock_sha256") != digest(ENVIRONMENT_LOCK):
        raise ModelSupportBuildError("environment lock mismatch")
    if source_freeze.get("outcome_namespace_read") is not False:
        raise ModelSupportBuildError("outcome namespace read flag is not false")
    panel = pd.read_parquet(package / "inference/model_support_panel.parquet")
    issue_support = pd.read_csv(
        package / "audit/issue_support.csv", dtype={"issue": str}
    )
    source_matches = pd.read_parquet(package / "sources/matches.parquet")
    source_snapshots = pd.read_parquet(
        package / "sources/selected_snapshots.parquet"
    )
    source_inventory = pd.read_csv(
        package / "sources/source_inventory.csv",
        dtype={"logical_source": str},
        keep_default_na=False,
    )
    expected_inventory_columns = [
        "logical_source",
        "filename",
        "bytes",
        "table_name",
        "schema_sha256",
        "value_rows_read",
        "classification",
        "exclusion_reason",
    ]
    if source_inventory.columns.tolist() != expected_inventory_columns:
        raise ModelSupportBuildError("source inventory schema mismatch")
    admitted_inventory = source_inventory[
        source_inventory["classification"].eq(
            "ADMITTED_TIMESTAMPED_SAME_ROW_CORE"
        )
    ]
    excluded_inventory = source_inventory[
        source_inventory["classification"].eq(
            "SCHEMA_ONLY_EXCLUDED_SOURCE"
        )
    ]
    if len(admitted_inventory) != 1 or admitted_inventory.iloc[0][
        "logical_source"
    ] != "beidan_live":
        raise ModelSupportBuildError("admitted source inventory mismatch")
    if admitted_inventory.iloc[0]["exclusion_reason"] != "":
        raise ModelSupportBuildError("admitted source has an exclusion reason")
    if len(excluded_inventory) != len(source_inventory) - 1:
        raise ModelSupportBuildError("source inventory classification mismatch")
    if not pd.to_numeric(
        excluded_inventory["value_rows_read"], errors="raise"
    ).eq(0).all():
        raise ModelSupportBuildError("excluded source values were read")
    expected_reasons = excluded_inventory["logical_source"].map(
        _inventory_exclusion_reason
    )
    if not excluded_inventory["exclusion_reason"].eq(expected_reasons).all():
        raise ModelSupportBuildError("source exclusion reason mismatch")
    if source_inventory["filename"].str.contains(r"[/\\]", regex=True).any():
        raise ModelSupportBuildError("source inventory exposes a local path")
    frozen_census = source_freeze.get("frozen_source_census", {})
    if frozen_census != {
        "matches": len(source_matches),
        "selected_snapshots": len(source_snapshots),
    }:
        raise ModelSupportBuildError("frozen source census mismatch")
    recomputed = assemble_panel(
        source_matches,
        source_snapshots,
        source_freeze_cutoff_utc=str(source_freeze["source_freeze_cutoff_utc"]),
    )
    expected_frames = {
        "issue support": (recomputed["issue_support"], issue_support),
        "candidate roster": (
            recomputed["candidate_roster"],
            pd.read_parquet(package / "audit/candidate_roster.parquet"),
        ),
        "inference panel": (recomputed["panel"], panel),
        "selected source": (recomputed["selected_source"], source_snapshots),
    }
    for name, (expected_frame, observed_frame) in expected_frames.items():
        try:
            pd.testing.assert_frame_equal(
                expected_frame.reset_index(drop=True),
                observed_frame.reset_index(drop=True),
                check_dtype=False,
                check_exact=False,
                rtol=1e-10,
                atol=1e-12,
            )
        except AssertionError as error:
            raise ModelSupportBuildError(
                f"{name} is not derivable from frozen sources"
            ) from error
    forbidden = sorted(
        column
        for column in panel.columns
        if any(part in column.lower() for part in FORBIDDEN_INFERENCE_PARTS)
    )
    if forbidden:
        raise ModelSupportBuildError(f"forbidden inference columns: {forbidden}")
    if panel["panel_row_id"].duplicated().any():
        raise ModelSupportBuildError("duplicate panel row identity")
    if not panel.empty:
        decision_time = pd.to_datetime(panel["decision_epoch_utc"], utc=True)
        market_time = pd.to_datetime(panel["market_observed_ts_utc"], utc=True)
        identity_time = pd.to_datetime(
            panel["identity_observed_ts_utc"], utc=True
        )
        kickoff_time = pd.to_datetime(panel["kickoff_ts_utc"], utc=True)
        if market_time.gt(decision_time).any() or identity_time.gt(decision_time).any():
            raise ModelSupportBuildError("post-epoch observation in panel")
        if kickoff_time.le(decision_time).any():
            raise ModelSupportBuildError("started match in panel")
        grouped = panel.sort_values("outcome_order").groupby(
            ["epoch_id", "match_id"], sort=False
        )["outcome_code"].agg(tuple)
        if not grouped.map(lambda value: value == OUTCOME_ORDER).all():
            raise ModelSupportBuildError("panel outcome axis is incomplete")
        numeric = panel[["bj_sp", "euro_odds", "devig_euro_probability"]]
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ModelSupportBuildError("non-finite core feature")
        probabilities = panel.groupby(["epoch_id", "match_id"], sort=False)[
            "devig_euro_probability"
        ].sum()
        if not np.allclose(probabilities.to_numpy(dtype=float), 1.0, atol=1e-8):
            raise ModelSupportBuildError("de-vigged probabilities do not sum to one")
    coverage = _coverage_by_role(recomputed["issue_support"])
    expected_decision = _decision(issue_support, coverage)
    if decision != expected_decision:
        raise ModelSupportBuildError("decision is not derivable from frozen audit")
    if manifest.get("disposition") != decision["disposition"]:
        raise ModelSupportBuildError("manifest disposition mismatch")
    return {
        "status": "PASS",
        "contract_version": CONTRACT_VERSION,
        "disposition": decision["disposition"],
        "model_ready_for_204": decision["model_ready_for_204"],
        "eligible_issue_epochs": int(
            issue_support["eligible_issue_epoch"].sum()
        ),
        "panel_rows": len(panel),
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "source_manifest_sha256": digest(package / "sources/MANIFEST.json"),
    }


def compare_packages(frozen: Path, replay: Path) -> dict[str, Any]:
    first = verify_package(frozen)
    second = verify_package(replay)
    first_sums = json.loads((frozen / "SHA256SUMS.json").read_text(encoding="utf-8"))
    second_sums = json.loads((replay / "SHA256SUMS.json").read_text(encoding="utf-8"))
    if first_sums != second_sums or first != second:
        raise ModelSupportBuildError("frozen and replay packages differ")
    return {**first, "status": "PASS_IDENTICAL"}


__all__ = [
    "EXPECTED_SOURCE_MANIFEST_SHA256",
    "ModelSupportBuildError",
    "assemble_panel",
    "build_package",
    "compare_packages",
    "verify_package",
    "write_parquet",
]
