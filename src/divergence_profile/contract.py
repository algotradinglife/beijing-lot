"""Issue #229 — divergence-aware M×3 data profile contract (v1, rework).

Freezes the source registry, probability-representation names, epsilon and
tolerance policies, stable exclusion reason codes, the causal decision-epoch
rule, per-feature observed-at/availability-mask policy, the payout-factor
boundary and the REQ-D evidence mapping for the
BJ-UNIFIED-DIVERGENCE-DATA-PROFILE-001 readiness package.

This module is contract, not implementation: every value here is a frozen
decision that the builder, notebook and tests share.  Nothing in this file
may be changed by the builder at build time.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Outcome axis
# ---------------------------------------------------------------------------
# Native Beijing handicap-result space: '3' home-covers, '1' draw, '0' away.
OUTCOME_CODES: tuple[str, str, str] = ("3", "1", "0")
OUTCOME_ORDER = {code: index for index, code in enumerate(OUTCOME_CODES)}

# ---------------------------------------------------------------------------
# Probability validity
# ---------------------------------------------------------------------------
# Every valid three-outcome vector must lie in [0,1] and sum to one within
# this frozen tolerance (matches #204's frozen acceptance 2e-6).
PROBABILITY_SUM_TOLERANCE = 2e-6
# Floor used for centered log-ratio / log-odds divergence computations.
# A vector component at or below this floor is not usable for the log
# transform; the divergence cell is emitted UNAVAILABLE with reason
# DIVERGENCE_LOG_EPSILON_VIOLATION rather than silently clipped.
LOG_EPSILON = 1e-9
# Beijing payout factor: ticket-level settlement metadata only. It may never
# appear at cell/per-leg level; 0.65^N constructions fail validation.
PAYOUT_FACTOR_BJ = 0.65

# ---------------------------------------------------------------------------
# Causal decision-epoch rule (REQ-D01, rework decision 2026-08-15)
# ---------------------------------------------------------------------------
# The decision epoch of a cell is the #203 issue-level feature cutoff
# (feature_cutoff_ts_utc, per-issue constant).  A feature is causally
# available on a cell only when:
#   source present
#   AND observed_at notna
#   AND observed_at <= decision_epoch
#   AND kickoff_ts_utc >= decision_epoch (match not already started)
# Cells whose #203 identity does not assert a decision epoch (2025-04+
# retrospective-proxy and 2026 identity-only rows) are NOT causal-feature
# cells; they remain countable identity/coverage rows with reason codes.
DECISION_EPOCH_COLUMN = "feature_cutoff_ts_utc"
KICKOFF_COLUMN = "kickoff_ts_utc"

# Per-feature observed-at columns bound from #203 identity (all match-level
# constants) and from each upstream source's own timestamp rule.
# #203 identity carries these per-match observed-at values:
OBSERVED_AT_IDENTITY = "identity_observed_ts_utc"
OBSERVED_AT_EURO_1H = "euro_1h_available_ts_utc"
OBSERVED_AT_PREDICTED_SP = "predicted_sp_available_ts_utc"
# #180 freeze carries its own model feature cutoff (per-match, equals the
# #180 common issue cutoff = first kickoff of the issue).
OBSERVED_AT_POWER = "feature_cutoff_ts"

# ---------------------------------------------------------------------------
# Probability representation names (contract section "Probability and
# handicap representations").
# ---------------------------------------------------------------------------
Q_BJ_SP_DEVIG = "Q_BJ_SP_DEVIG"          # normalized inverse decision-epoch BJ SP
Q_BJ_CALIBRATED = "Q_BJ_CALIBRATED"      # accepted causal market-anchor probability (#204)
BJ_LINE_BOUNDARY = "BJ_LINE_BOUNDARY"    # native handicap line as pricing boundary
Q_EU_RAW_1X2 = "Q_EU_RAW_1X2"            # de-vigged average European straight-result prob
Q_EU_BJLINE = "Q_EU_BJLINE"              # EU probability translated to native BJ space
P_POWER_BJLINE = "P_POWER_BJLINE"        # power/team model probability in native BJ space

# Q_BJ used as the divergence anchor: the calibrated market probability is
# the incumbent per #204's freeze card.
DIVERGENCE_ANCHOR = Q_BJ_CALIBRATED

# Per-representation observed-at / availability-mask column names (the
# canonical handoff must carry these for every representation).
def observed_at_col(representation: str) -> str:
    return f"{representation}_observed_at_utc"


def available_col(representation: str) -> str:
    return f"{representation}_available"


def reason_col(representation: str) -> str:
    return f"{representation}_unavailable_reason"


# ---------------------------------------------------------------------------
# Source identity (anti-alias registry, class-3 sweep)
# ---------------------------------------------------------------------------
# Per-cell source identity columns record which upstream value produced each
# representation so same-source "comparisons" are impossible by construction.
SOURCE_IDENTITY_Q_BJ = "qbj_source_identity"
SOURCE_IDENTITY_EU = "eu_source_identity"
SOURCE_IDENTITY_POWER = "power_source_identity"
SOURCE_IDENTITY_SP = "sp_source_identity"

# Accepted source identities (values of the *_source_identity columns).
SRC_BJ204_PCLOSE = "bj204_retrospective_proxy_pclose"
SRC_BJ204_AVG_EU = "bj204_retrospective_proxy_avg_eu"
SRC_BJ203_DEVIG_EURO = "bj203_devig_euro_probability"
SRC_BJ180_TEAM_MODEL = "bj180_team_primary"
SRC_BJ214_OBSERVATION = "bj214_decision_epoch_observation"
SRC_NONE = "none"

# Non-independent comparison reason: both sides of the "comparison" were
# produced from the SAME upstream value (e.g. Q_EU_RAW_1X2 and Q_BJ on a
# #204 avg-EU cell share market_probability).  Such rows must be explicitly
# unavailable for the comparison, never presented as independent.
REASON_SAME_SOURCE_NON_INDEPENDENT = "SAME_SOURCE_NON_INDEPENDENT"

# ---------------------------------------------------------------------------
# Upstream frozen packages (all committed and immutable).
# ---------------------------------------------------------------------------
UPSTREAM_PACKAGES = {
    "bj203": "results/bj203_causal_tensor_v2",
    "bj204": "results/bj204_gate_a_preoutcome_v5",
    "bj214": "results/bj214_decision_epoch_tensor_v1",
    "bj180": "results/bj180_gate_a_preoutcome_v2",
}

# Accepted European average-odds binding (raw, pre-de-vig).  The executed
# notebook stays byte-reproducible from committed packages; this binding is
# documented provenance, not a live read.
EURO_HISTORY_DB = "data/beidan_history.db"
# Raw league/handicap source used by #180 (committed binding in results
# package keeps the executed notebook independent of the 6.8 GB database).
LEAGUE_SOURCE_DB = "data/derived/beidan_xlsm/beidan_xlsm.sqlite"

# ---------------------------------------------------------------------------
# Cohort / label boundary
# ---------------------------------------------------------------------------
# Development labels may be opened for the dedicated profiling section only
# through calendar year 2023 (issue prefix 19/20/21/22/23). 2024+ results,
# final SP and payout labels are sealed.
LABEL_OPEN_MAX_YEAR = 2023
# 2024 identity/feature metadata is countable for coverage and covariate
# shift, but its label namespace is sealed.
SEALED_2024_MIN_YEAR = 2024
# 2025-04+ prospective issues retain the #210 admissible-use distinctions.
PROSPECTIVE_MIN_ISSUE = "25041"

# Development-label handoff payload: identity + label fields ONLY.  The
# ticket-level payout/settlement columns (payout_factor, payout_after_65_units,
# winning_zero_return_units, tax_*) are excluded from the cell-level payload
# per REQ-D07 — they may exist only as downstream ticket-level metadata.
DEV_LABEL_INCLUDE_COLUMNS = (
    "cell_join_key",
    "issue",
    "issue_instance",
    "match_id",
    "outcome_code",
    "result_code",
    "is_winner",
    "final_sp",
    "final_sp_available",
    "settlement_status",
    "settlement_quality",
    "settlement_source",
)

# ---------------------------------------------------------------------------
# Stable exclusion reason codes.  Every excluded row must carry one of these;
# nothing may be silently dropped.
# ---------------------------------------------------------------------------
REASON_MISSING_NATIVE_LINE = "MISSING_NATIVE_LINE"
REASON_MISSING_CALIBRATED_Q = "MISSING_CALIBRATED_Q"
REASON_DUPLICATE_CELL_IDENTITY = "DUPLICATE_CELL_IDENTITY"
REASON_INVALID_PROBABILITY_TRIPLET = "INVALID_PROBABILITY_TRIPLET"
REASON_IMPOSIBLE_SP = "IMPOSSIBLE_SP"
REASON_IMPOSIBLE_ODDS = "IMPOSSIBLE_ODDS"
REASON_NON_MONOTONE_TIMESTAMP = "NON_MONOTONE_TIMESTAMP"
REASON_POST_DECISION_OBSERVATION = "POST_DECISION_OBSERVATION"
REASON_MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
REASON_INVALID_HANDICAP_RESULT_MAPPING = "INVALID_HANDICAP_RESULT_MAPPING"
REASON_SOURCE_PROVENANCE_CONFLICT = "SOURCE_PROVENANCE_CONFLICT"
REASON_FEATURE_LABEL_OVERLAP = "FEATURE_LABEL_OVERLAP"
REASON_LABEL_BOUNDARY_SEALED = "LABEL_BOUNDARY_SEALED"
REASON_DIVERGENCE_LOG_EPSILON_VIOLATION = "DIVERGENCE_LOG_EPSILON_VIOLATION"
REASON_NO_EU_SOURCE = "NO_EU_SOURCE"
REASON_NO_POWER_SOURCE = "NO_POWER_SOURCE"
REASON_NO_BJ_SP_SOURCE = "NO_BJ_SP_SOURCE"
REASON_TRANSLATION_NOT_IDENTIFIABLE = "TRANSLATION_NOT_IDENTIFIABLE"
REASON_OUTLIER_REFERENCE = "OUTLIER_REFERENCE"
REASON_CONSTANT_NEAR_CONSTANT = "CONSTANT_NEAR_CONSTANT"
REASON_2024_LABEL_NAMESPACE_SEALED = "2024_LABEL_NAMESPACE_SEALED"
REASON_PAYOUT_FACTOR_AT_CELL_LEVEL = "PAYOUT_FACTOR_AT_CELL_LEVEL"
REASON_0_65_N_CONSTRUCTION = "0_65_N_CONSTRUCTION"
# Causal-eligibility exclusions (rework): a cell may exist on the #204 axis
# but be ineligible as a causal inference cell.
REASON_NO_CAUSAL_EPOCH = "NO_CAUSAL_EPOCH"          # no #203 decision epoch bound
REASON_IDENTITY_ONLY = "IDENTITY_ONLY"              # #203 identity-only row (no features)
REASON_RETROSPECTIVE_PROXY = "RETROSPECTIVE_PROXY"  # 2025-04+ retrospective-proxy panel
REASON_OBSERVED_AFTER_EPOCH = "OBSERVED_AFTER_DECISION_EPOCH"  # feature observed_at > decision epoch
REASON_NO_UNCERTAINTY_SOURCE = "NO_UNCERTAINTY_SOURCE"
REASON_INVALID_LINE = "INVALID_HANDICAP_LINE"

# ---------------------------------------------------------------------------
# Admissible-use classification (handoff feature dictionary).
# ---------------------------------------------------------------------------
ADMISSIBLE_INFERENCE = "inference"
ADMISSIBLE_DEVELOPMENT_LABEL = "development-label"
ADMISSIBLE_SEALED = "sealed"
ADMISSIBLE_IDENTITY_ONLY = "identity-only"

# ---------------------------------------------------------------------------
# Package layout
# ---------------------------------------------------------------------------
PACKAGE_NAME = "bj229_divergence_profile_v1"


def upstream_path(root: Path, key: str) -> Path:
    """Resolve an upstream package path relative to the repository root."""
    return root / UPSTREAM_PACKAGES[key]


def package_path(root: Path) -> Path:
    """Resolve the immutable results package path."""
    return root / "results" / PACKAGE_NAME
