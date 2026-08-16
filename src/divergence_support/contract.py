"""Issue #232 — causal SP-backed divergence support contract (v1, R2 fresh).

Frozen definitions for BJ-UNIFIED-DIVERGENCE-SUPPORT-001 (candidate mode).

R2 rework (EV REJECT method, 2026-08-16) changes vs R1:
- every causal decision flows through ``causal.causal_available``
  (observed_at <= decision_epoch <= kickoff) — no module-local gate logic;
- official 3SP export is fail-closed LABEL_ONLY (never a recovery source);
- POWER completeness uses ``team_primary_p*`` (frozen semantics), not
  ``market_p*``;
- terminal disposition is a pure function of the modelability support
  truth table (``disposition.terminal_disposition``), not builder branch code;
- the semantic verifier independently recomputes decisive payloads instead
  of trusting producer-written pass flags (``verifier.py``).

This module is contract, not implementation: values here are frozen
decisions shared by all modules.
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
# Causal decision-epoch rule (frozen; single implementation in causal.py)
# ---------------------------------------------------------------------------
# A feature is causally available on a cell only when ALL of:
#   source present AND observed_at notna AND observed_at <= decision_epoch
#   AND decision_epoch <= kickoff_ts_utc (match not already started).
# R2: the kickoff bound was missing from R1's recovery/waterfall/modelability
# gates (EV C1).  No module re-implements this rule.
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
# R2: ``full_3sp_official`` is graded LABEL_ONLY — #203 DATA_CARD adjudicates
# historical official 3SP as label-only (no trustworthy observation
# timestamp).  It is censused but NEVER read as a recovery source.
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
        "grade": "label_only_settlement_page",
        "note": "Official 500.com 3SP export; #203 DATA_CARD adjudicates historical "
        "official 3SP as label-only. R2: fail-closed — censused only, never "
        "enters recovery/triplet/waterfall-pass paths.",
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
        "note": "#180 team/matchup probability freeze with per-match cutoff. "
        "R2: completeness semantics are team_primary_p* (frozen), not market_p*.",
    },
)

# Accepted source identities (values of the *_source_identity columns).
SRC_BJ214_OBSERVATION = "bj214_decision_epoch_observation"
SRC_BJ203_DEVIG_EURO = "bj203_devig_euro_probability"
SRC_BJ180_TEAM_MODEL = "bj180_team_primary"
SRC_FULL_3SP_OFFICIAL = "full_3sp_official_export"
SRC_NONE = "none"

# R2: per-source field whitelist for read paths (fail-closed).  Any module
# reading a source must restrict to these columns; the census and verifier
# check that no settlement/label/final column is ever opened.
SOURCE_FIELD_WHITELIST: dict[str, tuple[str, ...]] = {
    "bj214_selected_market_observations": (
        "id", "match_id", "sp_3", "sp_1", "sp_0", "source", "snapshot_ts_utc",
    ),
    "full_3sp_official": (),  # LABEL_ONLY — no read path at all
    "beidan_live_snapshots": (),
    "sp_drift_panel": (),
    "500_bjdc_live_sp_snapshots": (),
    "bj203_devig_euro_probability": (
        "cell_join_key", "devig_euro_probability", "outcome_code_numeric",
    ),
    "bj204_avg_eu": (
        "cell_key", "issue", "match_idx", "outcome_code", "market_probability",
        "native_handicap_line", "source_is_pclose", "source_is_average_eu",
        "market_proxy_complete", "predicted_final_sp_input", "year",
    ),
    "bj180_match_probability_freeze": (
        "match_id", "issue", "match_idx", "kickoff_ts", "year", "handicap_line_norm",
        "feature_cutoff_ts", "team_primary_p3", "team_primary_p1", "team_primary_p0",
    ),
}

# Forbidden column-name substrings in any published payload (fail-closed).
FORBIDDEN_PAYLOAD_COLUMN_SUBSTRINGS = (
    "payout", "settle", "result", "final_sp", "winning_sp", "prize",
    "tax", "refund", "stake", "dividend",
)

# ---------------------------------------------------------------------------
# Waterfall stages (REQ-S06).  Every stage after RAW must be countable and
# every drop must carry a stable reason code.  R2: LINE_RECONCILIATION is
# emitted for EVERY source (EV E4) — identity line space is checked before
# the timestamp gate.
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
REASON_LABEL_ONLY_SOURCE = "LABEL_ONLY_SOURCE"
REASON_NO_IDENTITY_MATCH = "NO_IDENTITY_MATCH"
REASON_MISSING_NATIVE_LINE = "MISSING_NATIVE_LINE"
REASON_INVALID_LINE = "INVALID_HANDICAP_LINE"
REASON_LINE_MISMATCH = "SOURCE_HANDICAP_LINE_MISMATCH"
REASON_MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
REASON_POST_DECISION_OBSERVATION = "POST_DECISION_OBSERVATION"
REASON_POST_KICKOFF = "POST_KICKOFF_OBSERVATION"
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
# Modelability gate (contract "Modelability gate"; R2: truth table in
# disposition.py — READY requires EVERY necessary condition)
# ---------------------------------------------------------------------------
TERMINAL_READY_FOR_209 = "READY_FOR_209_PI_MODELABILITY_REVIEW"
TERMINAL_UNRECOVERABLE = "UNRECOVERABLE_WITH_CURRENT_SOURCES"

MODELABILITY_INTERFACES = (
    "Q_BJ_x_SP",
    "Q_BJ_x_EU_x_SP",
    "Q_BJ_x_POWER_x_SP",
)

# Every chronological role that must have issue-level support for READY.
REQUIRED_COHORTS_FOR_READY = (COHORT_FIT, COHORT_TUNE, COHORT_CALIBRATION)

# ---------------------------------------------------------------------------
# Package layout
# ---------------------------------------------------------------------------
PACKAGE_NAME = "bj232_divergence_support_v2"  # R2 fresh package

UPSTREAM_PACKAGES = {
    "bj203": "results/bj203_causal_tensor_v2",
    "bj204": "results/bj204_gate_a_preoutcome_v5",
    "bj214": "results/bj214_decision_epoch_tensor_v1",
    "bj180": "results/bj180_gate_a_preoutcome_v2",
    "bj229": "results/bj229_divergence_profile_v1",
}

# External trust anchors the verifier compares against (E1/E2 R2).
# The reviewed HEAD is supplied at verify time; this constant names the
# attribute used by the build receipt.
REVIEWED_COMMIT_SHA_ATTR = "reviewed_commit_sha"


def upstream_path(root: Path, key: str) -> Path:
    """Resolve an upstream package path relative to the repository root."""
    return root / UPSTREAM_PACKAGES[key]


def package_path(root: Path) -> Path:
    """Resolve the immutable results package path."""
    return root / "results" / PACKAGE_NAME
