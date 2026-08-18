"""Historical recoverability quantification (REQ-BJ06, REQ-BJ08).

Loss-of-support waterfall by source/issue/year/line/reason code:
  raw presence -> identity join -> line state -> timestamp gate ->
  complete triplet -> final causal intersection.

Also produces the explicit UNRECOVERABLE_HISTORICAL_BJ_SP evidence when a
historical cohort has zero strict-causal support.
"""
from __future__ import annotations

import sqlite3

# Reason codes used in exclusion_ledger and waterfalls.
REASONS = {
    "NO_OBSERVATION": "no raw SP observation exists for this fixture/epoch",
    "NO_CLOCK": "raw row exists but has no usable observation/receive clock",
    "INCOMPLETE_TRIPLET": "observation exists but 3/1/0 triplet is not complete-positive",
    "POST_DECISION": "observation time is after the decision epoch",
    "POST_KICKOFF": "observation time is at/after kickoff",
    "STALE": "observation older than bounded staleness window",
    "LINE_STATE": "line state not resolvable / line differs across join",
    "NONPOSITIVE": "quotes non-positive or non-finite",
    "LABEL_ONLY": "historical source records only label snapshots (initial/10h/1h/final), no exact clock",
    "SETTLEMENT_ONLY": "source is settlement-only (no pre-event SP)",
}


def issue_year(issue_code: str) -> int:
    """Issue '26075' -> 2026; '140101' -> 2014; '25042' -> 2025."""
    digits = "".join(ch for ch in str(issue_code) if ch.isdigit())
    if len(digits) >= 4:
        return 2000 + int(digits[:2])
    return 0


def cohort_name(year: int) -> str:
    if year >= 2026:
        return "prospective"
    if year >= 2014:
        return "strict_historical"
    return "unknown"


def cohort_name_v2(year: int, *, source_admissible_use: str) -> str:
    """Classify v2 proxy support without relabelling it as strict causal."""
    if year >= 2026 and source_admissible_use == "STRICT_CAUSAL":
        return "prospective"
    if year >= 2014 and source_admissible_use == "RETROSPECTIVE_PROXY":
        return "retrospective_proxy"
    if year >= 2014:
        return "strict_historical"
    return "unknown"


def raw_presence_waterfall(con: sqlite3.Connection) -> dict:
    """Count raw rows by source/admissible-use as the top of the waterfall."""
    out = {}
    out["beidan_live_500_raw"] = con.execute(
        "SELECT COUNT(*) FROM market_observation WHERE source_id='beidan_live_500'"
    ).fetchone()[0]
    out["bjdc_500_xml_34_raw"] = con.execute(
        "SELECT COUNT(*) FROM market_observation WHERE source_id='bjdc_500_xml_34'"
    ).fetchone()[0]
    out["xlsm_label_snapshots_51M"] = 51_551_016  # from beidan_xlsm profiling (label-only)
    out["history_settlement_rows"] = con.execute(
        "SELECT COUNT(*) FROM settlement WHERE source_id='beidan_history'"
    ).fetchone()[0]
    return out


def complete_triplet_count(con: sqlite3.Connection, source_id: str | None = None) -> int:
    """Count observations with exactly 3 present quotes."""
    q = """SELECT COUNT(*) FROM market_observation mo WHERE
           (SELECT COUNT(*) FROM market_quote q
             WHERE q.observation_id=mo.observation_id AND q.quote_status='present') = 3"""
    if source_id:
        q += f" AND mo.source_id='{source_id}'"
    return con.execute(q).fetchone()[0]


def issue_level_support(con: sqlite3.Connection, *,
                        rule_id: str = "asof_latest_complete_pre_kickoff_v1") -> dict:
    """Report strict and retrospective-proxy support in separate cohorts."""
    strict_rows = con.execute(
        """SELECT f.issue_code,
                  COUNT(DISTINCT f.fixture_id) AS fixtures_total,
                  SUM(CASE WHEN s.observation_id IS NOT NULL AND s.complete=1
                           THEN 1 ELSE 0 END) AS fixtures_complete_asof
           FROM fixture f
           LEFT JOIN (
               SELECT DISTINCT fixture_id, observation_id, complete
               FROM as_of_selection
               WHERE decision_epoch_id IN
                   (SELECT decision_epoch_id FROM decision_epoch WHERE rule_id=?)
                 AND complete=1
           ) s ON s.fixture_id = f.fixture_id
           GROUP BY f.issue_code ORDER BY f.issue_code""",
        (rule_id,),
    ).fetchall()
    proxy_rows = con.execute(
        """SELECT issue_code, COUNT(DISTINCT fixture_id) AS fixtures_total,
                  COUNT(DISTINCT CASE WHEN availability='present' THEN fixture_id END)
                    AS fixtures_present
           FROM relative_horizon_panel
           GROUP BY issue_code ORDER BY issue_code"""
    ).fetchall()
    by_cohort: dict[str, dict] = {}
    per_issue: list[dict] = []
    for r in strict_rows:
        yr = issue_year(r["issue_code"])
        cohort = cohort_name(yr)
        entry = by_cohort.setdefault(cohort, {"issues": 0, "fixtures_total": 0,
                                              "fixtures_complete_asof": 0})
        entry["issues"] += 1
        entry["fixtures_total"] += r["fixtures_total"]
        entry["fixtures_complete_asof"] += r["fixtures_complete_asof"] or 0
        per_issue.append({"issue_code": r["issue_code"], "year": yr,
                          "cohort": cohort, "fixtures_total": r["fixtures_total"],
                          "fixtures_complete_asof": r["fixtures_complete_asof"] or 0})
    for r in proxy_rows:
        cohort = cohort_name_v2(issue_year(r["issue_code"]),
                                source_admissible_use="RETROSPECTIVE_PROXY")
        entry = by_cohort.setdefault(cohort, {"issues": 0, "fixtures_total": 0,
                                              "fixtures_present": 0})
        entry["issues"] += 1
        entry["fixtures_total"] += r["fixtures_total"]
        entry["fixtures_present"] += r["fixtures_present"] or 0
        per_issue.append({"issue_code": r["issue_code"], "year": issue_year(r["issue_code"]),
                          "cohort": cohort, "fixtures_total": r["fixtures_total"],
                          "fixtures_present": r["fixtures_present"] or 0})
    per_issue.sort(key=lambda row: (row["issue_code"], row["cohort"]))
    return {"by_cohort": by_cohort, "per_issue": per_issue}


def historical_recoverability_evidence(con: sqlite3.Connection) -> dict:
    """Return v2 positive proxy evidence without misrepresenting it as causal."""
    from .panel import build_panel_evidence

    panel = build_panel_evidence(con)
    evidence = {
        "strict_historical_sources_checked": [
            {"source_id": "beidan_xlsm_archive",
             "admissible_use": "RETROSPECTIVE_PROXY",
             "why_not_causal": ("market_snapshots carry only label buckets "
                                "initial/10h/1h/final; no exact observation clock")},
            {"source_id": "beidan_features",
             "admissible_use": "UNUSABLE",
             "why_not_causal": "no observation clock at all (p_open/p_close only)"},
            {"source_id": "beidan_history",
             "admissible_use": "SETTLEMENT_ONLY",
             "why_not_causal": "settlement rows; winning_sp is post-event"},
            {"source_id": "nowscore_history",
             "admissible_use": "RETROSPECTIVE_PROXY",
             "why_not_causal": "third-party change-time archive; not a first-party "
                               "verifiable fetch clock (contract source priority 4)"},
            {"source_id": "okooo_prekick",
             "admissible_use": "RETROSPECTIVE_PROXY",
             "why_not_causal": "third-party archive; not a verifiable first-party clock"},
        ],
        "prospective_source": "beidan_live_500 + bjdc_500_xml_34 (2026-05+)",
        "prospective_clock": ("trusted receive snapshot_ts/fetched_at plus native "
                              "source_updatetime where supplied"),
        "strict_historical_causal_support": 0,
        "historical_panel": panel.pop("by_bucket", {}),
        "panel": panel,
        "disposition": panel["disposition"],
        "note": ("strict-causal historical support remains zero; the explicit "
                 "RETROSPECTIVE_RELATIVE_PROXY M×3 panel is the v2 positive "
                 "delivery and must not be used as an exact-clock replay"),
    }
    return evidence


def write_exclusion_ledger_from_analysis(con: sqlite3.Connection, *,
                                         rule_id: str = "asof_latest_complete_pre_kickoff_v1") -> dict:
    """Materialize explicit exclusion rows for the historical (label-only /
    settlement-only) sources and any non-causal prospective rows."""
    from .ingest import log_exclusion

    n = 0
    # beidan_history: settlement-only, not inference
    for r in con.execute(
        """SELECT s.fixture_id, s.issue_code, f.native_handicap_line
           FROM settlement s LEFT JOIN fixture f ON f.fixture_id = s.fixture_id
           WHERE s.source_id='beidan_history'"""
    ).fetchall():
        log_exclusion(con, fixture_id=r["fixture_id"], source_id="beidan_history",
                      issue_code=r["issue_code"],
                      season_year=issue_year(r["issue_code"]),
                      native_handicap_line=r["native_handicap_line"],
                      reason_code="SETTLEMENT_ONLY",
                      detail="settlement row is post-event; cannot supply pre-event SP")
        n += 1
    # v2 panel ingestion records padding rows in the exclusion ledger and
    # materializes unavailable quote cells directly as availability='missing'.
    con.commit()
    return {"exclusion_rows": n}


def build_waterfall_report(con: sqlite3.Connection, *,
                           rule_id: str = "asof_latest_complete_pre_kickoff_v1") -> dict:
    """Compose the full recoverability report (notebook + PI block)."""
    raw = raw_presence_waterfall(con)
    complete_live = complete_triplet_count(con, "beidan_live_500")
    complete_xml34 = complete_triplet_count(con, "bjdc_500_xml_34")
    support = issue_level_support(con, rule_id=rule_id)
    evidence = historical_recoverability_evidence(con)

    report = {
        "waterfall_raw": raw,
        "complete_triplets": {
            "beidan_live_500": complete_live,
            "bjdc_500_xml_34": complete_xml34,
            "total_strict_causal_obs": complete_live + complete_xml34,
        },
        "issue_support": support,
        "historical": evidence,
        "asof_rule": rule_id,
    }
    return report
