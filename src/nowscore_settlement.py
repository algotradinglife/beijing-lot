"""Source-pure Nowscore observations and deterministic diagnostic audit.

No historical fitting, settlement correction, source fallback or payout policy.
An observation passing these checks is not an official settlement notice.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import sys
from datetime import datetime
from importlib.metadata import version
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

from src.nowscore_bjdc_sp_history import TYPEID_LABELS

from packages.beidan.inst.python.beidan_backend.settlement import parser as settlement_parser, labels as settlement_labels
from packages.beidan.inst.python.beidan_backend.settlement.parser import (PLAYS, ABNORMAL, TITLE, EMPTY, ARCHIVE_SLUGS, TYPEID_LABELS, RosterConflict, digest, canonical, source_url, score, outcome, expected_option, parse_archive_page, parse_page, audit_rows)

def hash_json_texts(texts) -> str:
    """Hash a JSON array of canonical JSON strings without materializing it."""
    hasher = hashlib.sha256(b"[")
    for index, text in enumerate(texts):
        if index:
            hasher.update(b",")
        hasher.update(text.encode("utf-8"))
    hasher.update(b"]")
    return hasher.hexdigest()


def build_database(run_root: Path, output: Path) -> dict:
    """Replay evidence with only one issue's parsed observations in memory.

    Raw identity validation precedes output creation. Data writes and the final
    receipt share one transaction; errors leave an empty, unsealed database.
    Existing outputs are never overwritten. All connections close on failure.
    """
    manifest_bytes = (run_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["source"] != "nowscore" or manifest["schema"] not in {"nowscore_capture_v1", "nowscore_history_capture_v1"}:
        raise ValueError("wrong source manifest")
    history = manifest["schema"] == "nowscore_history_capture_v1"
    if history:
        from src.nowscore_history_assembly import verify_assembled_history
        verify_assembled_history(run_root, manifest)
    captures, failures, source_empty_pages = [], [], []
    by_issue = defaultdict(list)
    seen = set()
    for entry in manifest["captures"]:
        issue, typeid = entry["issue"], entry["typeid"]
        if entry["url"] != source_url(issue, typeid) or (issue, typeid) in seen:
            raise ValueError("invalid/duplicate capture identity")
        seen.add((issue, typeid))
        if entry.get("error"):
            failures.append(entry)
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("invalid source hash")
        if datetime.fromisoformat(entry["received_at"]).tzinfo is None:
            raise ValueError("capture receipt lacks timezone")
        raw_path = run_root / "raw" / (entry["sha256"] + ".html")
        payload = raw_path.read_bytes()
        if digest(payload) != entry["sha256"]:
            raise ValueError("source hash mismatch")
        captures.append(entry)
        by_issue[issue].append(entry)
    requested = {(i, t) for i in manifest["requested_issues"] for t in PLAYS}
    if requested != seen:
        raise ValueError("capture ledger does not cover requested issue/play domain")
    if len(manifest["requested_issues"]) != len(set(manifest["requested_issues"])):
        raise ValueError("duplicate requested issue")
    implementation = {p.name: digest(p.read_bytes()) for p in (
        Path(__file__), Path(__file__).with_name("nowscore_bjdc_sp_history.py"),
        Path(__file__).with_name("multimarket_p0.py"),
        Path(settlement_parser.__file__), Path(settlement_labels.__file__),
    )}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb"):
        pass
    con = sqlite3.connect(output)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA temp_store=FILE")
        con.executescript('''
          CREATE TABLE capture (issue TEXT, typeid INTEGER, source_url TEXT, received_at TEXT, sha256 TEXT, PRIMARY KEY(issue,typeid));
          CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT, slot INTEGER, play TEXT, native_match_id TEXT, status TEXT, score TEXT, halftime_score TEXT, expected_option TEXT, source_sha256 TEXT, source_url TEXT, received_at TEXT, payload_json TEXT);
          CREATE TABLE option_sp (observation_id INTEGER, option TEXT, raw_sp TEXT, sp REAL, cell_id TEXT, FOREIGN KEY(observation_id) REFERENCES observation(observation_id));
          CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT, detail TEXT, source_sha256 TEXT);
          CREATE TABLE receipt (payload_json TEXT);
          CREATE TEMP TABLE finding_order (payload_json TEXT);
        ''')
        observation_count, match_count, option_count, peak_issue_rows = 0, 0, 0, 0
        finding_counts, play_counts = Counter(), Counter()
        with con:
            con.executemany("INSERT INTO capture VALUES(?,?,?,?,?)", [(e["issue"],e["typeid"],e["url"],e["received_at"],e["sha256"]) for e in captures])
            for issue in manifest["requested_issues"]:
                rows = []
                for entry in by_issue[issue]:
                    payload = (run_root / "raw" / (entry["sha256"] + ".html")).read_bytes()
                    if digest(payload) != entry["sha256"]:
                        raise ValueError("source changed during rebuild")
                    try:
                        parsed = [] if payload == b"" and entry.get("classification") == "source_empty" else parse_page(payload, issue, entry["typeid"])
                    except RosterConflict as exc:
                        if history and (entry.get("classification") != "quarantined"
                                        or entry.get("quarantine_detail") != exc.args[1]):
                            raise ValueError("verified quarantine changed during rebuild") from exc
                        failures.append({**entry, "error": exc.args[0], "quarantine_detail": exc.args[1]})
                        for side, differences in exc.args[1].items():
                            for slot, native_id, count in differences:
                                finding = {"issue": issue, "slot": slot, "play": PLAYS[entry["typeid"]],
                                           "code": "source_roster_conflict", "detail": canonical({
                                               "side": side, "native_match_id": native_id, "count": count,
                                               "entire_page_quarantined": True}), "source_sha256": entry["sha256"]}
                                finding_counts[finding["code"]] += 1
                                con.execute("INSERT INTO finding VALUES(?,?,?,?,?,?)", tuple(finding[k] for k in (
                                    "issue", "slot", "play", "code", "detail", "source_sha256")))
                                con.execute("INSERT INTO finding_order VALUES(?)", (canonical(finding),))
                        continue
                    except (ValueError, UnicodeError) as exc:
                        if history:
                            raise ValueError("verified history parse changed during rebuild") from exc
                        failures.append({**entry, "error": str(exc)})
                        continue
                    if not parsed:
                        source_empty_pages.append({"issue": issue, "typeid": entry["typeid"], "sha256": entry["sha256"]})
                    for r in parsed:
                        r.update(source_sha256=entry["sha256"], source_url=entry["url"], received_at=entry["received_at"])
                    rows.extend(parsed)
                peak_issue_rows = max(peak_issue_rows, len(rows))
                match_count += len({r["slot"] for r in rows})
                for r in rows:
                    observation_count += 1
                    option_count += len(r["options"])
                    play_counts[r["play"]] += 1
                    con.execute("INSERT INTO observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (observation_count,r["issue"],r["slot"],r["play"],r["native_match_id"],r["status"],r["score"],r["halftime_score"],expected_option(r),r["source_sha256"],r["source_url"],r["received_at"],canonical(r)))
                    con.executemany("INSERT INTO option_sp VALUES(?,?,?,?,?)", [(observation_count,o["option"],o["raw_sp"],o["sp"],o["cell_id"]) for o in r["options"]])
                for finding in audit_rows(rows):
                    finding_counts[finding["code"]] += 1
                    con.execute("INSERT INTO finding VALUES(?,?,?,?,?,?)", tuple(finding[k] for k in ("issue", "slot", "play", "code", "detail", "source_sha256")))
                    con.execute("INSERT INTO finding_order VALUES(?)", (canonical(finding),))
            con.execute("CREATE INDEX observation_lookup ON observation(issue,slot,play,source_sha256)")
            con.execute("CREATE INDEX option_observation_lookup ON option_sp(observation_id)")
            con.execute("CREATE INDEX finding_detail_order ON finding(issue,slot,play,code,source_sha256)")
            receipt = {
                "schema": "nowscore_audit_v1", "source": "nowscore", "evidence_class": "HISTORICAL_PROXY",
                "manifest_sha256": digest(manifest_bytes), "implementation_sha256": implementation,
                "runtime": {"python": sys.version, "beautifulsoup4": version("beautifulsoup4")},
                "requested_issues": manifest["requested_issues"], "capture_count": len(captures),
                "capture_failures": failures, "source_empty_pages": source_empty_pages,
                "observations": observation_count, "matches": match_count, "options": option_count,
                "findings_by_code": dict(sorted(finding_counts.items())),
                "observations_by_play": dict(sorted(play_counts.items())),
                "data_sha256": hash_json_texts(r[0] for r in con.execute("SELECT payload_json FROM observation ORDER BY observation_id")),
                "audit_sha256": hash_json_texts(r[0] for r in con.execute("SELECT payload_json FROM finding_order ORDER BY payload_json COLLATE BINARY")),
                "peak_issue_observations": peak_issue_rows,
                "five_play_task_coverage_complete": history,
                "inventory_sha256": manifest["history_inventory"]["inventory_sha256"] if history else None,
                "historical_coverage_complete": False, "production_enabled": False,
                "historical_learning_functions": [],
            }
            con.execute("INSERT INTO receipt VALUES(?)", (canonical(receipt),))
    finally:
        con.close()
    return receipt
