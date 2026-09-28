"""Fixture-bound manual all-one decisions on an immutable Nowscore copy.

SP is dimensionless. NULL and empty raw cells stay unchanged. No network,
inferred target selection, official-notice claim, or ticket payout execution.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tempfile

from src.nowscore_settlement import PLAYS, TYPEID_LABELS, canonical, digest, expected_option
import json


def special_notices(con: sqlite3.Connection) -> list[dict]:
    """Read and validate five-play all-one notices; never infer a refund.

Only complete, consistent abnormal fixtures with 49 original SP=1 cells and
no other findings qualify. Incomplete/conflicting fixtures remain findings.
"""
    notices = []
    for issue, slot in con.execute("SELECT DISTINCT issue,slot FROM finding WHERE code='full_domain_all_one'"):
        raw_rows = con.execute('SELECT observation_id,payload_json FROM observation WHERE issue=? AND slot=?', (issue,slot)).fetchall()
        rows = [json.loads(p) for _,p in raw_rows]
        flags = con.execute('SELECT play,code FROM finding WHERE issue=? AND slot=? ORDER BY play', (issue,slot)).fetchall()
        if len(rows) != 5 or {r['play'] for r in rows} != set(PLAYS.values()) or flags != [(p,'full_domain_all_one') for p in sorted(PLAYS.values())]:
            continue
        if any(len({r[k] for r in rows}) != 1 for k in ('native_match_id','status','score','halftime_score','home','away')):
            continue
        if any(r['status'] not in {'取消','推迟','中断','腰斩'} or r['parse_errors'] or r['can_sale'] != 'false' for r in rows):
            continue
        valid = True
        for (oid,_),r in zip(raw_rows,rows,strict=True):
            opts = con.execute('SELECT option,raw_sp,sp,cell_id FROM option_sp WHERE observation_id=? ORDER BY option',(oid,)).fetchall()
            if (PLAYS[r['typeid']] != r['play'] or sorted(o[0] for o in opts) != sorted(TYPEID_LABELS[r['typeid']])
                or opts != sorted((o['option'],o['raw_sp'],o['sp'],o['cell_id']) for o in r['options'])
                or any(o[2] != 1 for o in opts)):
                valid = False
        if valid:
            notices.append({'issue':issue,'slot':slot,'status':rows[0]['status'],'code':'source_full_domain_all_one','official_notice_verified':False})
    return sorted(notices, key=lambda r:(r['issue'],r['slot']))


def prepare_decisions(con: sqlite3.Connection, targets: list[tuple[str, int]], reviewed_at: str, zero_targets: tuple[tuple[str, int], ...] = ()) -> dict:
    """Read explicit issue/slot targets; return frozen ledger or raise ValueError.

Requires a read-only, stable transaction and the approved BF database schema.
Each explicit target must have five consistent plays: either finished with one
score-consistent SP=1 and empty remaining cells, or abnormal with no scores,
BF summary SP=1 and complete positive reference vectors. Neither branch selects
targets automatically or changes source status.
Explicit zero_targets additionally admits original 0.00 cells (not empty cells)
on abnormal BF/BQ reference grids; no other parser errors are permitted.
"""
    if datetime.fromisoformat(reviewed_at).tzinfo is None:
        raise ValueError("review timestamp requires timezone")
    if not targets or len(set(targets)) != len(targets):
        raise ValueError("empty or duplicate targets")
    if len(set(zero_targets)) != len(zero_targets) or not set(zero_targets).issubset(targets):
        raise ValueError('zero targets must be unique explicit targets')
    receipt = con.execute("SELECT payload_json FROM receipt").fetchone()[0]
    if json.loads(receipt)["source"] != "nowscore":
        raise ValueError("wrong source")
    decisions = []
    for issue, slot in sorted(targets):
        if not isinstance(issue, str) or not issue.isdigit() or type(slot) is not int or slot <= 0:
            raise ValueError("invalid issue/slot")
        observed = con.execute("SELECT observation_id,play,payload_json FROM observation WHERE issue=? AND slot=? ORDER BY play", (issue, slot)).fetchall()
        if len(observed) != 5 or {r[1] for r in observed} != set(PLAYS.values()):
            raise ValueError("five-play coverage required")
        flags = con.execute("SELECT play,code FROM effective_finding WHERE issue=? AND slot=? ORDER BY play", (issue,slot)).fetchall()
        zero_review = (issue,slot) in zero_targets
        abnormal_flags = [(p,"abnormal_without_all_one") for p in sorted(PLAYS.values())]
        if zero_review:
            abnormal_flags += [('bf','invalid_sp'),('bq','invalid_sp')]
        abnormal = sorted(flags) == sorted(abnormal_flags)
        if zero_review and not abnormal:
            raise ValueError('zero exception requires abnormal BF/BQ invalid findings')
        if not abnormal and flags != [(p,"single_option_sp_one") for p in sorted(PLAYS.values())]:
            raise ValueError("unexpected additional or missing findings")
        snapshots = []
        for oid, play, payload in observed:
            raw = json.loads(payload)
            if (raw['issue'],raw['slot'],raw['play']) != (issue,slot,play):
                raise ValueError("payload identity mismatch")
            zeros = [o for o in raw['options'] if o['raw_sp']=='0.00' and o['sp'] is None]
            allowed_errors = ['invalid_sp'] * len(zeros) if zero_review and play in {'bf','bq'} else []
            if raw["parse_errors"] != allowed_errors or raw["can_sale"] != "false":
                raise ValueError("not a clean closed observation")
            if abnormal:
                if raw["status"] not in {"推迟", "中断", "取消", "腰斩"} or raw["score"] != "-" or raw["halftime_score"] != "-":
                    raise ValueError("abnormal status/no-score predicate failed")
                if play == "bf" and raw["summary_sp"] != 1:
                    raise ValueError("BF summary must equal one")
            elif raw["status"] != "完场":
                raise ValueError("not a clean finished observation")
            domain = TYPEID_LABELS[raw["typeid"]]
            if PLAYS[raw["typeid"]] != play:
                raise ValueError("typeid mismatch")
            options = con.execute("SELECT option,raw_sp,sp,cell_id FROM option_sp WHERE observation_id=? ORDER BY option", (oid,)).fetchall()
            if sorted(o[0] for o in options) != sorted(domain):
                raise ValueError("incomplete or duplicate option domain")
            if options != sorted((o["option"],o["raw_sp"],o["sp"],o["cell_id"]) for o in raw["options"]):
                raise ValueError("raw option representations disagree")
            winning = [o for o in options if o[2] is not None]
            if abnormal and (len(winning) + (len(zeros) if zero_review else 0) != len(domain) or any(o[2] < 1 for o in winning)):
                raise ValueError("complete positive reference vector required")
            if not abnormal and (len(winning) != 1 or winning[0][2] != 1 or winning[0][0] != expected_option(raw)):
                raise ValueError("single-one/score predicate failed")
            if any(o[1] != "" and not (zero_review and play in {'bf','bq'} and o[1]=='0.00') for o in options if o[2] is None):
                raise ValueError("nonempty invalid cells cannot be filled")
            snapshots.append({"observation_id": oid, "payload": raw, "options": options})
        for field in ("native_match_id", "home", "away", "status", "score", "halftime_score", "schedule_date", "kickoff_time", "handicap_raw"):
            if len({s["payload"][field] for s in snapshots}) != 1:
                raise ValueError("cross-play conflict: " + field)
        decisions.append({"decision_id": f"ns-manual-all-one-{issue}-{slot}", "issue": issue, "slot": slot,
                          "review_status": "user_confirmed", "evidence_class": "user_manual_all_one",
                          "reason": "manual_abnormal_with_original_zero_cells" if zero_review else "abnormal_status_bf_summary_one" if abnormal else "finished_single_option_one",
                          "zero_cells_reviewed": zero_review,
                          "official_notice_verified": False, "new_sp": 1, "snapshots": snapshots})
    return {"schema": "nowscore_manual_all_one_v1", "reviewed_at": reviewed_at,
            "source_snapshot_sha256": digest(con.serialize()), "source_receipt_sha256": digest(receipt.encode()),
            "decisions": decisions, "special_notices": special_notices(con)}


def persist_decisions(con: sqlite3.Connection, ledger: dict) -> dict:
    """Transactionally add a prepared ledger and replace effective views.

Input is prepare_decisions output, not an external unvalidated ledger. Raw and
prior BF tables are untouched. Any SQL failure rolls back DDL and inserted rows.
Caller owns connection closing; returns receipt with deterministic provenance.
"""
    rows = []
    for d in ledger["decisions"]:
        for s in d["snapshots"]:
            for option, raw_sp, old_sp, cell_id in s["options"]:
                rows.append((d["decision_id"],s["observation_id"],d["issue"],d["slot"],s["payload"]["play"],option,raw_sp,old_sp,1))
    receipt = {"ledger": ledger, "ledger_sha256": digest(canonical(ledger).encode()),
               "generation_time": ledger["reviewed_at"], "evidence_class": "user_manual_all_one",
               "implementation_sha256": digest(Path(__file__).read_bytes()),
               "helper_sha256": digest(Path(__file__).with_name("nowscore_settlement.py").read_bytes()),
               "domain_sha256": digest(Path(__file__).with_name("nowscore_bjdc_sp_history.py").read_bytes()),
               "matches": len(ledger["decisions"]), "options": len(rows),
               "newly_filled_options": sum(r[-3] == '' and r[-2] is None for r in rows),
               "reviewed_original_zero_options": sum(r[-3] == '0.00' and r[-2] is None for r in rows),
               "special_notice_matches": len(ledger['special_notices']),
               "replaced_reference_options": sum(r[-2] is not None and r[-2] != 1 for r in rows),
               "historical_availability": "HISTORICAL_PROXY", "production_enabled": False}
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("CREATE TABLE manual_all_one (decision_id TEXT, observation_id INTEGER, issue TEXT, slot INTEGER, play TEXT, option TEXT, original_raw_sp TEXT, original_sp REAL, effective_sp REAL CHECK(effective_sp=1), PRIMARY KEY(observation_id,option))")
        con.execute('CREATE TABLE special_settlement_notice(issue TEXT,slot INTEGER,status TEXT,code TEXT,payload_json TEXT,PRIMARY KEY(issue,slot))')
        con.executemany('INSERT INTO special_settlement_notice VALUES(?,?,?,?,?)',[(r['issue'],r['slot'],r['status'],r['code'],canonical(r)) for r in ledger['special_notices']])
        con.execute("CREATE TABLE manual_all_one_receipt(payload_json TEXT NOT NULL)")
        con.executemany("INSERT INTO manual_all_one VALUES(?,?,?,?,?,?,?,?,?)", rows)
        con.execute("DROP VIEW effective_option_sp")
        con.execute('''CREATE VIEW effective_option_sp AS SELECT o.*,
          COALESCE(m.effective_sp,d.derived_sp,o.sp) AS effective_sp,
          CASE WHEN m.decision_id IS NOT NULL THEN 'user_manual_all_one'
               WHEN d.decision_id IS NOT NULL THEN d.evidence_class ELSE 'source_observed' END AS evidence_class,
          COALESCE(m.decision_id,d.decision_id) AS decision_id
          FROM option_sp o LEFT JOIN bf_derivation d ON o.observation_id=d.observation_id AND o.option=d.derived_option
          LEFT JOIN manual_all_one m ON o.observation_id=m.observation_id AND o.option=m.option''')
        con.execute("DROP VIEW effective_finding")
        con.execute('''CREATE VIEW effective_finding AS SELECT f.* FROM finding f
          WHERE NOT (f.code='summary_sp_without_option' AND f.play='bf' AND EXISTS
            (SELECT 1 FROM bf_derivation d WHERE d.issue=f.issue AND d.slot=f.slot))
          AND NOT (f.code IN ('single_option_sp_one','abnormal_without_all_one') AND EXISTS
            (SELECT 1 FROM manual_all_one m WHERE m.issue=f.issue AND m.slot=f.slot AND m.play=f.play))
          AND NOT (f.code='invalid_sp' AND EXISTS
            (SELECT 1 FROM manual_all_one m WHERE m.issue=f.issue AND m.slot=f.slot AND m.play=f.play AND m.original_raw_sp='0.00'))
          AND NOT (f.code='full_domain_all_one' AND EXISTS
            (SELECT 1 FROM special_settlement_notice n WHERE n.issue=f.issue AND n.slot=f.slot))''')
        con.execute("INSERT INTO manual_all_one_receipt VALUES(?)", (canonical(receipt),))
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return receipt


def apply_decisions(source: Path, output: Path, targets: list[tuple[str, int]], reviewed_at: str, zero_targets: tuple[tuple[str, int], ...] = ()) -> dict:
    """Create a new SQLite copy atomically; refuse overwrite and rollback on error.

All paths explicit. Source opens read-only; output is published only after a
successful transaction/integrity check. Temporary files/connections are released.
Repeated input/time reproduces the same receipt; repeated output is an error.
"""
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri()+"?mode=ro",uri=True)) as src:
        src.execute("BEGIN")
        ledger = prepare_decisions(src,targets,reviewed_at,zero_targets)
        with tempfile.TemporaryDirectory(prefix=".nowscore-manual-",dir=output.parent) as work:
            temporary = Path(work)/"result.sqlite"
            with closing(sqlite3.connect(temporary)) as dest:
                src.backup(dest)
                result = persist_decisions(dest,ledger)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("SQLite integrity failure")
            os.link(temporary,output)  # Atomic, no overwrite; temp cleanup leaves published inode.
    return result
