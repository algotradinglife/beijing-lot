from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts import publish_natural_day_segment_manifest as natural_publisher
from scripts import publish_exact_n_segment_freeze as exact_n_publisher
from scripts import live_artifact_refresh_loop as refresh_loop
from scripts import publish_segment_recovery as recovery_publisher
from scripts.verify_exact_n_freeze import (
    verify_directory as verify_exact_n_directory,
)
from scripts.verify_segment_recovery import verify
from src.decision_api import app as decision_app
from src.segment_recovery import (
    SegmentRecoveryError,
    exact_event_lock,
    load_published_recovery,
    publish_exact_terminal_record,
    recovery_exact_terminal_path,
    verify_exact_terminal_record,
)
from src.structured_input_receipt import write_receipt


def _database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE matches(
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            end_time TEXT NOT NULL,
            league TEXT,
            home TEXT,
            away TEXT,
            result_code TEXT,
            winning_sp REAL
        );
        CREATE TABLE segment_decision_windows(
            issue TEXT NOT NULL,
            segment_idx INTEGER NOT NULL,
            segment_start TEXT NOT NULL,
            segment_end TEXT NOT NULL,
            freeze_at TEXT NOT NULL,
            match_indices_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            manual_frozen_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(issue,segment_idx)
        );
        """
    )
    rows: list[tuple[str, int, str]] = []
    rows.extend(("26078", idx, "2026-07-24T18:20:00+08:00") for idx in (1, 2))
    rows.append(("26078", 3, "2026-07-24T23:20:00+08:00"))
    rows.extend(("26078", idx, "2026-07-24T23:50:00+08:00") for idx in (4, 5, 6))
    rows.extend(("26078", idx, "2026-07-25T00:50:00+08:00") for idx in (7, 8, 9))
    rows.extend(("26078", idx, "2026-07-25T01:20:00+08:00") for idx in (10, 11, 12))
    rows.extend(("26078", idx, "2026-07-25T02:05:00+08:00") for idx in (13, 14))
    for idx in range(15, 64):
        minutes = min((idx - 15) * 25, 21 * 60 + 30)
        kickoff = datetime.fromisoformat("2026-07-25T02:20:00+08:00") + timedelta(
            minutes=minutes
        )
        rows.append(("26078", idx, kickoff.isoformat(timespec="seconds")))
    conn.executemany(
        "INSERT INTO matches(issue,match_idx,end_time) VALUES(?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def _publish_parent(db: Path, root: Path) -> dict[str, object]:
    return natural_publisher.publish(
        issue="26078",
        db_path=db,
        output_root=root,
        now=datetime.fromisoformat("2026-07-24T17:00:00+08:00"),
    )


def test_real_time_recovery_excludes_exact_t25_boundary_and_is_idempotent(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    parent = _publish_parent(db, tmp_path / "natural")
    before = (
        sqlite3.connect(db)
        .execute(
            """
        SELECT segment_idx,match_indices_json,freeze_at
        FROM segment_decision_windows WHERE issue='26078'
        """
        )
        .fetchall()
    )

    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    assert result["status"] == "PUBLISHED_RECOVERY"
    assert result["included_match_count"] == 51
    assert result["excluded_match_count"] == 12
    assert result["freeze_at"].startswith("2026-07-25T01:40:00")
    package = Path(str(result["manifest"])).parent
    receipt = verify(package, db)
    assert receipt["status"] == "PASS"
    manifest = json.loads((package / "recovery_manifest.json").read_text())
    assert [row["match_idx"] for row in manifest["included"]] == list(range(13, 64))
    assert [row["match_idx"] for row in manifest["excluded"]] == list(range(1, 13))
    assert manifest["parent_status"] == "MISSED_FREEZE"
    assert manifest["parent_segment_manifest_sha256"] == parent["sha256"]

    second = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T20:30:00+08:00"),
    )
    assert second["idempotent"] is True
    assert second["sha256"] == result["sha256"]
    assert second["freeze_at"] == result["freeze_at"]
    assert second["included_match_count"] == 51
    after = (
        sqlite3.connect(db)
        .execute(
            """
        SELECT segment_idx,match_indices_json,freeze_at
        FROM segment_decision_windows WHERE issue='26078'
        """
        )
        .fetchall()
    )
    assert after == before


def test_fixture_just_before_boundary_includes_matches_7_through_63(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:24:59.999999+08:00"),
    )
    manifest = json.loads(Path(str(result["manifest"])).read_text())
    assert [row["match_idx"] for row in manifest["included"]] == list(range(7, 64))
    assert result["included_match_count"] == 57
    assert result["freeze_at"].startswith("2026-07-25T00:25:00")


def test_insufficient_remainder_is_terminal_and_has_no_operational_window(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T20:25:00+08:00"),
        hard_stop_at=datetime.fromisoformat("2026-07-25T20:25:00+08:00"),
    )
    assert result["status"] == "MISSED_RECOVERY_FREEZE"
    conn = sqlite3.connect(db)
    assert (
        conn.execute("SELECT COUNT(*) FROM segment_recovery_windows").fetchone()[0] == 0
    )
    published = load_published_recovery(conn, "26078", 1)
    conn.close()
    assert published is not None
    assert published["status"] == "MISSED_RECOVERY_FREEZE"


def test_clean_checkout_verifier_rejects_rehashed_time_ineligible_membership(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    package = Path(str(result["manifest"])).parent
    path = package / "recovery_manifest.json"
    manifest = json.loads(path.read_text())
    moved = manifest["excluded"].pop()
    moved.pop("reason")
    manifest["included"].insert(0, moved)
    manifest["included_match_count"] += 1
    manifest["excluded_match_count"] -= 1
    manifest["manifest_sha256"] = recovery_publisher.manifest_sha256(manifest)
    path.write_bytes(recovery_publisher.canonical(manifest) + b"\n")
    (package / "SHA256SUMS").write_text(
        f"{recovery_publisher._file_hash(path)}  recovery_manifest.json\n"
    )
    with pytest.raises(SegmentRecoveryError, match="time eligibility"):
        recovery_publisher.verify_directory(package)


def test_clean_checkout_verifier_rejects_rehashed_non_hkt_schedule_clock(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    package = Path(str(result["manifest"])).parent
    path = package / "recovery_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["included"][0]["kickoff_at_hkt"] = "2026-07-24T18:05:00+00:00"
    manifest["included"][0]["freeze_boundary_at_hkt"] = "2026-07-24T17:40:00+00:00"
    manifest["schedule_input_sha256"] = recovery_publisher.schedule_input_sha256(
        manifest
    )
    manifest["manifest_sha256"] = recovery_publisher.manifest_sha256(manifest)
    path.write_bytes(recovery_publisher.canonical(manifest) + b"\n")
    (package / "SHA256SUMS").write_text(
        f"{recovery_publisher._file_hash(path)}  recovery_manifest.json\n"
    )
    with pytest.raises(SegmentRecoveryError, match="normalized to HKT"):
        recovery_publisher.verify_directory(package)


def test_clean_checkout_verifier_rejects_rehashed_schedule_reordering(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    package = Path(str(result["manifest"])).parent
    path = package / "recovery_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["included"][0], manifest["included"][-1] = (
        manifest["included"][-1],
        manifest["included"][0],
    )
    manifest["schedule_input_sha256"] = recovery_publisher.schedule_input_sha256(
        manifest
    )
    manifest["manifest_sha256"] = recovery_publisher.manifest_sha256(manifest)
    path.write_bytes(recovery_publisher.canonical(manifest) + b"\n")
    (package / "SHA256SUMS").write_text(
        f"{recovery_publisher._file_hash(path)}  recovery_manifest.json\n"
    )
    with pytest.raises(SegmentRecoveryError, match="schedule ordered"):
        recovery_publisher.verify_directory(package)


def test_decision_api_exposes_parent_and_child_identity_without_fallback(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    conn = sqlite3.connect(db)
    payload = decision_app._exact_n_freeze_payload(
        conn,
        "26078",
        output_root=tmp_path / "exact-output",
        ledger_root=tmp_path / "exact-ledger",
    )
    conn.close()
    identities = {item["segment_identity"]: item for item in payload["segments"]}
    assert identities["segment_1"]["is_recovery"] is False
    assert identities["segment_1"]["status"] == "MISSED_FREEZE"
    child = identities["segment_1_recovery_1"]
    assert child["is_recovery"] is True
    assert child["parent_segment_idx"] == 1
    assert child["parent_status"] == "MISSED_FREEZE"
    assert child["match_count"] == 51
    assert child["status"] == "pending"
    assert child["alternatives"] == []
    assert payload["exact_n_frontend_selectable"] is False


def test_exact_n_manual_path_rejects_self_consistent_noncanonical_recovery(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    canonical = json.loads(Path(str(result["manifest"])).read_text())
    decoy = {**canonical, "attacker_note": "self-consistent but noncanonical"}
    decoy["manifest_sha256"] = recovery_publisher.manifest_sha256(decoy)
    with pytest.raises(
        SegmentRecoveryError, match="differs from canonical SQLite publication"
    ):
        exact_n_publisher.require_canonical_recovery_contract(
            db,
            issue="26078",
            parent_segment_idx=1,
            supplied_manifest=decoy,
        )


def test_db_bound_verifier_rejects_self_consistent_noncanonical_package(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    canonical_package = Path(str(result["manifest"])).parent
    decoy_package = tmp_path / "decoy"
    decoy_package.mkdir()
    decoy = json.loads((canonical_package / "recovery_manifest.json").read_text())
    decoy["evidence_note"] = "self-consistent but noncanonical"
    decoy["manifest_sha256"] = recovery_publisher.manifest_sha256(decoy)
    decoy_path = decoy_package / "recovery_manifest.json"
    decoy_path.write_bytes(recovery_publisher.canonical(decoy) + b"\n")
    (decoy_package / "SHA256SUMS").write_text(
        f"{recovery_publisher._file_hash(decoy_path)}  recovery_manifest.json\n"
    )

    with pytest.raises(
        SegmentRecoveryError,
        match="differs from canonical SQLite recovery",
    ):
        verify(decoy_package, db)


def test_failed_visible_publication_consumes_one_attempt_and_never_retries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    original_verify = recovery_publisher.verify_directory
    calls = 0

    def fail_visible(path: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SegmentRecoveryError("injected visible failure")
        return original_verify(path)

    monkeypatch.setattr(recovery_publisher, "verify_directory", fail_visible)
    with pytest.raises(SegmentRecoveryError, match="injected visible failure"):
        recovery_publisher.publish(
            issue="26078",
            parent_segment_idx=1,
            db_path=db,
            output_root=tmp_path / "recovery",
            exact_ledger_root=tmp_path / "exact-ledger",
            observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
        )
    attempt = json.loads(
        (tmp_path / "recovery/26078/segment_1_recovery_1/attempt.json").read_text()
    )
    assert attempt["state"] == "MISSED_RECOVERY_FREEZE"
    monkeypatch.setattr(recovery_publisher, "verify_directory", original_verify)
    with pytest.raises(SegmentRecoveryError, match="attempt already consumed"):
        recovery_publisher.publish(
            issue="26078",
            parent_segment_idx=1,
            db_path=db,
            output_root=tmp_path / "recovery",
            exact_ledger_root=tmp_path / "exact-ledger",
            observed_at=datetime.fromisoformat("2026-07-25T01:00:00+08:00"),
        )


def test_live_coordinator_targets_recovery_identity_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    structured = tmp_path / "structured.csv"
    structured.write_text("fixture\n", encoding="utf-8")
    write_receipt(
        structured,
        issue="26078",
        generated_at=datetime.fromisoformat("2026-07-25T01:31:00+08:00"),
        source={"test": True},
    )
    pending = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=structured,
        now=datetime.fromisoformat("2026-07-25T01:00:00+08:00"),
        output_root=tmp_path / "exact-output",
        ledger_root=tmp_path / "exact-ledger",
        correct_score_root=tmp_path / "score",
    )
    assert pending["status"] == "pending"
    assert pending["next_freeze_at"].startswith("2026-07-25T01:40:00")
    commands: list[list[str]] = []
    verification = {"status": "PASS", "cells": 15}
    monkeypatch.setattr(
        refresh_loop, "verify_exact_n_directory", lambda _path: verification
    )

    def run(command, **_kwargs):
        commands.append(command)
        event_key = hashlib.sha256(
            json.dumps(
                {
                    "issue": "26078",
                    "segment_identity": "segment_1_recovery_1",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        artifact = tmp_path / "exact-output/manifest.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}\n")
        ledger = tmp_path / "exact-ledger" / f"{event_key}.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            json.dumps(
                {
                    "state": "PUBLISHED",
                    "artifact_manifest": str(artifact),
                    "package_verification": verification,
                }
            )
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"event_key": event_key, "verification": verification}),
            stderr="",
        )

    monkeypatch.setattr(refresh_loop.subprocess, "run", run)
    result = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=structured,
        now=datetime.fromisoformat("2026-07-25T01:32:00+08:00"),
        output_root=tmp_path / "exact-output",
        ledger_root=tmp_path / "exact-ledger",
        correct_score_root=tmp_path / "score",
    )
    assert result["status"] == "published"
    assert result["segment_identity"] == "segment_1_recovery_1"
    command = commands[0]
    assert command[command.index("--recovery-manifest") + 1] == recovery["manifest"]
    assert "--manifest" not in command


def test_past_due_recovery_creates_durable_terminal_exact_n_receipt(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery_result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    recovery = json.loads(Path(str(recovery_result["manifest"])).read_text())
    ledger_root = tmp_path / "exact-ledger"
    event_key = exact_n_publisher.digest(
        {
            "issue": "26078",
            "segment_identity": "segment_1_recovery_1",
        }
    )
    prior_path = ledger_root / f"{event_key}.json"
    prior_path.parent.mkdir(parents=True, exist_ok=True)
    prior_path.write_text(
        json.dumps({"state": "RESERVED", "event_key": event_key}) + "\n",
        encoding="utf-8",
    )

    first = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=tmp_path / "missing-structured.csv",
        now=datetime.fromisoformat("2026-07-25T01:40:01+08:00"),
        output_root=tmp_path / "exact-output",
        ledger_root=ledger_root,
        correct_score_root=tmp_path / "score",
    )
    assert first["status"] == "MISSED_RECOVERY_FREEZE", first
    assert first["idempotent"] is False
    assert len(first["exact_n_cells"]) == 15
    terminal_path = recovery_exact_terminal_path(
        ledger_root, "26078", "segment_1_recovery_1"
    )
    terminal = json.loads(terminal_path.read_text())
    receipt_sha = verify_exact_terminal_record(
        terminal, recovery, ledger_root=ledger_root
    )
    assert receipt_sha == first["terminal_receipt_sha256"]
    assert terminal["prior_ledger_state"] == "RESERVED"
    assert (
        terminal["prior_ledger_sha256"]
        == hashlib.sha256(prior_path.read_bytes()).hexdigest()
    )

    second = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=tmp_path / "still-missing.csv",
        now=datetime.fromisoformat("2026-07-25T02:00:00+08:00"),
        output_root=tmp_path / "exact-output",
        ledger_root=ledger_root,
        correct_score_root=tmp_path / "score",
    )
    assert second["status"] == "MISSED_RECOVERY_FREEZE"
    assert second["idempotent"] is True
    assert second["terminal_receipt_sha256"] == receipt_sha

    conn = sqlite3.connect(db)
    api = decision_app._exact_n_freeze_payload(
        conn,
        "26078",
        output_root=tmp_path / "exact-output",
        ledger_root=ledger_root,
    )
    conn.close()
    child = next(
        segment
        for segment in api["segments"]
        if segment["segment_identity"] == "segment_1_recovery_1"
    )
    assert child["status"] == "MISSED_RECOVERY_FREEZE"
    assert child["terminal_receipt_sha256"] == receipt_sha
    assert len(child["exact_n_terminal_cells"]) == 15
    assert child["correct_score"]["status"] == "MISSED_RECOVERY_FREEZE"


def test_terminal_receipt_tamper_is_rejected_by_api(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    ledger_root = tmp_path / "exact-ledger"
    refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=tmp_path / "missing.csv",
        now=datetime.fromisoformat("2026-07-25T01:40:01+08:00"),
        ledger_root=ledger_root,
    )
    terminal_path = recovery_exact_terminal_path(
        ledger_root, "26078", "segment_1_recovery_1"
    )
    terminal = json.loads(terminal_path.read_text())
    terminal["exact_n_cells"].pop()
    terminal["terminal_receipt_sha256"] = hashlib.sha256(
        recovery_publisher.canonical(
            {
                key: value
                for key, value in terminal.items()
                if key != "terminal_receipt_sha256"
            }
        )
    ).hexdigest()
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    conn = sqlite3.connect(db)
    api = decision_app._exact_n_freeze_payload(conn, "26078", ledger_root=ledger_root)
    conn.close()
    child = next(
        segment
        for segment in api["segments"]
        if segment["segment_identity"] == "segment_1_recovery_1"
    )
    assert child["status"] == "invalid_terminal_event"


def test_exact_published_and_missed_choice_is_atomic_under_interleaving(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery_result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    recovery = json.loads(Path(str(recovery_result["manifest"])).read_text())
    ledger_root = tmp_path / "exact-ledger"
    event_key = exact_n_publisher.digest(
        {
            "issue": "26078",
            "segment_identity": "segment_1_recovery_1",
        }
    )
    ledger = ledger_root / f"{event_key}.json"
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "manifest.json").write_text("{}\n", encoding="utf-8")
    (stage / "SHA256SUMS").write_text("fixture\n", encoding="utf-8")
    destination = tmp_path / "visible"
    verification = {"status": "PASS", "cells": 15}
    monkeypatch.setattr(
        exact_n_publisher,
        "verify_exact_n_directory",
        lambda _path: dict(verification),
    )
    publisher_at_terminal_gate = threading.Event()
    release_publisher = threading.Event()
    terminal_started = threading.Event()
    publisher_errors: list[BaseException] = []
    terminal_errors: list[BaseException] = []

    def before_published() -> None:
        publisher_at_terminal_gate.set()
        assert release_publisher.wait(timeout=2)

    def publish_exact() -> None:
        try:
            with exact_event_lock(ledger_root, event_key):
                exact_n_publisher.promote_verified_package(
                    stage=stage,
                    destination=destination,
                    ledger=ledger,
                    ledger_payload={
                        "event_key": event_key,
                        "artifact_manifest": str(destination / "manifest.json"),
                    },
                    before_published=before_published,
                )
        except BaseException as exc:
            publisher_errors.append(exc)

    def publish_terminal() -> None:
        terminal_started.set()
        try:
            publish_exact_terminal_record(
                ledger_root,
                recovery,
                observed_at=datetime.fromisoformat("2026-07-25T01:40:01+08:00"),
            )
        except BaseException as exc:
            terminal_errors.append(exc)

    publisher_thread = threading.Thread(target=publish_exact)
    publisher_thread.start()
    assert publisher_at_terminal_gate.wait(timeout=2)
    terminal_thread = threading.Thread(target=publish_terminal)
    terminal_thread.start()
    assert terminal_started.wait(timeout=2)
    terminal_thread.join(timeout=0.05)
    assert terminal_thread.is_alive(), "terminal writer bypassed the event lock"
    assert terminal_errors == []
    release_publisher.set()
    publisher_thread.join(timeout=2)
    terminal_thread.join(timeout=2)

    assert not publisher_thread.is_alive()
    assert not terminal_thread.is_alive()
    assert publisher_errors == []
    assert len(terminal_errors) == 1
    assert isinstance(terminal_errors[0], SegmentRecoveryError)
    assert json.loads(ledger.read_text())["state"] == "PUBLISHED"
    assert not recovery_exact_terminal_path(
        ledger_root, "26078", "segment_1_recovery_1"
    ).exists()


def test_deadline_loss_aborts_published_then_terminal_owns_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery_result = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    recovery = json.loads(Path(str(recovery_result["manifest"])).read_text())
    ledger_root = tmp_path / "exact-ledger"
    event_key = exact_n_publisher.digest(
        {
            "issue": "26078",
            "segment_identity": "segment_1_recovery_1",
        }
    )
    ledger = ledger_root / f"{event_key}.json"
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "manifest.json").write_text("{}\n", encoding="utf-8")
    (stage / "SHA256SUMS").write_text("fixture\n", encoding="utf-8")
    verification = {"status": "PASS", "cells": 15}
    monkeypatch.setattr(
        exact_n_publisher,
        "verify_exact_n_directory",
        lambda _path: dict(verification),
    )

    with pytest.raises(RuntimeError, match="lost terminal ownership"):
        with exact_event_lock(ledger_root, event_key):
            exact_n_publisher.promote_verified_package(
                stage=stage,
                destination=tmp_path / "visible",
                ledger=ledger,
                ledger_payload={
                    "event_key": event_key,
                    "artifact_manifest": str(tmp_path / "visible/manifest.json"),
                },
                before_published=lambda: (_ for _ in ()).throw(
                    ValueError("freeze deadline elapsed")
                ),
            )
    assert json.loads(ledger.read_text())["state"] == "PUBLICATION_ABORTED"
    terminal, idempotent = publish_exact_terminal_record(
        ledger_root,
        recovery,
        observed_at=datetime.fromisoformat("2026-07-25T01:40:01+08:00"),
    )
    assert idempotent is False
    assert terminal["state"] == "MISSED_RECOVERY_FREEZE"
    assert terminal["prior_ledger_state"] == "PUBLICATION_ABORTED"


def test_recovery_child_publishes_and_verifies_full_exact_n_package(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    _publish_parent(db, tmp_path / "natural")
    recovery = recovery_publisher.publish(
        issue="26078",
        parent_segment_idx=1,
        db_path=db,
        output_root=tmp_path / "recovery",
        exact_ledger_root=tmp_path / "exact-ledger",
        observed_at=datetime.fromisoformat("2026-07-25T00:55:15+08:00"),
    )
    # The existing replay loader consumes the repository's normalized naive-HKT
    # DB representation; recovery already froze the equivalent offset clocks.
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE matches SET end_time=substr(end_time,1,19) WHERE issue='26078'"
    )
    conn.commit()
    conn.close()

    structured = tmp_path / "structured.csv"
    fieldnames = [
        "issue",
        "match_idx",
        "match_id",
        "active_selection_codes",
        "shadow_selection_codes",
        "p_3",
        "p_1",
        "p_0",
        "sp_3",
        "sp_1",
        "sp_0",
    ]
    with structured.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for match_idx in range(1, 64):
            writer.writerow(
                {
                    "issue": "26078",
                    "match_idx": match_idx,
                    "match_id": f"26078_{match_idx:03d}",
                    "active_selection_codes": "3",
                    "shadow_selection_codes": "3",
                    "p_3": "0.80",
                    "p_1": "0.10",
                    "p_0": "0.10",
                    "sp_3": "2.00",
                    "sp_1": "3.50",
                    "sp_0": "4.00",
                }
            )
    write_receipt(
        structured,
        issue="26078",
        generated_at=datetime.fromisoformat("2026-07-25T01:31:00+08:00"),
        source={"test": "recovery-full-publisher"},
    )
    decision_at = datetime.fromisoformat("2026-07-25T01:32:00+08:00")
    monkeypatch.setattr(
        exact_n_publisher,
        "require_pre_freeze_wall_clock",
        lambda _scheduled: decision_at,
    )
    output_root = tmp_path / "exact-output"
    ledger_root = tmp_path / "exact-ledger"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish_exact_n_segment_freeze.py",
            "--issue",
            "26078",
            "--segment",
            "1",
            "--recovery-manifest",
            str(recovery["manifest"]),
            "--structured-csv",
            str(structured),
            "--db",
            str(db),
            "--output-root",
            str(output_root),
            "--ledger-root",
            str(ledger_root),
            "--correct-score-root",
            str(tmp_path / "score"),
            "--sample-attempts",
            "50",
        ],
    )
    exact_n_publisher.main()
    receipt = json.loads(capsys.readouterr().out)
    package = Path(receipt["destination"])
    verification = verify_exact_n_directory(package)
    assert verification["status"] == "PASS"
    assert verification["cells"] == 15
    manifest = json.loads((package / "manifest.json").read_text())
    assert manifest["segment_identity"] == "segment_1_recovery_1"
    assert manifest["recovery_manifest_sha256"] == recovery["sha256"]
    assert manifest["segment_match_indices"] == list(range(13, 64))
    ledger = json.loads(Path(receipt["ledger"]).read_text())
    assert ledger["state"] == "PUBLISHED"
    assert ledger["package_verification"] == verification
    conn = sqlite3.connect(db)
    api = decision_app._exact_n_freeze_payload(
        conn,
        "26078",
        output_root=output_root,
        ledger_root=ledger_root,
    )
    conn.close()
    api_segments = {segment["segment_identity"]: segment for segment in api["segments"]}
    assert api_segments["segment_1"]["status"] == "MISSED_FREEZE"
    assert api_segments["segment_1_recovery_1"]["status"] == "published"
    assert len(api_segments["segment_1_recovery_1"]["alternatives"]) == 15
