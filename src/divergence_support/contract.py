"""Issue #232 — causal SP-backed divergence support contract (v1).

Frozen definitions for BJ-UNIFIED-DIVERGENCE-SUPPORT-001 (candidate mode):

- source families and their recoverable pre-event candidates;
- the loss-of-support waterfall stages and stable reason codes;
- the chronological cohorts required by #209 (fit <= 2021, tune 2022,
  calibration 2023);
- the decision-epoch rule (observed_at <= decision_epoch, no timestamp
  inference);
- the modelability gate and terminal dispositions;
- the #229 evidence-debt E1-E4 closure contracts.

This module is contract, not implementation: values here are frozen decisions
shared by the census, waterfall, diagnosis, recovery, reconciliation,
modelability and debt modules.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Outcome axis (identical to #229 contract)
# ---------------------------------------------------------------------------
OUTCOME_CODES: tuple[str, str, str] = ("3", "1", "0")
OUTCOME_ORDER = {code: index for index, code in enumerate(OUTCOME_CODES)}

PROBABILITY_SUM_TOLERANCE = 2e-6
LOG_EPSILON = 1e-9
PAYOUT_FACTOR_BJ = 0.65

# ---------------------------------------------------------------------------
# Causal decision-epoch rule (identical to #229 rework decision)
# ---------------------------------------------------------------------------
# The decision epoch of a cell is the #203 issue-level feature cutoff.  A
# feature is causally available on a cell only when:
#   source present AND observed_at notna AND observed_at <= decision_epoch
#   AND kickoff_ts_utc >= decision_epoch (match not already started)
DECISION_EPOCH_COLUMN = "feature_cutoff_ts_utc"
KICKOFF_COLUMN = "kickoff_ts_utc"

# ---------------------------------------------------------------------------
# Probability representations (same names as #229 for continuity)
# ---------------------------------------------------------------------------
Q_BJ_SP_DEVIG = "Q_BJ_SP_DEVIG"
Q_BJ_CALIBRATED = "Q_BJ_CALIBRATED"
BJ_LINE_BOUNDARY = "BJ_LINE_BOUNDARY"
Q_EU_RAW_1X2 = "Q_EU_RAW_1X2"
Q_EU_BJLINE = "Q_EU_BJLINE"
P_POWER_BJLINE = "P_POWER_BJLINE"

DIVERGENCE_ANCHOR = Q_BJ_CALIBRATED

# ---------------------------------------------------------------------------
# Source families and recoverable pre-event candidates
# ---------------------------------------------------------------------------
# Family -> list of candidate sources, each with:
#   key: stable source key; committed: is the asset committed to git (True)
#        or a gitignored raw capture on the producer machine (False);
#   table: file/table path relative to repo root when committed;
#   clock: the timestamp column semantics; grade: source grade.
SP_SOURCE_CANDIDATES = (
    {
        "key": "bj214_selected_market_observations",
        "committed": True,
        "table": "results/bj214_decision_epoch_tensor_v1/sources/selected_market_observations.parquet",
        "clock": "snapshot_ts_utc",
        "grade": "accepted_decision_epoch_tensor",
        "note": "#214 selected decision-epoch BJ SP observations.",
    },
    {
        "key": "full_3sp_official",
        "committed": False,
        "table": "data/raw/beidan_full_3sp.csv",
        "clock": "last_update_ts",
        "grade": "official_3sp_settlement_page",
        "note": "Official 500.com 3SP export; #203 DATA_CARD adjudicates historical "
        "official 3SP as label-only (no trustworthy observation timestamp).",
    },
    {
        "key": "beidan_live_snapshots",
        "committed": False,
        "table": "data/beidan_live.db:snapshots",
        "clock": "snapshot_ts",
        "grade": "live_collector_timestamped",
        "note": "Live collector snapshots; observed 2026-05+ only.",
    },
    {
        "key": "sp_drift_panel",
        "committed": False,
        "table": "data/derived/sp_drift/panel.parquet",
        "clock": "snapshot_ts",
        "grade": "derived_timestamped_panel",
        "note": "SP drift research panel; observed 2026-05+ only.",
    },
    {
        "key": "500_bjdc_live_sp_snapshots",
        "committed": False,
        "table": "data/derived/500_bjdc/500_bjdc.sqlite:live_sp_snapshots",
        "clock": "fetched_at",
        "grade": "live_collector_timestamped",
        "note": "500.bjdc live SP captures; observed 2026-06+ only.",
    },
)

EU_SOURCE_CANDIDATES = (
    {
        "key": "bj203_devig_euro_probability",
        "committed": True,
        "table": "results/bj203_causal_tensor_v2/inference/feature_values.parquet",
        "clock": "euro_1h_available_ts_utc",
        "grade": "accepted_causal_tensor",
        "note": "#203 per-cell de-vig EURO probability with observed-at.",
    },
    {
        "key": "bj204_avg_eu",
        "committed": True,
        "table": "results/bj204_gate_a_preoutcome_v5/common_cell_features.parquet",
        "clock": "euro_1h_available_ts_utc",
        "grade": "accepted_market_anchor",
        "note": "#204 avg-EU market cells (same value as Q_BJ on avg-EU cells).",
    },
)

POWER_SOURCE_CANDIDATES = (
    {
        "key": "bj180_match_probability_freeze",
        "committed": True,
        "table": "results/bj180_gate_a_preoutcome_v2/match_probability_freeze.csv.gz",
        "clock": "feature_cutoff_ts",
        "grade": "accepted_unpromoted_expert",
        "note": "#180 team/matchup probability freeze with per-match cutoff.",
    },
)

# Accepted source identities (values of the *_source_identity columns).
SRC_BJ214_OBSERVATION = "bj214_decision_epoch_observation"
SRC_BJ203_DEVIG_EURO = "bj203_devig_euro_probability"
SRC_BJ180_TEAM_MODEL = "bj180_team_primary"
SRC_FULL_3SP_OFFICIAL = "full_3sp_official_export"
SRC_NONE = "none"

# ---------------------------------------------------------------------------
# Waterfall stages (REQ-S06).  Every stage after RAW must be countable and
# every drop must carry a stable reason code.
# ---------------------------------------------------------------------------
STAGE_RAW = "RAW_ROWS"
STAGE_IDENTITY_JOIN = "IDENTITY_JOIN"
STAGE_LINE_RECONCILIATION = "LINE_RECONCILIATION"
STAGE_TIMESTAMP_GATE = "TIMESTAMP_GATE"
STAGE_COMPLETE_TRIPLET = "COMPLETE_TRIPLET"
STAGE_CAUSAL_INTERSECTION = "CAUSAL_INTERSECTION"

WATERFALL_STAGES = (
    STAGE_RAW,
    STAGE_IDENTITY_JOIN,
    STAGE_LINE_RECONCILIATION,
    STAGE_TIMESTAMP_GATE,
    STAGE_COMPLETE_TRIPLET,
    STAGE_CAUSAL_INTERSECTION,
)

# Reason codes used inside the waterfall (in addition to #229's stable codes).
REASON_RAW_ASSET_ABSENT = "RAW_ASSET_ABSENT"
REASON_NO_IDENTITY_MATCH = "NO_IDENTITY_MATCH"
REASON_MISSING_NATIVE_LINE = "MISSING_NATIVE_LINE"
REASON_INVALID_LINE = "INVALID_HANDICAP_LINE"
REASON_LINE_MISMATCH = "SOURCE_HANDICAP_LINE_MISMATCH"
REASON_MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
REASON_POST_DECISION_OBSERVATION = "POST_DECISION_OBSERVATION"
REASON_PARTIAL_SOURCE_TRIPLET = "PARTIAL_SOURCE_TRIPLET"
REASON_IMPOSSIBLE_SP = "IMPOSSIBLE_SP"
REASON_NO_CAUSAL_EPOCH = "NO_CAUSAL_EPOCH"
REASON_IDENTITY_ONLY = "IDENTITY_ONLY"
REASON_RETROSPECTIVE_PROXY = "RETROSPECTIVE_PROXY"
REASON_ANCHOR_UNAVAILABLE = "ANCHOR_UNAVAILABLE"
REASON_SAME_SOURCE_NON_INDEPENDENT = "SAME_SOURCE_NON_INDEPENDENT"
REASON_NOT_IN_MODELING_AXIS = "NOT_IN_MODELING_AXIS"
REASON_LABEL_BOUNDARY_SEALED = "LABEL_BOUNDARY_SEALED"
REASON_TRANSLATION_NOT_IDENTIFIABLE = "TRANSLATION_NOT_IDENTIFIABLE"
REASON_DUPLICATE_SOURCE_ROW = "DUPLICATE_SOURCE_ROW"

# Root-cause classes for the zero-overlap diagnosis (contract item 2).
ROOT_ABSENT_OBSERVATIONS = "ABSENT_OBSERVATIONS"
ROOT_INCOMPATIBLE_SOURCE_CLOCKS = "INCOMPATIBLE_SOURCE_CLOCKS"
ROOT_WRONG_JOIN_KEYS = "WRONG_JOIN_KEYS"
ROOT_ISSUE_CALENDAR_MISMATCH = "ISSUE_CALENDAR_MISMATCH"
ROOT_LINE_SPACE_MISMATCH = "LINE_SPACE_MISMATCH"
ROOT_GENUINELY_UNAVAILABLE = "GENUINELY_UNAVAILABLE_HISTORICAL_DATA"
# Descriptive alias used in diagnosis rows for readability.
ROOT_GENUINELY_UNAVAILABLE_HISTORICAL_DATA = ROOT_GENUINELY_UNAVAILABLE

# ---------------------------------------------------------------------------
# Chronological cohorts required by #209 (fit/tune/calibration)
# ---------------------------------------------------------------------------
# #203 label years are authoritative for cohort assignment.
COHORT_FIT = "fit"             # issues with label year <= 2021
COHORT_TUNE = "tune"           # label year == 2022
COHORT_CALIBRATION = "calibration"  # label year == 2023
COHORT_LATER = "2024_plus"     # labels sealed

COHORT_BY_LABEL_YEAR = {
    2019: COHORT_FIT,
    2020: COHORT_FIT,
    2021: COHORT_FIT,
    2022: COHORT_TUNE,
    2023: COHORT_CALIBRATION,
}

# ---------------------------------------------------------------------------
# Modelability gate (contract "Modelability gate")
# ---------------------------------------------------------------------------
TERMINAL_READY_FOR_209 = "READY_FOR_209_PI_MODELABILITY_REVIEW"
TERMINAL_UNRECOVERABLE = "UNRECOVERABLE_WITH_CURRENT_SOURCES"

MODELABILITY_INTERFACES = (
    "Q_BJ_x_SP",
    "Q_BJ_x_EU_x_SP",
    "Q_BJ_x_POWER_x_SP",
)

# ---------------------------------------------------------------------------
# Package layout
# ---------------------------------------------------------------------------
PACKAGE_NAME = "bj232_divergence_support_v1"

UPSTREAM_PACKAGES = {
    "bj203": "results/bj203_causal_tensor_v2",
    "bj204": "results/bj204_gate_a_preoutcome_v5",
    "bj214": "results/bj214_decision_epoch_tensor_v1",
    "bj180": "results/bj180_gate_a_preoutcome_v2",
    "bj229": "results/bj229_divergence_profile_v1",
}


def upstream_path(root: Path, key: str) -> Path:
    """Resolve an upstream package path relative to the repository root."""
    return root / UPSTREAM_PACKAGES[key]


def package_path(root: Path) -> Path:
    """Resolve the immutable results package path."""
    return root / "results" / PACKAGE_NAME
