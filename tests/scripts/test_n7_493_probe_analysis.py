"""Offline tests for the #493 probe analysis and evidence reconstruction.

Synthetic HTML keeps these tests deterministic and network-free.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import n7_493_probe_analysis as an  # noqa: E402

HEADER = ("<tr class='gta'><td>时</td><td>比分</td><td>主</td><td>和局</td>"
          "<td>客</td><td>变化</td><td>状</td></tr>")


def row(minute, h, d, a, stamp, status):
    return (f"<tr><td>{minute}</td><td>-</td><td>{h}</td><td>{d}</td><td>{a}</td>"
            f"<td>{stamp}</td><td>{status}</td></tr>")


def table(rows):
    return "<table class='gts'>" + HEADER + "".join(rows) + "</table>"


def page(tables, companies=(), selected=None):
    html = "".join(tables)
    if companies:
        lis = "".join(f'<li><a href="?companyid={cid}&id=3061587" id="net{cid}">'
                      f"<span>{name}</span></a></li>" for cid, name in companies)
        html += f'<ul class="tg3" id="ulcompany">{lis}</ul>'
    if selected:
        html += f'<script>document.getElementById("net{selected}").className = "selected";</script>'
    return html


# --- parsing ------------------------------------------------------------------

def test_parse_market_tables_splits_the_three_markets():
    html = page([table([row("95", "0.92", "半/一", "0.96", "08-15 02:29", "滚")]),
                 table([row("95", "6.25", "1.5", "0.02", "08-15 02:29", "滚")]),
                 table([row("95", "1.01", "15.00", "21.00", "08-15 02:29", "滚")])])
    parsed = an.parse_market_tables(html)
    assert set(parsed) == set(an.MARKETS)
    assert parsed["euro_1x2"][1][2] == "1.01"
    assert parsed["asian_handicap"][1][3] == "半/一"


def test_parse_company_links_reads_id_and_masked_label():
    html = page([], companies=[("1", "澳*"), ("3", "Crow*"), ("9", "威廉希*")])
    assert an.parse_company_links(html) == [("1", "澳*"), ("3", "Crow*"), ("9", "威廉希*")]


def test_parse_company_links_absent_selector_is_empty():
    assert an.parse_company_links("<html></html>") == []


def test_selected_company_id_reads_the_page_anchor():
    html = page([], companies=[("3", "Crow*")], selected="3")
    assert an.selected_company_id(html) == "3"


def test_selected_company_id_is_none_without_an_anchor():
    assert an.selected_company_id("<html></html>") is None


def test_parse_change_stamp_applies_the_assumed_year():
    assert an.parse_change_stamp(["", "-", "1.62", "3.70", "4.70", "08-14 19:02", "即"]) \
        == "2026-08-14 19:02"


def test_parse_change_stamp_returns_none_without_a_time():
    assert an.parse_change_stamp(["", "-", "1.62", "3.70", "4.70", "-", "即"]) is None


def test_parse_change_stamp_is_year_configurable():
    assert an.parse_change_stamp(["08-14 19:02"], assumed_year=2025) \
        == "2025-08-14 19:02"


# --- cutoff selection ---------------------------------------------------------

def test_last_before_is_strictly_before_the_cutoff():
    rows = [["时"], ["1.56", "3.85", "5.00", "08-14 19:02", "即"],
            ["1.62", "3.70", "4.70", "08-14 20:00", "即"],
            ["1.63", "3.71", "4.71", "08-14 20:01", "即"]]
    stamp, _ = an.last_before(rows, "2026-08-14 20:00")
    assert stamp == "2026-08-14 19:02"


def test_last_before_excludes_live_rows():
    rows = [["时"], ["1.01", "15.00", "21.00", "08-14 19:30", "滚"],
            ["1.56", "3.85", "5.00", "08-14 19:02", "即"]]
    stamp, _ = an.last_before(rows, "2026-08-14 20:00")
    assert stamp == "2026-08-14 19:02", "in-play rows are not pre-match evidence"


def test_last_before_is_empty_when_nothing_precedes_the_cutoff():
    rows = [["时"], ["1.62", "3.70", "4.70", "08-14 21:00", "即"]]
    assert an.last_before(rows, "2026-08-14 20:00") == (None, None)


def test_last_before_picks_the_most_recent_not_the_first():
    rows = [["时"], ["1.40", "4.00", "4.50", "08-14 10:00", "即"],
            ["1.56", "3.85", "5.00", "08-14 19:02", "即"],
            ["1.45", "4.20", "5.70", "08-14 14:31", "即"]]
    stamp, _ = an.last_before(rows, "2026-08-14 20:00")
    assert stamp == "2026-08-14 19:02"


# --- diagnostics carry their assumptions --------------------------------------

def test_diagnostic_fields_name_their_assumptions(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "base_no_company.html").write_text(page(
        [table([row("", "1.56", "3.85", "5.00", "08-14 19:02", "即")])] * 3,
        companies=[("3", "Crow*")], selected="3"), encoding="utf-8")
    rows = an.build_diagnostic_rows(
        {"base_no_company": ("companyid=3", "anchor")}, raw, "2026-08-14 20:00")
    keys = set(rows[0])
    assert f"last_before_epoch_ASSUMED_UTC+8_YEAR_{an.YEAR_ASSUMED}" in keys
    assert f"rows_strictly_before_epoch_ASSUMED_UTC+8_YEAR_{an.YEAR_ASSUMED}" in keys
    assert rows[0]["tz_status"] == "TZ_UNDECIDED_DIAGNOSTIC_ONLY"
    assert rows[0]["availability_evidence"] == "NOT_PROVEN"


def test_diagnostics_exclude_the_header_from_the_row_count(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "base_no_company.html").write_text(page(
        [table([row("", "1.56", "3.85", "5.00", "08-14 19:02", "即")])] * 3),
        encoding="utf-8")
    rows = an.build_diagnostic_rows(
        {"base_no_company": ("v", "n")}, raw, "2026-08-14 20:00")
    assert all(r["rows_total"] == 1 for r in rows)


def test_diagnostics_csv_round_trips(tmp_path):
    rows = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    path = tmp_path / "d.csv"
    an.write_diagnostics_csv(rows, path)
    with path.open(encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [{"a": "1", "b": "x"},
                                                {"a": "2", "b": "y"}]


# --- ledger reconstruction leaves unknowns unknown ----------------------------

def make_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "base_no_company.html").write_bytes(b"base")
    (raw / "company_1.html").write_bytes(b"one")
    return raw


URLS = {"base_no_company": "https://live.nowscore.com/odds/3in1Odds.aspx?id=3061587",
        "company_1": "https://live.nowscore.com/odds/3in1Odds.aspx?companyid=1&id=3061587"}


def test_rebuild_leaves_unrecoverable_fields_unknown(tmp_path):
    raw = make_raw(tmp_path)
    surviving = {"requests": [{"label": "company_1", "http_status": 200,
                               "duration_ms": 167, "error": None,
                               "cookie_jar_id": "jar1"}]}
    ledger, _ = an.rebuild_request_ledger(tmp_path, surviving, URLS)
    base = next(r for r in ledger if r["label"] == "base_no_company")
    assert base["http_status"] is None
    assert base["http_status_provenance"] == "missing"
    assert base["duration_ms"] is None
    assert base["started_at"] is None
    assert base["cookie_jar_id"] is None
    assert base["hop"] is None
    assert base["hop_provenance"].startswith("missing")
    assert base["error"] is None and base["error_provenance"] == "missing"


def test_rebuild_preserves_genuinely_recorded_fields(tmp_path):
    raw = make_raw(tmp_path)
    surviving = {"requests": [{"label": "company_1", "http_status": 200,
                               "duration_ms": 167, "error": None,
                               "cookie_jar_id": "jar1"}]}
    ledger, _ = an.rebuild_request_ledger(tmp_path, surviving, URLS)
    company = next(r for r in ledger if r["label"] == "company_1")
    assert company["http_status"] == 200
    assert company["duration_ms"] == 167
    assert company["cookie_jar_id"] == "jar1"
    assert company["ended_at_provenance"] == "observed_file_mtime"
    assert company["sha256_provenance"] == "observed_file_content"
    assert company["sha256"] == an.hashlib.sha256(b"one").hexdigest()


def test_rebuild_never_claims_hop_accounting(tmp_path):
    raw = make_raw(tmp_path)
    ledger, provenance = an.rebuild_request_ledger(tmp_path, None, URLS)
    assert all(r["hop"] is None for r in ledger)
    assert provenance["redirect_occurrence"] == "UNKNOWN"
    assert provenance["hop_accounting_evidence"].startswith("UNKNOWN")


def test_rebuild_does_not_claim_the_serial_interval_was_satisfied(tmp_path):
    raw = make_raw(tmp_path)
    _, provenance = an.rebuild_request_ledger(tmp_path, None, URLS)
    assert provenance["serial_interval_compliance"] == "UNVERIFIED"
    assert "cannot establish" in provenance["serial_interval_evidence"]
    assert "satisfied" not in provenance["serial_interval_evidence"]


def test_rebuild_uses_each_entrys_own_jar_identity(tmp_path):
    raw = make_raw(tmp_path)
    (raw / "company_2.html").write_bytes(b"two")
    urls = dict(URLS, company_2="https://live.nowscore.com/odds/3in1Odds.aspx"
                                "?companyid=2&id=3061587")
    surviving = {"requests": [
        {"label": "company_1", "http_status": 200, "duration_ms": 10,
         "cookie_jar_id": "jar-A"},
        {"label": "company_2", "http_status": 200, "duration_ms": 10,
         "cookie_jar_id": "jar-B"}]}
    ledger, _ = an.rebuild_request_ledger(tmp_path, surviving, urls)
    by_label = {r["label"]: r for r in ledger}
    assert by_label["company_1"]["cookie_jar_id"] == "jar-A"
    assert by_label["company_2"]["cookie_jar_id"] == "jar-B"


def test_rebuild_leaves_a_missing_jar_unknown_rather_than_borrowing(tmp_path):
    raw = make_raw(tmp_path)
    (raw / "company_2.html").write_bytes(b"two")
    urls = dict(URLS, company_2="https://live.nowscore.com/odds/3in1Odds.aspx"
                                "?companyid=2&id=3061587")
    surviving = {"requests": [
        {"label": "company_1", "http_status": 200, "duration_ms": 10,
         "cookie_jar_id": "jar-A"},
        {"label": "company_2", "http_status": 200, "duration_ms": 10}]}
    ledger, _ = an.rebuild_request_ledger(tmp_path, surviving, urls)
    by_label = {r["label"]: r for r in ledger}
    assert by_label["company_2"]["cookie_jar_id"] is None
    assert by_label["company_2"]["cookie_jar_id_provenance"] == "missing"


def test_rebuild_marks_upper_limit_compliance_unverified(tmp_path):
    raw = make_raw(tmp_path)
    _, provenance = an.rebuild_request_ledger(tmp_path, None, URLS)
    assert provenance["upper_limit_compliance"] == "UNVERIFIED"
    assert "does not bound the start" in provenance["upper_limit_compliance_reason"]


def test_rebuild_wall_clock_lower_bound_matches_the_mtimes(tmp_path):
    raw = make_raw(tmp_path)
    _, provenance = an.rebuild_request_ledger(tmp_path, None, URLS)
    times = sorted((raw / n).stat().st_mtime
                   for n in ("base_no_company.html", "company_1.html"))
    assert provenance["wall_sec_lower_bound"] == pytest.approx(times[1] - times[0],
                                                               abs=1e-6)
    # The ledger reconstructs top-level requests only. Redirect occurrence is
    # unknown, so the per-hop attempt count and the remaining budget are not
    # derivable; asserting a remainder here would publish an unproven number.
    assert provenance["top_level_requests_reconstructed"] == 2
    assert provenance["hop_attempts_total"] == "UNVERIFIED"
    assert provenance["remaining_budget"] == "NOT_COMPUTABLE_TREATED_AS_ZERO"
    assert "attempts_unused" not in provenance


def test_rebuild_ledger_round_trips(tmp_path):
    raw = make_raw(tmp_path)
    ledger, _ = an.rebuild_request_ledger(tmp_path, None, URLS)
    path = tmp_path / "requests.jsonl"
    an.write_ledger(ledger, path)
    assert [json.loads(l)["label"] for l in path.read_text().splitlines()] \
        == [r["label"] for r in ledger]
