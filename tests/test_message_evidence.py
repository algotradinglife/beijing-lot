from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import jsonschema
import pytest

from src.message_evidence import (
    MAX_RAW_CAPTURE_BYTES,
    MessageEvidenceError,
    MessageEvidenceLedger,
    normalize_timestamp,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCHEMA = ROOT / "schemas/message_evidence_asof_v1.schema.json"
COVERAGE_SCHEMA = ROOT / "schemas/message_evidence_coverage_v1.schema.json"


class AutoClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(microseconds=1)
        return value


def _base_ledger(
    tmp_path: Path,
    *,
    clock: Callable[[], datetime] | None = None,
) -> MessageEvidenceLedger:
    active_clock = clock or AutoClock(datetime(2026, 8, 4, tzinfo=timezone.utc))
    ledger = MessageEvidenceLedger(
        tmp_path / "message-evidence.sqlite",
        clock=active_clock,
    )
    ledger.initialize()
    ledger.register_source(
        source_id="club.home",
        name="Home FC",
        source_type="official_club",
        provenance_tier="TIER_0_OFFICIAL",
        registered_at="2026-08-04T00:00:00+08:00",
        base_url="https://home.example/",
    )
    ledger.register_source(
        source_id="news.primary",
        name="Primary Reporter",
        source_type="primary_reporter",
        provenance_tier="TIER_1_PRIMARY",
        registered_at="2026-08-04T00:00:00+08:00",
    )
    for entity_id, entity_type, name in (
        ("team.home", "team", "Home FC"),
        ("team.away", "team", "Away FC"),
        ("player.home.9", "player", "Home Player 9"),
        ("competition.alpha", "competition", "Alpha League"),
    ):
        ledger.register_entity(
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=name,
            registered_at="2026-08-04T00:00:00+08:00",
        )
    ledger.register_match(
        issue="26081",
        match_idx=1,
        match_id="alpha-20260804-home-away",
        kickoff_at="2026-08-04T20:00:00+08:00",
        home_team_id="team.home",
        away_team_id="team.away",
        competition_id="competition.alpha",
        registered_at="2026-08-04T00:00:00+08:00",
    )
    return ledger


def _validate(payload: object, schema_path: Path) -> None:
    validator = jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    )
    validator.validate(payload)


def _capture(
    ledger: MessageEvidenceLedger,
    minute: int,
    payload: bytes,
    *,
    source_id: str = "club.home",
    published_minute: int | None = None,
) -> str:
    published = published_minute if published_minute is not None else minute
    return ledger.append_capture(
        source_id=source_id,
        source_url=f"https://home.example/reports/{minute}",
        raw_bytes=payload,
        published_at=f"2026-08-04T10:{published:02d}:00+08:00",
        observed_at=f"2026-08-04T10:{minute:02d}:00+08:00",
        fetched_at=f"2026-08-04T10:{minute:02d}:01+08:00",
        media_type="text/html",
    )


def _populate_replay(ledger: MessageEvidenceLedger) -> dict[str, str]:
    ledger.register_alias(
        entity_id="player.home.9",
        source_id="club.home",
        alias_text="Player Nine",
        observed_at="2026-08-04T10:00:00+08:00",
    )
    first_capture = _capture(ledger, 1, b"first replay report")
    first_fact = ledger.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={
            "status": "doubtful",
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    second_capture = _capture(ledger, 2, b"corrected replay report")
    second_fact = ledger.append_fact(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={
            "status": "available",
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    relation = ledger.append_relation(
        source_fact_id=second_fact,
        target_fact_id=first_fact,
        relation_type="corrects",
    )
    missing_capture = _capture(ledger, 3, b"lineup absent")
    missing = ledger.append_missingness(
        capture_id=missing_capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        reason_code="not_published",
    )
    observation = ledger.append_collection_observation(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        fact_kind="injury",
        status="complete",
        expected_entity_ids=["team.home", "team.away", "player.home.9"],
        checked_source_ids=["club.home"],
    )
    return {
        "first_capture": first_capture,
        "first_fact": first_fact,
        "second_capture": second_capture,
        "second_fact": second_fact,
        "relation": relation,
        "missing": missing,
        "observation": observation,
    }


def test_as_of_export_excludes_later_facts_relations_and_aliases(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    ledger.register_alias(
        entity_id="player.home.9",
        source_id="club.home",
        alias_text="P9",
        observed_at="2026-08-04T10:00:00+08:00",
    )
    ledger.register_alias(
        entity_id="player.home.9",
        source_id="news.primary",
        alias_text="Future nickname",
        observed_at="2026-08-04T10:20:00+08:00",
    )
    first_capture = _capture(ledger, 1, b"player doubtful")
    first_fact = ledger.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "doubtful"},
    )
    corrected_capture = _capture(ledger, 10, b"player cleared")
    corrected_fact = ledger.append_fact(
        capture_id=corrected_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "available"},
    )
    ledger.append_relation(
        source_fact_id=corrected_fact,
        target_fact_id=first_fact,
        relation_type="corrects",
        note="official correction",
    )

    before = ledger.export_as_of(cutoff="2026-08-04T10:05:00+08:00", issue="26081")
    assert [row["fact_id"] for row in before["facts"]] == [first_fact]
    assert before["facts"][0]["active"] is True
    assert before["relations"] == []
    assert [row["alias_text"] for row in before["entity_aliases"]] == ["P9"]

    after = ledger.export_as_of(cutoff="2026-08-04T10:30:00+08:00", issue="26081")
    by_id = {row["fact_id"]: row for row in after["facts"]}
    assert by_id[first_fact]["active"] is False
    assert by_id[corrected_fact]["active"] is True
    assert len(after["relations"]) == 1
    assert {row["alias_text"] for row in after["entity_aliases"]} == {
        "P9",
        "Future nickname",
    }
    assert after == ledger.export_as_of(
        cutoff="2026-08-04T10:30:00+08:00", issue="26081"
    )
    _validate(after, EXPORT_SCHEMA)


def test_append_only_raw_capture_and_timestamp_guards(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    capture_id = ledger.append_capture(
        source_id="club.home",
        source_url="https://home.example/late",
        raw_bytes=b"late report",
        published_at="2026-08-04T08:00:00+08:00",
        observed_at="2026-08-04T10:00:00+08:00",
        fetched_at="2026-08-04T10:00:01+08:00",
        media_type="text/plain",
    )
    ledger.append_missingness(
        capture_id=capture_id,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        reason_code="not_published",
    )
    exported = ledger.export_as_of(cutoff="2026-08-04T11:00:00+08:00", issue="26081")
    assert exported["captures"][0]["late_arriving"] is True
    assert (
        exported["captures"][0]["raw_sha256"]
        == hashlib.sha256(b"late report").hexdigest()
    )

    conn = sqlite3.connect(ledger.database)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "UPDATE raw_captures SET raw_bytes=? WHERE capture_id=?",
            (b"tampered", capture_id),
        )
    conn.close()

    with pytest.raises(MessageEvidenceError, match="timezone"):
        ledger.append_capture(
            source_id="club.home",
            source_url="https://home.example/no-zone",
            raw_bytes=b"x",
            observed_at="2026-08-04T10:00:00",
            fetched_at="2026-08-04T10:00:01+08:00",
        )
    with pytest.raises(MessageEvidenceError, match="published_at cannot be after"):
        ledger.append_capture(
            source_id="club.home",
            source_url="https://home.example/future",
            raw_bytes=b"x",
            published_at="2026-08-04T10:01:00+08:00",
            observed_at="2026-08-04T10:00:00+08:00",
            fetched_at="2026-08-04T10:00:01+08:00",
        )


def test_coverage_recovers_after_missingness_and_flags_active_conflict(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    missing_capture = _capture(ledger, 1, b"lineup not published")
    ledger.append_missingness(
        capture_id=missing_capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        reason_code="not_published",
    )
    before = ledger.coverage_report(
        cutoff="2026-08-04T10:05:00+08:00",
        issue="26081",
        required_fact_kinds=["confirmed_lineup"],
        max_age_seconds=3600,
    )
    assert before["matches"][0]["decision_chain_eligible"] is False
    assert before["matches"][0]["explicit_missing_fact_kinds"] == ["confirmed_lineup"]

    lineup_capture = _capture(ledger, 10, b"confirmed XI")
    ledger.append_fact(
        capture_id=lineup_capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        value={
            "coverage_entity_ids": ["team.home", "team.away"],
            "teams": {"team.home": ["player.home.9"], "team.away": []},
        },
    )
    ledger.append_collection_observation(
        capture_id=lineup_capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    recovered = ledger.coverage_report(
        cutoff="2026-08-04T10:15:00+08:00",
        issue="26081",
        required_fact_kinds=["confirmed_lineup"],
        max_age_seconds=3600,
    )
    assert recovered["matches"][0]["decision_chain_eligible"] is True
    assert recovered["matches"][0]["explicit_missing_fact_kinds"] == []
    assert recovered["issues"]["26081"]["eligible_rate"] == 1.0
    _validate(recovered, COVERAGE_SCHEMA)

    first_capture = _capture(ledger, 20, b"player suspended")
    first = ledger.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="suspension",
        value={
            "status": "suspended",
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    second_capture = _capture(
        ledger, 21, b"player not suspended", source_id="news.primary"
    )
    second = ledger.append_fact(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="suspension",
        assertion_state="denied",
        value={
            "status": "available",
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    ledger.append_relation(
        source_fact_id=second,
        target_fact_id=first,
        relation_type="contradicts",
    )
    ledger.append_collection_observation(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        fact_kind="suspension",
        status="complete",
        expected_entity_ids=["team.home", "team.away", "player.home.9"],
        checked_source_ids=["news.primary"],
    )
    conflict = ledger.coverage_report(
        cutoff="2026-08-04T10:25:00+08:00",
        issue="26081",
        required_fact_kinds=["suspension"],
        max_age_seconds=3600,
    )
    assert conflict["matches"][0]["decision_chain_eligible"] is False
    assert conflict["matches"][0]["unresolved_conflict_fact_ids"] == sorted(
        [first, second]
    )


def test_cli_initializes_and_writes_empty_schema_valid_export(tmp_path: Path) -> None:
    database = tmp_path / "cli.sqlite"
    output = tmp_path / "export.json"
    script = ROOT / "scripts/manage_message_evidence.py"
    init = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(database),
            "init",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr
    export = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(database),
            "export",
            "--cutoff",
            "2026-08-04T00:00:00Z",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert export.returncode == 0, export.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["counts"]["facts"] == 0
    _validate(payload, EXPORT_SCHEMA)


def test_system_receipt_time_prevents_retroactive_as_of_backfill(
    tmp_path: Path,
) -> None:
    clock = AutoClock(datetime(2026, 8, 4, tzinfo=timezone.utc))
    ledger = _base_ledger(tmp_path, clock=clock)
    clock.current = datetime(2026, 8, 4, 3, tzinfo=timezone.utc)
    capture = _capture(ledger, 1, b"backdated supplied timestamps")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "doubtful"},
    )

    earlier = ledger.export_as_of(cutoff="2026-08-04T10:30:00+08:00", issue="26081")
    assert earlier["facts"] == []
    later = ledger.export_as_of(cutoff="2026-08-04T11:01:00+08:00", issue="26081")
    assert len(later["facts"]) == 1
    assert later["facts"][0]["recorded_at_utc"] == "2026-08-04T03:00:00.000001Z"


def test_ledger_rejects_a_regressed_system_clock_after_reopen(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    regressed = MessageEvidenceLedger(
        ledger.database,
        clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(MessageEvidenceError, match="clock regressed"):
        regressed.register_entity(
            entity_id="team.too-late",
            entity_type="team",
            canonical_name="Too Late FC",
            registered_at="2026-08-04T00:00:00+08:00",
        )


def test_as_of_export_serializes_with_an_inflight_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"concurrent append")
    insert_reached = threading.Event()
    release_insert = threading.Event()
    export_done = threading.Event()
    failures: list[BaseException] = []
    original_insert = ledger._insert_idempotent

    def blocked_insert(*args: object, **kwargs: object) -> str:
        if kwargs.get("table") == "evidence_facts":
            insert_reached.set()
            if not release_insert.wait(timeout=5):
                raise AssertionError("timed out waiting to release fact insert")
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(ledger, "_insert_idempotent", blocked_insert)

    def append_worker() -> None:
        try:
            ledger.append_fact(
                capture_id=capture,
                issue="26081",
                match_idx=1,
                fact_kind="travel",
                value={"coverage_entity_ids": ["team.home", "team.away"]},
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    exported: list[dict[str, object]] = []

    def export_worker() -> None:
        try:
            exported.append(
                ledger.export_as_of(cutoff="2026-08-04T10:10:00+08:00", issue="26081")
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)
        finally:
            export_done.set()

    writer = threading.Thread(target=append_worker)
    writer.start()
    assert insert_reached.wait(timeout=5)
    reader = threading.Thread(target=export_worker)
    reader.start()
    assert not export_done.wait(timeout=0.1)
    release_insert.set()
    writer.join(timeout=5)
    reader.join(timeout=5)
    assert not writer.is_alive() and not reader.is_alive()
    assert failures == []
    assert len(exported[0]["facts"]) == 1
    assert exported[0] == ledger.export_as_of(
        cutoff="2026-08-04T10:10:00+08:00", issue="26081"
    )


def test_coverage_requires_entity_complete_observation_and_applicable_fact(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"partial lineup")
    with pytest.raises(MessageEvidenceError, match="non-empty JSON object"):
        ledger.append_fact(
            capture_id=capture,
            issue="26081",
            match_idx=1,
            fact_kind="confirmed_lineup",
            value=None,
        )
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        value={"coverage_entity_ids": ["team.home"], "teams": {"team.home": []}},
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    partial = ledger.coverage_report(
        cutoff="2026-08-04T10:10:00+08:00",
        issue="26081",
        required_fact_kinds=["confirmed_lineup"],
        max_age_seconds=3600,
    )
    row = partial["matches"][0]
    assert row["decision_chain_eligible"] is False
    assert row["uncovered_entity_ids_by_kind"] == {"confirmed_lineup": ["team.away"]}

    expired_capture = _capture(ledger, 2, b"old schedule")
    ledger.append_fact(
        capture_id=expired_capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
        effective_until="2026-08-04T10:05:00+08:00",
    )
    ledger.append_collection_observation(
        capture_id=expired_capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    expired = ledger.coverage_report(
        cutoff="2026-08-04T10:10:00+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=3600,
    )
    assert expired["matches"][0]["decision_chain_eligible"] is False
    assert expired["matches"][0]["missing_fact_kinds"] == ["schedule"]


def test_exact_kickoff_and_disallowed_provenance_are_ineligible(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"travel checked", source_id="news.primary")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["news.primary"],
    )
    restricted = ledger.coverage_report(
        cutoff="2026-08-04T10:10:00+08:00",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=36000,
        allowed_provenance_tiers=["TIER_0_OFFICIAL"],
    )
    assert restricted["matches"][0]["decision_chain_eligible"] is False
    at_kickoff = ledger.coverage_report(
        cutoff="2026-08-04T20:00:00+08:00",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=36000,
        allowed_provenance_tiers=["TIER_1_PRIMARY"],
    )
    assert at_kickoff["matches"][0]["cutoff_strictly_before_kickoff"] is False
    assert at_kickoff["matches"][0]["decision_chain_eligible"] is False


def test_correction_fold_restores_target_when_corrector_is_retracted(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    first_capture = _capture(ledger, 1, b"first")
    first = ledger.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "doubtful"},
    )
    second_capture = _capture(ledger, 2, b"second")
    second = ledger.append_fact(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "available"},
    )
    ledger.append_relation(
        source_fact_id=second,
        target_fact_id=first,
        relation_type="corrects",
    )
    third_capture = _capture(ledger, 3, b"retract correction")
    third = ledger.append_fact(
        capture_id=third_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "correction_retracted"},
    )
    ledger.append_relation(
        source_fact_id=third,
        target_fact_id=second,
        relation_type="retracts",
    )
    exported = ledger.export_as_of(cutoff="2026-08-04T10:10:00+08:00", issue="26081")
    active = {row["fact_id"] for row in exported["facts"] if row["active"]}
    assert active == {first, third}

    same_capture_fact = ledger.append_fact(
        capture_id=third_capture,
        issue="26081",
        match_idx=1,
        entity_id="player.home.9",
        fact_kind="injury",
        value={"status": "same_time"},
    )
    same_cutoff_relation = ledger.append_relation(
        source_fact_id=same_capture_fact,
        target_fact_id=third,
        relation_type="corrects",
    )
    assert same_cutoff_relation


def test_official_origin_and_cli_output_database_are_protected(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    with pytest.raises(MessageEvidenceError, match="registered base_url origin"):
        ledger.append_capture(
            source_id="club.home",
            source_url="https://attacker.example/report",
            raw_bytes=b"spoofed",
            observed_at="2026-08-04T10:00:00+08:00",
            fetched_at="2026-08-04T10:00:01+08:00",
        )
    for unsafe_url in (
        "https://user:password@home.example/report",
        "https://home.example/report?api_key=secret",
        "https://home.example/report?X-Amz-Signature=secret",
        "https://home.example/report?sv=2026-01-01&sig=secret",
    ):
        with pytest.raises(MessageEvidenceError, match="credentials|sensitive"):
            ledger.append_capture(
                source_id="club.home",
                source_url=unsafe_url,
                raw_bytes=b"secret-bearing URL",
                observed_at="2026-08-04T10:00:00+08:00",
                fetched_at="2026-08-04T10:00:01+08:00",
            )

    script = ROOT / "scripts/manage_message_evidence.py"
    attempted = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(ledger.database),
            "export",
            "--cutoff",
            "2026-08-04T10:00:00+08:00",
            "--output",
            str(ledger.database),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert attempted.returncode == 2
    assert "cannot replace the ledger database" in attempted.stderr
    assert ledger.database.read_bytes().startswith(b"SQLite format 3")

    hardlink = tmp_path / "ledger-hardlink.sqlite"
    os.link(ledger.database, hardlink)
    aliased = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(ledger.database),
            "export",
            "--cutoff",
            "2026-08-04T10:00:00+08:00",
            "--output",
            str(hardlink),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert aliased.returncode == 2
    assert "cannot alias the ledger database" in aliased.stderr

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = subprocess.run(
            [
                sys.executable,
                str(script),
                "--db",
                str(ledger.database),
                "export",
                "--cutoff",
                "2026-08-04T10:00:00+08:00",
                "--output",
                f"{ledger.database}{suffix}",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert sidecar.returncode == 2
        assert "cannot replace the ledger database" in sidecar.stderr


def test_as_of_export_works_from_a_filesystem_readonly_replica(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path / "ledger")
    capture = _capture(ledger, 1, b"readonly export")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    replica_dir = tmp_path / "replica"
    replica_dir.mkdir()
    replica_path = replica_dir / "message-evidence.sqlite"
    source = sqlite3.connect(ledger.database)
    destination = sqlite3.connect(replica_path)
    source.backup(destination)
    destination.execute("PRAGMA journal_mode=DELETE").fetchone()
    destination.close()
    source.close()
    replica = MessageEvidenceLedger(replica_path, readonly_replica=True)
    database_mode = replica_path.stat().st_mode & 0o777
    directory_mode = replica_dir.stat().st_mode & 0o777
    replica_path.chmod(0o444)
    replica_dir.chmod(0o555)
    try:
        exported = replica.export_as_of(
            cutoff="2026-08-04T10:10:00+08:00", issue="26081"
        )
        assert len(exported["facts"]) == 1
        output = tmp_path / "readonly-export.json"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/manage_message_evidence.py"),
                "--db",
                str(replica_path),
                "--readonly-replica",
                "export",
                "--cutoff",
                "2026-08-04T10:10:00+08:00",
                "--issue",
                "26081",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert len(json.loads(output.read_text(encoding="utf-8"))["facts"]) == 1
    finally:
        replica_dir.chmod(directory_mode)
        replica_path.chmod(database_mode)


def test_live_as_of_export_fails_closed_when_writer_lock_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = _base_ledger(tmp_path)
    attempts: list[bool] = []

    def permission_sensitive_connect(*, readonly: bool = False) -> sqlite3.Connection:
        attempts.append(readonly)
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(ledger, "_connect", permission_sensitive_connect)
    with pytest.raises(sqlite3.OperationalError, match="readonly database"):
        ledger.export_as_of(cutoff="2026-08-04T10:10:00+08:00", issue="26081")
    assert attempts == [False]


def test_replay_produces_identical_ids_and_cutoff_exports(tmp_path: Path) -> None:
    first_ledger = _base_ledger(tmp_path / "first")
    second_ledger = _base_ledger(tmp_path / "second")
    first_ids = _populate_replay(first_ledger)
    second_ids = _populate_replay(second_ledger)
    assert first_ids == second_ids

    for cutoff in (
        "2026-08-04T10:01:30+08:00",
        "2026-08-04T10:10:00+08:00",
    ):
        assert first_ledger.export_as_of(
            cutoff=cutoff, issue="26081"
        ) == second_ledger.export_as_of(cutoff=cutoff, issue="26081")


def test_every_evidence_table_rejects_update_and_delete(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    _populate_replay(ledger)
    tables = (
        "source_registry",
        "entity_registry",
        "entity_aliases",
        "match_registry",
        "raw_captures",
        "evidence_facts",
        "evidence_relations",
        "missingness_records",
        "collection_observations",
    )
    conn = sqlite3.connect(ledger.database)
    for table in tables:
        before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(f"UPDATE {table} SET record_sha256=record_sha256")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(f"DELETE FROM {table}")
        conn.rollback()
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == before
    conn.close()


def test_export_detects_provenance_or_cutoff_tampering(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"tamper target")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    conn = sqlite3.connect(ledger.database)
    conn.execute("DROP TRIGGER raw_captures_no_update")
    conn.execute(
        "UPDATE raw_captures SET source_url=? WHERE capture_id=?",
        ("https://home.example/tampered", capture),
    )
    conn.commit()
    conn.close()
    with pytest.raises(MessageEvidenceError, match="record hash mismatch"):
        ledger.export_as_of(cutoff="2026-08-04T10:10:00+08:00", issue="26081")


def test_export_detects_receipt_metadata_tampering(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"receipt tamper target")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    conn = sqlite3.connect(ledger.database)
    conn.execute("DROP TRIGGER evidence_facts_no_update")
    conn.execute(
        """
        UPDATE evidence_facts
        SET recorded_at_utc='2026-08-04T00:00:00.000000Z',
            effective_cutoff_utc='2026-08-04T02:01:01.000000Z'
        """
    )
    conn.commit()
    conn.close()
    with pytest.raises(MessageEvidenceError, match="receipt attestation mismatch"):
        ledger.export_as_of(cutoff="2026-08-04T10:10:00+08:00", issue="26081")


def test_complete_observation_cannot_shrink_match_team_scope(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"home only")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        value={"coverage_entity_ids": ["team.home"]},
    )
    with pytest.raises(MessageEvidenceError, match="both match teams"):
        ledger.append_collection_observation(
            capture_id=capture,
            issue="26081",
            match_idx=1,
            fact_kind="confirmed_lineup",
            status="complete",
            expected_entity_ids=["team.home"],
            checked_source_ids=["club.home"],
        )


def test_match_registration_enforces_distinct_typed_roles(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    common = {
        "issue": "26082",
        "match_idx": 1,
        "kickoff_at": "2026-08-04T20:00:00+08:00",
        "registered_at": "2026-08-04T00:00:00+08:00",
    }
    with pytest.raises(MessageEvidenceError, match="must be distinct"):
        ledger.register_match(
            **common,
            match_id="same-team",
            home_team_id="team.home",
            away_team_id="team.home",
        )
    with pytest.raises(MessageEvidenceError, match="must be teams"):
        ledger.register_match(
            **common,
            match_id="player-as-team",
            home_team_id="player.home.9",
            away_team_id="team.away",
        )
    with pytest.raises(MessageEvidenceError, match="must be a competition"):
        ledger.register_match(
            **common,
            match_id="team-as-competition",
            home_team_id="team.home",
            away_team_id="team.away",
            competition_id="team.home",
        )


def test_missingness_is_recovered_only_by_a_later_usable_fact(tmp_path: Path) -> None:
    recovered = _base_ledger(tmp_path / "recovered")
    first_capture = _capture(recovered, 1, b"first travel fact")
    recovered.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    recovered.append_collection_observation(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    missing_capture = _capture(recovered, 2, b"travel temporarily missing")
    recovered.append_missingness(
        capture_id=missing_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        reason_code="not_published",
    )
    later_capture = _capture(recovered, 3, b"travel recovered")
    recovered.append_fact(
        capture_id=later_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    recovered_row = recovered.coverage_report(
        cutoff="2026-08-04T10:04:00+08:00",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=600,
    )["matches"][0]
    assert recovered_row["explicit_missing_fact_kinds"] == []
    assert recovered_row["decision_chain_eligible"] is True

    still_missing = _base_ledger(tmp_path / "still-missing")
    fact_capture = _capture(still_missing, 1, b"travel fact")
    still_missing.append_fact(
        capture_id=fact_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    later_missing_capture = _capture(still_missing, 2, b"travel absent")
    still_missing.append_missingness(
        capture_id=later_missing_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        reason_code="not_published",
    )
    observation_capture = _capture(still_missing, 3, b"collection complete")
    still_missing.append_collection_observation(
        capture_id=observation_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    missing_row = still_missing.coverage_report(
        cutoff="2026-08-04T10:04:00+08:00",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=600,
    )["matches"][0]
    assert missing_row["explicit_missing_fact_kinds"] == ["travel"]
    assert missing_row["decision_chain_eligible"] is False


def test_coverage_freshness_is_enforced_for_every_expected_entity(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    away_capture = _capture(ledger, 1, b"away lineup")
    ledger.append_fact(
        capture_id=away_capture,
        issue="26081",
        match_idx=1,
        entity_id="team.away",
        fact_kind="confirmed_lineup",
        value={"players": []},
    )
    home_capture = _capture(ledger, 10, b"home lineup")
    ledger.append_fact(
        capture_id=home_capture,
        issue="26081",
        match_idx=1,
        entity_id="team.home",
        fact_kind="confirmed_lineup",
        value={"players": ["player.home.9"]},
    )
    ledger.append_collection_observation(
        capture_id=home_capture,
        issue="26081",
        match_idx=1,
        fact_kind="confirmed_lineup",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    report = ledger.coverage_report(
        cutoff="2026-08-04T10:15:00+08:00",
        issue="26081",
        required_fact_kinds=["confirmed_lineup"],
        max_age_seconds=300,
    )
    row = report["matches"][0]
    assert row["age_seconds_by_kind"]["confirmed_lineup"] == 840.0
    assert row["stale_fact_kinds"] == ["confirmed_lineup"]
    assert row["stale_entity_ids_by_kind"] == {"confirmed_lineup": ["team.away"]}
    assert row["decision_chain_eligible"] is False


def test_freshness_and_effective_until_boundaries_are_exact(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"boundary schedule")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
        effective_from="2026-08-04T10:01:01+08:00",
        effective_until="2026-08-04T10:06:01+08:00",
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    before_effective = ledger.coverage_report(
        cutoff="2026-08-04T10:01:00.999999+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=300,
    )
    assert before_effective["matches"][0]["decision_chain_eligible"] is False
    at_effective = ledger.coverage_report(
        cutoff="2026-08-04T10:01:01+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=300,
    )
    assert at_effective["matches"][0]["decision_chain_eligible"] is True
    at_boundary = ledger.coverage_report(
        cutoff="2026-08-04T10:06:01+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=301,
    )
    assert at_boundary["matches"][0]["age_seconds_by_kind"]["schedule"] == 301
    assert at_boundary["matches"][0]["decision_chain_eligible"] is True

    after_boundary = ledger.coverage_report(
        cutoff="2026-08-04T10:06:01.000001+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=301,
    )
    assert after_boundary["matches"][0]["missing_fact_kinds"] == ["schedule"]
    assert after_boundary["matches"][0]["decision_chain_eligible"] is False


def test_same_cutoff_collection_states_fail_closed(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"same cutoff observation")
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    with pytest.raises(MessageEvidenceError, match="immutable identity collision"):
        ledger.append_collection_observation(
            capture_id=capture,
            issue="26081",
            match_idx=1,
            fact_kind="travel",
            status="partial",
            expected_entity_ids=["team.home", "team.away"],
            checked_source_ids=["club.home"],
        )


def test_cli_rejects_malformed_records_and_unsafe_raw_files(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    script = ROOT / "scripts/manage_message_evidence.py"
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"unexpected": true}', encoding="utf-8")
    malformed_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(ledger.database),
            "register-source",
            "--record",
            str(malformed),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert malformed_result.returncode == 2
    assert "invalid fields for register-source" in malformed_result.stderr
    assert "Traceback" not in malformed_result.stderr

    capture_record = tmp_path / "capture.json"
    capture_record.write_text(
        json.dumps(
            {
                "source_id": "club.home",
                "source_url": "https://home.example/report",
                "observed_at": "2026-08-04T10:00:00+08:00",
                "fetched_at": "2026-08-04T10:00:01+08:00",
            }
        ),
        encoding="utf-8",
    )
    directory_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(ledger.database),
            "capture",
            "--record",
            str(capture_record),
            "--raw",
            str(tmp_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert directory_result.returncode == 2
    assert "regular file" in directory_result.stderr

    oversized = tmp_path / "oversized.raw"
    with oversized.open("wb") as handle:
        handle.truncate(MAX_RAW_CAPTURE_BYTES + 1)
    oversized_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(ledger.database),
            "capture",
            "--record",
            str(capture_record),
            "--raw",
            str(oversized),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert oversized_result.returncode == 2
    assert f"exceeds {MAX_RAW_CAPTURE_BYTES} bytes" in oversized_result.stderr


def test_alias_correction_is_resolved_globally_across_entities(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    ledger.register_entity(
        entity_id="team.renamed",
        entity_type="team",
        canonical_name="Renamed FC",
        registered_at="2026-08-04T00:00:00+08:00",
    )
    old_alias = ledger.register_alias(
        entity_id="team.home",
        source_id="club.home",
        alias_text="United",
        observed_at="2026-08-04T10:00:00+08:00",
    )
    new_alias = ledger.register_alias(
        entity_id="team.renamed",
        source_id="club.home",
        alias_text="United",
        observed_at="2026-08-04T10:01:00+08:00",
    )

    exported = ledger.export_as_of(
        cutoff="2026-08-04T10:02:00+08:00",
        issue="26081",
        match_idx=1,
    )
    aliases = {row["alias_id"]: row for row in exported["entity_aliases"]}
    assert aliases[old_alias]["active"] is False
    assert aliases[new_alias]["active"] is True
    assert "team.renamed" in {row["entity_id"] for row in exported["entities"]}
    _validate(exported, EXPORT_SCHEMA)


def test_stale_collection_observation_fails_coverage(tmp_path: Path) -> None:
    ledger = _base_ledger(tmp_path)
    old_capture = _capture(ledger, 1, b"old completed collection")
    ledger.append_collection_observation(
        capture_id=old_capture,
        issue="26081",
        match_idx=1,
        fact_kind="injury",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    fresh_capture = _capture(ledger, 5, b"fresh facts")
    ledger.append_fact(
        capture_id=fresh_capture,
        issue="26081",
        match_idx=1,
        fact_kind="injury",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )

    report = ledger.coverage_report(
        cutoff="2026-08-04T10:06:00+08:00",
        issue="26081",
        required_fact_kinds=["injury"],
        max_age_seconds=90,
    )
    row = report["matches"][0]
    assert row["stale_fact_kinds"] == []
    assert row["stale_observation_fact_kinds"] == ["injury"]
    assert row["complete_observation_fact_kinds"] == []
    assert row["decision_chain_eligible"] is False
    _validate(report, COVERAGE_SCHEMA)


def test_late_ingestion_does_not_refresh_old_source_evidence(tmp_path: Path) -> None:
    clock = AutoClock(datetime(2026, 8, 4, 10, tzinfo=timezone.utc))
    ledger = _base_ledger(tmp_path, clock=clock)
    capture = ledger.append_capture(
        source_id="club.home",
        source_url="https://home.example/old-report",
        raw_bytes=b"old source evidence",
        published_at="2026-08-04T01:00:00Z",
        observed_at="2026-08-04T01:00:00Z",
        fetched_at="2026-08-04T01:00:01Z",
    )
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    row = ledger.coverage_report(
        cutoff="2026-08-04T10:01:00Z",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=300,
    )["matches"][0]
    assert row["stale_fact_kinds"] == ["travel"]
    assert row["stale_observation_fact_kinds"] == ["travel"]
    assert row["decision_chain_eligible"] is False


@pytest.mark.parametrize(
    ("revised_kickoff", "cutoff", "expected_pre_kickoff"),
    (
        ("2026-08-04T10:30:00+08:00", "2026-08-04T11:00:00+08:00", False),
        ("2026-08-05T20:00:00+08:00", "2026-08-04T21:00:00+08:00", True),
    ),
)
def test_active_schedule_revision_controls_pre_kickoff_gate(
    tmp_path: Path,
    revised_kickoff: str,
    cutoff: str,
    expected_pre_kickoff: bool,
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, revised_kickoff.encode())
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        value={
            "kickoff_at_utc": revised_kickoff,
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    row = ledger.coverage_report(
        cutoff=cutoff,
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=172800,
    )["matches"][0]
    assert row["kickoff_at_utc"] == normalize_timestamp(revised_kickoff)
    assert row["cutoff_strictly_before_kickoff"] is expected_pre_kickoff
    assert row["decision_chain_eligible"] is expected_pre_kickoff


def test_denied_schedule_revision_cannot_reopen_pre_kickoff_gate(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    capture = _capture(ledger, 1, b"denied postponement")
    ledger.append_fact(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        assertion_state="denied",
        value={
            "kickoff_at_utc": "2026-08-05T20:00:00+08:00",
            "coverage_entity_ids": ["team.home", "team.away"],
        },
    )
    ledger.append_collection_observation(
        capture_id=capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    row = ledger.coverage_report(
        cutoff="2026-08-04T21:00:00+08:00",
        issue="26081",
        required_fact_kinds=["schedule"],
        max_age_seconds=172800,
    )["matches"][0]
    assert row["kickoff_at_utc"] == "2026-08-04T12:00:00.000000Z"
    assert row["cutoff_strictly_before_kickoff"] is False
    assert row["decision_chain_eligible"] is False


def test_schedule_conflict_blocks_gate_even_when_schedule_is_not_required(
    tmp_path: Path,
) -> None:
    ledger = _base_ledger(tmp_path)
    first_capture = _capture(ledger, 1, b"kickoff advanced")
    first_schedule = ledger.append_fact(
        capture_id=first_capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        value={"kickoff_at_utc": "2026-08-04T10:30:00+08:00"},
    )
    second_capture = _capture(ledger, 2, b"kickoff postponed")
    second_schedule = ledger.append_fact(
        capture_id=second_capture,
        issue="26081",
        match_idx=1,
        fact_kind="schedule",
        value={"kickoff_at_utc": "2026-08-05T20:00:00+08:00"},
    )
    ledger.append_relation(
        source_fact_id=second_schedule,
        target_fact_id=first_schedule,
        relation_type="contradicts",
    )
    travel_capture = _capture(ledger, 3, b"travel complete")
    ledger.append_fact(
        capture_id=travel_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        value={"coverage_entity_ids": ["team.home", "team.away"]},
    )
    ledger.append_collection_observation(
        capture_id=travel_capture,
        issue="26081",
        match_idx=1,
        fact_kind="travel",
        status="complete",
        expected_entity_ids=["team.home", "team.away"],
        checked_source_ids=["club.home"],
    )
    row = ledger.coverage_report(
        cutoff="2026-08-04T11:00:00+08:00",
        issue="26081",
        required_fact_kinds=["travel"],
        max_age_seconds=7200,
    )["matches"][0]
    assert row["unresolved_conflict_fact_ids"] == sorted(
        [first_schedule, second_schedule]
    )
    assert row["decision_chain_eligible"] is False
