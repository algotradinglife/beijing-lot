"""Offline five-play capture, failure recovery and evidence replay contracts."""
from datetime import datetime, timezone
import http.client
import json
import shutil

import pytest

from tests.test_nowscore_settlement import page
from src.nowscore_history_capture import capture_history_batch, verify_history_batch
from src.nowscore_history_plan import make_history_capture_plan
from src.nowscore_issue_inventory import canonical, digest, INVENTORY_SCHEMA


@pytest.fixture
def inputs():
    inventory = {"schema": INVENTORY_SCHEMA, "source": "nowscore",
                 "generated_at": "2026-09-06T00:00:00+00:00",
                 "candidate_coverage_complete": True, "production_enabled": False,
                 "issues": ["25053"], "source_empty_candidates": [],
                 "issue_count": 1, "source_empty_count": 0, "candidate_count": 1,
                 "five_play_pages_to_capture": 5}
    inventory["inventory_sha256"] = digest(canonical(inventory).encode())
    plan = make_history_capture_plan(inventory, issues_per_batch=1, control_issue="25053",
                                     interval_seconds=2, generated_at="2026-09-06T01:00:00+00:00")
    return plan, inventory


def transport(url, timeout):
    typeid = int(url.split("TypeID=")[1].split("&")[0])
    return {"status": 200, "final_url": url, "payload": page(typeid)}


def capture(inputs, root, **kwargs):
    options = {"transport": transport, "sleep": lambda _: None,
               "now": lambda: datetime(2026, 9, 6, 2, tzinfo=timezone.utc)}
    options.update(kwargs)
    return capture_history_batch(*inputs, "plays-0001", root, **options)


def test_full_batch_replays_after_directory_move(inputs, tmp_path):
    root = tmp_path / "batch"
    manifest = capture(inputs, root)
    assert len(manifest["captures"]) == 5
    assert len(manifest["controls"]) == 2
    assert manifest == verify_history_batch(*inputs, root)
    shutil.copytree(root, tmp_path / "copy")
    assert manifest == verify_history_batch(*inputs, tmp_path / "copy")
    with pytest.raises(FileExistsError):
        capture(inputs, root)


def test_retry_preserves_partial_and_parse_failure(inputs, tmp_path):
    calls = 0

    def flaky(url, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise http.client.IncompleteRead(b"partial", 50)
        if calls == 2:
            return {"status": 200, "final_url": url, "payload": b"invalid html"}
        return transport(url, timeout)

    root = tmp_path / "retry"
    manifest = capture(inputs, root, transport=flaky)
    attempts = manifest["controls"][0]["attempts"]
    assert len(attempts) == 3 and attempts[0]["partial"]
    assert attempts[1]["sha256"] == digest(b"invalid html")
    assert "error" in attempts[1] and attempts[1]["status"] == 200
    assert verify_history_batch(*inputs, root) == manifest


@pytest.mark.parametrize("failed_call", [1, 2, 7])
def test_failed_pre_data_post_never_seals(inputs, tmp_path, failed_call):
    calls = 0

    def failed(url, timeout):
        nonlocal calls
        calls += 1
        if calls == failed_call:
            return {"status": 503, "final_url": url, "payload": b"busy"}
        return transport(url, timeout)

    root = tmp_path / "failed"
    with pytest.raises(ValueError, match="exhausted"):
        capture(inputs, root, transport=failed, max_attempts=1)
    events = [json.loads(line) for line in (root / "capture_log.jsonl").read_text().splitlines()]
    assert events[-1]["error"] and events[-1]["sha256"] == digest(b"busy")
    assert not (root / "manifest.json").exists()


def test_empty_data_is_distinct_from_empty_control(inputs, tmp_path):
    def empty_data(url, timeout):
        if "TypeID=6&" in url:
            return {"status": 200, "final_url": url, "payload": b""}
        return transport(url, timeout)

    manifest = capture(inputs, tmp_path / "empty-data", transport=empty_data)
    assert manifest["captures"][1]["classification"] == "source_empty"
    verify_history_batch(*inputs, tmp_path / "empty-data")
    with pytest.raises(ValueError, match="control empty"):
        capture(inputs, tmp_path / "empty-control", transport=lambda url, _: {
            "status": 200, "final_url": url, "payload": b""})


def test_embedded_only_fixture_is_quarantined_through_database(inputs, tmp_path):
    """A successful HTTP response is not proof of complete source coverage."""
    payload = page(6).replace(b"M[1][0]=123;", b"M[1][0]=123; M[2][0]=999;")

    def conflicting(url, timeout):
        if "TypeID=6&" in url:
            return {"status": 200, "final_url": url, "payload": payload}
        return transport(url, timeout)

    root = tmp_path / "roster-conflict"
    manifest = capture(inputs, root, transport=conflicting, max_attempts=3)
    events = [json.loads(line) for line in (root / "capture_log.jsonl").read_text().splitlines()]
    attempts = [e for e in events if e["event"] == "attempt" and e["typeid"] == 6]
    assert [e["attempt"] for e in attempts] == [1]
    assert all(e["status"] == 200 and "error" not in e for e in attempts)
    assert all(e["sha256"] == digest(payload) for e in attempts)
    assert (root / "raw" / f"{digest(payload)}.html").read_bytes() == payload
    quarantine = manifest["captures"][1]
    assert quarantine["classification"] == "quarantined"
    assert quarantine["match_count"] == 0
    assert quarantine["quarantine_detail"] == {"embedded_only": [[2, "999", 1]], "visible_only": []}
    assert verify_history_batch(*inputs, root) == manifest
    from src.nowscore_history_assembly import assemble_history_batches
    from src.nowscore_settlement import build_database
    import sqlite3
    bundle = tmp_path / "bundle"
    assemble_history_batches(*inputs, [root], bundle, generated_at="2026-09-06T03:00:00+00:00")
    database = tmp_path / "audit.sqlite"
    receipt = build_database(bundle, database)
    assert receipt["capture_count"] == 5 and receipt["observations"] == 4
    assert len(receipt["capture_failures"]) == 1 and receipt["source_empty_pages"] == []
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT issue,slot,play FROM finding WHERE code='source_roster_conflict'").fetchall() == [("25053", 2, "jq")]
        assert con.execute("SELECT COUNT(*) FROM observation WHERE play='jq'").fetchone()[0] == 0
    with pytest.raises(FileExistsError):
        capture(inputs, root)


def test_roster_conflict_never_qualifies_as_control(inputs, tmp_path):
    def bad_control(url, timeout):
        result = transport(url, timeout)
        result["payload"] = result["payload"].replace(b"M[1][0]=123;", b"M[1][0]=123; M[2][0]=999;")
        return result

    with pytest.raises(ValueError, match="control empty"):
        capture(inputs, tmp_path / "bad-control", transport=bad_control)
    assert not (tmp_path / "bad-control" / "manifest.json").exists()


@pytest.mark.parametrize("damage", ["missing", "bytes", "count", "identity", "time", "status"])
def test_tampered_control_rejected(inputs, tmp_path, damage):
    manifest = capture(inputs, tmp_path / "batch")
    row = manifest["controls"][0]
    raw = tmp_path / "batch" / "raw" / f"{row['sha256']}.html"
    if damage == "missing":
        raw.unlink()
    elif damage == "bytes":
        raw.write_bytes(b"changed")
    elif damage == "count":
        row["match_count"] = 999
    elif damage == "identity":
        row["typeid"] = 9
    elif damage == "time":
        row["attempts"][-1]["received_at"] = "2099-01-01T00:00:00+00:00"
    else:
        row["attempts"][-1]["status"] = 503
    (tmp_path / "batch" / "manifest.json").write_text(canonical(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_history_batch(*inputs, tmp_path / "batch")


def test_parse_interruption_has_durable_response(inputs, tmp_path, monkeypatch):
    import src.nowscore_history_capture as module

    def interrupt(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(module, "classify_play", interrupt)
    root = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        capture(inputs, root)
    event = json.loads((root / "capture_log.jsonl").read_text())
    assert event["event"] == "response" and event["status"] == 200
    assert (root / "raw" / f"{event['sha256']}.html").exists()
    assert not (root / "manifest.json").exists()


def test_cli_verify_and_missing_capture_identity(inputs, tmp_path, capsys):
    from scripts.capture_nowscore_history import main

    plan, inventory = inputs
    plan_path = tmp_path / "plan.json"
    inventory_path = tmp_path / "inventory.json"
    plan_path.write_text(canonical(plan))
    inventory_path.write_text(canonical(inventory))
    capture(inputs, tmp_path / "batch")
    arguments = ["--plan", str(plan_path), "--inventory", str(inventory_path),
                 "--run-root", str(tmp_path / "batch")]
    main(["verify", *arguments])
    assert json.loads(capsys.readouterr().out)["data_pages"] == 5
    with pytest.raises(SystemExit):
        main(["capture", *arguments])
    with pytest.raises(SystemExit):
        main(["replay", *arguments])


def test_later_plan_replay_preserves_receipts_and_assembles(inputs, tmp_path, capsys):
    from src.nowscore_history_capture import replay_history_batch
    from src.nowscore_history_assembly import assemble_history_batches, verify_assembled_history
    old_plan, inventory = inputs
    original = capture(inputs, tmp_path / "original")
    old_path = tmp_path / "old-plan.json"
    old_path.write_text(canonical(old_plan))
    new_plan = make_history_capture_plan(inventory, issues_per_batch=1, control_issue="25053",
                                        interval_seconds=2, generated_at="2026-09-06T03:00:00+00:00")
    result = replay_history_batch(new_plan, inventory, old_path, tmp_path / "original",
                                  tmp_path / "replayed", generated_at="2026-09-06T04:00:00+00:00")
    assert result["captures"] == original["captures"]
    assert result["controls"] == original["controls"]
    assert verify_history_batch(new_plan, inventory, tmp_path / "replayed") == result
    bundle = assemble_history_batches(new_plan, inventory, [tmp_path / "replayed"], tmp_path / "bundle",
                                      generated_at="2026-09-06T05:00:00+00:00")
    verify_assembled_history(tmp_path / "bundle", bundle)
    from scripts.capture_nowscore_history import main
    new_path, inventory_path = tmp_path / "new-plan.json", tmp_path / "inventory.json"
    new_path.write_text(canonical(new_plan))
    inventory_path.write_text(canonical(inventory))
    main(["replay", "--plan", str(new_path), "--inventory", str(inventory_path),
          "--source-plan", str(old_path), "--source-root", str(tmp_path / "original"),
          "--run-root", str(tmp_path / "cli-replay"), "--generated-at", "2026-09-06T04:00:00+00:00"])
    assert json.loads(capsys.readouterr().out)["quarantined_pages"] == 0
    with pytest.raises(FileExistsError):
        replay_history_batch(new_plan, inventory, old_path, tmp_path / "original",
                             tmp_path / "replayed", generated_at="2026-09-06T04:00:00+00:00")
    with pytest.raises(ValueError, match="nested"):
        replay_history_batch(new_plan, inventory, old_path, tmp_path / "replayed",
                             tmp_path / "nested", generated_at="2026-09-06T04:00:00+00:00")
    (tmp_path / "replayed" / "capture_log.jsonl").write_text("")
    with pytest.raises(ValueError, match="event log changed"):
        verify_history_batch(new_plan, inventory, tmp_path / "replayed")
    evidence_log = tmp_path / "bundle" / "evidence" / "plays-0001" / "capture_log.jsonl"
    evidence_log.write_text("")
    bundle["batch_receipts"]["plays-0001"]["event_log_sha256"] = digest(b"")
    with pytest.raises(ValueError, match="differs from origin"):
        verify_assembled_history(tmp_path / "bundle", bundle)


@pytest.mark.parametrize("damage", ["raw", "origin_hash", "scope", "future", "observation", "log"])
def test_replay_rejects_tamper_and_chronology(inputs, tmp_path, damage):
    from src.nowscore_history_capture import replay_history_batch, verify_history_manifest
    old_plan, inventory = inputs
    original = capture(inputs, tmp_path / "original")
    old_path = tmp_path / "old-plan.json"
    old_path.write_text(canonical(old_plan))
    new_plan = make_history_capture_plan(inventory, issues_per_batch=1, control_issue="25053",
                                        interval_seconds=2, generated_at="2026-09-06T03:00:00+00:00")
    result = replay_history_batch(new_plan, inventory, old_path, tmp_path / "original",
                                  tmp_path / "replayed", generated_at="2026-09-06T04:00:00+00:00")
    origin = result["replay_origin"]
    if damage == "raw":
        sha = original["captures"][0]["sha256"]
        (tmp_path / "replayed" / "raw" / f"{sha}.html").write_bytes(b"tampered")
    elif damage == "origin_hash":
        origin["plan_text"] += " "
    elif damage in {"scope", "future"}:
        old = json.loads(origin["plan_text"])
        old["interval_seconds" if damage == "scope" else "generated_at"] = 3 if damage == "scope" else "2099-01-01T00:00:00+00:00"
        old["plan_sha256"] = digest(canonical({k:v for k,v in old.items() if k != "plan_sha256"}).encode())
        origin["plan_text"] = canonical(old)
        origin["plan_sha256"] = digest(origin["plan_text"].encode())
    elif damage == "observation":
        result["captures"][0]["match_count"] += 1
    else:
        origin["log_text"] = ""
        origin["log_sha256"] = digest(b"")
    with pytest.raises(ValueError):
        verify_history_manifest(new_plan, inventory, result, tmp_path / "replayed")
