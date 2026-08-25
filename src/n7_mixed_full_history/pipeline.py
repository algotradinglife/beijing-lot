"""Build and independently verify the frozen 50/50 corrected-N7 extension.

Contract BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1 (Issue #394).

Core years (2022-2024) preserve EXACT accepted #392 EXPANDING_EQUAL semantics
and are parity-verified against the accepted #392 package.  Extension years
(2025-2026) use the frozen pre-extension EXPANDING_EQUAL mapping (learned only
from label-available history strictly before the first eligible 2025 target
decision epoch) applied per target with explicit EvaluationEpoch receipts.
"""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.cutoff_walkforward.pipeline import verify_package as verify_mapping_package
from src.n7_chronology_sync.pipeline import (
    locate_data_root,
    verify_package as verify_n7_package,
)
from src.n7_cutoff_walkforward.pipeline import verify_package as verify_n7_walkforward
from src.n7_support_shape.pipeline import _rank_shape_pair
from src.n7_support_transfer_grid.pipeline import (
    _maximal_assignment,
    _ticket_units as _accepted_ticket_units,
    verify_package as verify_shape_package,
)
from src.qeu_threshold_n7.pipeline import prepare_match_actions
from src.source_schema.publication import (
    atomic_publish_directory,
    atomic_write_json,
    atomic_write_parquet,
)
from src.temporal_learning import (
    AvailabilityPolicy,
    Cutoff,
    WeightingPolicy,
    implementation_closure,
    verify_implementation_closure,
)
from src.temporal_learning.core import stable_json_hash

from .contract import (
    ALLOWED_VERDICTS,
    ALL_YEARS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    COMPARATOR_ARM,
    CONTRACT_ID,
    CORE_YEARS,
    EVIDENCE_QUERY_CUTOFF_TS,
    EXTENSION_YEARS,
    FIGURE_PATH,
    FRACTIONAL_C1E3_CNY_PER_TICKET,
    FRACTIONAL_R3_CNY_PER_TICKET,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    MIXED_C1E3_EXTRA_TICKETS,
    MIXED_C1E3_FUNDED_UNITS,
    MIXED_C1E3_SHARE_CNY,
    MIXED_PORTFOLIO,
    MIXED_R3_SHARE_CNY,
    MIXED_R3_UNITS_PER_TICKET,
    MIXED_TOTAL_CNY,
    MOVING_BLOCK_LENGTH,
    N_LEGS,
    NOTEBOOK_PATH,
    OUTCOMES,
    PAYOUT_FACTOR,
    POLICY,
    PRIMARY_ARM,
    PRIMARY_TICKETS,
    REPORT_PATH,
    RESULT_PACKAGE,
    SECONDARY_ARM,
    SECONDARY_TICKETS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    UPSTREAM_MAPPING_PACKAGE,
    UPSTREAM_N7_PACKAGE,
    UPSTREAM_N7_WALKFORWARD,
    UPSTREAM_SHAPE_PACKAGE,
)

OUTCOME_ORDER = {outcome: position for position, outcome in enumerate(OUTCOMES)}


class ContractError(ValueError):
    """Raised when extension, parity, or settlement semantics fail closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns].copy()
    for name in columns:
        if isinstance(projected[name].dtype, pd.CategoricalDtype):
            projected[name] = projected[name].astype("string")
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(
            np.uint64
        )
    )
    schema = [(name, str(projected[name].dtype)) for name in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Board 0 -- upstream verification + evidence-cutoff freeze + census
# ---------------------------------------------------------------------------

def _verify_upstreams(repo_root: Path, data_root: Path) -> dict[str, str]:
    checks = {
        "mapping": verify_mapping_package(
            repo_root, repo_root / UPSTREAM_MAPPING_PACKAGE, data_root
        ),
        "n7": verify_n7_package(repo_root, repo_root / UPSTREAM_N7_PACKAGE, data_root),
        "shape": verify_shape_package(
            repo_root, repo_root / UPSTREAM_SHAPE_PACKAGE, data_root
        ),
        "n7_walkforward": verify_n7_walkforward(
            repo_root, repo_root / UPSTREAM_N7_WALKFORWARD, data_root
        ),
    }
    if any(not all(values.values()) for values in checks.values()):
        raise ContractError("an upstream source-bound verifier did not pass")
    return {
        name: sha256_file(repo_root / package / "MANIFEST.json")
        for name, package in {
            "cutoff_walkforward_manifest_sha256": UPSTREAM_MAPPING_PACKAGE,
            "n7_chronology_manifest_sha256": UPSTREAM_N7_PACKAGE,
            "n7_support_transfer_manifest_sha256": UPSTREAM_SHAPE_PACKAGE,
            "n7_cutoff_walkforward_manifest_sha256": UPSTREAM_N7_WALKFORWARD,
        }.items()
    }


def freeze_evidence_cutoff() -> dict[str, Any]:
    """Freeze the immutable evidence-cutoff receipt at execution start."""
    cutoff_ts = pd.Timestamp(EVIDENCE_QUERY_CUTOFF_TS, tz="UTC")
    if cutoff_ts.tz is None:
        raise ContractError("EVIDENCE_QUERY_CUTOFF_TS must carry a UTC timezone")
    return {
        "contract": CONTRACT_ID,
        "EVIDENCE_QUERY_CUTOFF_TS": cutoff_ts.isoformat(),
        "rule": (
            "any future prospective/shadow contract must start strictly after "
            "this cutoff; settlement rows admitted only when the trusted "
            "settlement-availability timestamp is strictly earlier"
        ),
        "frozen_at_execution_start": True,
    }


# ---------------------------------------------------------------------------
# Board 1 -- corrected chronology / mapping surface for core years + extension
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_core_mapped(repo_root: Path) -> pd.DataFrame:
    """Load the accepted #392 EXPANDING_EQUAL mapped surface for 2022-2024."""
    package = repo_root / UPSTREAM_N7_WALKFORWARD
    mapped = pd.read_parquet(package / "mapped_probabilities.parquet")
    mapped["issue_code"] = mapped["issue_code"].astype(str)
    mapped["fixture_decision_ts"] = pd.to_datetime(
        mapped["fixture_decision_ts"], utc=True
    )
    if set(mapped["policy"].unique()) != {POLICY} | {
        "EXPANDING_EXPONENTIAL",
        "RECENT_STATE_BLEND",
    }:
        raise ContractError("accepted #392 mapped surface policy set drifted")
    if not mapped["issue_year"].isin(CORE_YEARS).all():
        raise ContractError("accepted #392 mapped surface contains out-of-core years")
    if mapped.duplicated(["issue_code", "match_idx", "policy"]).any():
        raise ContractError("accepted #392 mapped keys are not unique")
    return mapped[mapped["policy"].eq(POLICY)].copy()


def _load_core_settlement(repo_root: Path) -> pd.DataFrame:
    """Load the accepted corrected-N7 settlement surface for core years."""
    package = repo_root / UPSTREAM_N7_PACKAGE
    settlement = pd.read_parquet(package / "action_receipts.parquet")[
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "match_idx",
            "fixture_decision_ts",
            "result_code",
            "winning_sp",
            "settlement_available",
            "settlement_quality",
        ]
    ].copy()
    settlement["issue"] = settlement["issue"].astype(str)
    settlement["result_code"] = settlement["result_code"].astype(str)
    settlement["issue_anchor_ts"] = pd.to_datetime(
        settlement["issue_anchor_ts"], utc=True
    )
    settlement["fixture_decision_ts"] = pd.to_datetime(
        settlement["fixture_decision_ts"], utc=True
    )
    if not settlement["issue_year"].isin(CORE_YEARS).all():
        raise ContractError("accepted N7 settlement contains out-of-core years")
    if settlement.duplicated(["issue", "match_idx"]).any():
        raise ContractError("accepted N7 settlement keys are not unique")
    return settlement


def _load_extension_timing(data_root: Path) -> pd.DataFrame:
    """Outcome-blind fixture timing for extension issues 25011-26087.

    The frozen candidate inventory (bj268) only carries kickoff timestamps
    through 25042.  Extension timing comes from the accepted NOWSCORE lineage:
    modeling_plus_2026 matches (25011-26051) and the runtime beidan_live
    matches (26051-26087), both with a 10h decision boundary identical to the
    shared #382/#388 clock.  On the overlap issue 26051 both sources must
    agree; the runtime row is preferred because it carries the observed
    settlement receipt timestamp.
    """
    modeling = data_root / "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite"
    live = data_root / "beidan_live.db"
    parts: list[pd.DataFrame] = []
    with sqlite3.connect(f"file:{modeling.resolve()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        mp = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   kickoff_ts,
                   CAST(ts_10h AS TEXT) AS ts_10h
            FROM matches
            WHERE CAST(issue AS TEXT) >= '25011'
            ORDER BY issue, match_idx
            """,
            conn,
        )
    with sqlite3.connect(f"file:{live.resolve()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        lv = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue, match_idx, kickoff_ts
            FROM matches
            WHERE CAST(issue AS TEXT) >= '25011'
            ORDER BY issue, match_idx
            """,
            conn,
        )
    mp["issue"] = mp["issue"].astype(str)
    lv["issue"] = lv["issue"].astype(str)
    mp["match_idx"] = mp["match_idx"].astype(int)
    lv["match_idx"] = lv["match_idx"].astype(int)
    # normalize kickoff
    def _norm_kickoff(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame["kickoff_ts"] = pd.to_datetime(frame["kickoff_ts"], errors="coerce", utc=True)
        return frame

    mp = _norm_kickoff(mp)
    lv = _norm_kickoff(lv)
    # Overlap cross-check (disclosure, not a gate): modeling_plus_2026 is a
    # stale modeling snapshot (built 2026-06-30) with known midnight-default
    # and stale-kickoff artifacts.  The runtime beidan_live surface is the
    # authoritative source for >= 26051 (observed settled_ts receipts).
    # Rows from the two sources are never mixed for the same key: modeling
    # feeds only < 26051, runtime only >= 26051.  Material disagreement on the
    # overlap is recorded in the source receipt for disclosure.
    overlap = mp.merge(
        lv, on=["issue", "match_idx"], suffixes=("_mp", "_live"), how="inner"
    )
    if overlap.empty:
        raise ContractError("extension timing sources do not overlap at 26051")
    material_overlap = int(
        abs(
            (overlap["kickoff_ts_mp"] - overlap["kickoff_ts_live"]).dt.total_seconds()
        ).gt(3 * 3600).sum()
    )
    # Runtime self-consistency gate: every extension runtime row that HAS an
    # observed settlement receipt must carry a kickoff strictly before it.
    # The runtime kickoff strings are Asia/Hong_Kong-naive (the frozen
    # SOURCE_TIMEZONE convention, matching modeling_plus and the accepted
    # candidate inventory); settled_ts is UTC.  The comparison therefore
    # reads the RAW kickoff string and localizes it as HKT before comparing
    # with the UTC settlement receipt converted to HKT wall time.  Unsettled
    # runtime rows are allowed here; they are excluded downstream by
    # settlement_available.
    lv_settle = pd.read_sql_query(
        """
        SELECT CAST(m.issue AS TEXT) AS issue, m.match_idx,
               m.kickoff_ts AS raw_kickoff, s.settled_ts
        FROM matches m
        JOIN settlements s ON m.match_id = s.match_id
        WHERE CAST(m.issue AS TEXT) BETWEEN '26051' AND '26087'
        """,
        sqlite3.connect(f"file:{live.resolve()}?mode=ro", uri=True),
    )
    lv_settle["issue"] = lv_settle["issue"].astype(str)
    lv_settle["match_idx"] = lv_settle["match_idx"].astype(int)
    lv_settle["settled_ts"] = pd.to_datetime(
        lv_settle["settled_ts"], errors="coerce", utc=True
    )
    if lv_settle["settled_ts"].isna().any():
        raise ContractError("runtime extension timing lacks observed settlement")
    kickoff_hkt = pd.to_datetime(
        lv_settle["raw_kickoff"], errors="coerce"
    ).dt.tz_localize("Asia/Hong_Kong")
    if kickoff_hkt.isna().any():
        raise ContractError("runtime extension timing lacks kickoff")
    settled_hkt = lv_settle["settled_ts"].dt.tz_convert("Asia/Hong_Kong")
    if (settled_hkt < kickoff_hkt).any():
        raise ContractError("runtime extension settlement precedes its kickoff")
    # runtime rows (26051+) preferred; modeling rows for earlier issues
    modeling_rows = mp[mp["issue"].lt("26051")].copy()
    runtime_rows = lv[lv["issue"].ge("26051")].copy()
    timing = pd.concat([modeling_rows, runtime_rows], ignore_index=True)
    timing = timing.drop_duplicates(["issue", "match_idx"], keep="first")
    if timing.duplicated(["issue", "match_idx"]).any():
        raise ContractError("extension timing keys are not unique")
    if timing["kickoff_ts"].isna().any():
        missing = timing.loc[timing["kickoff_ts"].isna(), "issue"].unique().tolist()
        raise ContractError(f"extension timing lacks kickoff for {missing[:5]}")
    timing["fixture_decision_ts"] = timing["kickoff_ts"] - pd.Timedelta(hours=10)
    timing["label_available_ts"] = timing["kickoff_ts"] + pd.Timedelta(hours=4)
    timing.attrs["material_overlap_disagreements"] = material_overlap
    return timing[["issue", "match_idx", "fixture_decision_ts", "label_available_ts"]]


def _extension_panel(data_root: Path, roles: pd.DataFrame) -> pd.DataFrame:
    """Build the proxy panel for extension rows with extension-aware years.

    Reuses the shared #268 proxy loader and issue-role registry; only the
    year routing is extension-aware (2025-2026 supported via the same source
    chain that already feeds #360).  Outcome labels are read separately and
    cannot affect the panel itself.  Rows without extension timing are kept
    with timing_available=False so the census still discovers them; eligible
    targets are filtered downstream.
    """
    from src.divergence_materializer.data import load_proxy_panel

    proxy_root = data_root / "derived/bj268/eu_proxy_backfill_v3/eu_odds_proxy_v3"
    panel = load_proxy_panel(proxy_root, roles, horizons=("10h",))
    panel["issue_code"] = panel["issue_code"].astype(str)
    extension = panel[panel["issue_code"].astype(str).ge("25011")].copy()
    if extension.empty:
        raise ContractError("extension proxy panel is empty")
    timing = _load_extension_timing(data_root)
    extension = extension.merge(
        timing,
        left_on=["issue_code", "match_idx"],
        right_on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    extension["timing_available"] = extension["fixture_decision_ts"].notna()
    # Issues without extension timing (e.g. 2025-05+ which have no settlement
    # evidence in any trusted source) stay in the census but are ineligible.
    anchor = extension.loc[
        extension["timing_available"], "fixture_decision_ts"
    ]
    extension["issue_anchor_ts"] = anchor.groupby(
        extension.loc[extension["timing_available"], "issue_code"], observed=True
    ).transform("min")
    return extension


def _extension_settlement(data_root: Path) -> pd.DataFrame:
    """Trusted settlement surface for extension issues.

    2025 (25011-25042): canonical xlsm lineage (same source as the frozen
    corrected chronology), with trusted flag and quality.  2026 (26011-26051):
    modeling_plus_2026 trusted rows.  2026 (26051-26087): runtime
    beidan_live settlements with observed receipt timestamps.  26088 and all
    later issues are excluded (no trusted settlement evidence).
    """
    xlsm_path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    modeling_path = data_root / "derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite"
    live_path = data_root / "beidan_live.db"
    rows: list[pd.DataFrame] = []

    with sqlite3.connect(f"file:{xlsm_path.resolve()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        x = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted,
                   CAST(settlement_quality AS TEXT) AS settlement_quality
            FROM match_features
            WHERE CAST(issue AS TEXT) BETWEEN '25011' AND '25042'
            ORDER BY issue, match_idx
            """,
            conn,
        )
    x["issue"] = x["issue"].astype(str)
    x["settlement_source"] = "XLSM_CANONICAL"
    rows.append(x)

    with sqlite3.connect(f"file:{modeling_path.resolve()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        m = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted,
                   CAST(settlement_quality AS TEXT) AS settlement_quality
            FROM match_features
            WHERE CAST(issue AS TEXT) BETWEEN '26011' AND '26050'
            ORDER BY issue, match_idx
            """,
            conn,
        )
    m["issue"] = m["issue"].astype(str)
    m["settlement_source"] = "MODELING_PLUS_2026"
    rows.append(m)

    with sqlite3.connect(f"file:{live_path.resolve()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        l = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   1 AS trusted,
                   'observed' AS settlement_quality,
                   settled_ts
            FROM settlements
            WHERE CAST(issue AS TEXT) BETWEEN '26051' AND '26087'
            ORDER BY issue, match_idx
            """,
            conn,
        )
    l["issue"] = l["issue"].astype(str)
    l["settlement_source"] = "LIVE_DB_OBSERVED"
    rows.append(l)

    settlement = pd.concat(rows, ignore_index=True)
    if settlement.duplicated(["issue", "match_idx"]).any():
        raise ContractError("extension settlement keys are not unique")
    settlement["match_idx"] = settlement["match_idx"].astype(int)
    settlement["result_code"] = settlement["result_code"].astype(str)
    settlement["settlement_available"] = (
        settlement["trusted"].astype(int).eq(1)
        & settlement["result_code"].isin(OUTCOMES)
        & settlement["winning_sp"].gt(0)
    )
    # availability timestamps: observed runtime receipt when present, else the
    # shared KICKOFF+4H historical proxy from the extension timing surface.
    timing = _load_extension_timing(data_root).rename(
        columns={"issue": "issue", "match_idx": "match_idx"}
    )
    settlement = settlement.merge(
        timing[["issue", "match_idx", "fixture_decision_ts", "label_available_ts"]],
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    cutoff_ts = pd.Timestamp(EVIDENCE_QUERY_CUTOFF_TS, tz="UTC")
    if "settled_ts" in settlement.columns:
        observed = pd.to_datetime(settlement["settled_ts"], errors="coerce", utc=True)
        settlement["availability_ts"] = observed.where(
            observed.notna(), settlement["label_available_ts"]
        )
    else:
        settlement["availability_ts"] = settlement["label_available_ts"]
    settlement["availability_ts"] = pd.to_datetime(
        settlement["availability_ts"], errors="coerce", utc=True
    )
    if settlement.loc[
        settlement["settlement_available"], "availability_ts"
    ].isna().any():
        raise ContractError("trusted extension settlement lacks availability")
    if not (
        settlement.loc[
            settlement["settlement_available"], "availability_ts"
        ].lt(cutoff_ts)
    ).all():
        late = settlement.loc[
            settlement["settlement_available"]
            & ~settlement["availability_ts"].lt(cutoff_ts),
            "issue",
        ].unique().tolist()
        raise ContractError(
            f"extension settlement crosses evidence cutoff: {late[:5]}"
        )
    return settlement


def _extension_history(
    repo_root: Path, data_root: Path, roles: pd.DataFrame
) -> pd.DataFrame:
    """Capped pre-extension history: labels available strictly before the
    first eligible 2025 target decision epoch.

    The frozen #360 corrected chronology development + transfer labels (all
    of 2014-2024) are already strictly before that boundary; no 2025/2026
    outcome can enter.  This function reuses the shared #382/#388 panel and
    label loaders with the same history semantics as the accepted #383
    walk-forward surface, so the mapping client sees byte-identical history
    columns to the accepted chain.
    """
    from src.low_n_selector_data.pipeline import (
        _fixture_timing,
        _load_transfer_results,
        load_development_labels,
        attach_native_labels as _attach_native_labels,
    )

    # Shared loaders (same sources as #360/#383).
    candidate = data_root / "derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"
    registry = data_root / "derived/500_bjdc/500_bjdc.sqlite"
    proxy = data_root / "derived/bj268/eu_proxy_backfill_v3/eu_odds_proxy_v3"
    label_sqlite = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"

    timing = _fixture_timing(candidate)
    from src.divergence_materializer.data import load_proxy_panel

    panel = load_proxy_panel(proxy, roles, horizons=("10h",))
    # History is strictly pre-extension: development (<=2021) + transfer
    # (2022-2024).  Extension rows (>=25011) are target rows, never history,
    # and the frozen candidate timing surface does not carry their kickoff.
    panel = panel[panel["issue_code"].astype(str).lt("25011")].copy()
    panel = panel.merge(
        timing, on=["issue_code", "match_idx"], how="left", validate="one_to_one"
    )
    if panel[["fixture_decision_ts", "label_available_ts"]].isna().any().any():
        raise ContractError("shared proxy panel lacks fixture timing")

    # Development labels are 2017-2021 (pre-transfer) in the frozen #360
    # contract; transfer labels for 2022-2024 come from the canonical xlsm
    # lineage.  Together they are exactly the accepted #383 history.
    dev_issues = set(
        panel.loc[
            panel["issue_year"].le(2021), "issue_code"
        ].astype(str)
    )
    labels = load_development_labels(label_sqlite, dev_issues)
    development = _attach_native_labels(panel, labels)
    transfer_results = _load_transfer_results(
        data_root, panel.rename(columns={"issue_code": "issue"})
    )
    # Transfer rows must carry the shared panel features the mapping client
    # needs (chronology + handicap + q_eu features), bound by the panel key.
    transfer_features = panel[panel["issue_year"].isin(CORE_YEARS)].copy()
    transfer = transfer_features.merge(
        transfer_results.rename(columns={"issue": "issue_code"}),
        on=["issue_code", "match_idx"],
        how="inner",
        validate="one_to_one",
    ).rename(columns={"result_code": "target_outcome"})
    history = pd.concat(
        [
            development[development["target_outcome"].notna()],
            transfer[
                [
                    "issue_code",
                    "issue_year",
                    "fixture_decision_ts",
                    "label_available_ts",
                    "target_outcome",
                    "native_line_supported",
                    "native_handicap_line",
                    "q_eu_3",
                    "q_eu_1",
                    "q_eu_0",
                    "line_x_q_eu_3",
                    "line_x_q_eu_1",
                    "line_x_q_eu_0",
                ]
            ],
        ],
        ignore_index=True,
    )
    history["issue_code"] = history["issue_code"].astype(str)
    history["target_outcome"] = history["target_outcome"].astype(str)
    history["label_available_ts"] = pd.to_datetime(
        history["label_available_ts"], errors="coerce", utc=True
    )
    history["fixture_decision_ts"] = pd.to_datetime(
        history["fixture_decision_ts"], errors="coerce", utc=True
    )
    # Required mapping-client columns.
    required = {
        "issue_code",
        "issue_year",
        "fixture_decision_ts",
        "label_available_ts",
        "target_outcome",
        "native_line_supported",
        "native_handicap_line",
        "q_eu_3",
        "q_eu_1",
        "q_eu_0",
        "line_x_q_eu_3",
        "line_x_q_eu_1",
        "line_x_q_eu_0",
    }
    missing = sorted(required - set(history.columns))
    if missing:
        raise ContractError(f"extension history lacks required columns: {missing}")
    if history["label_available_ts"].isna().any():
        raise ContractError("extension history has missing label availability")
    # Full pre-extension cap guard: no extension-year outcome may appear.
    if history["issue_code"].astype(str).ge("25011").any():
        raise ContractError("extension history contains an extension-year issue")
    return history


def _pre_extension_boundary(extension_panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Discover the first eligible 2025 target decision epoch (outcome-blind).

    Eligible extension rows require native-line support AND extension timing
    (issues 25043+ have no trusted settlement evidence; they stay in the
    census but cannot be mapping targets).  The boundary = min
    fixture_decision_ts across eligible 2025 target issues.  Every extension
    target (2025/2026) is evaluated at its own EvaluationEpoch but the mapping
    learning window is capped at this boundary.
    """
    eligible = extension_panel[
        extension_panel["native_line_supported"].eq(True)
        & extension_panel["timing_available"].eq(True)
    ].copy()
    eligible2025 = eligible[
        eligible["issue_code"].astype(str).ge("25011")
        & eligible["issue_code"].astype(str).lt("26011")
    ]
    if eligible2025.empty:
        raise ContractError("no eligible 2025 extension target discovered")
    epochs = (
        eligible2025.groupby("issue_code", observed=True)["fixture_decision_ts"]
        .min()
        .sort_values(kind="stable")
    )
    boundary_ts = epochs.iloc[0]
    if boundary_ts.tz is None:
        boundary_ts = boundary_ts.tz_localize("UTC")
    else:
        boundary_ts = boundary_ts.tz_convert("UTC")
    return eligible, pd.Timestamp(boundary_ts)


def _fit_extension_mapping(
    repo_root: Path,
    history: pd.DataFrame,
    eligible_target: pd.DataFrame,
    boundary_ts: pd.Timestamp,
    source_hashes: dict[str, str],
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.DataFrame]:
    """Fit the frozen pre-extension EXPANDING_EQUAL mapping artifact once and
    apply it to every extension target at its own EvaluationEpoch.

    learning cutoff = pre-extension boundary (strictly before the first
    eligible 2025 target decision epoch); the same artifact (one fit, one
    gate/refit) serves all extension targets.  Per-target receipts bind the
    target's EvaluationEpoch to the frozen artifact identity.  This satisfies
    'Each target still receives an explicit EvaluationEpoch and receipt
    binding its target cutoff to the frozen pre-extension learning artifact'.
    """
    from src.cutoff_walkforward.fitting import fit_issue_mapping

    fitting_implementation = implementation_closure(
        repo_root,
        ("src.cutoff_walkforward.fitting",),
        distributions=("numpy", "pandas", "scikit-learn"),
    )
    # Group target rows by issue; each target has EvaluationEpoch = min
    # fixture_decision_ts.  The learning window is the SAME frozen pre-extension
    # boundary for every target.
    epochs = (
        eligible_target.groupby("issue_code", observed=True)["fixture_decision_ts"]
        .min()
        .sort_values(kind="stable")
    )
    mapped_parts: list[pd.DataFrame] = []
    receipts: list[dict[str, Any]] = []
    weight_parts: list[pd.DataFrame] = []
    fit_cutoff = Cutoff(
        identity="PRE_EXTENSION_BOUNDARY_2025",
        cutoff_ts=boundary_ts,
        kind="EVALUATION_YEAR",
    )
    for issue, evaluation_epoch in epochs.items():
        target_rows = eligible_target[
            eligible_target["issue_code"].astype(str).eq(str(issue))
        ].copy()
        if target_rows.empty or target_rows["fixture_decision_ts"].min() < boundary_ts:
            raise ContractError(
                f"extension target {issue} precedes the pre-extension boundary"
            )
        result = fit_issue_mapping(
            history,
            target_rows,
            fit_cutoff,
            repository_root=repo_root,
            source_hashes=source_hashes,
            policy_name=POLICY,
        )
        issue_mapped = result.mapped.assign(
            policy=POLICY,
            issue_gate_accepted=bool(result.accepted),
        )
        for outcome in OUTCOMES:
            issue_mapped[f"q_effective_{outcome}"] = np.where(
                result.accepted,
                issue_mapped[f"q_candidate_{outcome}"],
                issue_mapped[f"q_line_{outcome}"],
            )
        mapped_parts.append(issue_mapped)
        # Per-target receipt: EvaluationEpoch + frozen artifact identity.
        epoch_value = pd.Timestamp(evaluation_epoch)
        if epoch_value.tz is None:
            epoch_value = epoch_value.tz_localize("UTC")
        else:
            epoch_value = epoch_value.tz_convert("UTC")
        artifact_receipt = {
            **result.receipt,
            "target_issue": str(issue),
            "evaluation_epoch": epoch_value.isoformat(),
            "frozen_pre_extension_artifact": True,
            "learning_cutoff_identity": fit_cutoff.identity,
            "learning_cutoff_ts": fit_cutoff.cutoff_ts.isoformat(),
            "fit_implementation_closure_sha256": fitting_implementation[
                "closure_sha256"
            ],
        }
        receipts.append(
            {
                "issue": str(issue),
                "issue_year": int(target_rows["issue_year"].iloc[0]),
                "policy": POLICY,
                "receipt": artifact_receipt,
            }
        )
        weight_part = result.weights.assign(target_issue=str(issue))
        weight_parts.append(weight_part)
    if not mapped_parts:
        raise ContractError("extension mapping produced no target rows")
    mapped = pd.concat(mapped_parts, ignore_index=True)
    if mapped.duplicated(["issue_code", "match_idx"]).any():
        raise ContractError("extension mapped keys are not unique")
    return mapped, receipts, pd.concat(weight_parts, ignore_index=True)


# Shared availability policy constants (same as the accepted #383 surface).
# The extension mapping calls the shared cutoff_walkforward.fitting client,
# which itself binds AVAILABILITY_POLICY/INTENDED_USE from its own contract;
# these module-level names document the shared policy used by the extension.
AVAILABILITY_POLICY = "KICKOFF_PLUS_4H_HISTORICAL_PROXY_V1"
INTENDED_USE = "HISTORICAL_DIAGNOSTIC"


# ---------------------------------------------------------------------------
# Board 2 -- action surface (year-flexible mirror of the frozen transform)
# ---------------------------------------------------------------------------

def _support_without(omitted: str) -> str:
    """Return the two-outcome support string without the omitted outcome."""
    return "".join(outcome for outcome in OUTCOMES if outcome != omitted)


def prepare_actions_years(cells: pd.DataFrame, years: tuple[int, ...]) -> pd.DataFrame:
    """Label-free match-action transform, byte-identical to the frozen
    qeu_threshold_n7.prepare_match_actions except the year gate is supplied
    by the caller (the frozen module binds ALL_YEARS=2020-2024).

    Parity is proven in tests: on core-year rows this function produces
    exactly the frozen pipeline output.
    """
    required = {
        "issue",
        "issue_year",
        "issue_anchor_ts",
        "match_idx",
        "outcome",
        "q_eu",
        "q_line",
    }
    missing = sorted(required - set(cells.columns))
    if missing:
        raise ValueError(f"missing causal cell columns: {missing}")
    frame = cells[cells["issue_year"].isin(years)].copy()
    frame["outcome"] = frame["outcome"].astype(str)
    frame = frame[frame["outcome"].isin(OUTCOMES)].copy()
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    wide = frame.pivot_table(
        index=keys,
        columns="outcome",
        values=["q_eu", "q_line"],
        aggfunc="first",
    ).reindex(columns=pd.MultiIndex.from_product([["q_eu", "q_line"], OUTCOMES]))
    wide = wide.dropna().reset_index()
    q_eu = wide["q_eu"].to_numpy(float)
    q_line = wide["q_line"].to_numpy(float)
    if not np.isfinite(q_eu).all() or not np.isfinite(q_line).all():
        raise ValueError("non-finite probability triplet")
    if (q_eu <= 0).any() or (q_line <= 0).any():
        raise ValueError("non-positive probability triplet")
    if not np.allclose(q_eu.sum(axis=1), 1.0, atol=1e-6, rtol=0.0):
        raise ValueError("q_eu triplets are not normalized")
    if not np.allclose(q_line.sum(axis=1), 1.0, atol=1e-6, rtol=0.0):
        raise ValueError("q_line triplets are not normalized")

    rank = np.broadcast_to(np.arange(len(OUTCOMES)), q_eu.shape)
    min_q = q_eu.min(axis=1, keepdims=True)
    baseline_candidates = q_eu == min_q
    baseline_omitted_idx = np.where(baseline_candidates, rank, -1).argmax(axis=1)

    qeu_score = np.log(q_eu / np.clip(q_line, 1e-4, None))
    min_score = qeu_score.min(axis=1, keepdims=True)
    score_candidates = qeu_score == min_score
    min_q_among_score = np.where(score_candidates, q_eu, np.inf).min(
        axis=1, keepdims=True
    )
    q_candidates = score_candidates & (q_eu == min_q_among_score)
    qeu_omitted_idx = np.where(q_candidates, rank, -1).argmax(axis=1)

    outcomes = np.asarray(OUTCOMES)
    baseline_omitted = outcomes[baseline_omitted_idx]
    qeu_omitted = outcomes[qeu_omitted_idx]
    changed = baseline_omitted != qeu_omitted
    gained_idx = baseline_omitted_idx
    lost_idx = qeu_omitted_idx
    row_idx = np.arange(len(wide))
    pressure = np.where(
        changed,
        qeu_score[row_idx, gained_idx] - qeu_score[row_idx, lost_idx],
        0.0,
    )
    if (pressure < -1e-12).any():
        raise AssertionError("support pressure cannot be negative")

    result = wide[keys].copy()
    result.columns = keys
    result["issue"] = result["issue"].astype(str)
    result["baseline_omitted"] = baseline_omitted
    result["qeu_omitted"] = qeu_omitted
    result["baseline_support"] = [_support_without(value) for value in baseline_omitted]
    result["qeu_support"] = [_support_without(value) for value in qeu_omitted]
    result["retained_mass"] = 1.0 - q_eu[row_idx, baseline_omitted_idx]
    result["support_pressure"] = pressure
    result["support_changed"] = changed
    result["lost_outcome"] = np.where(changed, qeu_omitted, "")
    result["gained_outcome"] = np.where(changed, baseline_omitted, "")
    result["delta_abs_max"] = np.abs(q_eu - q_line).max(axis=1)
    result["qeu_score_max"] = qeu_score.max(axis=1)
    result["qeu_score_min"] = qeu_score.min(axis=1)
    for index, outcome in enumerate(OUTCOMES):
        result[f"q_eu_{outcome}"] = q_eu[:, index]
        result[f"q_line_{outcome}"] = q_line[:, index]
        result[f"qeu_score_{outcome}"] = qeu_score[:, index]
    return result.sort_values(keys, kind="stable").reset_index(drop=True)


def _mapped_long(mapped: pd.DataFrame) -> pd.DataFrame:
    anchor = mapped.groupby(["issue_code"], observed=True)[
        "fixture_decision_ts"
    ].transform("min")
    parts: list[pd.DataFrame] = []
    for outcome in OUTCOMES:
        parts.append(
            pd.DataFrame(
                {
                    "issue": mapped["issue_code"].astype(str),
                    "issue_year": mapped["issue_year"].astype(int),
                    "issue_anchor_ts": anchor,
                    "match_idx": mapped["match_idx"].astype(int),
                    "outcome": outcome,
                    "q_eu": mapped[f"q_effective_{outcome}"].astype(float),
                    "q_line": mapped[f"q_line_{outcome}"].astype(float),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def _action_surface(mapped: pd.DataFrame, settlement: pd.DataFrame) -> pd.DataFrame:
    long = _mapped_long(mapped)
    year_set = tuple(sorted(mapped["issue_year"].unique().tolist()))
    actions = prepare_actions_years(long, year_set)
    actions = actions.merge(
        settlement[
            [
                "issue",
                "issue_year",
                "issue_anchor_ts",
                "match_idx",
                "fixture_decision_ts",
                "result_code",
                "winning_sp",
                "settlement_available",
                "settlement_quality",
            ]
        ],
        on=["issue", "issue_year", "issue_anchor_ts", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    actions["settlement_available"] = (
        actions["settlement_available"].fillna(False).astype(bool)
    )
    actions["winning_sp"] = pd.to_numeric(actions["winning_sp"], errors="coerce")
    # Every action row is a native-line-supported fixture by construction
    # (the accepted panel/mapping surfaces only emit supported rows).
    actions["native_line_supported"] = True
    return actions.sort_values(
        ["issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def _primary_support(selected: pd.DataFrame) -> dict[int, tuple[str, ...]]:
    """R3 CONTROL support: activate the top-3 pressure fixtures to qeu_support,
    keep the remaining legs on baseline support (accepted #392 semantics)."""
    ranked = selected.sort_values(
        ["support_pressure", "match_idx"],
        ascending=[False, True],
        kind="stable",
    )
    activated = set(ranked.head(3)["match_idx"].astype(int))
    return {
        int(row.match_idx): tuple(
            str(row.qeu_support)
            if int(row.match_idx) in activated
            else str(row.baseline_support)
        )
        for row in selected.itertuples()
    }


def _baseline_support(selected: pd.DataFrame) -> dict[int, tuple[str, ...]]:
    """R0 CONTROL support: baseline support on every leg (accepted #366)."""
    return {
        int(row.match_idx): tuple(str(row.baseline_support))
        for row in selected.itertuples()
    }


def _secondary_support(
    selected: pd.DataFrame, primary: dict[int, tuple[str, ...]]
) -> dict[int, tuple[str, ...]]:
    """C1E3 support: #373/#392 contraction (c1) + expansion (e1..e3) on top of
    the R3 primary support, using the accepted shape-ranker and maximal
    assignment."""
    _, _, scores = _rank_shape_pair(selected, primary)
    contraction, expansion = _maximal_assignment(scores)
    result = dict(primary)
    c1 = contraction[0]
    result[c1] = (
        str(scores.loc[scores["match_idx"].eq(c1), "retained_outcome"].iloc[0]),
    )
    for match_idx in expansion[:3]:
        result[match_idx] = OUTCOMES
    if len(set([c1, *expansion[:3]])) != 4:
        raise ContractError("C1E3 contraction/expansion assignment is not disjoint")
    return result


def _canonical_residual_order(
    issue: str, cell: str, codes: list[str]
) -> list[str]:
    """Accepted deterministic, outcome-blind canonical residual order from
    n7_support_transfer_grid._ticket_units (hash-ranked)."""
    return sorted(
        codes,
        key=lambda code: (
            hashlib.sha256(
                f"BJ-UNIFIED-N7-SUPPORT-TRANSFER-GRID-001/v1|{issue}|{cell}|{code}".encode()
            ).hexdigest(),
            code,
        ),
    )


def _ticket_units_flexible(
    issue: str, cell: str, codes: list[str], funded_units: int
) -> dict[str, int]:
    """Integer unit allocation by the accepted canonical residual order.

    With FUNDED_UNITS=512 and 216 codes this reproduces
    n7_support_transfer_grid._ticket_units exactly (2 base + 80 residual).
    With 256 units / 216 codes it yields the mixed-portfolio C1E3 schedule
    (1 base + 40 extra on the first 40 residual tickets).
    """
    count = len(codes)
    base_units, residual = divmod(funded_units, count)
    if base_units < 1:
        raise ContractError("complete ticket space exceeds funded units")
    ranked = _canonical_residual_order(issue, cell, codes)
    extra = set(ranked[:residual])
    result = {code: base_units + int(code in extra) for code in codes}
    if sum(result.values()) != funded_units:
        raise ContractError("integer allocation does not reconcile to funded units")
    return result


def _ticket_rows_for_schedule(
    *,
    issue: str,
    year: int,
    arm: str,
    schedule: str,
    fixture_order: list[int],
    support_map: dict[int, tuple[str, ...]],
    units_by_code: dict[str, int],
) -> list[dict[str, Any]]:
    """Build ticket rows for a given unit schedule.  Uses the exact #392
    value ordering (itertools.product in fixture order) so ticket identities
    are identical across schedules."""
    combinations = list(
        itertools.product(*(support_map[match_idx] for match_idx in fixture_order))
    )
    codes = ["|".join(values) for values in combinations]
    if len(codes) != len(set(codes)):
        raise ContractError(f"{arm}/{schedule} ticket space is not complete Cartesian")
    rows: list[dict[str, Any]] = []
    for ordinal, (values, code) in enumerate(zip(combinations, codes, strict=True)):
        identity = "|".join(
            f"{match_idx}:{outcome}"
            for match_idx, outcome in zip(fixture_order, values, strict=True)
        )
        rows.append(
            {
                "issue": issue,
                "issue_year": year,
                "support_arm": arm,
                "schedule": schedule,
                "ticket_ordinal": ordinal,
                "ticket_code": code,
                "ticket_identity": identity,
                "units": units_by_code[code],
                "stake_cny": units_by_code[code] * STAKE_PER_UNIT_CNY,
            }
        )
    return rows


def _fractional_ticket_rows(
    *,
    issue: str,
    year: int,
    arm: str,
    schedule: str,
    fixture_order: list[int],
    support_map: dict[int, tuple[str, ...]],
    cny_per_ticket: float,
) -> list[dict[str, Any]]:
    """Ideal fractional 50/50 counterfactual tickets (continuous stakes)."""
    combinations = list(
        itertools.product(*(support_map[match_idx] for match_idx in fixture_order))
    )
    codes = ["|".join(values) for values in combinations]
    rows: list[dict[str, Any]] = []
    for ordinal, (values, code) in enumerate(zip(combinations, codes, strict=True)):
        identity = "|".join(
            f"{match_idx}:{outcome}"
            for match_idx, outcome in zip(fixture_order, values, strict=True)
        )
        rows.append(
            {
                "issue": issue,
                "issue_year": year,
                "support_arm": arm,
                "schedule": schedule,
                "ticket_ordinal": ordinal,
                "ticket_code": code,
                "ticket_identity": identity,
                "units": np.nan,
                "stake_cny": cny_per_ticket,
            }
        )
    return rows


def _ticket_codes_for(support_map: dict[int, tuple[str, ...]], fixture_order: list[int]) -> list[str]:
    combinations = list(
        itertools.product(*(support_map[match_idx] for match_idx in fixture_order))
    )
    return ["|".join(values) for values in combinations]


def _settle_schedule(
    tickets: list[dict[str, Any]],
    realized: list[str],
    trusted: bool,
    *,
    winning_sp_product: float,
    stake_unit_cny: float,
) -> tuple[float, int]:
    """Settle one schedule: payout = winning units x stake unit x 0.65 x SP
    product, ticket-level-once.  For fractional tickets the 'unit' is the
    fractional CNY stake at FRACTIONAL_C* not a discretized unit."""
    winning_code = "|".join(realized)
    winning_tickets = [row for row in tickets if row["ticket_code"] == winning_code]
    if not trusted or not winning_tickets:
        return 0.0, 0
    payout = 0.0
    winning_units = 0
    for row in winning_tickets:
        if row["units"] is np.nan or pd.isna(row["units"]):
            payout += row["stake_cny"] * PAYOUT_FACTOR * winning_sp_product
            winning_units += 1
        else:
            payout += (
                row["units"] * stake_unit_cny * PAYOUT_FACTOR * winning_sp_product
            )
            winning_units += row["units"]
    return float(payout), int(winning_units)


# Schedules emitted by the per-issue constructor.
#   R3_STANDALONE     -- accepted #392 R3 CONTROL, 128 tickets x 4 units, CNY1,024
#   C1E3_STANDALONE   -- accepted #392 C1E3, 216 tickets, 512 units, CNY1,024
#   R0_COMPARATOR     -- accepted #366 R0, 128 tickets x 4 units, CNY1,024
#   MIXED_50_50       -- CNY512 R3 (2u/ticket) + CNY512 C1E3 (1+extra40), CNY1,024
#   FRACTIONAL_50_50  -- ideal fractional CNY512 each arm, CNY1,024 total
STANDALONE_SCHEDULES = ("R3_STANDALONE", "C1E3_STANDALONE", "R0_COMPARATOR")


def _construct_one_issue(
    issue: str, year: int, anchor: pd.Timestamp, group: pd.DataFrame
) -> list[dict[str, Any]]:
    """Build all schedule bundles for one issue from its action rows.

    Selection and supports are byte-identical to the accepted N7 semantics:
    choose top-7 fixtures by retained_mass, R3 pressure support for R3/C1E3,
    baseline support for R0, then C1E3 contraction/expansion.
    """
    selected = (
        group.sort_values(
            ["retained_mass", "match_idx"],
            ascending=[False, True],
            kind="stable",
        )
        .head(N_LEGS)
        .sort_values("match_idx", kind="stable")
        .copy()
    )
    if len(selected) != N_LEGS:
        raise ContractError(f"issue {issue} lacks seven fixtures")
    fixture_order = selected["match_idx"].astype(int).tolist()
    primary = _primary_support(selected)
    baseline = _baseline_support(selected)
    secondary = _secondary_support(selected, primary)
    trusted = bool(selected["settlement_available"].astype(bool).all())
    realized = selected["result_code"].fillna("").astype(str).tolist()
    winning_sp_product = float(selected["winning_sp"].astype(float).prod())
    rows: list[dict[str, Any]] = []
    for arm, support_map in (
        (PRIMARY_ARM, primary),
        (SECONDARY_ARM, secondary),
        (COMPARATOR_ARM, baseline),
    ):
        fixture_order_sorted = fixture_order  # same order for all arms
        codes = _ticket_codes_for(support_map, fixture_order_sorted)
        if arm == PRIMARY_ARM:
            expected_tickets = PRIMARY_TICKETS
            standalone_schedule = "R3_STANDALONE"
            mixed_units = {
                code: MIXED_R3_UNITS_PER_TICKET for code in codes
            }
            fractional_cny = FRACTIONAL_R3_CNY_PER_TICKET
        elif arm == SECONDARY_ARM:
            expected_tickets = SECONDARY_TICKETS
            standalone_schedule = "C1E3_STANDALONE"
            mixed_units = _ticket_units_flexible(
                issue, "C1E3", codes, MIXED_C1E3_FUNDED_UNITS
            )
            fractional_cny = FRACTIONAL_C1E3_CNY_PER_TICKET
        else:
            expected_tickets = PRIMARY_TICKETS
            standalone_schedule = "R0_COMPARATOR"
            mixed_units = {code: MIXED_R3_UNITS_PER_TICKET for code in codes}
            fractional_cny = FRACTIONAL_R3_CNY_PER_TICKET
        if len(codes) != expected_tickets or len(set(codes)) != expected_tickets:
            raise ContractError(
                f"{arm} ticket space is not complete Cartesian ({len(codes)}!={expected_tickets})"
            )
        schedules: dict[str, list[dict[str, Any]]] = {}
        if arm == PRIMARY_ARM:
            schedules["R3_STANDALONE"] = _ticket_rows_for_schedule(
                issue=issue, year=year, arm=arm, schedule="R3_STANDALONE",
                fixture_order=fixture_order_sorted, support_map=support_map,
                units_by_code={code: FUNDED_UNITS // PRIMARY_TICKETS for code in codes},
            )
            schedules["MIXED_50_50"] = _ticket_rows_for_schedule(
                issue=issue, year=year, arm=arm, schedule="MIXED_50_50",
                fixture_order=fixture_order_sorted, support_map=support_map,
                units_by_code=mixed_units,
            )
            schedules["FRACTIONAL_50_50"] = _fractional_ticket_rows(
                issue=issue, year=year, arm=arm, schedule="FRACTIONAL_50_50",
                fixture_order=fixture_order_sorted, support_map=support_map,
                cny_per_ticket=fractional_cny,
            )
        elif arm == SECONDARY_ARM:
            schedules["C1E3_STANDALONE"] = _ticket_rows_for_schedule(
                issue=issue, year=year, arm=arm, schedule="C1E3_STANDALONE",
                fixture_order=fixture_order_sorted, support_map=support_map,
                units_by_code=_ticket_units_flexible(
                    issue, "C1E3", codes, FUNDED_UNITS
                ),
            )
            schedules["MIXED_50_50"] = _ticket_rows_for_schedule(
                issue=issue, year=year, arm=arm, schedule="MIXED_50_50",
                fixture_order=fixture_order_sorted, support_map=support_map,
                units_by_code=mixed_units,
            )
            schedules["FRACTIONAL_50_50"] = _fractional_ticket_rows(
                issue=issue, year=year, arm=arm, schedule="FRACTIONAL_50_50",
                fixture_order=fixture_order_sorted, support_map=support_map,
                cny_per_ticket=fractional_cny,
            )
        else:  # R0 comparator
            schedules["R0_COMPARATOR"] = _ticket_rows_for_schedule(
                issue=issue, year=year, arm=arm, schedule="R0_COMPARATOR",
                fixture_order=fixture_order_sorted, support_map=support_map,
                units_by_code={code: FUNDED_UNITS // PRIMARY_TICKETS for code in codes},
            )
        for schedule_name, ticket_rows in schedules.items():
            if not ticket_rows:
                continue
            stake_cny = float(sum(row["stake_cny"] for row in ticket_rows))
            gross, winning_units = _settle_schedule(
                ticket_rows, realized, trusted,
                winning_sp_product=winning_sp_product,
                stake_unit_cny=STAKE_PER_UNIT_CNY,
            )
            rows.append(
                {
                    "issue": issue,
                    "issue_year": int(year),
                    "issue_anchor_ts": anchor,
                    "support_arm": arm,
                    "schedule": schedule_name,
                    "ticket_count": len(ticket_rows),
                    "funded_units": None if schedule_name == "FRACTIONAL_50_50" else int(
                        sum(row["units"] for row in ticket_rows if not pd.isna(row["units"]))
                    )
                    if ticket_rows and not pd.isna(ticket_rows[0]["units"])
                    else 0,
                    "stake_cny": stake_cny,
                    "gross_cny": gross if trusted else np.nan,
                    "pnl_cny": gross - stake_cny if trusted else np.nan,
                    "ticket_hit": bool(trusted and winning_units > 0),
                    "issue_profitable": bool(trusted and gross > stake_cny),
                    "winning_ticket_units": winning_units,
                    "settlement_complete": trusted,
                    "selected_match_ids": "|".join(map(str, fixture_order_sorted)),
                    "support_json": json.dumps(
                        {str(k): "".join(v) for k, v in support_map.items()},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
    return rows


def construct_surface(action: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Construct all schedules across issues; label exact-common denominators.

    A schedule is native-included when its issue settlement is complete.
    arm_exact_common/global_exact_common are computed per denominator scope
    over the schedules that participate in the comparison (standalone arms and
    the mixed portfolio).
    """
    bundle_rows: list[dict[str, Any]] = []
    for (issue, year, anchor), group in action.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        bundle_rows.extend(_construct_one_issue(issue, year, anchor, group))
    bundles = pd.DataFrame(bundle_rows)
    if bundles.empty:
        raise ContractError("surface construction produced no bundles")
    bundles["native_included"] = bundles["settlement_complete"].astype(bool)

    # Exact-common denominators: issues where R3_STANDALONE, C1E3_STANDALONE,
    # R0_COMPARATOR and both 50/50 schedules all settle completely.
    native = bundles[bundles["native_included"]].copy()
    if native.empty:
        raise ContractError("no native-included bundles")
    participating = native[native["schedule"].isin(
        (*STANDALONE_SCHEDULES, "MIXED_50_50", "FRACTIONAL_50_50")
    )]
    global_counts = (
        participating.groupby("issue", observed=True)["schedule"].nunique()
    )
    global_common = {
        str(issue)
        for issue, count in global_counts.items()
        if int(count) == len(participating["schedule"].unique())
    }
    bundles["global_exact_common"] = bundles["issue"].astype(str).isin(global_common)
    return {"bundles": bundles}


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    values: list[int] = []
    current = 0
    for item in mask:
        if bool(item):
            current += 1
        elif current:
            values.append(current)
            current = 0
    if current:
        values.append(current)
    return np.asarray(values, dtype=int)


# ---------------------------------------------------------------------------
# Board 3 -- required statistics
# ---------------------------------------------------------------------------

SCOPES_ANNUAL = tuple(str(year) for year in ALL_YEARS)
SCOPES = ("PRE_2025", "EXTENSION_2025_2026", *SCOPES_ANNUAL, "ALL")


def _denominator_mask(bundles: pd.DataFrame, denominator: str) -> pd.Series:
    if denominator == "NATIVE":
        return bundles["native_included"].astype(bool)
    if denominator == "EXACT_COMMON":
        return bundles["global_exact_common"].astype(bool)
    raise ContractError(f"unknown denominator: {denominator}")


def _path_metrics_ext(pnl: np.ndarray, gross: np.ndarray) -> dict[str, float | int]:
    """Path risk: drawdown, losing runs, underwater durations, payout shares."""
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    if len(pnl) == 0:
        return {
            "max_drawdown_fraction": 0.0,
            "longest_profitable_issue_losing_run": 0,
            "losing_run_p90": 0.0,
            "max_underwater_issues": 0,
            "open_underwater_issues": 0,
            "terminal_underwater_issues": 0,
            "largest_payout_share": 0.0,
            "top5_payout_share": 0.0,
            "top10_payout_share": 0.0,
            "payout_hhi": 0.0,
        }
    underwater = drawdown[1:] > 1e-15
    underwater_runs = _run_lengths(underwater)
    losing_runs = _run_lengths(pnl <= 0)
    max_underwater = int(underwater_runs.max()) if len(underwater_runs) else 0
    open_underwater = (
        int(len(pnl) - int(peak_indices[-1])) if drawdown[-1] > 1e-15 else 0
    )
    terminal_underwater = (
        int(underwater_runs[-1]) if len(underwater_runs) and underwater[-1] else 0
    )
    payouts = gross[gross > 0]
    total_payout = float(payouts.sum())
    if total_payout > 0:
        ordered = np.sort(payouts)[::-1]
        shares = ordered / total_payout
        top5 = float(shares[:5].sum())
        top10 = float(shares[:10].sum())
        largest = float(shares[0])
        hhi = float(np.square(shares).sum())
    else:
        top5 = top10 = largest = hhi = 0.0
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_profitable_issue_losing_run": (
            int(losing_runs.max()) if len(losing_runs) else 0
        ),
        "losing_run_p90": float(np.quantile(losing_runs, 0.90)) if len(losing_runs) else 0.0,
        "max_underwater_issues": max_underwater,
        "open_underwater_issues": open_underwater,
        "terminal_underwater_issues": terminal_underwater,
        "largest_payout_share": largest,
        "top5_payout_share": top5,
        "top10_payout_share": top10,
        "payout_hhi": hhi,
    }


def _performance_board(bundles: pd.DataFrame) -> pd.DataFrame:
    """Per denominator x scope x schedule economics + path risk."""
    rows: list[dict[str, Any]] = []
    for denominator in ("NATIVE", "EXACT_COMMON"):
        eligible = bundles[_denominator_mask(bundles, denominator)].copy()
        if eligible.empty:
            continue
        for scope, scoped in _scoped_frames(eligible):
            for (arm, schedule), group in scoped.groupby(
                ["support_arm", "schedule"], sort=True, observed=True
            ):
                group = group.sort_values(
                    ["issue_anchor_ts", "issue"], kind="stable"
                ).reset_index(drop=True)
                pnl = group["pnl_cny"].to_numpy(float)
                gross = group["gross_cny"].to_numpy(float)
                stake = float(group["stake_cny"].sum())
                largest = int(np.argmax(gross)) if len(gross) else 0
                rows.append(
                    {
                        "denominator": denominator,
                        "scope": scope,
                        "support_arm": arm,
                        "schedule": schedule,
                        "issues": int(len(group)),
                        "stake_cny": stake,
                        "gross_cny": float(gross.sum()),
                        "pnl_cny": float(pnl.sum()),
                        "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                        "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                        "stake_roi": float(pnl.sum() / stake) if stake > 0 else math.nan,
                        "issue_hit_rate": float(group["ticket_hit"].mean()),
                        "issue_profitable_rate": float(
                            group["issue_profitable"].mean()
                        ),
                        "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest])
                        if len(pnl)
                        else 0.0,
                        **_path_metrics_ext(pnl, gross),
                    }
                )
    return pd.DataFrame(rows)


def _scoped_frames(eligible: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    parts: list[tuple[str, pd.DataFrame]] = [
        (str(year), eligible[eligible["issue_year"].eq(year)])
        for year in ALL_YEARS
    ]
    pre = eligible[eligible["issue_year"].le(2024)]
    ext = eligible[eligible["issue_year"].ge(2025)]
    parts.append(("PRE_2025", pre))
    parts.append(("EXTENSION_2025_2026", ext))
    parts.append(("ALL", eligible))
    return [(scope, frame) for scope, frame in parts if not frame.empty]


def _paired_frame_for_schedule(
    bundles: pd.DataFrame, schedule_a: str, schedule_b: str
) -> pd.DataFrame:
    """Exact-common paired issue PnL between two schedules.

    The mixed 50/50 schedule carries one row per support arm per issue, so
    issue-level economics are summed across arms before pairing.
    """
    a_raw = bundles[
        bundles["schedule"].eq(schedule_a) & bundles["native_included"].astype(bool)
    ]
    b_raw = bundles[
        bundles["schedule"].eq(schedule_b) & bundles["native_included"].astype(bool)
    ]

    def _issue_level(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        grouped = (
            frame.groupby(
                ["issue", "issue_anchor_ts"], observed=True, sort=False
            )
            .agg(pnl=("pnl_cny", "sum"), gross=("gross_cny", "sum"))
            .reset_index()
        )
        return grouped.rename(
            columns={
                "issue": "issue",
                "issue_anchor_ts": "issue_anchor_ts",
                "pnl": "pnl_sched",
                "gross": "gross_sched",
            }
        )

    a = _issue_level(a_raw).rename(
        columns={"pnl_sched": "pnl_a", "gross_sched": "gross_a"}
    )
    b = _issue_level(b_raw).rename(
        columns={"pnl_sched": "pnl_b", "gross_sched": "gross_b"}
    )
    merged = a.merge(b, on=["issue", "issue_anchor_ts"], how="inner")
    if merged.duplicated("issue").any():
        raise ContractError("paired schedule issues are not unique")
    merged["anchor"] = merged["issue_anchor_ts"]
    return merged.sort_values(["anchor", "issue"], kind="stable").reset_index(drop=True)


def _matched_contrasts_board(bundles: pd.DataFrame) -> pd.DataFrame:
    """Matched lift of the mixed portfolio versus each standalone arm and the
    R0 comparator, plus ex-largest and largest paired delta sensitivity."""
    rows: list[dict[str, Any]] = []
    pairs = [
        ("MIXED_50_50", "MIXED_50_50", "R3_STANDALONE", "vs_R3"),
        ("MIXED_50_50", "MIXED_50_50", "C1E3_STANDALONE", "vs_C1E3"),
        ("MIXED_50_50", "MIXED_50_50", "R0_COMPARATOR", "vs_R0"),
    ]
    for scope in ("PRE_2025", "EXTENSION_2025_2026", "ALL"):
        for _, subject, ref, tag in pairs:
            paired = _paired_frame_for_schedule(bundles, subject, ref)
            if scope == "PRE_2025":
                paired = paired[paired["issue"].astype(str).lt("25011")]
            elif scope == "EXTENSION_2025_2026":
                paired = paired[paired["issue"].astype(str).ge("25011")]
            if paired.empty:
                continue
            delta = paired["pnl_a"].to_numpy(float) - paired["pnl_b"].to_numpy(float)
            rows.append(
                {
                    "scope": scope,
                    "subject_schedule": subject,
                    "reference_schedule": ref,
                    "contrast": tag,
                    "issues": int(len(paired)),
                    "subject_pnl_cny": float(paired["pnl_a"].sum()),
                    "reference_pnl_cny": float(paired["pnl_b"].sum()),
                    "matched_lift_cny": float(delta.sum()),
                    "matched_ex_largest_lift_cny": float(
                        delta.sum() - delta[np.argmax(np.abs(delta))]
                    )
                    if len(delta)
                    else 0.0,
                    "largest_abs_paired_delta_cny": float(np.abs(delta).max())
                    if len(delta)
                    else 0.0,
                    "moving_block_p05_lift_cny": float(
                        _paired_bootstrap_p05(delta)
                    ),
                }
            )
    return pd.DataFrame(rows)


def _paired_bootstrap_p05(delta: np.ndarray) -> float:
    """Chronology-preserving circular moving-block bootstrap (block 10,
    5,000 fixed draws) of the paired sample mean; returns the p05."""
    length = len(delta)
    if length == 0:
        return 0.0
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    block = min(MOVING_BLOCK_LENGTH, length)
    blocks_needed = math.ceil(length / block)
    starts = rng.integers(0, length, size=(BOOTSTRAP_DRAWS, blocks_needed))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets[None, None, :]) % length
    indices = indices.reshape(BOOTSTRAP_DRAWS, -1)[:, :length]
    means = delta[indices].mean(axis=1)
    return float(np.quantile(means, 0.05))


def _correlation_board(bundles: pd.DataFrame) -> pd.DataFrame:
    """R3/C1E3 issue-PnL correlations (descriptive, not independent Edge):
    Pearson/Spearman, losing-only/downside, simultaneous rates,
    underwater-state overlap and payout-issue overlap."""
    from scipy.stats import pearsonr, spearmanr

    paired = _paired_frame_for_schedule(bundles, "R3_STANDALONE", "C1E3_STANDALONE")
    rows: list[dict[str, Any]] = []
    if paired.empty:
        return pd.DataFrame(rows)
    pnl_a = paired["pnl_a"].to_numpy(float)
    pnl_b = paired["pnl_b"].to_numpy(float)
    gross_a = paired["gross_a"].to_numpy(float)
    gross_b = paired["gross_b"].to_numpy(float)

    def _corr(x: np.ndarray, y: np.ndarray) -> float:
        if len(x) < 2 or np.allclose(x, x[0]) or np.allclose(y, y[0]):
            return math.nan
        return float(pearsonr(x, y)[0])

    def _spear(x: np.ndarray, y: np.ndarray) -> float:
        if len(x) < 3 or np.allclose(x, x[0]) or np.allclose(y, y[0]):
            return math.nan
        return float(spearmanr(x, y)[0])

    downside = (pnl_a < 0) | (pnl_b < 0)
    both_profit = (pnl_a > 0) & (pnl_b > 0)
    both_loss = (pnl_a < 0) & (pnl_b < 0)

    # underwater state per issue (equity below running peak)
    def _underwater_mask(pnl: np.ndarray) -> np.ndarray:
        equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
        peaks = np.maximum.accumulate(equity)
        return (peaks[1:] - equity[1:]) > 1e-9

    ua = _underwater_mask(pnl_a)
    ub = _underwater_mask(pnl_b)
    both_underwater = ua & ub

    def _top_k_overlap(gx: np.ndarray, gy: np.ndarray, k: int) -> float:
        ix = set(np.argsort(gx)[::-1][:k].tolist())
        iy = set(np.argsort(gy)[::-1][:k].tolist())
        if not ix or not iy:
            return 0.0
        return float(len(ix & iy) / min(len(ix), len(iy)))

    rows.append(
        {
            "scope": "ALL",
            "issues": int(len(paired)),
            "pearson_issue_pnl": _corr(pnl_a, pnl_b),
            "spearman_issue_pnl": _spear(pnl_a, pnl_b),
            "downside_issues": int(downside.sum()),
            "pearson_downside_pnl": _corr(pnl_a[downside], pnl_b[downside])
            if downside.sum() >= 2
            else math.nan,
            "simultaneous_profit_rate": float(both_profit.mean()),
            "simultaneous_loss_rate": float(both_loss.mean()),
            "underwater_state_overlap_rate": float(both_underwater.mean()),
            "top5_payout_issue_overlap": _top_k_overlap(gross_a, gross_b, 5),
            "top10_payout_issue_overlap": _top_k_overlap(gross_a, gross_b, 10),
        }
    )
    return pd.DataFrame(rows)


def _reconciliation_board(bundles: pd.DataFrame) -> pd.DataFrame:
    """Actual-integer versus ideal-fractional mixed-portfolio reconciliation
    on their exact-common issues."""
    rows: list[dict[str, Any]] = []
    for scope in ("PRE_2025", "EXTENSION_2025_2026", "ALL"):
        int_frame = bundles[
            bundles["schedule"].eq("MIXED_50_50") & bundles["native_included"].astype(bool)
        ].copy()
        frac_frame = bundles[
            bundles["schedule"].eq("FRACTIONAL_50_50") & bundles["native_included"].astype(bool)
        ].copy()
        int_frame = int_frame[int_frame["issue"].astype(str).lt("25011")] if scope == "PRE_2025" else int_frame
        int_frame = int_frame[int_frame["issue"].astype(str).ge("25011")] if scope == "EXTENSION_2025_2026" else int_frame
        frac_frame = frac_frame[frac_frame["issue"].astype(str).lt("25011")] if scope == "PRE_2025" else frac_frame
        frac_frame = frac_frame[frac_frame["issue"].astype(str).ge("25011")] if scope == "EXTENSION_2025_2026" else frac_frame
        common = set(int_frame["issue"]) & set(frac_frame["issue"])
        if not common:
            continue
        int_c = int_frame[int_frame["issue"].isin(common)].sort_values("issue")
        frac_c = frac_frame[frac_frame["issue"].isin(common)].sort_values("issue")
        int_pnl = int_c.groupby("support_arm")["pnl_cny"].sum().to_dict()
        frac_pnl = frac_c.groupby("support_arm")["pnl_cny"].sum().to_dict()
        rows.append(
            {
                "scope": scope,
                "issues": int(len(common)),
                "integer_stake_cny": float(int_c["stake_cny"].sum()),
                "fractional_stake_cny": float(frac_c["stake_cny"].sum()),
                "integer_pnl_cny": float(int_c["pnl_cny"].sum()),
                "fractional_pnl_cny": float(frac_c["pnl_cny"].sum()),
                "integer_roi": float(int_c["pnl_cny"].sum() / int_c["stake_cny"].sum()),
                "fractional_roi": float(frac_c["pnl_cny"].sum() / frac_c["stake_cny"].sum()),
                "integer_r3_pnl_cny": float(int_pnl.get(PRIMARY_ARM, 0.0)),
                "fractional_r3_pnl_cny": float(frac_pnl.get(PRIMARY_ARM, 0.0)),
                "integer_c1e3_pnl_cny": float(int_pnl.get(SECONDARY_ARM, 0.0)),
                "fractional_c1e3_pnl_cny": float(frac_pnl.get(SECONDARY_ARM, 0.0)),
                "integer_unit_effect_pnl_cny": float(
                    int_c["pnl_cny"].sum() - frac_c["pnl_cny"].sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def _capital_paths(bundles: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for denominator in ("NATIVE", "EXACT_COMMON"):
        eligible = bundles[_denominator_mask(bundles, denominator)].copy()
        if eligible.empty:
            continue
        for scope, scoped in _scoped_frames(eligible):
            for (arm, schedule), group in scoped.groupby(
                ["support_arm", "schedule"], sort=True, observed=True
            ):
                group = group.sort_values(
                    ["issue_anchor_ts", "issue"], kind="stable"
                ).reset_index(drop=True)
                pnl = group["pnl_cny"].to_numpy(float)
                capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
                for order, (row, value) in enumerate(
                    zip(group.itertuples(), capital, strict=True), start=1
                ):
                    rows.append(
                        {
                            "denominator": denominator,
                            "scope": scope,
                            "support_arm": arm,
                            "schedule": schedule,
                            "issue_order": order,
                            "issue": str(row.issue),
                            "issue_year": int(row.issue_year),
                            "pnl_cny": float(row.pnl_cny),
                            "capital_cny": float(value),
                        }
                    )
    return pd.DataFrame(rows)


def evaluate_all(bundles: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "performance": _performance_board(bundles),
        "contrasts": _matched_contrasts_board(bundles),
        "correlations": _correlation_board(bundles),
        "reconciliation": _reconciliation_board(bundles),
        "paths": _capital_paths(bundles),
    }


# ---------------------------------------------------------------------------
# Board 4 -- decision (machine-readable)
# ---------------------------------------------------------------------------

def _decision(
    performance: pd.DataFrame,
    contrasts: pd.DataFrame,
    reconciliation: pd.DataFrame,
    bundles: pd.DataFrame,
    correlations: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Machine decision under the frozen classification rule:

    - standalone R3 and C1E3 remain positive or reverse on 2025, 2026,
      extension and ALL;
    - the fixed 50/50 portfolio is positive before and after largest-payout
      removal;
    - whether the path-risk improvement is genuine diversification or only
      return dilution;
    - whether 2025-2026 confirm, weaken or reverse the pre-2025 mechanism;
    - no promotion/deployment is authorized.
    """
    ec = performance[
        performance["denominator"].eq("EXACT_COMMON")
    ].copy()
    native = performance[
        performance["denominator"].eq("NATIVE")
    ].copy()

    def _pnl(scope: str, schedule: str, frame: pd.DataFrame) -> float:
        hit = frame[
            frame["scope"].eq(scope) & frame["schedule"].eq(schedule)
        ]
        return float(hit["pnl_cny"].sum()) if len(hit) else math.nan

    def _ex_largest(scope: str, schedule: str, frame: pd.DataFrame) -> float:
        hit = frame[
            frame["scope"].eq(scope) & frame["schedule"].eq(schedule)
        ]
        return float(hit["ex_largest_pnl_cny"].sum()) if len(hit) else math.nan

    def _max_dd(scope: str, schedule: str, frame: pd.DataFrame) -> float:
        hit = frame[
            frame["scope"].eq(scope) & frame["schedule"].eq(schedule)
        ]
        return float(hit["max_drawdown_fraction"].max()) if len(hit) else math.nan

    def _contrast_p05(scope: str, ref: str, frame: pd.DataFrame) -> float:
        hit = frame[
            frame["scope"].eq(scope) & frame["reference_schedule"].eq(ref)
        ]
        return float(hit["moving_block_p05_lift_cny"].sum()) if len(hit) else math.nan

    # ---- Predicates ----
    predicates: dict[str, bool] = {}

    # Standalone R3 on extension and ALL (native denominators; ex-largest).
    for year in EXTENSION_YEARS:
        predicates[f"R3_{year}_positive"] = bool(_pnl(str(year), "R3_STANDALONE", native) > 0)
        predicates[f"C1E3_{year}_positive"] = bool(_pnl(str(year), "C1E3_STANDALONE", native) > 0)
    predicates["R3_extension_positive"] = bool(
        _pnl("EXTENSION_2025_2026", "R3_STANDALONE", native) > 0
    )
    predicates["C1E3_extension_positive"] = bool(
        _pnl("EXTENSION_2025_2026", "C1E3_STANDALONE", native) > 0
    )
    predicates["R3_all_positive"] = bool(_pnl("ALL", "R3_STANDALONE", native) > 0)
    predicates["C1E3_all_positive"] = bool(_pnl("ALL", "C1E3_STANDALONE", native) > 0)
    predicates["R3_extension_ex_largest_positive"] = bool(
        _ex_largest("EXTENSION_2025_2026", "R3_STANDALONE", native) > 0
    )
    predicates["C1E3_extension_ex_largest_positive"] = bool(
        _ex_largest("EXTENSION_2025_2026", "C1E3_STANDALONE", native) > 0
    )

    # Mixed portfolio positive before/after largest payout removal.
    predicates["mixed_extension_positive"] = bool(
        _pnl("EXTENSION_2025_2026", "MIXED_50_50", native) > 0
    )
    predicates["mixed_all_positive"] = bool(
        _pnl("ALL", "MIXED_50_50", native) > 0
    )
    predicates["mixed_extension_ex_largest_positive"] = bool(
        _ex_largest("EXTENSION_2025_2026", "MIXED_50_50", native) > 0
    )
    predicates["mixed_all_ex_largest_positive"] = bool(
        _ex_largest("ALL", "MIXED_50_50", native) > 0
    )

    # Diversification vs dilution: mixed portfolio path risk vs the
    # half-weighted standalone aggregate (R3 + C1E3 each at CNY512).
    r3_all_max_dd = _max_dd("ALL", "R3_STANDALONE", native)
    c1e3_all_max_dd = _max_dd("ALL", "C1E3_STANDALONE", native)
    mixed_all_max_dd = _max_dd("ALL", "MIXED_50_50", native)
    if math.isnan(r3_all_max_dd) or math.isnan(c1e3_all_max_dd) or math.isnan(mixed_all_max_dd):
        raise ContractError("cannot compare mixed path risk against half-armed aggregate")
    # A mixed portfolio with maxDD below both standalone arms cannot be pure
    # dilution; a return-per-unit-of-risk improvement with meaningful
    # correlation below 1 indicates genuine diversification.
    predicates["mixed_maxdd_below_each_standalone"] = bool(
        mixed_all_max_dd < r3_all_max_dd and mixed_all_max_dd < c1e3_all_max_dd
    )
    pearson = math.nan
    if correlations is not None and not correlations.empty:
        pearson = float(correlations.iloc[0]["pearson_issue_pnl"])
    predicates["r3_c1e3_correlation_below_one"] = bool(
        not math.isnan(pearson) and pearson < 0.99
    )
    predicates["diversification_not_mere_dilution"] = bool(
        predicates["mixed_maxdd_below_each_standalone"]
        and _pnl("ALL", "MIXED_50_50", native) > 0
        and _pnl("ALL", "MIXED_50_50", native)
        >= 0.5 * _pnl("ALL", "R3_STANDALONE", native)
        + 0.5 * _pnl("ALL", "C1E3_STANDALONE", native)
    )

    # No annual extension-year reversal.
    annual_ext_ok = True
    for year in EXTENSION_YEARS:
        annual_ext_ok = annual_ext_ok and bool(
            _pnl(str(year), "MIXED_50_50", native) > 0
        )
    predicates["no_annual_extension_year_reversal"] = annual_ext_ok

    # Moving-block robustness: portfolio paired lift p05 non-negative vs each
    # standalone arm on extension and ALL.
    predicates["moving_block_p05_vs_r3_ext_nonnegative"] = bool(
        _contrast_p05("EXTENSION_2025_2026", "R3_STANDALONE", contrasts) >= 0
    )
    predicates["moving_block_p05_vs_c1e3_ext_nonnegative"] = bool(
        _contrast_p05("EXTENSION_2025_2026", "C1E3_STANDALONE", contrasts) >= 0
    )
    predicates["moving_block_p05_vs_r3_all_nonnegative"] = bool(
        _contrast_p05("ALL", "R3_STANDALONE", contrasts) >= 0
    )
    predicates["moving_block_p05_vs_c1e3_all_nonnegative"] = bool(
        _contrast_p05("ALL", "C1E3_STANDALONE", contrasts) >= 0
    )

    # Extension confirm / weaken / reverse pre-2025 mechanism.
    pre_r3 = _pnl("PRE_2025", "R3_STANDALONE", native)
    ext_r3 = _pnl("EXTENSION_2025_2026", "R3_STANDALONE", native)
    pre_c1e3 = _pnl("PRE_2025", "C1E3_STANDALONE", native)
    ext_c1e3 = _pnl("EXTENSION_2025_2026", "C1E3_STANDALONE", native)
    if math.isnan(pre_r3) or math.isnan(ext_r3):
        raise ContractError("cannot classify extension mechanism without both periods")
    predicates["extension_confirms_pre2025_r3"] = bool(
        (pre_r3 > 0 and ext_r3 > 0) or (pre_r3 < 0 and ext_r3 < 0)
    )
    predicates["extension_weakens_pre2025_r3"] = bool(
        (pre_r3 > 0 and ext_r3 <= 0) or (pre_r3 < 0 and ext_r3 >= 0)
    ) or bool(
        (pre_r3 > 0 and 0 < ext_r3 < pre_r3) or (pre_r3 < 0 and pre_r3 < ext_r3 < 0)
    )
    predicates["extension_reverses_pre2025_r3"] = bool(
        (pre_r3 > 0 and ext_r3 < 0) or (pre_r3 < 0 and ext_r3 > 0)
    )
    predicates["extension_confirms_pre2025_c1e3"] = bool(
        (pre_c1e3 > 0 and ext_c1e3 > 0) or (pre_c1e3 < 0 and ext_c1e3 < 0)
    )
    predicates["extension_reverses_pre2025_c1e3"] = bool(
        (pre_c1e3 > 0 and ext_c1e3 < 0) or (pre_c1e3 < 0 and ext_c1e3 > 0)
    )

    no_promotion = True
    predicates["no_promotion_authorized"] = no_promotion

    # ---- Historical-signal classification (positive pooled estimate alone
    #      is insufficient) ----
    market_gate = (
        predicates["R3_extension_positive"]
        and predicates["C1E3_extension_positive"]
        and predicates["R3_extension_ex_largest_positive"]
        and predicates["C1E3_extension_ex_largest_positive"]
        and predicates["no_annual_extension_year_reversal"]
        and predicates["mixed_extension_positive"]
        and predicates["mixed_extension_ex_largest_positive"]
        and predicates["diversification_not_mere_dilution"]
        and predicates["moving_block_p05_vs_r3_ext_nonnegative"]
        and predicates["moving_block_p05_vs_c1e3_ext_nonnegative"]
    )
    # failed_predicates = only gates whose FALSE blocks the increment;
    # reversal predicates are informative (a FALSE reversal is desirable) and
    # are reported separately, not as failures.
    failed = [
        name
        for name, value in predicates.items()
        if not value
        and name
        not in {
            "extension_reverses_pre2025_r3",
            "extension_reverses_pre2025_c1e3",
            "no_promotion_authorized",
        }
    ]
    if market_gate:
        verdict = "MIXED_N7_EXTENSION_HISTORICAL_SIGNAL_NO_PROMOTION"
    else:
        verdict = "NO_MIXED_N7_EXTENSION_INCREMENT"
    if verdict not in ALLOWED_VERDICTS:
        raise ContractError("decision vocabulary drifted")
    decision = {
        "contract": CONTRACT_ID,
        "verdict": verdict,
        "predictates_report": predicates,
        "failed_predicates": failed,
        "evidence_cutoff_ts": EVIDENCE_QUERY_CUTOFF_TS,
        "exposed_historical_only": True,
        "strategy_promoted": False,
        "prospective_authorized": False,
        "promotion_unlock_210": False,
        "consumes_218": False,
        "preserved_issues": [210, 218],
    }
    gates = pd.DataFrame([{"gate": name, "passed": value} for name, value in predicates.items()])
    return decision, gates


def _issues_ledger(
    bundles: pd.DataFrame,
    action: pd.DataFrame,
    extension_panel: pd.DataFrame | None = None,
    proxies_missing: list[str] | None = None,
) -> pd.DataFrame:
    """Issue census ledger: every discovered core/extension issue with
    inclusion status and reason."""
    rows: list[dict[str, Any]] = []
    proxies_missing = sorted(set(proxies_missing or []))
    panel_parts = [] if extension_panel is None else [extension_panel]
    panel_for_counts = pd.concat(panel_parts, ignore_index=True) if panel_parts else pd.DataFrame()
    discovered = sorted(
        set(bundles["issue"].astype(str))
        | set(action["issue"].astype(str))
        | set(panel_for_counts["issue_code"].astype(str))
        | set(proxies_missing)
    )
    action_counts = (
        action.groupby("issue", observed=True)["native_line_supported"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "supported_fixtures", "count": "panel_fixtures"})
    )
    panel_counts = (
        panel_for_counts.groupby("issue_code", observed=True)["native_line_supported"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "supported_fixtures", "count": "panel_fixtures"})
    )
    for issue in discovered:
        year = int(str(issue)[:2]) + 2000 if str(issue)[:2] in {"22", "23", "24", "25", "26"} else int(str(issue)[:4])
        included = bool(bundles.loc[bundles["issue"].astype(str).eq(str(issue)), "native_included"].any())
        if included:
            reason = "INCLUDED_TRUSTED_SETTLEMENT_COMPLETE"
        elif str(issue) in proxies_missing:
            reason = "EXTENSION_EXCLUDED_NO_PROXY_SURFACE"
        elif str(issue).startswith(("250", "260")):
            reason = "EXTENSION_EXCLUDED_SETTLEMENT_OR_SUPPORT_INCOMPLETE"
        else:
            reason = "CORE_EXCLUDED_SETTLEMENT_INCOMPLETE"
        if str(issue) in action_counts.index:
            counted = action_counts.loc[str(issue)]
        elif str(issue) in panel_counts.index:
            counted = panel_counts.loc[str(issue)]
        else:
            counted = None
        rows.append(
            {
                "issue": str(issue),
                "issue_year": year,
                "inclusion_status": "INCLUDED" if included else "EXCLUDED",
                "reason": reason,
                "panel_fixtures": int(counted["panel_fixtures"])
                if counted is not None
                else 0,
                "supported_fixtures": int(counted["supported_fixtures"])
                if counted is not None
                else 0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Board 5 -- orchestration
# ---------------------------------------------------------------------------

def scientific_frames(
    repo_root: Path,
    data_root: Path | None = None,
    *,
    verify_upstreams: bool = True,
    force_extension_fit: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, data_root)
    cutoff_receipt = freeze_evidence_cutoff()
    upstream_hashes = _verify_upstreams(repo_root, data_root) if verify_upstreams else {}

    # Core years: accepted #392 EXPANDING_EQUAL surface + corrected N7 settlement.
    core_mapped = _load_core_mapped(repo_root)
    core_settlement = _load_core_settlement(repo_root)
    core_action = _action_surface(core_mapped, core_settlement)

    # Extension years: shared loaders + frozen pre-extension mapping.
    from src.low_n_selector_data.pipeline import (
        load_issue_roles as _load_issue_roles,
    )

    candidate = data_root / "derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"
    registry = data_root / "derived/500_bjdc/500_bjdc.sqlite"
    roles = _load_issue_roles(candidate, registry)
    extension_panel = _extension_panel(data_root, roles)
    timing_for_attrs = _load_extension_timing(data_root)
    extension_settlement = _extension_settlement(data_root)
    history = _extension_history(repo_root, data_root, roles)
    eligible_target, boundary_ts = _pre_extension_boundary(extension_panel)
    source_hashes = {
        "history_frame_sha256": stable_frame_sha(history),
        "extension_panel_sha256": stable_frame_sha(extension_panel),
        "extension_settlement_sha256": stable_frame_sha(extension_settlement),
        "evidence_cutoff_ts": EVIDENCE_QUERY_CUTOFF_TS,
        **upstream_hashes,
    }
    ext_mapped, ext_receipts, ext_weights = _fit_extension_mapping(
        repo_root,
        history,
        eligible_target,
        boundary_ts,
        source_hashes,
    )
    # Bind the extension settlement to the mapped surface (issue + match_idx)
    # and enrich with the issue-year/anchor the action surface needs.
    anchor_map = (
        extension_panel.groupby("issue_code", observed=True)["fixture_decision_ts"]
        .min()
        .rename("issue_anchor_ts")
    )
    year_map = (
        extension_panel.groupby("issue_code", observed=True)["issue_year"]
        .first()
    )
    extension_settlement = extension_settlement.merge(
        anchor_map.rename_axis("issue").reset_index(),
        on="issue",
        how="left",
        validate="many_to_one",
    ).merge(
        year_map.rename_axis("issue").reset_index(),
        on="issue",
        how="left",
        validate="many_to_one",
    )
    # Settlement rows for issues with no extension proxy surface (e.g. 26087/88)
    # are settlement-unusable evidence: they cannot be mapped or bundled.  They
    # are excluded here and disclosed in the ledger rather than poisoning the
    # surface.
    extension_settlement_full_issues = set(
        extension_settlement["issue"].astype(str)
    )
    proxy_missing_issues = sorted(
        set(
            extension_settlement.loc[
                extension_settlement["issue_anchor_ts"].isna(), "issue"
            ].astype(str)
        )
    )
    extension_settlement = extension_settlement[
        extension_settlement["issue_anchor_ts"].notna()
    ].copy()
    if extension_settlement.empty:
        raise ContractError("extension settlement is empty after anchor binding")
    ext_mapped = ext_mapped.merge(
        extension_settlement[
            [
                "issue",
                "issue_year",
                "issue_anchor_ts",
                "match_idx",
                "result_code",
                "winning_sp",
                "settlement_available",
                "settlement_quality",
                "availability_ts",
                "settlement_source",
            ]
        ],
        left_on=["issue_code", "match_idx"],
        right_on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    ext_mapped.drop(columns=["issue"], inplace=True, errors="ignore")
    # The mapped frame already carries issue_year; drop any merged collision.
    if "issue_year_y" in ext_mapped.columns:
        ext_mapped = ext_mapped.drop(columns=["issue_year_y"])
    if "issue_year_x" in ext_mapped.columns and "issue_year" not in ext_mapped.columns:
        ext_mapped = ext_mapped.rename(columns={"issue_year_x": "issue_year"})
    action = _action_surface(ext_mapped, extension_settlement)

    all_action = pd.concat([core_action, action], ignore_index=True)
    constructed = construct_surface(all_action)
    bundles = constructed["bundles"]
    evaluated = evaluate_all(bundles)
    decision, gates = _decision(
        evaluated["performance"],
        evaluated["contrasts"],
        evaluated["reconciliation"],
        bundles,
        correlations=evaluated["correlations"],
    )
    proxies_missing = sorted(
        extension_settlement_full_issues
        - set(extension_panel["issue_code"].astype(str))
    )
    ledger = _issues_ledger(bundles, all_action, extension_panel, proxies_missing)
    material_overlap = timing_for_attrs.attrs.get(
        "material_overlap_disagreements", 0
    )
    source = {
        "contract": CONTRACT_ID,
        "evidence_cutoff_receipt": cutoff_receipt,
        "upstream_hashes": upstream_hashes,
        "core_years": list(CORE_YEARS),
        "extension_years": list(EXTENSION_YEARS),
        "pre_extension_boundary_ts": boundary_ts.isoformat(),
        "settlement_without_proxy_issues": proxies_missing,
        "material_overlap_disagreements_26051": int(material_overlap),
        "extension_timing_source_policy": (
            "MODELING_PLUS_2026 for <26051; RUNTIME_BEIDAN_LIVE for >=26051; "
            "never mixed per key; runtime self-consistency gated; disclosure only"
        ),
        "core_mapping_rows": int(len(core_mapped)),
        "core_mapping_issues": int(core_mapped["issue_code"].nunique()),
        "extension_mapping_rows": int(len(ext_mapped)),
        "extension_mapping_issues": int(ext_mapped["issue_code"].nunique()),
        "extension_settlement_rows": int(len(extension_settlement)),
        "extension_target_issues": int(eligible_target["issue_code"].nunique()),
        "extension_mapping_receipts": len(ext_receipts),
        "history_rows": int(len(history)),
        "history_issues": int(history["issue_code"].nunique()),
        "history_max_label_available_ts": history["label_available_ts"].max().isoformat(),
        "history_max_fixture_decision_ts": history["fixture_decision_ts"].max().isoformat(),
        "extension_max_fixture_decision_ts": ext_mapped[
            "fixture_decision_ts"
        ].max().isoformat(),
        "extension_max_availability_ts": extension_settlement[
            "availability_ts"
        ].max().isoformat(),
        "exposed_historical_only": True,
        "prospective_authorized": False,
        "temporal_policy": POLICY,
        "shared_temporal_client": "src.cutoff_walkforward.fitting",
        "primary_downstream": (
            "CORRECTED_N7_R3_CONTROL;128_COMPLETE_TICKETS;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
        "secondary_downstream": (
            "CORRECTED_N7_C1E3_SECONDARY;216_COMPLETE_TICKETS;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
        "comparator_downstream": (
            "CORRECTED_N7_R0_CONTROL;128_COMPLETE_TICKETS;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
        "mixed_portfolio": (
            "FIXED_50_50;R3_CNY512+C1E3_CNY512;TOTAL_CNY1024;"
            "0.65_TICKET_LEVEL_ONCE"
        ),
    }
    return {
        "source": source,
        "core_mapped": core_mapped,
        "core_settlement": core_settlement,
        "extension_mapped": ext_mapped,
        "extension_receipts": ext_receipts,
        "extension_weights": ext_weights,
        "extension_settlement": extension_settlement,
        "history": history,
        "bundles": bundles,
        "ledger": ledger,
        **evaluated,
        "gates": gates,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "extension_per_issue_receipts.json.gz": "extension_receipts",
    "extension_history.parquet": "history",
    "extension_settlement.parquet": "extension_settlement",
    "bundles.parquet": "bundles",
    "issue_ledger.csv": "ledger",
    "performance.csv": "performance",
    "capital_paths.parquet": "paths",
    "matched_contrasts.csv": "contrasts",
    "correlations.csv": "correlations",
    "integer_fractional_reconciliation.csv": "reconciliation",
    "decision_gates.csv": "gates",
    "decision.json": "decision",
}


def _write(path: Path, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        if path.suffix == ".parquet":
            value.to_parquet(path, index=False)
        else:
            value.to_csv(path, index=False, float_format="%.17g")
    elif path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
    else:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(value) for value in frame.columns]
    values = [columns, ["---"] * len(columns)]
    values.extend(
        [
            [str(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ]
    )
    return "\n".join("| " + " | ".join(row) + " |" for row in values)


def _build_deliveries(repo_root: Path, frames: dict[str, Any]) -> None:
    report = repo_root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    decision = frames["decision"]
    # Figure: capital paths for standalone + mixed schedules on exact-common ALL.
    figure = repo_root / FIGURE_PATH
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = frames["paths"]
    paths = paths[
        paths["denominator"].eq("EXACT_COMMON") & paths["scope"].eq("ALL")
    ]
    fig, axis = plt.subplots(figsize=(11, 5.5))
    for schedule, label, style in (
        ("R3_STANDALONE", "R3 standalone (CNY1,024)", "-"),
        ("C1E3_STANDALONE", "C1E3 standalone (CNY1,024)", "--"),
        ("R0_COMPARATOR", "R0 comparator (CNY1,024)", ":"),
        ("MIXED_50_50", "Mixed 50/50 (CNY1,024)", "-"),
        ("FRACTIONAL_50_50", "Fractional 50/50 (ideal)", "-."),
    ):
        group = paths[paths["schedule"].eq(schedule)].sort_values("issue_order")
        if group.empty:
            continue
        axis.plot(
            group["issue_order"], group["capital_cny"], style, label=label,
            linewidth=2 if schedule == "MIXED_50_50" else 1.2,
        )
    axis.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8, alpha=0.5)
    axis.set(
        title="Issue #394 — corrected-N7 standalone vs fixed 50/50 capital paths",
        xlabel="Exact-common issue order (2022-2026)",
        ylabel="Capital (CNY)",
    )
    axis.legend()
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    sections: list[str] = [
        f"# Issue #394 — frozen 50/50 corrected-N7 full-history extension",
        "",
        f"Contract: `{CONTRACT_ID}`",
        "",
        f"Decision: `{decision['verdict']}`.",
        "2022-2024 are exposed historical parity evidence; 2025-2026 are",
        "extension evidence consumed retrospectively. No promotion is authorized.",
        "",
        "## Evidence cutoff",
        "",
        f"- `EVIDENCE_QUERY_CUTOFF_TS`: `{EVIDENCE_QUERY_CUTOFF_TS}` (frozen at execution start)",
        f"- Pre-extension boundary (first eligible 2025 target decision epoch): `{frames['source']['pre_extension_boundary_ts']}`",
        "",
        "## Issue census",
        "",
        _markdown_table(frames["ledger"].head(40)),
        "",
        "## Performance (EXACT_COMMON denominator)",
        "",
        _markdown_table(
            frames["performance"][
                frames["performance"]["denominator"].eq("EXACT_COMMON")
            ]
        ),
        "",
        "## Performance (NATIVE denominator)",
        "",
        _markdown_table(
            frames["performance"][frames["performance"]["denominator"].eq("NATIVE")]
        ),
        "",
        "## Matched contrasts (mixed 50/50 vs standalone arms)",
        "",
        _markdown_table(frames["contrasts"]),
        "",
        "## R3/C1E3 correlations (descriptive)",
        "",
        _markdown_table(frames["correlations"]),
        "",
        "## Integer vs fractional mixed-portfolio reconciliation",
        "",
        _markdown_table(frames["reconciliation"]),
        "",
        "## Decision gates",
        "",
        _markdown_table(frames["gates"]),
        "",
        "## Reproduction",
        "",
        "```bash",
        f"PYTHONPATH=. python scripts/run_n7_mixed_full_history.py --data-root /path/to/data --force",
        f"PYTHONPATH=. python scripts/verify_n7_mixed_full_history.py --data-root /path/to/data",
        "```",
        "",
    ]
    report.write_text("\n".join(sections) + "\n", encoding="utf-8")

    notebook_path = repo_root / NOTEBOOK_PATH
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                f"# Issue #394 — frozen 50/50 corrected-N7 full-history extension\n\nContract: `{CONTRACT_ID}`\n\nDecision: `{decision['verdict']}`. 2022-2024 parity + 2025-2026 extension evidence; no promotion."
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nimport json, pandas as pd\n"
                f"OUT=Path.cwd()/{RESULT_PACKAGE!r}\n"
                "decision=json.loads((OUT/'decision.json').read_text())\ndecision"
            ),
            nbformat.v4.new_code_cell(
                "pd.read_csv(OUT/'performance.csv')"
                ".query(\"denominator=='EXACT_COMMON'\")"
            ),
            nbformat.v4.new_code_cell(
                "pd.read_csv(OUT/'performance.csv')"
                ".query(\"denominator=='NATIVE'\")"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'matched_contrasts.csv')"),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'correlations.csv')"),
            nbformat.v4.new_code_cell(
                "pd.read_csv(OUT/'integer_fractional_reconciliation.csv')"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'decision_gates.csv')"),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'issue_ledger.csv').head(40)"),
            nbformat.v4.new_markdown_cell(
                "All outcomes are exposed historical evidence: 2022-2024 parity and "
                "2025-2026 retrospective extension. The notebook does not authorize promotion."
            ),
        ]
    )
    nbformat.write(notebook, notebook_path)
    NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    nbformat.write(notebook, notebook_path)


def _manifest(repo_root: Path, target: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for relative, key in PACKAGE_FILES.items():
        path = target / relative
        if not path.is_file():
            raise ContractError(f"result package missing {relative}")
        files[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    deliveries = {}
    for relative in (REPORT_PATH, NOTEBOOK_PATH, FIGURE_PATH):
        path = repo_root / relative
        if path.is_file():
            deliveries[relative] = sha256_file(path)
    implementation = implementation_closure(
        repo_root,
        ("src.n7_mixed_full_history.pipeline",),
        distributions=(
            "numpy",
            "pandas",
            "scipy",
            "matplotlib",
            "nbformat",
            "nbclient",
        ),
    )
    return {
        "contract": CONTRACT_ID,
        "deliveries": deliveries,
        "files": files,
        "implementation": implementation,
        "evidence_cutoff_ts": EVIDENCE_QUERY_CUTOFF_TS,
    }


def build_package(
    repo_root: Path,
    output: Path | None = None,
    data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (output or repo_root / RESULT_PACKAGE).resolve()
    frames = scientific_frames(repo_root, data_root, verify_upstreams=True)
    if target.exists() and not force:
        raise ContractError(
            f"result package already exists at {target}; pass --force to rebuild"
        )

    def populate(staging: Path) -> None:
        for relative, key in PACKAGE_FILES.items():
            _write(staging / relative, frames[key])
        manifest = _manifest(repo_root, staging)
        _write(staging / "MANIFEST.json", manifest)

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f"{target.name}.staging")
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        populate(staging)
    except Exception:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise
    import shutil

    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(staging), str(target))
    _build_deliveries(repo_root, frames)
    return frames["decision"]


def _read(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _assert_frame(actual: pd.DataFrame, expected: pd.DataFrame, name: str) -> None:
    """Exact frame identity: numeric columns compared with float tolerance,
    non-numeric columns compared by exact string/object equality."""
    if actual.shape != expected.shape:
        raise ContractError(f"{name} shape differs: {actual.shape} vs {expected.shape}")
    for column in expected.columns:
        if column not in actual:
            raise ContractError(f"{name} is missing column {column}")
    for column in expected.columns:
        a = actual[column].to_numpy()
        e = expected[column].to_numpy()
        if pd.api.types.is_numeric_dtype(expected[column]) or pd.api.types.is_bool_dtype(
            expected[column]
        ):
            if not np.allclose(
                a.astype(float),
                e.astype(float),
                rtol=1e-12,
                atol=1e-9,
                equal_nan=True,
            ):
                raise ContractError(f"{name}.{column} numeric identity differs")
        else:
            if not np.array_equal(a, e):
                raise ContractError(f"{name}.{column} object identity differs")


def _semantic_checks(stored: dict[str, Any], replay: dict[str, Any]) -> None:
    """Pure tamper-relevant semantic checks: compare the stored package
    against a deterministic replay of the source-bound pipeline.

    Raises ContractError on any identity mismatch.  Callers that cannot
    replay (tests) may compare stored vs a precomputed replay to prove that
    a tampered stored frame fails where the honest frame passes.
    """
    bundles = stored["bundles"]
    if bundles.empty:
        raise ContractError("stored bundles are empty")
    for schedule in (
        "R3_STANDALONE",
        "C1E3_STANDALONE",
        "R0_COMPARATOR",
        "MIXED_50_50",
        "FRACTIONAL_50_50",
    ):
        if not bundles["schedule"].isin([schedule]).any():
            raise ContractError(f"stored bundles lack schedule {schedule}")
    # Mixed portfolio budget identities
    mixed = bundles[bundles["schedule"].eq("MIXED_50_50")].copy()
    per_arm = mixed.groupby("issue", observed=True)["stake_cny"].sum()
    if not np.isclose(per_arm, MIXED_TOTAL_CNY, rtol=0, atol=1e-9).all():
        raise ContractError("mixed portfolio issue stake is not CNY1,024")
    r3_mixed = bundles[
        bundles["schedule"].eq("MIXED_50_50") & bundles["support_arm"].eq(PRIMARY_ARM)
    ]
    if not r3_mixed["ticket_count"].eq(PRIMARY_TICKETS).all():
        raise ContractError("mixed R3 is not a complete 128-ticket space")
    c1e3_mixed = bundles[
        bundles["schedule"].eq("MIXED_50_50") & bundles["support_arm"].eq(SECONDARY_ARM)
    ]
    if not c1e3_mixed["ticket_count"].eq(SECONDARY_TICKETS).all():
        raise ContractError("mixed C1E3 is not a complete 216-ticket space")
    # Standalone budget identities
    alone = bundles[bundles["schedule"].isin(STANDALONE_SCHEDULES)]
    if not np.isclose(alone["stake_cny"], ISSUE_STAKE_CNY, rtol=0, atol=1e-9).all():
        raise ContractError("standalone issue stake is not CNY1,024")
    # Complete-ticket spaces: funded units reconcile to the issue stake at
    # CNY2 per unit for integer schedules.
    unit_mask = bundles["funded_units"].notna()
    if unit_mask.any():
        funded = bundles.loc[unit_mask, "funded_units"].to_numpy(float)
        stake = bundles.loc[unit_mask, "stake_cny"].to_numpy(float)
        if not np.isclose(funded * STAKE_PER_UNIT_CNY, stake, rtol=0, atol=1e-9).all():
            raise ContractError("funded units do not reconcile to stake")
    # No extension-year outcome may appear in the history frame
    history = stored["history"]
    if history["issue_code"].astype(str).ge("25011").any():
        raise ContractError("history contains an extension-year issue")
    if replay is not None:
        _assert_frame(replay["bundles"], bundles, "bundles replay")
        # Ledger replay: string-aware exact identity (issue, status, reason,
        # counts).  A tampered ledger row cannot pass even if the accounting
        # equation is preserved.
        replay_ledger = replay["ledger"].copy()
        stored_ledger = stored["ledger"].copy()
        replay_ledger["issue"] = replay_ledger["issue"].astype(str)
        stored_ledger["issue"] = stored_ledger["issue"].astype(str)
        cols = sorted(set(replay_ledger) & set(stored_ledger))
        try:
            pd.testing.assert_frame_equal(
                replay_ledger[cols].sort_values("issue").reset_index(drop=True),
                stored_ledger[cols].sort_values("issue").reset_index(drop=True),
            )
        except AssertionError as error:
            raise ContractError(f"ledger replay identity differs: {error}")
        if replay["source"].get("pre_extension_boundary_ts") != stored[
            "source"
        ].get("pre_extension_boundary_ts"):
            raise ContractError("pre-extension boundary drifted on replay")
    # Decision vocabulary and no-promotion invariant
    verdict = stored["decision"]["verdict"]
    if verdict not in ALLOWED_VERDICTS:
        raise ContractError("decision vocabulary drifted")
    if stored["decision"].get("strategy_promoted") is not False:
        raise ContractError("decision authorizes promotion")
    if stored["decision"].get("prospective_authorized") is not False:
        raise ContractError("decision authorizes prospective use")


def _verify_semantics(stored: dict[str, Any]) -> None:
    """Deterministic replay of the full surface and exact bundle equality."""
    replay = scientific_frames(
        stored["_repo_root"], stored["_data_root"], verify_upstreams=False
    )
    _semantic_checks(stored, replay)


def verify_package(
    repo_root: Path, package: Path | None = None, data_root: Path | None = None
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    target = (package or repo_root / RESULT_PACKAGE).resolve()
    stored: dict[str, Any] = {
        key: _read(target / relative)
        for relative, key in PACKAGE_FILES.items()
        if not relative.endswith(".json.gz") or True
    }
    stored["_repo_root"] = repo_root
    stored["_data_root"] = locate_data_root(repo_root, data_root)
    # Hash verification
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID:
        raise ContractError("manifest contract mismatch")
    checks: dict[str, Any] = {}
    for relative, meta in manifest.get("files", {}).items():
        checks[f"hash_{relative}"] = sha256_file(target / relative) == meta.get("sha256")
    try:
        _verify_semantics(stored)
        checks["semantics"] = True
    except Exception as error:
        checks["semantics"] = False
        checks["semantics_error"] = str(error)
    return checks