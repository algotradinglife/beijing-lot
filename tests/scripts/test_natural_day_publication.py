from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import publish_natural_day_segment_manifest as publisher  # noqa: E402
from scripts import live_artifact_refresh_loop as refresh_loop  # noqa: E402
from scripts import replay_rolling_segment_n_tickets as rolling  # noqa: E402
from scripts.verify_natural_day_segment_consistency import verify  # noqa: E402
from src.decision_api import app as decision_app  # noqa: E402
from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    load_published_manifest,
)


def _database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE matches(
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            end_time TEXT NOT NULL
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
        INSERT INTO segment_decision_windows VALUES(
            '26078',1,'2026-07-25T18:20:00+08:00','2026-07-27T04:10:00+08:00',
            '2026-07-25T17:55:00+08:00','[1,2,3]','legacy',''
        );
        """
    )
    starts = (
        (1, 63, datetime.fromisoformat("2026-07-25T18:20:00")),
        (64, 72, datetime.fromisoformat("2026-07-26T01:20:00")),
        (136, 38, datetime.fromisoformat("2026-07-27T01:05:00")),
    )
    rows = []
    for first_idx, count, start in starts:
        rows.extend(
            (
                "26078",
                first_idx + offset,
                (start + timedelta(minutes=5 * offset)).isoformat(
                    timespec="seconds"
                ),
            )
            for offset in range(count)
        )
    conn.executemany("INSERT INTO matches VALUES(?,?,?)", rows)
    conn.commit()
    conn.close()


def _publish(db: Path, output: Path, when: str = "2026-07-24T12:00:00+08:00"):
    return publisher.publish(
        issue="26078",
        db_path=db,
        output_root=output,
        now=datetime.fromisoformat(when),
    )


def test_publication_is_content_addressed_atomic_and_idempotent(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    _database(db)

    first = _publish(db, output)
    assert first["segments"] == [63, 72, 38]
    assert first["idempotent"] is False
    manifest_path = Path(str(first["manifest"]))
    assert manifest_path.parent.name == first["sha256"]
    original_bytes = manifest_path.read_bytes()

    # Idempotency is semantic: a later invocation returns the same bytes even
    # after the first freeze and does not mint a timestamp-derived identity.
    second = _publish(db, output, "2026-07-26T12:00:00+08:00")
    assert second == {**first, "idempotent": True}
    assert manifest_path.read_bytes() == original_bytes

    conn = sqlite3.connect(db)
    published = load_published_manifest(conn, "26078")
    counts = [
        len(json.loads(row[0]))
        for row in conn.execute(
            """
            SELECT match_indices_json
            FROM segment_decision_windows
            WHERE issue='26078'
            ORDER BY segment_idx
            """
        )
    ]
    conn.close()
    assert published is not None
    assert published["manifest_sha256"] == first["sha256"]
    assert counts == [63, 72, 38]


def test_failed_cross_store_publish_rolls_back_windows_and_removes_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    _database(db)

    def fail_after_rename(_conn, _manifest):
        raise NaturalDayManifestError("injected failure after package rename")

    monkeypatch.setattr(publisher, "verify_operational_windows", fail_after_rename)
    with pytest.raises(
        NaturalDayManifestError, match="injected failure after package rename"
    ):
        _publish(db, output)

    conn = sqlite3.connect(db)
    assert conn.execute(
        """
        SELECT match_indices_json
        FROM segment_decision_windows
        WHERE issue='26078' AND segment_idx=1
        """
    ).fetchone()[0] == "[1,2,3]"
    assert conn.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='natural_day_segment_publications'
        """
    ).fetchone() is None
    conn.close()
    assert not list((output / "26078/natural_day_v1").glob("[0-9a-f]" * 64))


def test_verified_pre_freeze_manifest_can_be_adopted_without_rewriting_windows(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    original_output = tmp_path / "original"
    adopted_output = tmp_path / "adopted"
    _database(db)
    original = _publish(db, original_output)
    semantic = json.loads(Path(str(original["manifest"])).read_text(encoding="utf-8"))
    legacy = {
        **semantic,
        "published_at_hkt": "2026-07-24T17:07:01+08:00",
        "incident_audit": {"replaced_window_count": 1},
    }
    legacy.pop("manifest_sha256")
    legacy["manifest_sha256"] = publisher.hashlib.sha256(
        publisher.canonical(legacy)
    ).hexdigest()
    legacy_path = tmp_path / "legacy_manifest.json"
    legacy_path.write_bytes(publisher.canonical(legacy) + b"\n")

    conn = sqlite3.connect(db)
    created_before = conn.execute(
        """
        SELECT created_at
        FROM segment_decision_windows
        WHERE issue='26078' AND segment_idx=1
        """
    ).fetchone()[0]
    conn.execute("DROP TABLE natural_day_segment_publications")
    conn.commit()
    conn.close()

    adopted = publisher.publish(
        issue="26078",
        db_path=db,
        output_root=adopted_output,
        now=datetime.fromisoformat("2026-07-25T20:00:00+08:00"),
        adopt_pre_freeze_manifest=legacy_path,
    )
    conn = sqlite3.connect(db)
    created_after = conn.execute(
        """
        SELECT created_at
        FROM segment_decision_windows
        WHERE issue='26078' AND segment_idx=1
        """
    ).fetchone()[0]
    conn.close()
    assert adopted["sha256"] == original["sha256"]
    assert created_after == created_before
    audit = json.loads(
        (
            Path(str(adopted["manifest"])).parent
            / "incident_wrong_entire_issue_window.json"
        ).read_text(encoding="utf-8")
    )
    assert audit["adoption_proof"]["legacy_manifest_sha256"] == legacy["manifest_sha256"]


def test_cross_layer_verifier_rejects_stale_by_segment_artifact(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    plans = tmp_path / "plans"
    structured = tmp_path / "structured.csv"
    structured.write_text("fixture\n", encoding="utf-8")
    _database(db)
    result = _publish(db, output)
    manifest_path = Path(str(result["manifest"]))
    plan = plans / "26078_active_fixture"
    plan.mkdir(parents=True)
    summary = plan / "segment_betting_plan_summary.json"
    summary.write_text(
        json.dumps({
            "issue": "26078",
            "artifact_planning_scope": "by_segment",
            "segment_manifest_sha256": "stale",
        }),
        encoding="utf-8",
    )

    with pytest.raises(NaturalDayManifestError, match="stale by_segment"):
        verify(manifest_path=manifest_path, db_path=db, plan_root=plans)

    payload = json.loads(summary.read_text(encoding="utf-8"))
    payload["segment_manifest_sha256"] = result["sha256"]
    summary.write_text(json.dumps(payload), encoding="utf-8")
    report = verify(manifest_path=manifest_path, db_path=db, plan_root=plans)
    assert report["status"] == "PASS"
    assert report["by_segment_artifacts_checked"] == 1


def test_runtime_consumers_bind_to_publication_and_reject_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    plans = tmp_path / "plans"
    structured = tmp_path / "structured.csv"
    structured.write_text("fixture\n", encoding="utf-8")
    _database(db)
    result = _publish(db, output)

    conn = sqlite3.connect(db)
    match_rows = conn.execute(
        """
        SELECT match_idx,end_time
        FROM matches
        WHERE issue='26078'
        ORDER BY match_idx
        """
    ).fetchall()
    conn.close()
    legs = [
        SimpleNamespace(
            issue="26078",
            match_idx=int(match_idx),
            kickoff=datetime.fromisoformat(end_time),
        )
        for match_idx, end_time in match_rows
    ]
    segments = rolling.build_segments(legs, db_path=db)
    assert [len(segment.legs) for segment in segments] == [63, 72, 38]
    conn = sqlite3.connect(db)
    exact_n_api = decision_app._exact_n_freeze_payload(
        conn,
        "26078",
        output_root=tmp_path / "freeze-root",
        ledger_root=tmp_path / "ledger",
    )
    conn.close()
    assert exact_n_api["segment_counts"] == [63, 72, 38]
    assert [segment["status"] for segment in exact_n_api["segments"]] == [
        "pending",
        "pending",
        "pending",
    ]

    plan = plans / "26078_active_fixture"
    plan.mkdir(parents=True)
    summary_path = plan / "segment_betting_plan_summary.json"
    base_summary = {
        "issue": "26078",
        "label": "fixture",
        "betting_strategy_version": "segment_betting_v0.4.0000",
        "structured_csv": str(tmp_path / "structured.csv"),
        "structured_csv_sha256": hashlib.sha256(
            structured.read_bytes()
        ).hexdigest(),
        "planning_scope": "by_segment",
        "artifact_planning_scope": "by_segment",
        "segment_manifest_sha256": "stale",
        "settings": {
            "planning_scope": "by_segment",
            "stake_mode": "scale_to_budget",
            "segment_budget_yuan": 1000,
        },
    }
    summary_path.write_text(json.dumps(base_summary), encoding="utf-8")
    (plan / "segment_betting_plan_segments.csv").write_text("segment_idx\n1\n")
    (plan / "segment_betting_plan_bundles.csv").write_text("segment_idx\n1\n")
    spec = {
        "label": "fixture",
        "betting_strategy_version": "segment_betting_v0.4.0000",
        "structured_csv": tmp_path / "structured.csv",
        "stake_mode": "scale_to_budget",
        "segment_budget_yuan": 1000,
    }
    assert not refresh_loop._segment_plan_exists(
        "26078",
        spec,
        scope="by_segment",
        plan_dir=plans,
        segment_manifest_sha256=str(result["sha256"]),
    )
    base_summary["segment_manifest_sha256"] = result["sha256"]
    summary_path.write_text(json.dumps(base_summary), encoding="utf-8")
    assert refresh_loop._segment_plan_exists(
        "26078",
        spec,
        scope="by_segment",
        plan_dir=plans,
        segment_manifest_sha256=str(result["sha256"]),
    )

    stale_option = {
        "plan_id": "stale",
        "artifact_planning_scope": "by_segment",
        "segment_manifest_sha256": "old",
    }
    monkeypatch.setattr(
        decision_app, "_segment_plan_options", lambda *_args, **_kwargs: [stale_option]
    )
    payload, status = decision_app._segment_betting_plan_payload(
        "26078",
        planning_scope="by_segment",
        release={"artifacts": {}},
        segment_contract={
            "policy": "BJ-SEG-DAY-001/natural_day_v1",
            "manifest_sha256": result["sha256"],
            "manifest_path": result["manifest"],
            "segments": [{"match_count": 63}, {"match_count": 72}, {"match_count": 38}],
        },
    )
    assert status == 200
    assert payload["status"] == "missing"
    assert payload["freeze_state"]["stale_segment_contract_plan_count"] == 1
    assert payload["source"]["segment_contract"]["segment_counts"] == [63, 72, 38]


def test_live_coordinator_publishes_due_segment_from_canonical_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    structured = tmp_path / "structured.csv"
    structured.write_text("fixture\n", encoding="utf-8")
    _database(db)
    publication = _publish(db, output)
    refreshed_at = datetime.fromisoformat("2026-07-25T17:45:00+08:00")
    os.utime(structured, (refreshed_at.timestamp(), refreshed_at.timestamp()))
    commands: list[list[str]] = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({
                "event_key": "fixture",
                "destination": str(tmp_path / "freeze"),
                "variants": 15,
            }),
            stderr="",
        )

    monkeypatch.setattr(refresh_loop.subprocess, "run", run)
    result = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=structured,
        now=datetime.fromisoformat("2026-07-25T17:50:00+08:00"),
        output_root=tmp_path / "freeze-root",
        ledger_root=tmp_path / "ledger",
        correct_score_root=tmp_path / "score",
    )
    assert result["status"] == "published"
    assert result["segment_idx"] == 1
    assert result["segment_manifest_sha256"] == publication["sha256"]
    assert len(commands) == 1
    assert commands[0][commands[0].index("--manifest") + 1] == publication["manifest"]
    assert commands[0][commands[0].index("--segment") + 1] == "1"


def test_freeze_state_advances_to_next_unfrozen_segment(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    _database(db)
    _publish(db, output)
    conn = sqlite3.connect(db)
    state = decision_app._segment_plan_freeze_state(
        conn,
        "26078",
        observed_at=datetime.fromisoformat("2026-07-26T00:00:00+08:00"),
    )
    conn.close()
    assert state["segment_idx"] == 2
    assert state["locked"] is False
    assert state["segments"][0]["locked"] is True
    assert state["segments"][1]["locked"] is False


def test_operational_by_segment_requires_published_manifest(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    _database(db)
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT match_idx,end_time FROM matches WHERE issue='26078' ORDER BY match_idx"
    ).fetchall()
    conn.close()
    legs = [
        SimpleNamespace(
            issue="26078",
            match_idx=int(match_idx),
            kickoff=datetime.fromisoformat(end_time),
        )
        for match_idx, end_time in rows
    ]
    with pytest.raises(ValueError, match="published natural-day segment contract"):
        rolling.build_segments(
            legs,
            db_path=db,
            require_published_contract=True,
        )


def test_live_coordinator_rejects_stale_previous_segment_input(
    tmp_path: Path,
) -> None:
    db = tmp_path / "test.sqlite"
    output = tmp_path / "results"
    structured = tmp_path / "structured.csv"
    structured.write_text("fixture\n", encoding="utf-8")
    stale = datetime.fromisoformat("2026-07-24T17:45:00+08:00")
    os.utime(structured, (stale.timestamp(), stale.timestamp()))
    _database(db)
    _publish(db, output)
    result = refresh_loop.coordinate_due_exact_n_freeze(
        db,
        "26078",
        structured_csv=structured,
        now=datetime.fromisoformat("2026-07-26T00:50:00+08:00"),
        output_root=tmp_path / "freeze-root",
        ledger_root=tmp_path / "ledger",
        correct_score_root=tmp_path / "score",
    )
    assert result["status"] == "failed_closed_stale_segment_input"
    assert result["segment_idx"] == 2
