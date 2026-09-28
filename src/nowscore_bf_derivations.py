#!/usr/bin/env python3
"""Apply an explicit user-approved, fixture-bound BF derivation ledger to a copy.

Raw observations, raw options, findings and the original receipt are unchanged.
Only effective views resolve approved missing-option findings. No payout engine.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from src.nowscore_settlement import TYPEID_LABELS, canonical, digest, expected_option
from scripts.verify_nowscore_bf_history import parse_history, verify

ROOT = Path(__file__).resolve().parents[1]


def make_ledger(source: sqlite3.Connection, verification: dict, history_root: Path | None = None) -> dict:
    """Prepare approved derivations; supported history requires hash-checked HTML.

SP retains roster precision. No writes/network; raise on evidence conflicts.
"""
    records = []
    for r in verification["results"]:
        supported = r["classification"] == "历史页支持（SP按两位小数一致）"
        if r["classification"] != "无历史记录" and not supported:
            continue
        if supported:
            if history_root is None:
                raise ValueError("history-backed decisions require raw evidence")
            sha = r["history_sha256"]
            if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValueError("invalid history hash")
            body = (history_root / 'raw' / (sha + '.html')).read_bytes()
            if digest(body) != sha:
                raise ValueError("history hash mismatch")
            checked = verify(r, parse_history(body, r['issue'], r['slot']))
            if checked['classification'] != r['classification']:
                raise ValueError("history replay conflict")
            for field in ('history_rows', 'single_option', 'single_sp_raw', 'vector_raw', 'distinct_single_vectors'):
                if canonical(checked[field]) != canonical(r[field]):
                    raise ValueError("history evidence conflict: " + field)
        rows = source.execute("SELECT observation_id,payload_json FROM observation WHERE issue=? AND slot=? AND play='bf'", (r["issue"], r["slot"])).fetchall()
        if len(rows) != 1:
            raise ValueError("target identity not unique")
        oid, payload = rows[0]
        raw = json.loads(payload)
        if raw["score"] != r["score"] or raw["source_sha256"] != r["roster_sha256"] or raw["summary_sp_raw"] != r["summary_sp_raw"] or expected_option(raw) != r["expected_option"]:
            raise ValueError("verification/source conflict")
        records.append({"decision_id": f'ns-bf-derived-{r["issue"]}-{r["slot"]}',
                        "issue": r["issue"], "slot": r["slot"], "observation_id": oid,
                        "native_match_id": raw["native_match_id"], "score": raw["score"],
                        "source_sha256": raw["source_sha256"], "source_url": raw["source_url"],
                        "summary_sp_raw": raw["summary_sp_raw"], "derived_option": r["expected_option"],
                        "derived_sp": raw["summary_sp"], "review_status": "user_confirmed",
                        "evidence_class": "history_supported_score_summary_derivation" if supported else "user_confirmed_score_summary_derivation",
                        "history_status": "latest_single_option_and_rounded_sp_agree" if supported else "empty_history_not_a_settlement_blocker",
                        **({"history_evidence": r} if supported else {}),
                        "official_notice_verified": False})
    receipt = source.execute("SELECT payload_json FROM receipt").fetchone()[0]
    return {"schema": "nowscore_bf_derivations_v1", "reviewed_on": "2026-09-05",
            "approval": "User approved score/summary derivation for reviewed empty-history and raw-history-supported targets.",
            "source_receipt_sha256": digest(receipt.encode()),
            "verification_results_sha256": verification["results_sha256"], "decisions": records}


def apply(source: sqlite3.Connection, ledger: dict, output: Path, history_root: Path | None = None):
    """Validate prepared ledger and atomically publish a new copy, never overwrite.

Caller owns stable source connection. Raw NULLs and source tables stay intact.
On SQL failure the unpublished temporary database is closed and removed.
"""
    if ledger["schema"] != "nowscore_bf_derivations_v1":
        raise ValueError("unsupported ledger")
    receipt = source.execute("SELECT payload_json FROM receipt").fetchone()[0]
    if json.loads(receipt)["source"] != "nowscore" or digest(receipt.encode()) != ledger["source_receipt_sha256"]:
        raise ValueError("source receipt mismatch")
    records = ledger["decisions"]
    if not records or len({r["decision_id"] for r in records}) != len(records) or len({r["observation_id"] for r in records}) != len(records):
        raise ValueError("empty or duplicate decisions")
    for d in records:
        if d['evidence_class'] == 'history_supported_score_summary_derivation':
            verified = make_ledger(source, {'results': [d['history_evidence']], 'results_sha256': ledger['verification_results_sha256']}, history_root)
            if canonical(verified['decisions'][0]) != canonical(d):
                raise ValueError('history-backed ledger conflict')
        if d["review_status"] != "user_confirmed" or d["evidence_class"] not in {"user_confirmed_score_summary_derivation", "history_supported_score_summary_derivation"} or d["official_notice_verified"] is not False:
            raise ValueError("unapproved decision")
        rows = source.execute("SELECT payload_json FROM observation WHERE observation_id=? AND issue=? AND slot=? AND play='bf'", (d["observation_id"], d["issue"], d["slot"])).fetchall()
        if len(rows) != 1:
            raise ValueError("missing target")
        raw = json.loads(rows[0][0])
        for field in ("native_match_id", "score", "source_sha256", "source_url", "summary_sp_raw"):
            if raw[field] != d[field]:
                raise ValueError("original value conflict: " + field)
        if raw["status"] != "完场" or expected_option(raw) != d["derived_option"] or d["derived_option"] not in {"胜其他", "平其他", "负其他"}:
            raise ValueError("score/status conflict")
        if raw["summary_sp"] != d["derived_sp"] or d["derived_sp"] <= 1:
            raise ValueError("SP conflict or special SP")
        options = source.execute("SELECT option,raw_sp,sp FROM option_sp WHERE observation_id=?", (d["observation_id"],)).fetchall()
        if sorted(o[0] for o in options) != sorted(TYPEID_LABELS[8]) or any(o[1] != "" or o[2] is not None for o in options):
            raise ValueError("original option grid is not entirely empty")
        flags = source.execute("SELECT code FROM finding WHERE issue=? AND slot=?", (d["issue"], d["slot"])).fetchall()
        if flags != [("summary_sp_without_option",)]:
            raise ValueError("unexpected additional findings")
        peers = source.execute("SELECT payload_json FROM observation WHERE issue=? AND slot=? AND play!='bf'", (d["issue"], d["slot"])).fetchall()
        if len(peers) != 4:
            raise ValueError("peer coverage missing")
        peer_rows = [json.loads(p[0]) for p in peers]
        if {p["play"] for p in peer_rows} != {"spf", "jq", "ds", "bq"}:
            raise ValueError("peer play identities conflict")
        for p in peer_rows:
            winning = [o for o in p["options"] if o["sp"] is not None]
            if p["status"] != "完场" or p["score"] != raw["score"] or p["native_match_id"] != raw["native_match_id"] or len(winning) != 1 or winning[0]["sp"] <= 1 or winning[0]["option"] != expected_option(p):
                raise ValueError("peer result conflict")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(prefix='.nowscore-bf-', dir=output.parent) as work, closing(sqlite3.connect(Path(work)/'result.sqlite')) as dest:
        source.backup(dest)
        dest.executescript('''
          BEGIN IMMEDIATE;
          CREATE TABLE bf_derivation (decision_id TEXT PRIMARY KEY, observation_id INTEGER UNIQUE,
            issue TEXT, slot INTEGER, derived_option TEXT, derived_sp REAL, evidence_class TEXT, payload_json TEXT);
          CREATE TABLE derivation_receipt (payload_json TEXT);
          CREATE VIEW effective_option_sp AS
            SELECT o.*, COALESCE(d.derived_sp,o.sp) AS effective_sp,
              CASE WHEN d.decision_id IS NULL THEN 'source_observed' ELSE d.evidence_class END AS evidence_class,
              d.decision_id FROM option_sp o LEFT JOIN bf_derivation d
              ON o.observation_id=d.observation_id AND o.option=d.derived_option;
          CREATE VIEW effective_finding AS
            SELECT f.* FROM finding f WHERE NOT (f.code='summary_sp_without_option' AND EXISTS
              (SELECT 1 FROM bf_derivation d WHERE d.issue=f.issue AND d.slot=f.slot AND f.play='bf'));
        ''')
        dest.executemany("INSERT INTO bf_derivation VALUES(?,?,?,?,?,?,?,?)", [(d["decision_id"],d["observation_id"],d["issue"],d["slot"],d["derived_option"],d["derived_sp"],d["evidence_class"],canonical(d)) for d in records])
        result = {"ledger_sha256": digest(canonical(ledger).encode()), "source_receipt_sha256": ledger["source_receipt_sha256"],
                  "implementation_sha256": digest(Path(__file__).read_bytes()),
                  "helper_sha256": digest((ROOT / "src/nowscore_settlement.py").read_bytes()),
                  "domain_sha256": digest((ROOT / "src/nowscore_bjdc_sp_history.py").read_bytes()),
                  "history_parser_sha256": digest((ROOT / "scripts/verify_nowscore_bf_history.py").read_bytes()),
                  "ledger": ledger,
                  "approved_derivations": len(records), "raw_tables_unchanged": True,
                  "historical_availability": "HISTORICAL_PROXY", "production_enabled": False}
        dest.execute("INSERT INTO derivation_receipt VALUES(?)", (canonical(result),))
        dest.commit()
        if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity failure')
        os.link(Path(work)/'result.sqlite', output)
    return result


def main(argv=None):
    """CLI: explicit source/evidence/output paths, no network or source writes."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-db", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approved-verification", type=Path, help="Explicit user approval for its empty-history targets")
    g.add_argument("--ledger", type=Path, help="Replay an existing approval ledger")
    p.add_argument("--history-root", type=Path, help="Raw history evidence for supported targets")
    a = p.parse_args(argv)
    with closing(sqlite3.connect(a.source_db.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute('BEGIN')
        if a.ledger:
            ledger = json.loads(a.ledger.read_text())
        else:
            verification = json.loads(a.approved_verification.read_text())
            if digest(canonical(verification["results"]).encode()) != verification["results_sha256"]:
                raise ValueError("verification hash mismatch")
            ledger = make_ledger(source, verification, a.history_root)
            with a.output.with_suffix(".decisions.json").open("x", encoding="utf-8") as handle:
                handle.write(canonical(ledger) + "\n")
        print(canonical(apply(source, ledger, a.output, a.history_root)))


if __name__ == "__main__":
    main()
