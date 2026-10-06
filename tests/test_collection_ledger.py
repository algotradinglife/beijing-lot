"""Deterministic, offline tests for the collection master ledger and drift report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from collection_ledger import ledger as ledger_mod  # noqa: E402
from collection_ledger import readers  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _plan_entry(collector_id: str, code_entry: str, *, database="data/demo.sqlite", enabled=True) -> dict:
    return {
        "collector_id": collector_id,
        "label": collector_id,
        "importance": "critical",
        "enabled": enabled,
        "owner_process": "demo_refresh",
        "source": "example.com",
        "code_entry": code_entry,
        "database": database,
        "tables": ["demo"],
        "schedule_interval_sec": 900,
        "stale_after_sec": 1200,
        "coverage_check": "matches_sp",
    }


def _repo(tmp_path: Path, collectors: list[dict]) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "config/data_collection_plan.json", json.dumps({
        "schema_version": "data_collection_plan_v1",
        "updated_at": "2026-10-01",
        "collectors": collectors,
    }))
    _write(repo / "scripts/demo_scrape.py", "# demo entry\n")
    return repo


def _host_unit(tmp_path: Path, name: str, body: str, *, scheduled: bool) -> Path:
    host = tmp_path / "host-units"
    unit = _write(host / name, body)
    if scheduled:
        link = host / "default.target.wants" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(unit)
    return host


def _build(repo: Path, **kwargs):
    params = dict(
        plan_path=repo / "config/data_collection_plan.json",
        repo_root=repo,
        unit_dirs=[],
        registry_dir=None,
        external_data_root=None,
        generated_at="2026-10-04T00:00:00+00:00",
    )
    params.update(kwargs)
    return ledger_mod.build_ledger(**params)


# --------------------------------------------------------------------------- #
# Unit text parsing and path expansion
# --------------------------------------------------------------------------- #

def test_parse_unit_text_joins_continuations():
    text = "[Service]\nExecStart=/usr/bin/python \\\n  scripts/demo_scrape.py \\\n  --flag\n"
    entries = readers.parse_unit_text(text)
    assert entries["service.execstart"] == ["/usr/bin/python scripts/demo_scrape.py --flag"]
    assert readers.extract_paths(entries["service.execstart"]) == ["scripts/demo_scrape.py"]
    assert readers.extract_modules(["/usr/bin/python -m live_collector"]) == ["live_collector"]


def test_expand_unit_path_handles_supported_and_unsupported_specifiers():
    expanded, unsupported = readers.expand_unit_path("%h/project/run.py", home="/home/x")
    assert expanded == "/home/x/project/run.py"
    assert unsupported == []
    expanded, unsupported = readers.expand_unit_path("~/run.py", home="/home/x")
    assert expanded == "/home/x/run.py"
    expanded, unsupported = readers.expand_unit_path("%i/run.py", home="/home/x")
    assert unsupported == ["%i"]


def test_is_collection_unit_filters_unrelated_services():
    unrelated = {"unit": "hermes-gateway.service", "code_paths": ["/opt/hermes/app.py"], "working_directory": "/opt/hermes"}
    assert not readers.is_collection_unit(unrelated, markers=("/home/x/.local/lib",))
    assert readers.is_collection_unit({"unit": "beidanlot-sp-refresh.service", "code_paths": []}, markers=())
    vendored = {"unit": "market.service", "code_paths": [], "working_directory": "/home/x/.local/lib/beijing-lot/market-capture/abc"}
    assert readers.is_collection_unit(vendored, markers=("/home/x/.local/lib",))


# --------------------------------------------------------------------------- #
# Collector / unit classification
# --------------------------------------------------------------------------- #

def test_scheduled_unit_marks_collector_running(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = _host_unit(tmp_path, "beidanlot-demo.service", body, scheduled=True)
    ledger = _build(repo, unit_dirs=[host])
    collector = ledger["objects"]["collectors"][0]
    assert collector["state"] == readers.RUNNING
    unit = ledger["objects"]["units"][0]
    assert unit["state"] == readers.RUNNING and unit["in_repo_units"] is False


def test_unscheduled_unit_marks_collector_archived(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = _host_unit(tmp_path, "beidanlot-demo.service", body, scheduled=False)
    ledger = _build(repo, unit_dirs=[host])
    assert ledger["objects"]["collectors"][0]["state"] == readers.ARCHIVED
    assert any(f["code"] == "unit_not_in_repo" for f in ledger["findings"])


def test_timer_with_explicit_unit_does_not_schedule_basename_service(tmp_path):
    repo = _repo(tmp_path, [
        _plan_entry("demo_a", "scripts/demo_scrape.py"),
        _plan_entry("demo_b", "scripts/other_scrape.py"),
    ])
    _write(repo / "scripts/other_scrape.py", "# other\n")
    host = tmp_path / "host-units"
    _write(host / "beidanlot-a.service",
           f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n")
    _write(host / "beidanlot-b.service",
           f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/other_scrape.py\n")
    timer = _write(host / "beidanlot-a.timer", "[Timer]\nOnCalendar=daily\nUnit=beidanlot-b.service\n")
    link = host / "timers.target.wants/beidanlot-a.timer"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(timer)

    ledger = _build(repo, unit_dirs=[host])
    by_id = {u["id"]: u for u in ledger["objects"]["units"]}
    # Only the explicit target is scheduled; the basename service is not.
    assert by_id["beidanlot-b.service"]["scheduled"] is True
    assert by_id["beidanlot-b.service"]["scheduled_by_timer"] == "beidanlot-a.timer"
    assert by_id["beidanlot-a.service"]["scheduled"] is False


def test_enabled_timer_schedules_its_service_collector(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    service_body = f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = _host_unit(tmp_path, "beidanlot-demo.service", service_body, scheduled=False)
    # The timer, not the service, carries the want link and names the service.
    timer = _write(host / "beidanlot-demo.timer",
                   "[Timer]\nOnCalendar=daily\n")
    link = host / "timers.target.wants" / "beidanlot-demo.timer"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(timer)
    ledger = _build(repo, unit_dirs=[host])
    collector = ledger["objects"]["collectors"][0]
    assert collector["state"] == readers.RUNNING
    service = next(u for u in ledger["objects"]["units"] if u["id"] == "beidanlot-demo.service")
    assert service["scheduled"] is True
    assert service["scheduled_by_timer"] == "beidanlot-demo.timer"


def test_repo_unit_is_not_host_evidence(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    _write(repo / "ops/systemd/user/beidanlot-demo.service",
           f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n")
    # Host dir has no unit at all: the repo copy must not make the collector run.
    ledger = _build(repo, unit_dirs=[])
    assert ledger["objects"]["collectors"][0]["state"] == readers.ARCHIVED
    assert [u["id"] for u in ledger["objects"]["repo_units"]] == ["beidanlot-demo.service"]
    assert any(f["code"] == "repo_unit_not_scheduled" for f in ledger["findings"])
    assert any(f["code"] == "plan_enabled_but_unscheduled" for f in ledger["findings"])


def test_enabled_collector_without_scheduler_is_reported(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    ledger = _build(repo, unit_dirs=[])
    assert any(f["code"] == "plan_enabled_but_unscheduled" for f in ledger["findings"])


def test_collector_matches_only_its_exact_code_identity(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    # A different checkout has a same-named script; it must not schedule us.
    other = tmp_path / "other-checkout/scripts/demo_scrape.py"
    _write(other, "# foreign\n")
    body = f"[Service]\nWorkingDirectory={tmp_path / 'other-checkout'}\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = _host_unit(tmp_path, "beidanlot-foreign.service", body, scheduled=True)
    ledger = _build(repo, unit_dirs=[host])
    collector = ledger["objects"]["collectors"][0]
    assert collector["state"] != readers.RUNNING
    assert collector["units"] == []
    assert collector["foreign_units"] == ["beidanlot-foreign.service"]


def test_missing_code_entry_is_error(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/does_not_exist.py")])
    ledger = _build(repo, unit_dirs=[])
    assert ledger["objects"]["collectors"][0]["state"] == readers.UNKNOWN
    finding = next(f for f in ledger["findings"] if f["code"] == "missing_code_entry")
    assert finding["severity"] == "error"


def test_unit_code_missing_is_error(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = "[Service]\nWorkingDirectory=/gone\nExecStart=/venv/python scripts/vanished.py\n"
    host = _host_unit(tmp_path, "beidanlot-demo.service", body, scheduled=True)
    ledger = _build(repo, unit_dirs=[host])
    finding = next(f for f in ledger["findings"] if f["code"] == "unit_code_missing")
    assert finding["severity"] == "error"
    assert finding["evidence"]["missing"] == ["scripts/vanished.py"]


def test_unsupported_specifier_is_unknown_not_missing(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = "[Service]\nWorkingDirectory=%i/run\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = _host_unit(tmp_path, "beidanlot-demo.service", body, scheduled=True)
    ledger = _build(repo, unit_dirs=[host])
    assert ledger["objects"]["units"][0]["state"] == readers.UNKNOWN
    assert any(f["code"] == "unit_path_unsupported" for f in ledger["findings"])


def test_dangling_wants_link_does_not_schedule(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n"
    host = tmp_path / "host-units"
    _write(host / "beidanlot-demo.service", body)
    link = host / "default.target.wants" / "beidanlot-demo.service"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(host / "missing.service")
    ledger = _build(repo, unit_dirs=[host])
    assert ledger["objects"]["units"][0]["state"] == readers.ARCHIVED
    assert any(f["code"] == "dangling_wants_link" for f in ledger["findings"])


# --------------------------------------------------------------------------- #
# Store classification
# --------------------------------------------------------------------------- #

def test_live_store_beside_backup_is_not_retired(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py", database="data/demo.sqlite")])
    _write(repo / "data/demo.sqlite", "live")
    _write(repo / "data/demo.sqlite.bak", "backup")
    ledger = _build(repo, unit_dirs=[])
    collector = ledger["objects"]["collectors"][0]
    assert collector["state"] != readers.RETIRED
    assert collector["store"]["state"] == readers.RUNNING


def test_absent_store_with_exact_bak_sibling_is_retired(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py", database="data/demo.sqlite")])
    _write(repo / "data/demo.sqlite.bak", "old")
    ledger = _build(repo, unit_dirs=[])
    collector = ledger["objects"]["collectors"][0]
    assert collector["state"] == readers.RETIRED
    assert collector["store"]["retired_sibling"].endswith("demo.sqlite.bak")
    assert any(f["code"] == "plan_points_at_retired_store" for f in ledger["findings"])


def test_unrelated_suffix_bak_does_not_retire(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py", database="data/demo.sqlite")])
    _write(repo / "data/demo.sqlite-other.bak", "unrelated")
    ledger = _build(repo, unit_dirs=[])
    assert ledger["objects"]["collectors"][0]["state"] != readers.RETIRED


def test_store_stale_days_parameter_is_honored(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py", database="data/demo.sqlite")])
    store = _write(repo / "data/demo.sqlite", "x")
    old = 100 * 86400
    import os, time
    now = time.time()
    os.utime(store, (now - old, now - old))
    fresh_policy = _build(repo, unit_dirs=[], store_stale_days=1000)
    strict_policy = _build(repo, unit_dirs=[], store_stale_days=1)
    assert fresh_policy["objects"]["collectors"][0]["store"]["state"] == readers.RUNNING
    assert strict_policy["objects"]["collectors"][0]["store"]["state"] == readers.ARCHIVED


# --------------------------------------------------------------------------- #
# Registry and inputs
# --------------------------------------------------------------------------- #

def test_read_external_registry_only_trusts_retirement_schema(tmp_path):
    registry = tmp_path / "registry"
    _write(registry / "migration.json", json.dumps({
        "schema": "beijing_lot_workspace_migration_v1",
        "status": "pending_classification",
        "entries": {"/old/a": {"state": "REMOVED"}},
    }))
    _write(registry / "proposal.json", json.dumps({"state": "RETIRED", "entries": {"/old/x": {"state": "REMOVED"}}}))
    _write(registry / "retirement.json", json.dumps({
        "schema": "beijing_lot_source_retirement_v1",
        "entries": {"/old/b": {"state": "REMOVED", "archive": "x.tar.zst", "archive_sha256": "abc"}},
    }))
    result = readers.read_external_registry(registry)
    assert [r["source"] for r in result["retired"]] == ["/old/b"]


def test_read_external_registry_distinguishes_failure_modes(tmp_path):
    registry = tmp_path / "registry"
    _write(registry / "capacity.json", json.dumps([{"a": 1}]))
    _write(registry / "broken.json", "{not json")
    (registry / "bad-bytes.json").write_bytes(b"\xff\xfe\x00bad")
    result = readers.read_external_registry(registry)
    errors = {f["file"]: f["error"] for f in result["files"]}
    assert errors["capacity.json"] == "not-an-object"
    assert errors["broken.json"] == "unreadable"
    assert errors["bad-bytes.json"] == "unreadable"


def test_registry_declared_missing_store_is_an_error(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    registry = tmp_path / "registry"
    _write(registry / "reference.json", json.dumps({
        "schema": "beijing_lot_market_reference_v1",
        "database": "markets/missing.sqlite",
    }))
    ledger = _build(repo, unit_dirs=[], registry_dir=registry, external_data_root=tmp_path / "data")
    finding = next(f for f in ledger["findings"] if f["code"] == "registry_store_missing")
    assert finding["severity"] == "error"


def test_unavailable_inputs_are_reported(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    ledger = _build(
        repo, unit_dirs=[tmp_path / "absent-units"],
        registry_dir=tmp_path / "absent-registry",
        external_data_root=tmp_path / "absent-root")
    codes = {f["code"] for f in ledger["findings"]}
    assert {"unit_dir_unavailable", "external_registry_unavailable", "external_data_root_unavailable"} <= codes
    assert ledger["summary"]["inputs_unavailable"] >= 3
    assert ledger["inputs"]["registry_dir"]["available"] is False


def test_external_registry_group_excluded_from_stores(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    root = tmp_path / "data"
    (root / "registry").mkdir(parents=True)
    (root / "markets").mkdir()
    ledger = _build(repo, unit_dirs=[], registry_dir=None, external_data_root=root)
    ids = {s["id"] for s in ledger["objects"]["stores"]}
    assert "markets" in ids and "registry" not in ids


# --------------------------------------------------------------------------- #
# Plan staleness, drift, rendering
# --------------------------------------------------------------------------- #

def test_stale_plan_is_warning(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    _write(repo / "config/data_collection_plan.json", json.dumps({
        "schema_version": "data_collection_plan_v1",
        "updated_at": "2026-01-01",
        "collectors": [_plan_entry("demo", "scripts/demo_scrape.py")],
    }))
    ledger = _build(repo, unit_dirs=[])
    finding = next(f for f in ledger["findings"] if f["code"] == "plan_stale")
    assert finding["severity"] == "warning"


def test_diff_ledgers_reports_transition_and_new_finding():
    previous = {
        "generated_at": "2026-10-03T00:00:00+00:00",
        "objects": {"collectors": [{"id": "a", "state": "running"}], "units": [], "stores": []},
        "findings": [],
    }
    current = {
        "generated_at": "2026-10-04T00:00:00+00:00",
        "objects": {"collectors": [{"id": "a", "state": "retired"}], "units": [], "stores": []},
        "findings": [{"code": "plan_stale", "subject": "plan"}],
    }
    drift = ledger_mod.diff_ledgers(previous, current)
    assert drift["transitions"] == [{"object": "collector:a", "from": "running", "to": "retired"}]
    assert drift["new_findings"] == ["plan_stale|plan"]


def test_render_text_reports_unavailable_inputs(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    ledger = _build(repo, unit_dirs=[], registry_dir=tmp_path / "absent", external_data_root=tmp_path / "absent-root")
    text = ledger_mod.render_text(ledger)
    assert "collection ledger" in text
    assert "UNAVAILABLE INPUT" in text


def test_cli_main_writes_and_fails_on_error(tmp_path, monkeypatch, capsys):
    from scripts import collection_ledger as cli  # noqa: E402
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/missing_entry.py")])
    out = tmp_path / "out/ledger.json"
    rc = cli.main([
        "--plan", str(repo / "config/data_collection_plan.json"),
        "--repo-root", str(repo),
        "--no-external", "--unit-dir", str(tmp_path / "none"),
        "--output", str(out), "--fail-on-error",
        "--generated-at", "2026-10-04T00:00:00+00:00",
    ])
    assert rc == 2
    assert out.exists()
    assert "collection ledger" in capsys.readouterr().out


def test_evidence_digest_changes_when_a_store_appears(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    root = tmp_path / "data"
    (root / "markets").mkdir(parents=True)
    registry = tmp_path / "registry"
    _write(registry / "reference.json", json.dumps({
        "schema": "beijing_lot_market_reference_v1",
        "database": "markets/demo.sqlite",
    }))
    before = _build(repo, unit_dirs=[], registry_dir=registry, external_data_root=root)
    _write(root / "markets/demo.sqlite", "store")
    after = _build(repo, unit_dirs=[], registry_dir=registry, external_data_root=root)
    digest_before = {e["input"]: e["digest"] for e in before["evidence"]}
    digest_after = {e["input"]: e["digest"] for e in after["evidence"]}
    assert digest_before["collector_stores"] != digest_after["collector_stores"]
    assert digest_before["external_data_root"] != digest_after["external_data_root"]


def test_evidence_digest_changes_when_wants_directory_moves(tmp_path):
    repo = _repo(tmp_path, [_plan_entry("demo", "scripts/demo_scrape.py")])
    body = f"[Service]\nWorkingDirectory={repo}\nExecStart=/venv/python scripts/demo_scrape.py\n"

    def build_with(wants_dir: str):
        host = tmp_path / f"host-{wants_dir.split('.')[0]}"
        unit = _write(host / "beidanlot-demo.service", body)
        link = host / wants_dir / "beidanlot-demo.service"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(unit)
        return _build(repo, unit_dirs=[host])

    default = build_with("default.target.wants")
    timers = build_with("timers.target.wants")
    d1 = {e["input"]: e["digest"] for e in default["evidence"]}["host_units"]
    d2 = {e["input"]: e["digest"] for e in timers["evidence"]}["host_units"]
    assert d1 != d2


def test_cli_parser_defaults():
    from scripts import collection_ledger as cli  # noqa: E402
    args = cli.build_parser().parse_args([])
    assert args.unit_dir is None
    assert args.store_stale_days == ledger_mod.DEFAULT_STORE_STALE_DAYS
    assert args.no_external is False
