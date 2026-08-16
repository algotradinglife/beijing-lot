"""Issue #234 — BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 contract constants.

Frozen contract data shared by census, DDL, source registry, verifier and
the executed notebook.  Every domain value is defined here once so the
machine-readable outputs cannot drift from the code (REQ-DS07).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------
CONTRACT_VERSION = "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001"
CONTRACT_MODE = "candidate"
DDL_VERSION = f"{CONTRACT_VERSION}-ddl-v2"
PACKAGE_DIR_NAME = "bj234_source_schema_contract_v1"
NOTEBOOK_DIR = "notebooks/research/issue-234"
NOTEBOOK_NAME = "bj234_source_schema.ipynb"
REQUIREMENTS_HASH_SOURCE = "requirements.txt"

# ---------------------------------------------------------------------------
# Domains (single source of truth)
# ---------------------------------------------------------------------------
OUTCOME_CODES = ("3", "1", "0")
MARKET_TYPES = ("euro_1x2", "sp_1x2", "asian_hcap")
# snapshot kinds: historical workbook labels (initial/10h/1h/final) PLUS the
# prospective live/instant capture kind used by the timestamped live collector
# (EV R1 C3-5: live snapshot kinds must be expressible).
SNAPSHOT_KINDS = ("initial", "10h", "1h", "final", "live")
QUOTE_STATUSES = ("LIVE", "CLOSED", "VOID")

ADMISSIBLE_USES = (
    "STRICT_CAUSAL",      # observed before decision epoch with trusted clock
    "RETROSPECTIVE_PROXY",  # timestamp semantics insufficient; proxy only
    "SETTLEMENT_ONLY",    # after-event truth; never inference input
    "UNUSABLE",           # no clock / no identity / corrupt / not owned
)
CLOCK_SEMANTICS = (
    "TIMESTAMPED_UTC",
    "TIMESTAMPED_LOCAL_NO_TZ",
    "LABEL_RELATIVE",
    "SCHEDULE_ONLY",
    "SETTLEMENT_AFTER_EVENT",
    "NO_CLOCK",
)
COVERAGE_GRADES = ("A", "B", "C", "D", "F")
IDENTITY_STATUSES = ("CANONICAL", "ALIAS", "AMBIGUOUS", "UNIDENTIFIED")

# Downstream branches that consume this contract (REQ-DS08).
BRANCH_BEIJING = "BJ_SP_TIMESERIES #235"
BRANCH_EUROPEAN = "EU_ODDS #236"
BRANCH_POWER = "POWER_FEATURES #237"
BRANCH_INTEGRATION = "INTEGRATION #238"

# Namespaces (REQ-DS05): physically distinguishable research projections.
INFERENCE_NAMESPACE = "inference"
PROXY_NAMESPACE = "proxy"
SETTLEMENT_NAMESPACE = "settlement"
CAPTURE_NAMESPACE = "capture"

# ---------------------------------------------------------------------------
# Source families (issue contract section "Source families to register")
# ---------------------------------------------------------------------------
FAMILY_BEIJING = "F1_BJ_FIRST_PARTY"
FAMILY_INTERNAL_HISTORICAL = "F2_INTERNAL_ARCHIVE"
FAMILY_EUROPEAN_FEED = "F3_EUROPEAN_FEED"
FAMILY_FOOTBALL_DATA = "F4_FOOTBALL_DATA_CSV"
FAMILY_RESULTS_POWER = "F5_RESULTS_POWER"

# ---------------------------------------------------------------------------
# Beijing payout factor boundary: 0.65 is absent from every source/quote/
# probability table (contract rule).  It exists only in downstream ticket
# settlement metadata.
# ---------------------------------------------------------------------------
PAYOUT_FACTOR = 0.65  # referenced only by boundary checks; never emitted

# Canonical UTC timestamp shape enforced by DDL CHECK (ISO-8601, Z suffix).
UTC_TS_GLOB = "????-??-??T??:??:??Z"
UTC_TS_GLOB_MS = "????-??-??T??:??:??.???Z"
