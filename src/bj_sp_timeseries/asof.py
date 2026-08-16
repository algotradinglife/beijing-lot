"""Deterministic as-of replay at decision epochs (REQ-BJ03).

Selection rule `asof_latest_complete_pre_kickoff_v1`:

For each (fixture, decision_epoch) pick the latest complete 3/1/0 triplet
whose observation is causally available:
  - effective observation time = COALESCE(observed_at_utc, received_at_utc)
  - selection window: obs_time <= decision_at AND obs_time < kickoff_at
    (kickoff missing -> kickoff gate waived, but decision gate still applies)
  - bounded staleness: obs_time >= decision_at - max_staleness_seconds
  - completeness: exactly 3 quotes for the observation, all present (>0)
  - ties: pick max(obs_time), then max(observation_id)
  - NEVER join across different native-line states (REQ-BJ04): the selected
    observation carries its own handicap_line; a later observation with a
    different line does not retro-fit the earlier line.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from . import DECISION_RULES


def build_decision_epochs(con: sqlite3.Connection, *,
                          epochs_hours_before_kickoff: tuple[float, ...] = (0.5, 1.0, 6.0, 24.0),
                          rule_id: str = "asof_latest_complete_pre_kickoff_v1",
                          max_staleness_seconds: int = 24 * 3600,
                          roster_version: str = "v1") -> dict:
    """Create decision epochs for every fixture at kickoff-Nh.

    Epochs with decision_at <= kickoff are created only when kickoff is known;
    a fixture without kickoff gets no epochs (explicit unavailable).
    Returns summary counts.
    """
    assert rule_id in DECISION_RULES, f"unknown rule {rule_id}"
    con.execute(
        """INSERT OR IGNORE INTO ingestion_batch
           (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
            raw_sha256, parser_version, row_count, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (f"decision_epochs_{rule_id}", "beidan_live_500", None, None, None,
         None, "bj_sp_timeseries/v1", None, "completed"),
    )
    fixtures = con.execute(
        "SELECT fixture_id, issue_code, kickoff_at_utc FROM fixture WHERE kickoff_at_utc IS NOT NULL"
    ).fetchall()
    n = 0
    for f in fixtures:
        kickoff = _parse_iso(f["kickoff_at_utc"])
        if kickoff is None:
            continue
        for h in epochs_hours_before_kickoff:
            decision_at = kickoff - _hours(h)
            eid = f"de_{f['fixture_id']}_{rule_id}_{int(h*100)}"
            con.execute(
                """INSERT OR IGNORE INTO decision_epoch
                   (decision_epoch_id, issue_code, fixture_id, decision_at_utc,
                    rule_id, roster_version)
                   VALUES (?,?,?,?,?,?)""",
                (eid, f["issue_code"], f["fixture_id"],
                 decision_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                 rule_id, roster_version),
            )
            n += 1
    con.commit()
    return {"epochs_created": n, "fixtures_with_kickoff": len(fixtures),
            "rule": rule_id, "max_staleness_seconds": max_staleness_seconds}


def run_asof_replay(con: sqlite3.Connection, *,
                    rule_id: str = "asof_latest_complete_pre_kickoff_v1",
                    max_staleness_seconds: int = 24 * 3600) -> dict:
    """For every decision epoch, select the as-of observation (if any).

    Deterministic rule: the LATEST COMPLETE 3/1/0 triplet within the causal
    window wins. If no complete triplet exists, the latest observation in the
    window is recorded with complete=0 so the gap is explicit (REQ-BJ02);
    any incomplete observation that lost to a complete one is logged to the
    exclusion ledger (INCOMPLETE_TRIPLET). No observation in window -> no
    selection (counted as NO_OBSERVATION).
    """
    from .ingest import log_exclusion

    epochs = con.execute(
        """SELECT decision_epoch_id, issue_code, fixture_id, decision_at_utc, rule_id
           FROM decision_epoch WHERE rule_id=? ORDER BY fixture_id, decision_at_utc""",
        (rule_id,),
    ).fetchall()

    stats = {"epochs": 0, "selected_complete": 0, "selected_incomplete": 0,
             "no_observation": 0, "stale_rejected": 0, "post_kickoff_rejected": 0,
             "post_decision_rejected": 0, "incomplete_lost_explicit": 0}

    for ep in epochs:
        stats["epochs"] += 1
        fid = ep["fixture_id"]
        decision_at = _parse_iso(ep["decision_at_utc"])
        kickoff = _parse_iso(
            con.execute("SELECT kickoff_at_utc FROM fixture WHERE fixture_id=?",
                        (fid,)).fetchone()["kickoff_at_utc"]
        )

        # candidates: observations with effective obs time in window
        candidates = con.execute(
            """SELECT mo.observation_id, mo.observed_at_utc, mo.received_at_utc,
                      mo.handicap_line,
                      (SELECT COUNT(*) FROM market_quote q
                        WHERE q.observation_id = mo.observation_id
                          AND q.quote_status='present') AS present_count,
                      (SELECT COUNT(*) FROM market_quote q
                        WHERE q.observation_id = mo.observation_id) AS quote_count
               FROM market_observation mo
               WHERE mo.fixture_id=?
                 AND (mo.observed_at_utc IS NOT NULL OR mo.received_at_utc IS NOT NULL)
               ORDER BY
                 COALESCE(mo.observed_at_utc, mo.received_at_utc) DESC,
                 mo.observation_id DESC""",
            (fid,),
        ).fetchall()

        in_window: list = []
        for c in candidates:
            obs_time = _parse_iso(c["observed_at_utc"] or c["received_at_utc"])
            if obs_time is None or decision_at is None:
                continue
            # kickoff gate: obs < kickoff (waived when kickoff unknown)
            if kickoff is not None and obs_time >= kickoff:
                stats["post_kickoff_rejected"] += 1
                continue
            # causal gate: obs <= decision
            if obs_time > decision_at:
                stats["post_decision_rejected"] += 1
                continue
            # staleness bound
            if (decision_at - obs_time).total_seconds() > max_staleness_seconds:
                stats["stale_rejected"] += 1
                continue
            in_window.append(c)

        if not in_window:
            stats["no_observation"] += 1
            continue

        # latest COMPLETE triplet wins
        chosen = next((c for c in in_window if c["present_count"] == 3), None)
        if chosen is None:
            # no complete triplet: latest candidate is explicit incomplete
            chosen = in_window[0]
            stats["selected_incomplete"] += 1
        else:
            stats["selected_complete"] += 1
            # any later incomplete observations that lost stay explicit
            for c in in_window:
                if c is chosen or c["present_count"] == 3:
                    continue
                if (c["observed_at_utc"] or c["received_at_utc"]) > \
                   (chosen["observed_at_utc"] or chosen["received_at_utc"]):
                    log_exclusion(con, fixture_id=fid, source_id=None,
                                  issue_code=ep["issue_code"], season_year=None,
                                  native_handicap_line=c["handicap_line"],
                                  reason_code="INCOMPLETE_TRIPLET",
                                  detail=f"observation {c['observation_id']} lost to "
                                         f"complete {chosen['observation_id']} at "
                                         f"decision epoch {ep['decision_epoch_id']}")
                    stats["incomplete_lost_explicit"] += 1

        complete = 1 if chosen["present_count"] == 3 else 0
        obs_time = _parse_iso(chosen["observed_at_utc"] or chosen["received_at_utc"])
        staleness = None
        if obs_time is not None and decision_at is not None:
            staleness = int((decision_at - obs_time).total_seconds())
        sel_id = f"sel_{ep['decision_epoch_id']}_{chosen['observation_id']}"
        con.execute(
            """INSERT OR IGNORE INTO as_of_selection
               (selection_id, decision_epoch_id, fixture_id, observation_id,
                observed_at_utc, received_at_utc, staleness_seconds, complete)
               VALUES (?,?,?,?,?,?,?,?)""",
            (sel_id, ep["decision_epoch_id"], fid,
             chosen["observation_id"],
             chosen["observed_at_utc"] or chosen["received_at_utc"],
             chosen["received_at_utc"],
             staleness, complete),
        )
    con.commit()
    return stats


# ---------------------------------------------------------------------------
# probability estimation (inverse-SP normalization) — REQ-BJ05 separation
# ---------------------------------------------------------------------------
def build_probability_estimates(con: sqlite3.Connection, *,
                                rule_id: str = "asof_latest_complete_pre_kickoff_v1",
                                estimator_id: str = "inverse_sp_normalized_v1") -> dict:
    """For every COMPLETE as-of selection, compute normalized inverse-SP
    probabilities: p_k = (1/odds_k) / sum_j(1/odds_j).

    Stored in probability_estimate — physically separate from raw quotes and
    from settlement (REQ-BJ05: no 0.65, no winning SP in inference tables).
    """
    selections = con.execute(
        """SELECT s.selection_id, s.decision_epoch_id, s.fixture_id,
                  s.observed_at_utc, s.received_at_utc, mo.handicap_line
           FROM as_of_selection s
           JOIN market_observation mo ON mo.observation_id = s.observation_id
           WHERE s.complete=1 AND s.decision_epoch_id IN
               (SELECT decision_epoch_id FROM decision_epoch WHERE rule_id=?)""",
        (rule_id,),
    ).fetchall()
    n = 0
    for s in selections:
        quotes = con.execute(
            """SELECT outcome_code, decimal_odds FROM market_quote
               WHERE observation_id = (
                   SELECT observation_id FROM as_of_selection WHERE selection_id=?)
                 AND quote_status='present'""",
            (s["selection_id"],),
        ).fetchall()
        inv = {q["outcome_code"]: 1.0 / q["decimal_odds"] for q in quotes
               if q["decimal_odds"] and q["decimal_odds"] > 0}
        total = sum(inv.values())
        if total <= 0:
            continue
        for code in ("3", "1", "0"):
            prob = inv.get(code, 0.0) / total
            pid = f"pe_{s['selection_id']}_{code}"
            con.execute(
                """INSERT OR IGNORE INTO probability_estimate
                   (estimate_id, fixture_id, decision_epoch_id, estimator_id,
                    market_type, handicap_line, outcome_code, probability,
                    observed_at_utc, provenance_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (pid, s["fixture_id"], s["decision_epoch_id"], estimator_id,
                 "handicap_3way", s["handicap_line"], code, prob,
                 s["observed_at_utc"] or s["received_at_utc"],
                 f"asof:{s['selection_id']}"),
            )
            n += 1
    con.commit()
    return {"probability_rows": n}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _parse_iso(ts) -> Optional[datetime]:
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _hours(h: float):
    from datetime import timedelta
    return timedelta(hours=h)
