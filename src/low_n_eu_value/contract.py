"""Frozen constants for BJ-UNIFIED-LOWN-EU-VALUE-DATA-001."""

from __future__ import annotations

CONTRACT_ID = "BJ-UNIFIED-LOWN-EU-VALUE-DATA-001/v1"
ISSUE_NUMBER = 358
OUTCOMES = ("3", "1", "0")
HORIZON = "10h"
CAUSAL_GRADE = "RETROSPECTIVE_RELATIVE_PROXY"
SOURCE_ROLE = "Nowscore_Titan_historical_market_proxy"
SOURCE_TIMESTAMP_SEMANTICS = "RELATIVE_10H_LABEL_NO_EXACT_OBSERVATION_TIMESTAMP"
TICKET_PAYOUT_FACTOR = 0.65
N_VALUES = (3, 4, 5)

# #354's committed MANIFEST binds this pre-outcome feature payload.  It is the
# calibrated-probability lineage, not an outcome or settlement artifact.
SELECTOR_FEATURE_SHA256 = "3fbb9f316ca7542c3310a0e6bf2cafb565b99d87b4c2d8feed9ffe789ddbf592"
SELECTOR_FEATURE_FRAME_SHA256 = "43e3b0b47a54e4eb41d6fb4103a0adea9af3b2e11d3e9992a5fb1912f5f0d98b"
EU_WORKBOOK_SOURCE_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"

FEATURE_REQUIRED_COLUMNS = {
    "issue", "issue_year", "issue_anchor_ts", "match_idx", "prediction_role",
    "train_year_max", "baseline_support", "retained_mass", "prior_global_hit_rate",
    "n_available_books", "input_missing_count", "causal_grade",
    "q_raw_eu_3", "q_raw_eu_1", "q_raw_eu_0",
    "q_candidate_3", "q_candidate_1", "q_candidate_0",
}
RAW_REQUIRED_COLUMNS = {
    "issue_code", "match_idx", "source_match_id", "snapshot_kind", "bookmaker_id",
    "v1", "v2", "v3",
}
