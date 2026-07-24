from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import scrape_500_bjdc as scraper  # noqa: E402
from src import multimarket_p0 as p0  # noqa: E402


def market_xml(playid: int, *, winner_only: str | None = None, winner_sp: float = 5.25) -> bytes:
    _, outcomes = scraper.MARKET_OUTCOMES[playid]
    attributes = []
    for index, (code, _label, attribute) in enumerate(outcomes):
        value = winner_sp if winner_only == code else "" if winner_only else 2.25 + index
        attributes.append(f'{attribute}="{value}"')
    return (
        '<root updatetime="2026-07-16 20:00:00">'
        f'<w1 {" ".join(attributes)} h="主队" a="客队" gn="测试联赛" r="0" st="" />'
        "</root>"
    ).encode("gb18030")


def make_db(path: Path, *, cutoff: str = "2026-07-17 06:50", disabled: str = "no") -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    scraper.create_schema(connection)
    connection.execute(
        """
        INSERT INTO matches(
            issue,match_idx,home,away,end_time,schedule_date,disabled,score,fetched_at
        ) VALUES('P0X',1,'主队','客队',?,'2026-07-17',?,'','2026-07-16 10:00:00')
        """,
        (cutoff, disabled),
    )
    connection.execute(
        """
        CREATE TABLE nowscore_bjdc_matches(
            issue TEXT,match_idx INTEGER,kickoff_time TEXT,score TEXT,
            status_text TEXT,status TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO nowscore_bjdc_matches VALUES('P0X',1,'07:00','','','scheduled')"
    )
    connection.execute(
        "CREATE TABLE segment_decision_windows(issue TEXT,segment_idx INTEGER,freeze_at TEXT,manual_frozen_at TEXT,match_indices_json TEXT)"
    )
    connection.commit()
    return connection


def capture(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    playid: int,
    payload: bytes,
    *,
    fetched_at: str = "2026-07-16 12:00:00",
) -> int:
    monkeypatch.setattr(
        scraper,
        "fetch_url",
        lambda *args, **kwargs: scraper.FetchResult(
            url=f"https://example.test/{playid}.xml",
            status=200,
            body=payload,
            elapsed_sec=0.1,
        ),
    )
    monkeypatch.setattr(scraper, "now_utc", lambda: fetched_at)
    args = argparse.Namespace(
        playid=playid,
        timeout=10,
        user_agent="test",
        keep_going=False,
        capture_root=tmp_path / "captures",
    )
    return scraper.scrape_live_sp(connection, "P0X", args)


def test_append_only_capture_bundle_is_hashed_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = make_db(tmp_path / "db.sqlite")
    payload = market_xml(40)

    assert capture(connection, monkeypatch, tmp_path, 40, payload) == 1
    assert capture(connection, monkeypatch, tmp_path, 40, payload) == 1
    batches = connection.execute("SELECT * FROM market_sp_capture_batches").fetchall()
    assert len(batches) == 1
    assert connection.execute("SELECT COUNT(*) FROM live_market_sp_snapshots").fetchone()[0] == 8
    bundle = Path(batches[0]["bundle_path"])
    assert p0.verify_bundle(bundle)["raw.xml"] == p0.sha256_bytes(payload)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete_forward_open_rows"] == 1
    assert manifest["classification_summary"] == {"forward_complete_open": 8}
    row = connection.execute(
        "SELECT match_id,sale_status,sale_cutoff_hkt,capture_classification,parlay_allowed "
        "FROM live_market_sp_snapshots LIMIT 1"
    ).fetchone()
    assert tuple(row) == (
        "P0X_001",
        "open",
        "2026-07-17T06:50:00+08:00",
        "forward_complete_open",
        "unknown",
    )
    connection.close()


def test_10h_freeze_links_valid_dual_clock_batches_and_rejects_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "db.sqlite")
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))

    result = p0.freeze_10h(connection, "P0X", tmp_path / "freeze")
    assert result["frozen_match_markets"] == 2
    assert result["frozen_outcome_rows"] == 33
    with (tmp_path / "freeze/frozen_outcomes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["sale_status"] for row in rows} == {"open"}
    assert len({row["batch_id"] for row in rows}) == 2
    assert p0.verify_freeze(tmp_path / "freeze")["status"] == "valid"
    with (tmp_path / "freeze/frozen_outcomes.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")
    with pytest.raises(p0.MultimarketP0Error, match="checksum mismatch"):
        p0.verify_freeze(tmp_path / "freeze")

    tampered_connection = make_db(tmp_path / "tampered.sqlite")
    capture(tampered_connection, monkeypatch, tmp_path / "tampered", 40, market_xml(40))
    batch = tampered_connection.execute("SELECT bundle_path FROM market_sp_capture_batches").fetchone()
    with (Path(batch[0]) / "raw.xml").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(p0.MultimarketP0Error, match="checksum mismatch"):
        p0.freeze_10h(tampered_connection, "P0X", tmp_path / "bad-freeze", playids=(40,))
    connection.close()
    tampered_connection.close()


def test_capture_database_rows_rollback_together(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = make_db(tmp_path / "db.sqlite")
    connection.execute(
        """
        CREATE TRIGGER reject_market_rows BEFORE INSERT ON live_market_sp_snapshots
        BEGIN SELECT RAISE(ABORT, 'forced detail failure'); END
        """
    )
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError, match="forced detail failure"):
        capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    assert connection.execute("SELECT COUNT(*) FROM market_sp_capture_batches").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM live_market_sp_snapshots").fetchone()[0] == 0
    connection.close()


def test_terminal_backfill_and_closed_capture_cannot_enter_10h(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminal = make_db(tmp_path / "terminal.sqlite", cutoff="2026-07-16 19:00", disabled="yes")
    capture(terminal, monkeypatch, tmp_path / "terminal", 40, market_xml(40, winner_only="3"))
    row = terminal.execute(
        "SELECT capture_classification,sale_status FROM live_market_sp_snapshots LIMIT 1"
    ).fetchone()
    assert tuple(row) == ("terminal_backfill_exploratory_only", "closed")
    with pytest.raises(p0.MultimarketP0Error, match="no valid 10h"):
        p0.freeze_10h(terminal, "P0X", tmp_path / "terminal-freeze", playids=(40,))
    terminal.close()


def test_segment_freeze_is_recursive_hashed_idempotent_and_rejects_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "db.sqlite")
    connection.execute(
        "INSERT INTO segment_decision_windows VALUES('P0X',1,'2026-07-16T21:00:00+08:00',NULL,'[1]')"
    )
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))

    result = p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment")
    package = Path(result["output_dir"])
    assert result["status"] == "valid"
    assert result["frozen_match_markets"] == 2
    assert result["paired_overlap_matches"] == 1
    repeated = p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment")
    assert repeated["event_id"] == result["event_id"]
    assert repeated["idempotent"] is True
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["non_execution_flags"] == {
        "execution_enabled": False, "frontend_selectable": False, "roi_authorized": False,
    }
    raw = next((package / "inputs/raw_batches").glob("*/raw.xml"))
    with raw.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(p0.MultimarketP0Error, match="checksum mismatch"):
        p0.verify_segment_freeze(package)
    connection.close()


def test_segment_freeze_skips_late_candidate_and_rejects_closed_sale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "db.sqlite")
    connection.execute(
        "INSERT INTO segment_decision_windows VALUES('P0X',1,'2026-07-16T21:00:00+08:00',NULL,'[1]')"
    )
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))
    # A newer otherwise-valid batch is after the shared absolute decision time.
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40, winner_sp=3.5), fetched_at="2026-07-16 14:00:00")
    result = p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment")
    package = Path(result["output_dir"])
    skipped = list(csv.DictReader((package / "skipped_candidates.csv").open(encoding="utf-8", newline="")))
    assert any(row["reason"] == "post_freeze_clock" for row in skipped)
    frozen = list(csv.DictReader((package / "frozen_outcomes.csv").open(encoding="utf-8", newline="")))
    assert {row["batch_id"] for row in frozen if row["playid"] == "40"} != {skipped[0]["batch_id"]}
    connection.close()


def test_segment_freeze_is_strict_recursive_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "segment.sqlite")
    connection.execute("INSERT INTO segment_decision_windows VALUES('P0X',7,'2026-07-16 21:00:00',NULL,'[1]')")
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))

    result = p0.freeze_segment(connection, "P0X", 7, tmp_path / "segment-freezes")
    assert result["frozen_match_markets"] == 2
    assert result["frozen_outcome_rows"] == 33
    assert result["paired_overlap_matches"] == 1
    package = Path(result["output_dir"])
    assert p0.verify_segment_freeze(package)["status"] == "valid"
    repeated = p0.freeze_segment(connection, "P0X", 7, tmp_path / "segment-freezes")
    assert repeated["event_id"] == result["event_id"]
    raw = next((package / "inputs/raw_batches").glob("*/raw.xml"))
    with raw.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(p0.MultimarketP0Error, match="checksum mismatch"):
        p0.verify_segment_freeze(package)
    connection.close()


def test_segment_freeze_skips_post_freeze_candidate_for_earlier_valid_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "segment-late.sqlite")
    connection.execute("INSERT INTO segment_decision_windows VALUES('P0X',1,'2026-07-16 21:00:00',NULL,'[1]')")
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))
    # A newer post-freeze p40 candidate is deliberately ineligible.
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40), fetched_at="2026-07-16 14:00:00")
    result = p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment-freezes")
    assert result["frozen_match_markets"] == 2
    skipped = list(csv.DictReader((Path(result["output_dir"]) / "skipped_candidates.csv").open(encoding="utf-8")))
    assert any(row["reason"] == "post_freeze_clock" for row in skipped)
    connection.close()


def test_segment_freeze_verifier_rejects_unlisted_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "segment-verify.sqlite")
    connection.execute("INSERT INTO segment_decision_windows VALUES('P0X',1,'2026-07-16 21:00:00',NULL,'[1]')")
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))
    package = Path(p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment-freezes")["output_dir"])
    (package / "unexpected.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(p0.MultimarketP0Error, match="cover exactly"):
        p0.verify_segment_freeze(package)
    connection.close()


def test_segment_verifier_rejects_semantic_tampering_after_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = make_db(tmp_path / "semantic.sqlite")
    connection.execute("INSERT INTO segment_decision_windows VALUES('P0X',1,'2026-07-16 21:00:00',NULL,'[1]')")
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42))
    package = Path(p0.freeze_segment(connection, "P0X", 1, tmp_path / "segment-freezes")["output_dir"])

    wrong_codes = tmp_path / "wrong-codes" / package.name
    shutil.copytree(package, wrong_codes)
    rows = list(csv.DictReader((wrong_codes / "frozen_outcomes.csv").open(encoding="utf-8", newline="")))
    next(row for row in rows if row["playid"] == "40")["outcome_code"] = "wrong-but-eight"
    with (wrong_codes / "frozen_outcomes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    p0._write_recursive_sums(wrong_codes)
    with pytest.raises(p0.MultimarketP0Error, match="raw batch SP mismatch"):
        p0.verify_segment_freeze(wrong_codes)

    bad_manifest = tmp_path / "bad-manifest" / package.name
    shutil.copytree(package, bad_manifest)
    manifest = json.loads((bad_manifest / "manifest.json").read_text(encoding="utf-8"))
    manifest["event_id"] = "0" * 64
    (bad_manifest / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    p0._write_recursive_sums(bad_manifest)
    with pytest.raises(p0.MultimarketP0Error, match="event identity"):
        p0.verify_segment_freeze(bad_manifest)

    bad_overlap = tmp_path / "bad-overlap" / package.name
    shutil.copytree(package, bad_overlap)
    overlap = list(csv.DictReader((bad_overlap / "paired_overlap.csv").open(encoding="utf-8", newline="")))
    overlap[0]["p40_batch_id"] = "0" * 64
    with (bad_overlap / "paired_overlap.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=overlap[0].keys(), lineterminator="\n")
        writer.writeheader(); writer.writerows(overlap)
    p0._write_recursive_sums(bad_overlap)
    with pytest.raises(p0.MultimarketP0Error, match="paired overlap"):
        p0.verify_segment_freeze(bad_overlap)

    malformed_overlap = tmp_path / "malformed-overlap" / package.name
    shutil.copytree(package, malformed_overlap)
    overlap = list(csv.DictReader((malformed_overlap / "paired_overlap.csv").open(encoding="utf-8", newline="")))
    extra = dict(overlap[0]); extra["issue"] = "WRONG"
    overlap.append(extra)
    with (malformed_overlap / "paired_overlap.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=overlap[0].keys(), lineterminator="\n")
        writer.writeheader(); writer.writerows(overlap)
    manifest = json.loads((malformed_overlap / "manifest.json").read_text())
    manifest["paired_overlap_matches"] = 2
    (malformed_overlap / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    p0._write_recursive_sums(malformed_overlap)
    with pytest.raises(p0.MultimarketP0Error, match="row identity"):
        p0.verify_segment_freeze(malformed_overlap)

    duplicate_overlap = tmp_path / "duplicate-overlap" / package.name
    shutil.copytree(package, duplicate_overlap)
    overlap = list(csv.DictReader((duplicate_overlap / "paired_overlap.csv").open(encoding="utf-8", newline="")))
    overlap.append(dict(overlap[0]))
    with (duplicate_overlap / "paired_overlap.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=overlap[0].keys(), lineterminator="\n")
        writer.writeheader(); writer.writerows(overlap)
    manifest = json.loads((duplicate_overlap / "manifest.json").read_text())
    manifest["paired_overlap_matches"] = 2
    (duplicate_overlap / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    p0._write_recursive_sums(duplicate_overlap)
    with pytest.raises(p0.MultimarketP0Error, match="duplicate"):
        p0.verify_segment_freeze(duplicate_overlap)

    bad_sp = tmp_path / "bad-sp" / package.name
    shutil.copytree(package, bad_sp)
    rows = list(csv.DictReader((bad_sp / "frozen_outcomes.csv").open(encoding="utf-8", newline="")))
    rows[0]["sp"] = "99.0"
    with (bad_sp / "frozen_outcomes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    p0._write_recursive_sums(bad_sp)
    with pytest.raises(p0.MultimarketP0Error, match="SP mismatch"):
        p0.verify_segment_freeze(bad_sp)

    bad_match = tmp_path / "bad-match" / package.name
    shutil.copytree(package, bad_match)
    rows = list(csv.DictReader((bad_match / "frozen_outcomes.csv").open(encoding="utf-8", newline="")))
    rows[0]["match_idx"] = "999"; rows[0]["match_id"] = "P0X_999"
    with (bad_match / "frozen_outcomes.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    p0._write_recursive_sums(bad_match)
    with pytest.raises(p0.MultimarketP0Error, match="manifest mapping"):
        p0.verify_segment_freeze(bad_match)
    connection.close()


def test_prospective_g5_requires_both_preregistered_events() -> None:
    assert not p0.prospective_segment_g5_ready(["event-1"], ["event-1"])
    assert not p0.prospective_segment_g5_ready(["event-1", "event-2"], ["event-1"])
    assert p0.prospective_segment_g5_ready(["event-1", "event-2"], ["event-2", "event-1"])
    assert not p0.prospective_segment_event_ready({"status": "valid", "paired_overlap_matches": 0})
    assert p0.prospective_segment_event_ready({"status": "valid", "paired_overlap_matches": 1})


def test_settlement_truth_maps_total_score_other_and_sp1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    connection = make_db(tmp_path / "db.sqlite", cutoff="2026-07-16 19:00", disabled="yes")
    connection.execute("UPDATE matches SET score='5:4' WHERE issue='P0X'")
    connection.execute(
        "UPDATE nowscore_bjdc_matches SET score='5-4',status_text='完场',status='finished' WHERE issue='P0X'"
    )
    connection.commit()
    capture(connection, monkeypatch, tmp_path, 40, market_xml(40, winner_only="7+", winner_sp=1.0))
    capture(connection, monkeypatch, tmp_path, 42, market_xml(42, winner_only="home_other", winner_sp=42.0))

    result = p0.build_settlement_truth(connection, "P0X")
    assert result["status_counts"] == {"void_sp1": 1, "settled": 1}
    rows = {
        row["market_key"]: row
        for row in connection.execute("SELECT * FROM multimarket_settlement_truth")
    }
    assert (rows["total_goals"]["fthg"], rows["total_goals"]["ftag"]) == (5, 4)
    assert rows["total_goals"]["outcome_code"] == "7+"
    assert rows["total_goals"]["settlement_status"] == "void_sp1"
    assert json.loads(rows["total_goals"]["special_flags_json"]) == ["sp1_void"]
    assert rows["total_goals"]["winning_sp_source"] == "terminal_backfill_exploratory_only"
    assert rows["correct_score"]["outcome_code"] == "home_other"
    assert rows["correct_score"]["winning_sp"] == 42.0
    assert rows["correct_score"]["source_batch_id"]
    connection.close()
