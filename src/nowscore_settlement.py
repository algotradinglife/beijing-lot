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

PLAYS = {5: "spf", 6: "jq", 7: "ds", 8: "bf", 9: "bq"}
ABNORMAL = {"取消", "推迟", "中断", "腰斩", "延期", "待定"}
TITLE = {5: "让球胜平负", 6: "总进球", 7: "上下单双", 8: "单场比分", 9: "半全场"}
EMPTY = {"", "-", "--"}
ARCHIVE_SLUGS = {5: "rangqiushengpingfu", 6: "zongjinqiuhu", 7: "shangxiapandanshuang",
                 8: "bifen", 9: "banquanchangshengfu"}


class RosterConflict(ValueError):
    """Identity-valid page with contradictory rosters; args[1] binds differences."""


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def source_url(issue: str, typeid: int) -> str:
    if not re.fullmatch(r"\d{5,6}", issue) or typeid not in PLAYS:
        raise ValueError("invalid issue/typeid")
    if len(issue) == 6:
        return f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_{issue}.html"
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


def parse_archive_page(payload: bytes, issue: str, typeid: int) -> list[dict]:
    """Parse a native archive's labelled result and settlement SP only.

    Reference odds remain in raw bytes, never in the option vector. Missing
    status, full date, sale flag and unshown handicap are not inferred. The
    observed result is a partial option vector, not a full-domain observation.
    Native match ID sentinel -1 is preserved and flagged, never used as a key.
    Raises on layout/identity drift; malformed values become explicit findings.
    """
    source_url(issue, typeid)
    soup = BeautifulSoup(payload.decode("utf-8-sig", errors="strict"), "html.parser")
    active = soup.select("#mymenu li.myons a[href]")
    expected = f"/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_{issue}.html"
    title = "单场进球数" if typeid == 6 else TITLE[typeid]
    if soup.title is None or title not in soup.title.get_text() or len(active) != 1 or active[0]["href"] != expected:
        raise ValueError("archive SPF identity mismatch")
    selected = soup.select("#dropIssue option[selected]")
    if len(selected) > 1 or (selected and selected[0].get("value") != issue):
        raise ValueError("selected archive issue mismatch")
    expected_headers = ["场次", "赛事", "开赛时间", "主队(让球)" if typeid == 5 else "主队",
                        "比分", "客队", "半场", "彩果", "开奖SP", "平均欧*", "Crow*", "数据"]
    rows, slots = [], set()
    for tr in soup.select('tr[id^="row_"]'):
        ident = re.fullmatch(r"row_([1-9]\d*)", tr.get("id", ""))
        td = tr.find_all("td", recursive=False)
        headers = tr.find_parent("table").select("tr.ttis")
        if len(headers) != 1 or [c.get_text(strip=True) for c in headers[0].find_all("td", recursive=False)] != expected_headers or len(td) != 14:
            raise ValueError("archive SPF column contract mismatch")
        if ident is None or td[0].get_text(strip=True) != ident[1] or int(ident[1]) in slots:
            raise ValueError("archive SPF slot identity mismatch")
        slot = int(ident[1])
        slots.add(slot)
        links = td[8].select("a[href]")
        if len(links) != 1 or links[0]["href"] != f"/sp/danchang/{issue}_{slot}_{typeid}.html" or td[8].get("title") != "开奖SP":
            raise ValueError("archive SPF settlement link mismatch")
        native_ids = [m.group(1) for a in td[13].select("a[href]") if
                      (m := re.fullmatch(r"(?:(?:https?:)?//live\.nowscore\.com)/analysis/(-1|\d+)cn\.html", a["href"]))]
        if len(native_ids) != 1:
            raise ValueError("archive SPF native match identity missing or duplicated")
        errors = ["archive_partial_option_coverage", "unobserved_status", "unobserved_full_schedule_date"]
        if native_ids[0] == "-1":
            errors.append("missing_native_match_id")
        home_raw = td[3].get_text(" ", strip=True)
        line_match = re.search(r"\(\s*([+-]\d+)\s*\)\s*$", home_raw) if typeid == 5 else None
        line_raw = line_match[1] if line_match else ""
        home = home_raw[:line_match.start()].strip() if line_match else home_raw
        if typeid == 5 and not line_match:
            errors.append("missing_or_invalid_handicap")
        label_nodes = td[7].select("span.spitems")
        if len(label_nodes) > 1 or (not label_nodes and td[7].get_text(strip=True)):
            raise ValueError("archive SPF result label container missing or duplicated")
        label = label_nodes[0].get_text(strip=True) if label_nodes else ""
        raw = links[0].get_text(strip=True)
        normalized_label = label.replace("其它", "其他")
        if typeid == 6 and label in {"0", "1", "2", "3", "4", "5", "6", "7+"}:
            normalized_label = label + "球"
        if typeid == 7 and label in {"上单", "上双", "下单", "下双"}:
            normalized_label = label[0] + "+" + label[1]
        value = None
        if raw not in EMPTY:
            try:
                value = float(raw)
                if not math.isfinite(value) or value < 1:
                    raise ValueError()
            except ValueError:
                value = None
                errors.append("invalid_sp")
        options = []
        if normalized_label in TYPEID_LABELS[typeid]:
            options.append({"option": normalized_label, "raw_sp": raw, "sp": value, "cell_id": f"archive_result_{slot}"})
        else:
            errors.append("unrecognized_archive_result")
        rows.append({
            "issue": issue, "slot": slot, "typeid": typeid, "play": PLAYS[typeid], "native_match_id": native_ids[0],
            "home": home, "away": td[5].get_text(strip=True), "league": td[1].get_text(strip=True),
            "schedule_date": "", "kickoff_time": td[2].get_text(strip=True), "status": "",
            "cutoff_text": "", "can_sale": "", "score": td[4].get_text(strip=True),
            "halftime_score": td[6].get_text(strip=True), "handicap_raw": line_raw,
            "handicap": int(line_raw) if line_match else None, "options": options, "parse_errors": errors,
            "summary_sp_raw": raw, "summary_sp": value, "archive_result_raw": label,
            "source_layout": "archive_result_v1",
        })
    if not rows:
        tables = soup.select("table.socai")
        empty_rows = tables[0].select("tr") if len(tables) == 1 else []
        if (len(empty_rows) != 1 or "ttis" not in empty_rows[0].get("class", [])
                or [c.get_text(strip=True) for c in empty_rows[0].find_all("td", recursive=False)] != expected_headers
                or soup.select('[id^="row_"]')
                or any('/sp/danchang/' in a.get('href', '') for a in soup.select('a[href]'))):
            raise ValueError("archive SPF fixture rows missing")
    return rows


def parse_page(payload: bytes, issue: str, typeid: int) -> list[dict]:
    """Validate page identity and parse labels, never numerical cell order."""
    source_url(issue, typeid)
    if len(issue) == 6 and b"dropIssueNum" not in payload:
        return parse_archive_page(payload, issue, typeid)
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
    if not matrix:
        raise ValueError("embedded roster missing")
    embedded = Counter((int(i), n) for i, n in matrix)
    visible = Counter((r["slot"], r["native_match_id"]) for r in rows)
    if embedded != visible:
        raise RosterConflict("embedded roster and visible all=1 rows differ", {
            "embedded_only": [list(key) + [count] for key, count in sorted((embedded - visible).items())],
            "visible_only": [list(key) + [count] for key, count in sorted((visible - embedded).items())],
        })
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
        if r.get("source_layout") == "archive_result_v1" and not filled:
            if r["options"]:
                add(r, "archive_result_missing_sp", "彩果已观测，开奖SP未观测或无效；不填充")
                if exp is not None and r["options"][0]["option"] != exp:
                    add(r, "option_score_mismatch", f'{r["options"][0]["option"]} -> {exp}')
        if all_one:
            add(r, "full_domain_all_one", "特殊结算形态，非官方无效公告；不自动填充或退款")
        elif len(filled) == 1:
            if filled[0]["sp"] == 1:
                add(r, "single_option_sp_one")
            if exp is not None and filled[0]["option"] != exp:
                add(r, "option_score_mismatch", f'{filled[0]["option"]} -> {exp}')
            if r["status"] and r["status"] != "完场":
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
        if r["status"] not in ABNORMAL | {"完场", "未", "未开", "未开始", "上", "中", "下", "加", "点"} and not re.fullmatch(r"\d+['′]?", r["status"]) and not (r["status"] == "" and r.get("source_layout") == "archive_result_v1"):
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
