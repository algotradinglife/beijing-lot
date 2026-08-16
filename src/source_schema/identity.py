"""Issue #234 — canonical fixture identity and alias crosswalk (REQ-DS02).

The canonical identity of a fixture is ``(issue_code, match_idx)`` — the
Beijing-issue slot number.  Source-specific keys (``provider_match_id``,
``fid``, ``match_id`` strings) are aliases that resolve through the crosswalk
tables; they never become the primary key of the canonical ``fixture`` table.

Rules frozen here:

1. **Unique within ``issue_code x match_idx``**: two rows with the same
   (issue_code, match_idx) are the same fixture; the schema enforces a unique
   constraint and identity_status CANONICAL.
2. **Aliases resolve, never replace**: ``team_alias`` and ``competition_alias``
   map source keys to canonical ids with valid-from/to windows; an unmapped
   source key is UNIDENTIFIED (never silently dropped or matched by string).
3. **Ambiguity is a defect**: a source key mapping to multiple canonical rows
   is AMBIGUOUS and blocks ingestion for that row.
4. **Decision epochs key by issue**: ``decision_epoch(issue_code, ...)`` binds
   the frozen decision time per issue; a fixture's decision time is looked up
   by issue, never inferred from observation labels.
"""

from __future__ import annotations

import pandas as pd



def _to_int(value: object) -> int:
    """Convert a scalar (int / numpy int / pandas scalar) to plain int."""
    if value is None:
        return -1
    if isinstance(value, float) and value != value:  # NaN
        return -1
    return int(value)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Crosswalk contract rows (frozen values for the package)
# ---------------------------------------------------------------------------
# team_alias / competition_alias templates: the contract fixes the column set
# and the resolution rule, not the concrete rows (rows are populated by each
# ingestion branch).  The identity-crosswalk contract document is emitted from
# these constants so the machine-readable contract and the markdown stay in
# sync (REQ-DS02/DS04).

TEAM_ALIAS_COLUMNS: tuple[str, ...] = (
    "source_id",
    "source_team_key",
    "team_id",
    "valid_from_utc",
    "valid_to_utc",
)

COMPETITION_ALIAS_COLUMNS: tuple[str, ...] = (
    "source_id",
    "source_competition_key",
    "competition_id",
    "valid_from_utc",
    "valid_to_utc",
)

# Alias resolution rules: source key -> canonical id with a validity window.
# valid_to_utc = NULL means "current".  Two aliases for the same source key
# with overlapping windows are a schema violation (REQ-DS04).
ALIAS_VALIDITY_RULE = (
    "An alias row is active when valid_from_utc <= asof <= COALESCE(valid_to_utc, "
    "'9999-12-31T23:59:59Z').  Overlapping active windows for the same "
    "(source_id, source_team_key) are forbidden by a partial unique index."
)


def identity_crosswalk_contract() -> str:
    """Render the identity-crosswalk contract document (markdown)."""
    lines = [
        "# Identity Crosswalk Contract (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)",
        "",
        "## Canonical identity",
        "",
        "A fixture's canonical identity is `(issue_code, match_idx)`.  The "
        "Beijing issue (e.g. `25042`) plus the slot index inside that issue "
        "uniquely names one match.  The `fixture` table enforces:",
        "",
        "- `PRIMARY KEY (fixture_id)`,",
        "- `UNIQUE (issue_code, match_idx)`,",
        "- `identity_status IN ('CANONICAL','ALIAS','AMBIGUOUS','UNIDENTIFIED')`.",
        "",
        "## Alias tables",
        "",
        "Source-specific keys are aliases, never primary keys.  `team_alias` "
        "and `competition_alias` map a source key to a canonical id:",
        "",
        f"- `team_alias({', '.join(TEAM_ALIAS_COLUMNS)})`",
        f"- `competition_alias({', '.join(COMPETITION_ALIAS_COLUMNS)})`",
        "",
        "Resolution rule:",
        "",
        f"> {ALIAS_VALIDITY_RULE}",
        "",
        "## Identity status semantics",
        "",
        "| status | meaning |",
        "|---|---|",
        "| CANONICAL | the fixture row is the canonical identity |",
        "| ALIAS | resolved from a source key through an alias row |",
        "| AMBIGUOUS | source key maps to multiple canonical fixtures (blocked) |",
        "| UNIDENTIFIED | source key has no alias row (never silently matched) |",
        "",
        "## Decision epoch",
        "",
        "`decision_epoch(decision_epoch_id, issue_code, decision_at_utc, "
        "rule_id, roster_version)` binds one frozen decision time per issue.  "
        "A market observation is causally admissible for a fixture only when "
        "`observed_at_utc <= decision_at_utc AND observed_at_utc < kickoff_at_utc` "
        "with the exact epoch looked up by issue — never inferred from "
        "`initial/10h/1h/final` labels (REQ-DS03).",
        "",
        "## Non-interchangeability (REQ-DS03)",
        "",
        "| column | meaning | never interchangeable with |",
        "|---|---|---|",
        "| observed_at_utc | when the market state was observed | received_at_utc, decision_at_utc |",
        "| received_at_utc | when our pipeline captured it | observed_at_utc |",
        "| decision_at_utc | frozen decision epoch | any observation label |",
        "| kickoff_at_utc | scheduled match start | decision_at_utc |",
        "| settled_at_utc | settlement time (after event) | any pre-event time |",
        "",
        "## Schema-level enforcement (REQ-DS04)",
        "",
        "```sql",
        "-- partial unique index on active alias windows (SQLite)",
        "CREATE UNIQUE INDEX ux_team_alias_active ON team_alias(",
        "    source_id, source_team_key",
        ") WHERE valid_to_utc IS NULL;",
        "",
        "-- canonical fixture identity",
        "CREATE UNIQUE INDEX ux_fixture_issue_idx ON fixture(issue_code, match_idx);",
        "```",
        "",
    ]
    return "\n".join(lines)


def build_identity_checks(census_identity: pd.DataFrame) -> pd.DataFrame:
    """Summarize measured identity uniqueness per database/table.

    The census measures ``distinct_identity`` vs ``row_count`` for every table
    carrying (issue, match_idx).  A table with duplicate identity rows is
    flagged AMBIGUOUS for ingestion and must be reconciled at the alias level
    (REQ-DS02 evidence: uniqueness is enforced in the canonical schema and the
    measured legacy defects are named).
    """
    checks: list[dict[str, object]] = []
    for _, row in census_identity.iterrows():
        row_count = _to_int(row["row_count"])
        distinct = _to_int(row["distinct_identity"])
        duplicate_rows = _to_int(row["duplicate_identity_rows"])
        if row_count < 0:
            verdict = "UNMEASURED"
        elif duplicate_rows == 0:
            verdict = "UNIQUE"
        else:
            verdict = "DUPLICATE_DEFECT"
        checks.append(
            {
                "database_key": row["database_key"],
                "table": row["table"],
                "row_count": row_count,
                "distinct_identity": distinct,
                "duplicate_identity_rows": duplicate_rows,
                "uniqueness_verdict": verdict,
                "contract_rule": "UNIQUE(issue_code, match_idx)",
            }
        )
    return pd.DataFrame(checks)
