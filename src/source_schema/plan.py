"""Issue #234 — migration-free replacement plan (deliverable 4).

Obsolete ambiguous schemas are removed from the accepted interface rather
than wrapped in compatibility layers (repo principle 1: no backward-compat
tax).  The plan names each legacy table, its verdict (REMOVE / REDIRECT /
KEEP_AS_SOURCE) and the exact replacement contract it must map to.

- REMOVE: the table's semantics are subsumed by the canonical schema and the
  legacy table is dropped from the accepted interface.
- REDIRECT: consumers switch to the canonical table; the legacy table remains
  only as an ingestion source until a cleanup milestone.
- KEEP_AS_SOURCE: the asset is a raw capture/source (registry receipt) and is
  not part of the accepted research interface.
"""

from __future__ import annotations

import pandas as pd

from . import contract

PLAN_ROWS: tuple[dict[str, str], ...] = (
    # --- beidan_xlsm.sqlite ---
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "market_snapshots",
        "verdict": "REDIRECT",
        "replacement": "market_observation + market_quote (long Mx3, snapshot_kind label)",
        "rationale": "Legacy wide Mx3 rows with label snapshots map onto canonical "
        "market_observation/market_quote; labels stay LABEL_RELATIVE (RETROSPECTIVE_PROXY).",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "market_consensus",
        "verdict": "REMOVE",
        "replacement": "computed view over market_quote; never a stored table",
        "rationale": "Aggregated consensus is derivable; storing it invites drift with "
        "the raw quotes (REQ-DS04).",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "exotic_odds",
        "verdict": "REMOVE",
        "replacement": "out of accepted scope; market_type domain is 3/1/0 1X2 + hcap",
        "rationale": "Exotic (goals/half_full/score) markets are not in the frozen "
        "market_type domain; removed from the accepted interface.",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "matches",
        "verdict": "REDIRECT",
        "replacement": "fixture + team + team_alias + competition + competition_alias",
        "rationale": "Identity columns (issue, match_idx) carry 1 duplicate pair and "
        "2,560 null kickoffs in legacy; canonical fixture enforces UNIQUE and NOT NULL.",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "action_candidates",
        "verdict": "REMOVE",
        "replacement": "derived selection views (not a source table)",
        "rationale": "Selection candidates are downstream derived artifacts, not source "
        "registry assets.",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "outcome_features",
        "verdict": "REMOVE",
        "replacement": "probability_estimate + derived feature views",
        "rationale": "Feature-engineered columns (kelly_*, euro_* moves) are derivable "
        "from market_quote/probability_estimate; removing the denormalized legacy table "
        "eliminates drift.",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "official_500_settlements",
        "verdict": "REDIRECT",
        "replacement": "settlement (physically separate namespace)",
        "rationale": "Settlement rows carry result + winning_sp + fetched_at; canonical "
        "settlement keeps result_code/winning_sp/settled_at_utc/source_id only.",
    },
    {
        "legacy_database": "beidan_xlsm.sqlite",
        "legacy_table": "official_3sp_settlements",
        "verdict": "REDIRECT",
        "replacement": "settlement (via raw export import)",
        "rationale": "Official 3SP export is a settlement source; #203 DATA_CARD "
        "adjudicates historical 3SP as label-only (no trustworthy observation time).",
    },
    # --- beidan_features.db ---
    {
        "legacy_database": "beidan_features.db",
        "legacy_table": "matches",
        "verdict": "REDIRECT",
        "replacement": "fixture + probability_estimate (EU p_close/p_open triplets)",
        "rationale": "EU probability features map onto canonical probability_estimate "
        "with estimator_id='eu_features_v1'; kickoff is SCHEDULE_ONLY.",
    },
    # --- beidan_history.db ---
    {
        "legacy_database": "beidan_history.db",
        "legacy_table": "historical_matches",
        "verdict": "REDIRECT",
        "replacement": "settlement + market_quote (avg closing odds as SETTLEMENT_ONLY proxy)",
        "rationale": "Settlement/history rows and average closing odds are not "
        "inference-time observations (REQ-DS03); REDIRECT to settlement namespace.",
    },
    {
        "legacy_database": "beidan_history.db",
        "legacy_table": "scrape_log",
        "verdict": "REDIRECT",
        "replacement": "ingestion_batch (batch receipt)",
        "rationale": "The scrape log's fetched_at/n_matches/status maps onto "
        "ingestion_batch.requested_at/received_at/row_count/status.",
    },
    # --- beidan_live.db ---
    {
        "legacy_database": "beidan_live.db",
        "legacy_table": "snapshots",
        "verdict": "REDIRECT",
        "replacement": "market_observation + market_quote (sp_1x2 + euro_1x2)",
        "rationale": "Live snapshots with snapshot_ts (TIMESTAMPED_UTC) are the primary "
        "prospective causal source; REDIRECT to canonical observation tables.",
    },
    {
        "legacy_database": "beidan_live.db",
        "legacy_table": "matches",
        "verdict": "REDIRECT",
        "replacement": "fixture + team_alias (fid alias)",
        "rationale": "Live matches carry fid; canonical fixture keeps source_match_key "
        "and resolves fid via alias crosswalk.",
    },
    {
        "legacy_database": "beidan_live.db",
        "legacy_table": "settlements",
        "verdict": "REDIRECT",
        "replacement": "settlement (source='live_collector')",
        "rationale": "Live settlements are after-event truth; canonical settlement "
        "namespace is physically separate (REQ-DS05).",
    },
)


def replacement_plan() -> pd.DataFrame:
    """Return the frozen migration-free replacement plan."""
    return pd.DataFrame(list(PLAN_ROWS))


def plan_document() -> str:
    """Render the migration-free replacement plan as markdown."""
    lines = [
        "# Migration-Free Replacement Plan (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)",
        "",
        "Obsolete ambiguous schemas are **removed from the accepted interface** "
        "rather than wrapped in compatibility layers (repository principle 1: "
        "no backward-compat tax).  Every legacy table is adjudicated:",
        "",
        "- **REMOVE** — subsumed by the canonical schema; dropped from the accepted interface.",
        "- **REDIRECT** — consumers switch to the canonical table; the legacy asset "
        "remains only as an ingestion source until a cleanup milestone.",
        "- **KEEP_AS_SOURCE** — raw capture/source asset; registry receipt, not "
        "part of the accepted research interface.",
        "",
        "| legacy_database | legacy_table | verdict | replacement | rationale |",
        "|---|---|---|---|---|",
    ]
    for row in PLAN_ROWS:
        lines.append(
            f"| {row['legacy_database']} | {row['legacy_table']} | {row['verdict']} "
            f"| {row['replacement']} | {row['rationale']} |"
        )
    lines.append("")
    lines.append("## Contract checklist")
    lines.append("")
    lines.append("- " + contract.PACKAGE_NAME)
    lines.append("- " + contract.CONTRACT_VERSION + " / " + contract.CONTRACT_VERSION_TAG)
    lines.append("")
    return "\n".join(lines)
