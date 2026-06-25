#!/usr/bin/env python3
"""Build narrow modeling tables from the converted Beidan XLSM SQLite DB."""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


RETURN_RATE = 0.65


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def exec_step(conn: sqlite3.Connection, label: str, sql: str) -> None:
    started = time.time()
    print(f"[build] {label}...", flush=True)
    conn.executescript(sql)
    elapsed = time.time() - started
    print(f"[build] {label} done in {elapsed:.1f}s", flush=True)


def build(sqlite_path: Path, history_db: Path) -> None:
    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-1000000")
    conn.execute("PRAGMA synchronous=OFF")
    if not column_exists(conn, "matches", "handicap_line_norm"):
        raise RuntimeError(
            "matches.handicap_line_norm is missing. Run "
            "scripts/normalize_beidan_xlsm_handicap.py first."
        )
    conn.execute(f"ATTACH DATABASE '{history_db}' AS hist")

    exec_step(
        conn,
        "drop old modeling tables",
        """
        DROP TABLE IF EXISTS action_candidates;
        DROP TABLE IF EXISTS action_definitions;
        DROP TABLE IF EXISTS outcome_features;
        DROP TABLE IF EXISTS match_features;
        DROP TABLE IF EXISTS market_consensus;
        """,
    )

    exec_step(
        conn,
        "market_consensus",
        """
        CREATE TABLE market_consensus AS
        SELECT
            match_id,
            market,
            snapshot,
            COUNT(*) AS n_rows,
            SUM(CASE WHEN v1 IS NOT NULL THEN 1 ELSE 0 END) AS n_v1,
            SUM(CASE WHEN v2 IS NOT NULL THEN 1 ELSE 0 END) AS n_v2,
            SUM(CASE WHEN v3 IS NOT NULL THEN 1 ELSE 0 END) AS n_v3,
            SUM(CASE WHEN v1 IS NOT NULL AND v2 IS NOT NULL AND v3 IS NOT NULL THEN 1 ELSE 0 END) AS n_complete,
            AVG(v1) AS v1_avg,
            AVG(v2) AS v2_avg,
            AVG(v3) AS v3_avg,
            AVG(v1 * v1) AS v1_sq_avg,
            AVG(v2 * v2) AS v2_sq_avg,
            AVG(v3 * v3) AS v3_sq_avg,
            MIN(v1) AS v1_min,
            MIN(v2) AS v2_min,
            MIN(v3) AS v3_min,
            MAX(v1) AS v1_max,
            MAX(v2) AS v2_max,
            MAX(v3) AS v3_max
        FROM market_snapshots
        GROUP BY match_id, market, snapshot;

        CREATE INDEX idx_market_consensus_match ON market_consensus(match_id);
        CREATE INDEX idx_market_consensus_lookup ON market_consensus(market, snapshot, match_id);
        """,
    )

    exec_step(
        conn,
        "match_features",
        """
        CREATE TABLE match_features AS
        SELECT
            m.match_id,
            m.issue,
            m.match_idx,
            m.kickoff_ts,
            CAST(substr(m.kickoff_ts, 1, 4) AS INTEGER) AS season_year,
            m.league,
            m.home,
            m.away,
            m.score,
            m.home_rank,
            m.away_rank,
            m.handicap_line AS handicap_line_raw,
            m.handicap_line_norm,
            m.handicap_norm_source,
            m.result_label,
            CASE m.result_label
                WHEN '胜' THEN '3'
                WHEN '平' THEN '1'
                WHEN '负' THEN '0'
                ELSE NULL
            END AS result_code_from_label,
            h.result_code AS result_code_history,
            COALESCE(h.result_code, CASE m.result_label
                WHEN '胜' THEN '3'
                WHEN '平' THEN '1'
                WHEN '负' THEN '0'
                ELSE NULL
            END) AS result_code,
            h.winning_sp,
            h.fthg,
            h.ftag,
            h.handicap_line AS handicap_line_history,
            h.avg_eu_home AS history_avg_eu_home,
            h.avg_eu_draw AS history_avg_eu_draw,
            h.avg_eu_away AS history_avg_eu_away,
            CASE WHEN h.id IS NOT NULL THEN 1 ELSE 0 END AS has_history_join,
            CASE WHEN h.winning_sp IS NOT NULL AND h.winning_sp > 0 THEN 1 ELSE 0 END AS has_winning_sp
        FROM matches m
        LEFT JOIN hist.historical_matches h
          ON h.issue = m.issue
         AND h.match_idx = m.match_idx;

        CREATE INDEX idx_match_features_match ON match_features(match_id);
        CREATE INDEX idx_match_features_issue_idx ON match_features(issue, match_idx);
        CREATE INDEX idx_match_features_league ON match_features(league);
        CREATE INDEX idx_match_features_hcp ON match_features(handicap_line_norm);
        CREATE INDEX idx_match_features_has_sp ON match_features(has_winning_sp);
        """,
    )

    exec_step(
        conn,
        "outcome_features",
        """
        CREATE TABLE outcome_features AS
        WITH
        ei AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='euro_1x2' AND snapshot='initial'),
        e10 AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='euro_1x2' AND snapshot='10h'),
        e1 AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='euro_1x2' AND snapshot='1h'),
        ef AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='euro_1x2' AND snapshot='final'),
        ki AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='kelly_1x2' AND snapshot='initial'),
        k10 AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='kelly_1x2' AND snapshot='10h'),
        k1 AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='kelly_1x2' AND snapshot='1h'),
        kf AS (SELECT match_id, v1_avg h, v2_avg d, v3_avg a FROM market_consensus WHERE market='kelly_1x2' AND snapshot='final'),
        b AS (
            SELECT
                mf.*,
                ei.h ei_h, ei.d ei_d, ei.a ei_a,
                e10.h e10_h, e10.d e10_d, e10.a e10_a,
                e1.h e1_h, e1.d e1_d, e1.a e1_a,
                ef.h ef_h, ef.d ef_d, ef.a ef_a,
                ki.h ki_h, ki.d ki_d, ki.a ki_a,
                k10.h k10_h, k10.d k10_d, k10.a k10_a,
                k1.h k1_h, k1.d k1_d, k1.a k1_a,
                kf.h kf_h, kf.d kf_d, kf.a kf_a,
                CASE WHEN ef.h > 1 AND ef.d > 1 AND ef.a > 1 THEN (1.0 / ef.h) / (1.0 / ef.h + 1.0 / ef.d + 1.0 / ef.a) END AS pf_h,
                CASE WHEN ef.h > 1 AND ef.d > 1 AND ef.a > 1 THEN (1.0 / ef.d) / (1.0 / ef.h + 1.0 / ef.d + 1.0 / ef.a) END AS pf_d,
                CASE WHEN ef.h > 1 AND ef.d > 1 AND ef.a > 1 THEN (1.0 / ef.a) / (1.0 / ef.h + 1.0 / ef.d + 1.0 / ef.a) END AS pf_a,
                CASE WHEN e10.h > 1 AND e10.d > 1 AND e10.a > 1 THEN (1.0 / e10.h) / (1.0 / e10.h + 1.0 / e10.d + 1.0 / e10.a) END AS p10_h,
                CASE WHEN e10.h > 1 AND e10.d > 1 AND e10.a > 1 THEN (1.0 / e10.d) / (1.0 / e10.h + 1.0 / e10.d + 1.0 / e10.a) END AS p10_d,
                CASE WHEN e10.h > 1 AND e10.d > 1 AND e10.a > 1 THEN (1.0 / e10.a) / (1.0 / e10.h + 1.0 / e10.d + 1.0 / e10.a) END AS p10_a,
                CASE WHEN e1.h > 1 AND e1.d > 1 AND e1.a > 1 THEN (1.0 / e1.h) / (1.0 / e1.h + 1.0 / e1.d + 1.0 / e1.a) END AS p1_h,
                CASE WHEN e1.h > 1 AND e1.d > 1 AND e1.a > 1 THEN (1.0 / e1.d) / (1.0 / e1.h + 1.0 / e1.d + 1.0 / e1.a) END AS p1_d,
                CASE WHEN e1.h > 1 AND e1.d > 1 AND e1.a > 1 THEN (1.0 / e1.a) / (1.0 / e1.h + 1.0 / e1.d + 1.0 / e1.a) END AS p1_a
            FROM match_features mf
            LEFT JOIN ei ON ei.match_id = mf.match_id
            LEFT JOIN e10 ON e10.match_id = mf.match_id
            LEFT JOIN e1 ON e1.match_id = mf.match_id
            LEFT JOIN ef ON ef.match_id = mf.match_id
            LEFT JOIN ki ON ki.match_id = mf.match_id
            LEFT JOIN k10 ON k10.match_id = mf.match_id
            LEFT JOIN k1 ON k1.match_id = mf.match_id
            LEFT JOIN kf ON kf.match_id = mf.match_id
        )
        SELECT
            match_id, issue, match_idx, kickoff_ts, season_year, league,
            handicap_line_norm, result_code, winning_sp, has_winning_sp,
            '3' AS outcome_code,
            CASE WHEN result_code = '3' THEN 1 WHEN result_code IS NULL THEN NULL ELSE 0 END AS hit,
            ef_h AS euro_final_odds,
            pf_h AS euro_final_p,
            e10_h AS euro_10h_odds,
            p10_h AS euro_10h_p,
            e1_h AS euro_1h_odds,
            p1_h AS euro_1h_p,
            ei_h AS euro_initial_odds,
            CASE WHEN e10_h > 0 AND ef_h > 0 THEN ef_h / e10_h - 1 END AS euro_odds_move_10h_final,
            CASE WHEN e1_h > 0 AND ef_h > 0 THEN ef_h / e1_h - 1 END AS euro_odds_move_1h_final,
            CASE WHEN p10_h > 0 AND pf_h > 0 THEN pf_h / p10_h - 1 END AS euro_p_move_10h_final,
            CASE WHEN p1_h > 0 AND pf_h > 0 THEN pf_h / p1_h - 1 END AS euro_p_move_1h_final,
            1 + CASE WHEN pf_d > pf_h THEN 1 ELSE 0 END + CASE WHEN pf_a > pf_h THEN 1 ELSE 0 END AS euro_final_rank,
            kf_h AS kelly_final,
            k10_h AS kelly_10h,
            k1_h AS kelly_1h,
            ki_h AS kelly_initial,
            CASE WHEN k10_h > 0 AND kf_h > 0 THEN kf_h / k10_h - 1 END AS kelly_move_10h_final
        FROM b
        UNION ALL
        SELECT
            match_id, issue, match_idx, kickoff_ts, season_year, league,
            handicap_line_norm, result_code, winning_sp, has_winning_sp,
            '1' AS outcome_code,
            CASE WHEN result_code = '1' THEN 1 WHEN result_code IS NULL THEN NULL ELSE 0 END AS hit,
            ef_d AS euro_final_odds,
            pf_d AS euro_final_p,
            e10_d AS euro_10h_odds,
            p10_d AS euro_10h_p,
            e1_d AS euro_1h_odds,
            p1_d AS euro_1h_p,
            ei_d AS euro_initial_odds,
            CASE WHEN e10_d > 0 AND ef_d > 0 THEN ef_d / e10_d - 1 END AS euro_odds_move_10h_final,
            CASE WHEN e1_d > 0 AND ef_d > 0 THEN ef_d / e1_d - 1 END AS euro_odds_move_1h_final,
            CASE WHEN p10_d > 0 AND pf_d > 0 THEN pf_d / p10_d - 1 END AS euro_p_move_10h_final,
            CASE WHEN p1_d > 0 AND pf_d > 0 THEN pf_d / p1_d - 1 END AS euro_p_move_1h_final,
            1 + CASE WHEN pf_h > pf_d THEN 1 ELSE 0 END + CASE WHEN pf_a > pf_d THEN 1 ELSE 0 END AS euro_final_rank,
            kf_d AS kelly_final,
            k10_d AS kelly_10h,
            k1_d AS kelly_1h,
            ki_d AS kelly_initial,
            CASE WHEN k10_d > 0 AND kf_d > 0 THEN kf_d / k10_d - 1 END AS kelly_move_10h_final
        FROM b
        UNION ALL
        SELECT
            match_id, issue, match_idx, kickoff_ts, season_year, league,
            handicap_line_norm, result_code, winning_sp, has_winning_sp,
            '0' AS outcome_code,
            CASE WHEN result_code = '0' THEN 1 WHEN result_code IS NULL THEN NULL ELSE 0 END AS hit,
            ef_a AS euro_final_odds,
            pf_a AS euro_final_p,
            e10_a AS euro_10h_odds,
            p10_a AS euro_10h_p,
            e1_a AS euro_1h_odds,
            p1_a AS euro_1h_p,
            ei_a AS euro_initial_odds,
            CASE WHEN e10_a > 0 AND ef_a > 0 THEN ef_a / e10_a - 1 END AS euro_odds_move_10h_final,
            CASE WHEN e1_a > 0 AND ef_a > 0 THEN ef_a / e1_a - 1 END AS euro_odds_move_1h_final,
            CASE WHEN p10_a > 0 AND pf_a > 0 THEN pf_a / p10_a - 1 END AS euro_p_move_10h_final,
            CASE WHEN p1_a > 0 AND pf_a > 0 THEN pf_a / p1_a - 1 END AS euro_p_move_1h_final,
            1 + CASE WHEN pf_h > pf_a THEN 1 ELSE 0 END + CASE WHEN pf_d > pf_a THEN 1 ELSE 0 END AS euro_final_rank,
            kf_a AS kelly_final,
            k10_a AS kelly_10h,
            k1_a AS kelly_1h,
            ki_a AS kelly_initial,
            CASE WHEN k10_a > 0 AND kf_a > 0 THEN kf_a / k10_a - 1 END AS kelly_move_10h_final
        FROM b;

        CREATE INDEX idx_outcome_features_match ON outcome_features(match_id);
        CREATE INDEX idx_outcome_features_code ON outcome_features(outcome_code);
        CREATE INDEX idx_outcome_features_hit ON outcome_features(has_winning_sp, hit);
        CREATE INDEX idx_outcome_features_rank ON outcome_features(euro_final_rank);
        CREATE INDEX idx_outcome_features_league ON outcome_features(league);
        """,
    )

    exec_step(
        conn,
        "action_candidates",
        f"""
        CREATE TABLE action_definitions (
            action_code TEXT PRIMARY KEY,
            action_label TEXT NOT NULL,
            selection_set TEXT NOT NULL,
            cover_count INTEGER NOT NULL
        );

        INSERT INTO action_definitions(action_code, action_label, selection_set, cover_count) VALUES
            ('NONE', '不买', '', 0),
            ('3', '胜', '3', 1),
            ('1', '平', '1', 1),
            ('0', '负', '0', 1),
            ('31', '胜平', '31', 2),
            ('30', '胜负', '30', 2),
            ('10', '平负', '10', 2),
            ('310', '胜平负', '310', 3);

        CREATE TABLE action_candidates AS
        SELECT
            mf.match_id,
            mf.issue,
            mf.match_idx,
            mf.kickoff_ts,
            mf.season_year,
            mf.league,
            mf.handicap_line_norm,
            mf.result_code,
            mf.winning_sp,
            mf.has_winning_sp,
            ad.action_code,
            ad.action_label,
            ad.selection_set,
            ad.cover_count,
            CASE
                WHEN ad.cover_count = 0 THEN NULL
                WHEN mf.result_code IS NULL THEN NULL
                WHEN instr(ad.selection_set, mf.result_code) > 0 THEN 1
                ELSE 0
            END AS hit,
            CASE
                WHEN ad.cover_count = 0 THEN NULL
                WHEN mf.winning_sp IS NULL OR mf.winning_sp <= 0 THEN NULL
                WHEN instr(ad.selection_set, mf.result_code) > 0 THEN mf.winning_sp / ad.cover_count
                ELSE 0.0
            END AS factor,
            CASE
                WHEN ad.cover_count = 0 THEN NULL
                WHEN mf.winning_sp IS NULL OR mf.winning_sp <= 0 THEN NULL
                WHEN instr(ad.selection_set, mf.result_code) > 0 THEN {RETURN_RATE} * (mf.winning_sp / ad.cover_count) - 1.0
                ELSE -1.0
            END AS single_return_after_65
        FROM match_features mf
        CROSS JOIN action_definitions ad;

        CREATE INDEX idx_action_candidates_match ON action_candidates(match_id);
        CREATE INDEX idx_action_candidates_action ON action_candidates(action_code);
        CREATE INDEX idx_action_candidates_sp ON action_candidates(has_winning_sp);
        CREATE INDEX idx_action_candidates_league ON action_candidates(league);
        CREATE INDEX idx_action_candidates_hcp ON action_candidates(handicap_line_norm);
        """,
    )

    exec_step(
        conn,
        "source_meta",
        """
        INSERT OR REPLACE INTO source_meta(key, value) VALUES
            ('modeling_tables_built', datetime('now')),
            ('modeling_tables_version', 'v1');
        """,
    )

    conn.execute("DETACH DATABASE hist")
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--history-db", required=True, type=Path)
    args = parser.parse_args()
    build(args.sqlite, args.history_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
