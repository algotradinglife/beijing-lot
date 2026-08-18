"""Issue #234 — unified data source schema contract (v1, candidate mode).

Freezes BJ-UNIFIED-DATA-SOURCE-SCHEMA-001:

- the source registry row contract (every source carries an admissible-use
  class, clock semantics, coverage grade and raw-content hash receipt);
- canonical fixture identity rules (unique within ``issue_code x match_idx``,
  aliases resolved through a crosswalk, never by string equality);
- non-interchangeable temporal semantics: ``observed_at_utc`` (when the
  market was observed), ``received_at_utc`` (when we captured it),
  ``decision_at_utc`` (the frozen decision epoch) and ``kickoff_at_utc``
  (scheduled start) are distinct columns with distinct meanings;
- the canonical physical design: SQLite in WAL mode for one-writer
  append-only capture/control tables, immutable partitioned Parquet for
  research snapshots read by pandas/PyArrow;
- the versioned SQL DDL and pandas/PyArrow schema definitions;
- the domain dictionary (outcome codes exactly 3/1/0, market types,
  snapshot kinds, admissible-use classes);
- the migration-free replacement plan: obsolete ambiguous schemas are
  removed from the accepted interface, never wrapped in compatibility
  layers.

This module is contract, not implementation: every value here is a frozen
decision shared by the census, identity, feasibility, plan and builder
modules.  Nothing in this file may be changed by the builder at build time.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------
CONTRACT_VERSION = "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001"
CONTRACT_VERSION_TAG = "v1"
AUDIT_MODE = "candidate"
PACKAGE_NAME = "bj234_source_schema_contract_v1"
MILESTONE = "M1"
OWNER_ROLE = "Engineer"
PARENT_ISSUE = 232
ISSUE = 234


def package_path(root: Path) -> Path:
    return root / "results" / PACKAGE_NAME


# ---------------------------------------------------------------------------
# Outcome axis (must match #229/#232 exactly)
# ---------------------------------------------------------------------------
OUTCOME_CODES: tuple[str, str, str] = ("3", "1", "0")
OUTCOME_ORDER = {code: index for index, code in enumerate(OUTCOME_CODES)}

# The Beijing 0.65 payout coefficient is absent from every source, quote and
# probability table; it exists only in downstream ticket settlement metadata.
PAYOUT_FACTOR_BJ = 0.65
PAYOUT_FACTOR_FORBIDDEN_IN_TABLES = True

# ---------------------------------------------------------------------------
# Admissible-use classes (REQ-DS01)
# ---------------------------------------------------------------------------
# Every source is classified by causal admissibility with evidence, never by
# reputation.  A source may carry at most one admissible_use at a time; the
# class is frozen per source row in the registry.
USE_STRICT_CAUSAL = "STRICT_CAUSAL"          # observed before decision epoch
USE_RETROSPECTIVE_PROXY = "RETROSPECTIVE_PROXY"  # timestamp semantics insufficient
USE_SETTLEMENT_ONLY = "SETTLEMENT_ONLY"      # after-event truth, never inference input
USE_UNUSABLE = "UNUSABLE"                    # no clock / no identity / corrupt

ADMISSIBLE_USE_CLASSES: tuple[str, ...] = (
    USE_STRICT_CAUSAL,
    USE_RETROSPECTIVE_PROXY,
    USE_SETTLEMENT_ONLY,
    USE_UNUSABLE,
)

# ---------------------------------------------------------------------------
# Clock semantics (REQ-DS03)
# ---------------------------------------------------------------------------
# How a source's time columns relate to wall-clock observation.  Labels such
# as ``initial/10h/1h/final`` are NOT timestamps and force RETROSPECTIVE_PROXY
# unless independently proven otherwise.
CLOCK_TIMESTAMPED_UTC = "TIMESTAMPED_UTC"        # parseable UTC timestamps
CLOCK_TIMESTAMPED_LOCAL = "TIMESTAMPED_LOCAL_NO_TZ"  # local naive timestamps
CLOCK_LABEL_RELATIVE = "LABEL_RELATIVE"          # initial/10h/1h/final labels
CLOCK_SCHEDULE_ONLY = "SCHEDULE_ONLY"            # kickoff schedule, no observation clock
CLOCK_SETTLEMENT_AFTER_EVENT = "SETTLEMENT_AFTER_EVENT"
CLOCK_NO_CLOCK = "NO_CLOCK"

CLOCK_SEMANTICS: tuple[str, ...] = (
    CLOCK_TIMESTAMPED_UTC,
    CLOCK_TIMESTAMPED_LOCAL,
    CLOCK_LABEL_RELATIVE,
    CLOCK_SCHEDULE_ONLY,
    CLOCK_SETTLEMENT_AFTER_EVENT,
    CLOCK_NO_CLOCK,
)

# ---------------------------------------------------------------------------
# Coverage grades
# ---------------------------------------------------------------------------
GRADE_A = "A"  # full league/issue coverage with trusted clock
GRADE_B = "B"  # broad coverage, some clock caveats
GRADE_C = "C"  # partial coverage or unproven clock
GRADE_D = "D"  # narrow or settlement-only
GRADE_F = "F"  # unusable

COVERAGE_GRADES: tuple[str, ...] = (GRADE_A, GRADE_B, GRADE_C, GRADE_D, GRADE_F)

# ---------------------------------------------------------------------------
# Temporal column semantics — non-interchangeable (REQ-DS03)
# ---------------------------------------------------------------------------
# The four temporal meanings are distinct and must never be merged:
OBSERVED_AT = "observed_at_utc"      # when the market state was observed
RECEIVED_AT = "received_at_utc"      # when our pipeline captured/ingested it
DECISION_AT = "decision_at_utc"      # frozen decision epoch (per issue)
KICKOFF_AT = "kickoff_at_utc"        # scheduled kickoff (match start)
SETTLED_AT = "settled_at_utc"        # when the result was settled

TEMPORAL_SEMANTICS: tuple[str, ...] = (
    OBSERVED_AT,
    RECEIVED_AT,
    DECISION_AT,
    KICKOFF_AT,
    SETTLED_AT,
)

# ---------------------------------------------------------------------------
# Identity status (REQ-DS02)
# ---------------------------------------------------------------------------
IDENTITY_CANONICAL = "CANONICAL"      # fixture row is the canonical identity
IDENTITY_ALIAS = "ALIAS"              # resolves through team/competition alias
IDENTITY_AMBIGUOUS = "AMBIGUOUS"      # source key maps to multiple fixtures
IDENTITY_UNIDENTIFIED = "UNIDENTIFIED"

IDENTITY_STATUSES: tuple[str, ...] = (
    IDENTITY_CANONICAL,
    IDENTITY_ALIAS,
    IDENTITY_AMBIGUOUS,
    IDENTITY_UNIDENTIFIED,
)

# ---------------------------------------------------------------------------
# Market types (sampled from beidan_xlsm.market_snapshots market column)
# ---------------------------------------------------------------------------
MARKET_EURO_1X2 = "euro_1x2"
MARKET_SP_1X2 = "sp_1x2"
MARKET_ASIAN_HCAP = "asian_hcap"

MARKET_TYPES: tuple[str, ...] = (
    MARKET_EURO_1X2,
    MARKET_SP_1X2,
    MARKET_ASIAN_HCAP,
)

# Snapshot kinds observed in the legacy workbook.  These are LABELS, not
# observation timestamps; the registry records them as clock semantics
# LABEL_RELATIVE unless independently proven.
SNAPSHOT_KIND_INITIAL = "initial"
SNAPSHOT_KIND_10H = "10h"
SNAPSHOT_KIND_1H = "1h"
SNAPSHOT_KIND_FINAL = "final"

SNAPSHOT_KINDS: tuple[str, ...] = (
    SNAPSHOT_KIND_INITIAL,
    SNAPSHOT_KIND_10H,
    SNAPSHOT_KIND_1H,
    SNAPSHOT_KIND_FINAL,
)

# ---------------------------------------------------------------------------
# Source families (REQ-DS08: concrete selected source per downstream branch)
# ---------------------------------------------------------------------------
# Family -> canonical downstream branch name + selected concrete source.
# A "selected source" is the registry source_id the branch must consume.
FAMILY_BEIJING = "BEIJING_FIRST_PARTY"
FAMILY_INTERNAL_HISTORICAL = "INTERNAL_HISTORICAL"
FAMILY_EUROPEAN_FEED = "EUROPEAN_BOOKMAKER_FEED"
FAMILY_FOOTBALL_DATA_CSV = "FOOTBALL_DATA_CSV"
FAMILY_POWER_FEATURES = "POWER_FEATURES"

SOURCE_FAMILIES: tuple[str, ...] = (
    FAMILY_BEIJING,
    FAMILY_INTERNAL_HISTORICAL,
    FAMILY_EUROPEAN_FEED,
    FAMILY_FOOTBALL_DATA_CSV,
    FAMILY_POWER_FEATURES,
)

# Concrete selected source per downstream branch (REQ-DS08 handoff names the
# exact input/interface each subissue must consume).
BRANCH_BEIJING = "beijing"
BRANCH_EUROPEAN = "european"
BRANCH_POWER = "power"
BRANCH_INTEGRATION = "integration"

SELECTED_SOURCES: dict[str, str] = {
    BRANCH_BEIJING: "beijing_official_interface",       # prospective first-party capture
    BRANCH_EUROPEAN: "odds_api_historical",             # licensed timestamped EU feed
    BRANCH_POWER: "internal_results_public_football",   # causal power features
    BRANCH_INTEGRATION: "bj234_canonical_schema",       # this contract's physical schema
}

# ---------------------------------------------------------------------------
# Registry row contract
# ---------------------------------------------------------------------------
SOURCE_REGISTRY_COLUMNS: tuple[str, ...] = (
    "source_id",
    "provider",
    "endpoint",
    "acquisition_method",
    "terms_status",
    "timezone",
    "clock_semantics",
    "cadence_seconds",
    "parser_version",
    "admissible_use",
    "first_usable_at_utc",
    "last_usable_at_utc",
    "coverage_grade",
    "raw_sha256",
    "notes",
)

# ---------------------------------------------------------------------------
# Canonical physical tables (minimum normalized set from the issue contract)
# ---------------------------------------------------------------------------
# SQLite WAL capture/control tables (one-writer append-only):
CAPTURE_TABLES: tuple[str, ...] = (
    "source_registry",
    "ingestion_batch",
    "team",
    "team_alias",
    "competition",
    "competition_alias",
    "fixture",
    "decision_epoch",
    "market_observation",
    "market_quote",
    "probability_estimate",
)
# Physically separate settlement namespace (REQ-DS05):
SETTLEMENT_TABLES: tuple[str, ...] = ("settlement",)

# Research snapshot Parquet namespaces (immutable, partitioned):
INFERENCE_NAMESPACE = "inference"     # probability_estimate projection
PROXY_NAMESPACE = "proxy"             # RETROSPECTIVE_PROXY projections
SETTLEMENT_NAMESPACE = "settlement"   # physically separate settlement truth

# ---------------------------------------------------------------------------
# Replay / environment constants
# ---------------------------------------------------------------------------
REQUIREMENTS_HASH_SOURCE = "requirements.txt"
NOTEBOOK_DIR = "notebooks/research/issue-234"
NOTEBOOK_NAME = "bj234_source_schema.ipynb"
BUILD_SCRIPT = "scripts/build_bj234_source_schema.py"
EXECUTE_SCRIPT = "scripts/execute_bj234_notebook.py"
