"""Source-pure Nowscore observations and deterministic diagnostic audit.

No historical fitting, settlement correction, source fallback or payout policy.
An observation passing these checks is not an official settlement notice.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from importlib.metadata import version
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

from src.nowscore_bjdc_sp_history import TYPEID_LABELS

PLAYS = {5: "spf", 6: "jq", 7: "ds", 8: "bf", 9: "bq"}
ABNORMAL = {"取消", "推迟", "中断", "腰斩", "延期", "待定"}
TITLE = {5: "让球胜平负", 6: "总进球", 7: "上下单双", 8: "单场比分", 9: "半全场"}
EMPTY = {"", "-", "--"}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def source_url(issue: str, typeid: int) -> str:
    if not re.fullmatch(r"\d{5,6}", issue) or typeid not in PLAYS:
        raise ValueError("invalid issue/typeid")
    return f"https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID={typeid}&issueNum={issue}"


def score(text: str):
    m = re.fullmatch(r"(\d+)\s*[-:]\s*(\d+)", text)
    return tuple(map(int, m.groups())) if m else None


def outcome(home: int, away: int) -> str:
    return "胜" if home > away else "负" if home < away else "平"


def expected_option(row: dict):
    ft = score(row["score"])
    if ft is None:
        return None
    h, a = ft
    play = row["play"]
    if play == "spf":
        line = row["handicap"]
        return None if line is None else outcome(h + line, a)
    if play == "jq":
        return f"{h+a}球" if h+a < 7 else "7+球"
    if play == "ds":
        return ("上" if h+a >= 3 else "下") + "+" + ("单" if (h+a) % 2 else "双")
    if play == "bf":
        exact = f"{h}:{a}"
        return exact if exact in TYPEID_LABELS[8] else outcome(h, a) + "其他"
    ht = score(row["halftime_score"])
    return None if ht is None else outcome(*ht) + "-" + outcome(h, a)


def parse_page(payload: bytes, issue: str, typeid: int) -> list[dict]:
    """Validate page identity and parse labels, never numerical cell order."""
    source_url(issue, typeid)
    text = payload.decode("utf-8-sig", errors="strict")
    soup = BeautifulSoup(text, "html.parser")
    if soup.title is None or TITLE[typeid] not in soup.title.get_text():
        raise ValueError("wrong play title or non-data response")
    selected = soup.select_one("#dropIssueNum option[selected]")
    if selected is None or selected.get("value") != issue:
        raise ValueError("selected issue differs from requested issue")
    score_containers = {}
    if typeid == 8:
        for node in soup.find_all("tr", id=re.compile(r"^tr_\d+$")):
            if node["id"] in score_containers:
                raise ValueError("duplicate correct-score container")
            score_containers[node["id"]] = node
    rows = []
    for tr in soup.select('tr[id^="row_"]'):
        ident = re.fullmatch(r"row_(\d+)", tr.get("id", ""))
        if ident is None or tr.get("matchid") != ident[1]:
            raise ValueError("row identity malformed")
        slot = int(ident[1])
        if slot <= 0:
            raise ValueError("invalid slot")
        td = tr.find_all("td", recursive=False)
        offset = 1 if typeid == 5 else 0
        if len(td) < 9 + offset:
            raise ValueError("fixture row too short")
        home = tr.select_one('a[id^="HomeTeam_"]')
        away = tr.select_one('a[id^="GuestTeam_"]')
        if home is None or away is None:
            raise ValueError("missing native team/match identity")
        native_id = home["id"].removeprefix("HomeTeam_")
        if not native_id.isdigit() or away["id"] != f"GuestTeam_{native_id}":
            raise ValueError("home/away native identity mismatch")
        team_ids = []
        for side in (home, away):
            matches = re.findall(rf"/temp/{re.escape(native_id)}_(\d+)\.htm", side.get("onmouseover", ""), re.I)
            team_ids.append(matches[0] if len(matches) == 1 and int(matches[0]) > 0 else None)
        links = [x.get("href", "") for x in tr.select("a[href]")]
        if f"/sp/danchang/{issue}_{slot}_{typeid}.html" not in links:
            raise ValueError("row SP link identity mismatch")
        errors = []
        if None in team_ids or team_ids[0] == team_ids[1]:
            errors.append("missing_or_invalid_native_team_identity")
        line_text = tr.get("polygoal", "")
        line = int(line_text) if re.fullmatch(r"[+-]?\d+", line_text) else None
        if typeid == 5 and line is None:
            errors.append("missing_or_invalid_handicap")
        vector = []
        container = score_containers.get(f"tr_{slot}") if typeid == 8 else tr
        if container is None:
            errors.append("missing_option_container")
        else:
            for span in container.select('span[id^="sp_"]'):
                if not re.fullmatch(rf"sp_{slot}_\d+", span.get("id", "")):
                    continue
                cell = span.find_parent("td")
                label_node = cell.find("b", recursive=False)
                label = (label_node.get_text(strip=True) if typeid == 8 and label_node else cell.get("title", ""))
                label = {"主胜": "胜", "平局": "平", "客胜": "负"}.get(label, label).replace("其它", "其他")
                raw = span.get_text(" ", strip=True)
                value = None
                if raw not in EMPTY:
                    try:
                        value = float(raw)
                        if not math.isfinite(value) or value < 1:
                            raise ValueError()
                    except ValueError:
                        value = None
                        errors.append("invalid_sp")
                vector.append({"option": label, "raw_sp": raw, "sp": value, "cell_id": span["id"]})
        labels = [x["option"] for x in vector]
        if Counter(labels) != Counter(TYPEID_LABELS[typeid]):
            errors.append("option_domain_mismatch")
        summary_raw, summary_sp = "", None
        if typeid == 8:
            toggle = tr.select_one(f"#sp_{slot}")
            summary_cell = toggle.find_parent("td").find_previous_sibling("td") if toggle else None
            if summary_cell is not None:
                summary_raw = summary_cell.get_text(strip=True)
                if summary_raw not in EMPTY:
                    try:
                        summary_sp = float(summary_raw)
                        if not math.isfinite(summary_sp) or summary_sp < 1:
                            raise ValueError()
                    except ValueError:
                        summary_sp = None
                        errors.append("invalid_summary_sp")
        row = {
            "issue": issue, "slot": slot, "typeid": typeid, "play": PLAYS[typeid],
            "native_match_id": native_id, "home": home.get_text(strip=True), "away": away.get_text(strip=True),
            "home_id": team_ids[0], "away_id": team_ids[1],
            "league": tr.get("gamename", ""), "schedule_date": tr.get("name", ""),
            "kickoff_time": td[2].get_text(strip=True), "status": td[3].get_text(strip=True),
            "cutoff_text": td[3].get("title", ""), "can_sale": tr.get("cansale", ""),
            "score": td[5 + offset].get_text(strip=True),
            "halftime_score": td[7 + offset].get_text(strip=True),
            "handicap_raw": line_text, "handicap": line, "options": vector, "parse_errors": errors,
            "summary_sp_raw": summary_raw, "summary_sp": summary_sp,
        }
        rows.append(row)
    if not rows:
        raise ValueError("no fixture rows; cannot assert an empty issue")
    matrix = re.findall(r"M\[(\d+)\]\[0\]\s*=\s*['\"]?(\d+)['\"]?\s*;", text)
    if not matrix or Counter((int(i), n) for i, n in matrix) != Counter((r["slot"], r["native_match_id"]) for r in rows):
        raise ValueError("embedded roster and visible all=1 rows differ or roster missing")
    return rows


def audit_rows(rows: list[dict]) -> list[dict]:
    findings = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r["issue"], r["slot"])].append(r)

    def add(r, code, detail=""):
        findings.append({"issue": r["issue"], "slot": r["slot"], "play": r["play"],
                         "code": code, "detail": detail, "source_sha256": r.get("source_sha256", "")})

    for r in rows:
        for e in sorted(set(r["parse_errors"])):
            add(r, e)
        ft, ht = score(r["score"]), score(r["halftime_score"])
        for field in ("score", "halftime_score"):
            if r[field] not in EMPTY and score(r[field]) is None:
                add(r, "malformed_" + field, r[field])
        if ft and ht and (ht[0] > ft[0] or ht[1] > ft[1]):
            add(r, "halftime_exceeds_fulltime")
        filled = [o for o in r["options"] if o["sp"] is not None]
        complete = Counter(o["option"] for o in r["options"]) == Counter(TYPEID_LABELS[r["typeid"]])
        all_one = complete and len(filled) == len(r["options"]) and all(o["sp"] == 1 for o in filled)
        exp = expected_option(r)
        if all_one:
            add(r, "full_domain_all_one", "特殊结算形态，非官方无效公告；不自动填充或退款")
        elif len(filled) == 1:
            if filled[0]["sp"] == 1:
                add(r, "single_option_sp_one")
            if exp is not None and filled[0]["option"] != exp:
                add(r, "option_score_mismatch", f'{filled[0]["option"]} -> {exp}')
            if r["status"] != "完场":
                add(r, "single_option_nonfinished")
            if r["status"] == "完场" and exp is None:
                add(r, "missing_score_or_handicap_for_result")
        elif r["status"] == "完场":
            if not filled and r.get("summary_sp") is not None:
                add(r, "summary_sp_without_option", "保留汇总SP，但不根据比分补造选项SP")
            else:
                add(r, "finished_missing_sp" if not filled else "finished_multiple_sp")
        elif r["status"] in ABNORMAL:
            add(r, "abnormal_without_all_one", "不把参考SP向量当中奖选项")
        elif filled and len(filled) != len(r["options"]):
            add(r, "partial_reference_vector")
        if r["status"] == "完场" and ft is None:
            add(r, "finished_missing_score")
        if r["status"] == "完场" and r["can_sale"] != "false":
            add(r, "finished_sale_flag_conflict")
        if r["status"] not in ABNORMAL | {"完场", "未", "未开", "未开始", "上", "中", "下", "加", "点"} and not re.fullmatch(r"\d+['′]?", r["status"]):
            add(r, "unrecognized_status", r["status"])
    for key, group in sorted(groups.items()):
        counts = Counter(r["play"] for r in group)
        for r in group:
            if counts[r["play"]] > 1:
                add(r, "duplicate_issue_slot_play")
        missing = sorted(set(PLAYS.values()) - counts.keys())
        if missing:
            add(group[0], "missing_play_coverage", ",".join(missing))
        for field in ("native_match_id", "home", "away", "schedule_date", "kickoff_time", "score", "halftime_score", "status", "handicap_raw"):
            values = sorted({r[field] for r in group})
            if len(values) > 1:
                for r in group:
                    add(r, "cross_play_" + field, canonical(values))
    return sorted(findings, key=canonical)


def build_database(run_root: Path, output: Path) -> dict:
    """Replay a sealed capture manifest; fail if output exists or input hashes differ."""
    manifest_bytes = (run_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["source"] != "nowscore" or manifest["schema"] != "nowscore_capture_v1":
        raise ValueError("wrong source manifest")
    rows, captures, failures = [], [], []
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
        try:
            parsed = parse_page(payload, issue, typeid)
        except (ValueError, UnicodeError) as exc:
            failures.append({**entry, "error": str(exc)})
            continue
        for r in parsed:
            r.update(source_sha256=entry["sha256"], source_url=entry["url"], received_at=entry["received_at"])
        rows.extend(parsed)
    requested = {(i, t) for i in manifest["requested_issues"] for t in PLAYS}
    if requested != seen:
        raise ValueError("capture ledger does not cover requested issue/play domain")
    findings = audit_rows(rows)
    implementation = {str(p): digest(p.read_bytes()) for p in (
        Path(__file__), Path(__file__).with_name("nowscore_bjdc_sp_history.py"),
        Path(__file__).with_name("multimarket_p0.py"),
    )}
    receipt = {
        "schema": "nowscore_audit_v1", "source": "nowscore", "evidence_class": "HISTORICAL_PROXY",
        "manifest_sha256": digest(manifest_bytes), "implementation_sha256": implementation,
        "runtime": {"python": sys.version, "beautifulsoup4": version("beautifulsoup4")},
        "requested_issues": manifest["requested_issues"], "capture_count": len(captures),
        "capture_failures": failures, "observations": len(rows),
        "matches": len({(r["issue"], r["slot"]) for r in rows}),
        "options": sum(len(r["options"]) for r in rows),
        "findings_by_code": dict(sorted(Counter(f["code"] for f in findings).items())),
        "observations_by_play": dict(sorted(Counter(r["play"] for r in rows).items())),
        "data_sha256": digest(canonical(rows).encode()), "audit_sha256": digest(canonical(findings).encode()),
        "historical_coverage_complete": False, "production_enabled": False,
        "historical_learning_functions": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".nowscore-audit-") as temporary:
        stage = Path(temporary) / "audit.sqlite"
        con = sqlite3.connect(stage)
        try:
            con.executescript('''
          CREATE TABLE capture (issue TEXT, typeid INTEGER, source_url TEXT, received_at TEXT, sha256 TEXT, PRIMARY KEY(issue,typeid));
          CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT, slot INTEGER, play TEXT, native_match_id TEXT, status TEXT, score TEXT, halftime_score TEXT, expected_option TEXT, source_sha256 TEXT, source_url TEXT, received_at TEXT, payload_json TEXT);
          CREATE TABLE option_sp (observation_id INTEGER, option TEXT, raw_sp TEXT, sp REAL, cell_id TEXT, FOREIGN KEY(observation_id) REFERENCES observation(observation_id));
          CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT, detail TEXT, source_sha256 TEXT);
          CREATE TABLE receipt (payload_json TEXT);
        ''')
            with con:
                con.executemany("INSERT INTO capture VALUES(?,?,?,?,?)", [(e["issue"],e["typeid"],e["url"],e["received_at"],e["sha256"]) for e in captures])
                for i, r in enumerate(rows, 1):
                    con.execute("INSERT INTO observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (i,r["issue"],r["slot"],r["play"],r["native_match_id"],r["status"],r["score"],r["halftime_score"],expected_option(r),r["source_sha256"],r["source_url"],r["received_at"],canonical(r)))
                    con.executemany("INSERT INTO option_sp VALUES(?,?,?,?,?)", [(i,o["option"],o["raw_sp"],o["sp"],o["cell_id"]) for o in r["options"]])
                con.executemany("INSERT INTO finding VALUES(?,?,?,?,?,?)", [(f["issue"],f["slot"],f["play"],f["code"],f["detail"],f["source_sha256"]) for f in findings])
                con.execute("INSERT INTO receipt VALUES(?)", (canonical(receipt),))
        finally:
            con.close()
        os.link(stage, output)
    return receipt
