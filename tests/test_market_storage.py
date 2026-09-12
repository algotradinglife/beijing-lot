import hashlib
import fcntl
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.market_storage import stage_market_inputs


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    root = tmp_path / "persistent"
    root.mkdir()
    inventory = source / "inventory.json"
    inventory.write_bytes(b'{"issues": []}')
    response = source / "response.json"
    response.write_bytes(b'{"status":200,"raw":"original"}')
    roster = source / "rosters/001/status.json"
    roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps({"issue": "001", "roster_path": str(inventory), "processing_complete": True}))
    plan = source / "plan.json"
    plan.write_text(json.dumps({"inventory_path": str(inventory), "inventory_sha256": hashlib.sha256(inventory.read_bytes()).hexdigest(),
                               "roster_root": str(source / "rosters"), "reused_issues": [], "batches": [[{"issue": "001"}]]}))
    index = source / "index.json"
    item = {"path": str(response), "sha256": hashlib.sha256(response.read_bytes()).hexdigest(), "status": 200}
    index.write_text(json.dumps({"euro:1": {"attempts": [item], "selected": item}}))
    return plan, index, root, response


def test_stage_exact_bytes_paths_and_refuse_published_overwrite(inputs):
    plan, index, root, response = inputs
    receipt = stage_market_inputs(plan, index, root, mountpoint="/")
    assert receipt["state"] == "STAGED_NOT_ACTIVATED"
    bundle = root / "markets/manifests/persistent-forward-v1"
    copied = json.loads((bundle / "existing-captures.json").read_text())["euro:1"]
    assert copied["attempts"][0] == copied["selected"]
    assert Path(copied["selected"]["path"]).read_bytes() == response.read_bytes()
    relocated_plan = json.loads((bundle / "plan.json").read_text())
    assert Path(relocated_plan["inventory_path"]).is_relative_to(root)
    status = json.loads((Path(relocated_plan["roster_root"]) / "001/status.json").read_text())
    assert status["issue"] == "001" and status["processing_complete"] is True
    assert Path(status["roster_path"]).is_relative_to(root)
    assert hashlib.sha256((bundle / "plan.json").read_bytes()).hexdigest() == receipt["plan_sha256"]
    with pytest.raises(FileExistsError):
        stage_market_inputs(plan, index, root, mountpoint="/")


def test_hash_failure_unpublished_and_retry(inputs):
    plan, index, root, response = inputs
    content = response.read_bytes()
    response.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source hash"):
        stage_market_inputs(plan, index, root, mountpoint="/")
    assert not (root / "markets/manifests/persistent-forward-v1/ready.json").exists()
    response.write_bytes(content)
    assert stage_market_inputs(plan, index, root, mountpoint="/")["cache_keys"] == 1


def test_existing_destination_corruption_not_overwritten(inputs):
    plan, index, root, response = inputs
    digest = hashlib.sha256(response.read_bytes()).hexdigest()
    destination = root / "markets/raw/verified-responses" / (digest + ".json")
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="destination hash"):
        stage_market_inputs(plan, index, root, mountpoint="/")
    assert destination.read_bytes() == b"corrupt"


def test_invalid_mount_and_unsafe_issue(inputs):
    plan, index, root, response = inputs
    with pytest.raises(ValueError, match="mounted"):
        stage_market_inputs(plan, index, root, mountpoint=root)
    data = json.loads(plan.read_text())
    data["batches"][0][0]["issue"] = "../escape"
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="unsafe issue"):
        stage_market_inputs(plan, index, root, mountpoint="/")


def test_no_roster_and_empty_cache_preserve_unavailable_state(inputs):
    plan, index, root, response = inputs
    status_path = plan.parent / "rosters/001/status.json"
    status_path.write_text(json.dumps({"processing_complete": True, "roster_error": "missing"}))
    index.write_text("{}")
    receipt = stage_market_inputs(plan, index, root, mountpoint="/")
    assert receipt["cache_keys"] == 0
    status = json.loads((root / "shared/fixtures/persistent-forward-v1/001/status.json").read_text())
    assert status["roster_error"] == "missing" and "roster_path" not in status


def test_pending_upstream_is_not_fabricated_as_empty_issue(inputs):
    plan, index, root, response = inputs
    (plan.parent / "rosters/001/status.json").unlink()
    receipt = stage_market_inputs(plan, index, root, mountpoint="/")
    assert receipt["pending_roster_issues"] == ["001"]
    assert not (root / "shared/fixtures/persistent-forward-v1/001/status.json").exists()


def test_cutover_cli_locks_ledger_and_preserves_interrupted_attempt(inputs):
    plan, index, root, response = inputs
    stage_market_inputs(plan, index, root, mountpoint="/")
    live = plan.parent / "live"
    attempt = live / "responses/euro-2/attempt-01"
    attempt.mkdir(parents=True)
    url = "https://1x2d.titan007.com/2.js"
    body = json.dumps({"url": url, "error": "timeout", "status": None, "received_at_utc": "2026-01-01T00:00:00Z"}).encode()
    (attempt / "response.json").write_bytes(body)
    (attempt / "capture-manifest.json").write_text(json.dumps({"documents": [{"url": url, "filename": "response.json", "state": "TRANSPORT_FAILURE"}],
        "file_hashes": {"response.json": hashlib.sha256(body).hexdigest()}}))
    (attempt.parent / "attempt-02.json").write_text(json.dumps({"url": url, "error": "INTERRUPTED_OR_RESERVED", "received_at_utc": "2026-01-01T00:00:01Z"}))
    old = plan.parent / "ledger.sqlite"
    with sqlite3.connect(old) as con:
        con.execute("CREATE TABLE budgets (id TEXT, cap INTEGER, interval REAL, used INTEGER)")
        con.execute("INSERT INTO budgets VALUES ('test',100,1,7)")
        con.execute("CREATE TABLE source_clock (source TEXT, started REAL, next_allowed REAL)")
        con.execute("INSERT INTO source_clock VALUES ('titan',9,10)")
    command = [sys.executable, "scripts/finalize_market_storage_cutover.py", "--data-root", str(root), "--mountpoint", "/",
               "--live-output", str(live), "--old-ledger", str(old)]
    with (live / "worker.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        blocked = subprocess.run(command, capture_output=True, text=True)
        assert blocked.returncode != 0
        assert not (root / "runtime/state/request_ledger.sqlite").exists()
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    final = root / "markets/manifests/market-forward-persistent-v1"
    ready = json.loads((final / "ready.json").read_text())
    assert ready["staged_cache_keys"] == 1 and ready["additional_cache_keys"] == 1
    assert len(ready["interrupted_reservations"]) == 1
    cache = json.loads((final / "existing-captures.json").read_text())
    assert cache["euro:2"]["selected"]["state"] == "INTERRUPTED"
    assert len(cache["euro:2"]["attempts"]) == 2
    with sqlite3.connect(root / "runtime/state/request_ledger.sqlite") as con:
        assert con.execute("SELECT used, interval FROM budgets").fetchall() == [(7, 1.0)]
        assert con.execute("SELECT next_allowed FROM source_clock").fetchall() == [(10.0,)]
    assert old.exists() and (attempt / "response.json").read_bytes() == body
    assert subprocess.run(command, capture_output=True).returncode != 0
