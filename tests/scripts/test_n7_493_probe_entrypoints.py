"""Offline entry-point tests for the #493 probe scripts.

Each script must be importable without side effects and must do its work only
when main() is called. No test issues a network request.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import n7_493_probe as probe  # noqa: E402

ARTIFACTS = ROOT / "results/data_collection/n7_493_3in1_probe_v1"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scripts():
    return {name: load_script(name) for name in (
        "probe_n7_493_3in1_identity",
        "rebuild_n7_493_probe_ledger",
        "analyze_n7_493_3in1_probe",
        "freeze_n7_493_reviewed_revision")}


def test_importing_the_scripts_creates_no_artifacts(tmp_path, monkeypatch):
    """Import must not run main() or write anything."""
    before = {p.name for p in ARTIFACTS.iterdir()}
    load_script("rebuild_n7_493_probe_ledger")
    load_script("analyze_n7_493_3in1_probe")
    load_script("probe_n7_493_3in1_identity")
    assert {p.name for p in ARTIFACTS.iterdir()} == before


def test_rebuild_main_writes_the_ledger_and_provenance(tmp_path, scripts):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("base_no_company", "company_1", "company_0"):
        (raw / f"{name}.html").write_bytes(b"body")
    (tmp_path / "manifest.json").write_text(json.dumps({"requests": [
        {"label": "company_1", "http_status": 200, "duration_ms": 5,
         "cookie_jar_id": "j"},
        {"label": "company_0", "http_status": 200, "duration_ms": 5,
         "cookie_jar_id": "j"}]}))
    assert scripts["rebuild_n7_493_probe_ledger"].main(["--out", str(tmp_path)]) == 0
    ledger = probe.load_ledger(tmp_path / "requests.jsonl")
    assert {r["label"] for r in ledger} == {"base_no_company", "company_1",
                                            "company_0"}
    provenance = json.loads((tmp_path / "ledger_provenance.json").read_text())
    # Top-level requests only: the per-hop count is unverified, so no remaining
    # budget may be published from this ledger.
    assert provenance["top_level_requests_reconstructed"] == 3
    assert provenance["hop_attempts_total"] == "UNVERIFIED"
    assert provenance["remaining_budget"] == "NOT_COMPUTABLE_TREATED_AS_ZERO"
    assert "attempts_unused" not in provenance
    assert provenance["upper_limit_compliance"] == "UNVERIFIED"


def test_analyze_main_writes_diagnostics(tmp_path, scripts):
    shutil.copytree(ARTIFACTS / "raw", tmp_path / "raw")
    shutil.copy(ARTIFACTS / "requests.jsonl", tmp_path / "requests.jsonl")
    shutil.copy(ARTIFACTS / "ledger_provenance.json",
                tmp_path / "ledger_provenance.json")
    assert scripts["analyze_n7_493_3in1_probe"].main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / "diagnostics.csv").exists()
    manifest = json.loads((tmp_path / "diagnostics_manifest.json").read_text())
    assert manifest["default_view_identity"]["companyid"] == "3"
    assert manifest["wall_clock"]["upper_limit_compliance"] == "UNVERIFIED"


def test_analyze_main_rejects_a_missing_raw_directory(tmp_path, scripts):
    with pytest.raises(FileNotFoundError):
        scripts["analyze_n7_493_3in1_probe"].main(["--out", str(tmp_path)])


def test_probe_main_fails_closed_on_the_reconstructed_ledger(tmp_path, scripts):
    """The delivered ledger is historical evidence, not dispatchable.

    A copy is used so the test never touches (or locks) the delivered artifact.
    """
    if not (ARTIFACTS / "requests.jsonl").exists():
        pytest.skip("delivered ledger not present")
    out = tmp_path / "probe"
    out.mkdir()
    shutil.copy(ARTIFACTS / "requests.jsonl", out / "requests.jsonl")
    before = (out / "requests.jsonl").read_text()
    with pytest.raises(probe.LedgerContractError):
        scripts["probe_n7_493_3in1_identity"].main(
            ["--plan", "base", "--out", str(out)])
    # Fail-closed must not have appended an attempt.
    assert (out / "requests.jsonl").read_text() == before


def test_freeze_main_records_the_reviewed_hashes(tmp_path, scripts):
    """The freeze entry point must bind the revision to real digests."""
    out = tmp_path / "reviewed.json"
    assert scripts["freeze_n7_493_reviewed_revision"].main(
        ["--round", "99", "--out", str(out)]) == 0
    record = json.loads(out.read_text())
    assert record["review_round"] == 99
    assert record["schema"] == "n7_493_reviewed_revision_v1"
    assert len(record["files"]) == len(
        scripts["freeze_n7_493_reviewed_revision"].REVIEWED_FILES)
    for relative, digest in record["files"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert digest == actual, relative
    # The QMD is part of the reviewed revision, not an afterthought.
    assert "quarto/493_n7_input_probe.qmd" in record["files"]


def test_freeze_main_refuses_a_missing_reviewed_file(tmp_path, scripts):
    module = scripts["freeze_n7_493_reviewed_revision"]
    original = module.REVIEWED_FILES
    module.REVIEWED_FILES = original + ("src/definitely_missing.py",)
    try:
        with pytest.raises(SystemExit):
            module.main(["--round", "99", "--out", str(tmp_path / "r.json")])
    finally:
        module.REVIEWED_FILES = original


def test_every_planned_url_stays_inside_the_authorised_scope(scripts):
    """Guards the plan builder itself; never dispatch a real request in a test."""
    module = scripts["probe_n7_493_3in1_identity"]
    for plan, companies in (("base", ""), ("follow", "1,3,9")):
        for _label, url in probe.build_request_plan(plan, companies):
            assert probe.assert_in_scope(url) == url


def test_the_probe_script_has_no_unscoped_plan_escape_hatch(scripts):
    """There is no CLI path that yields an out-of-scope URL."""
    import inspect

    source = inspect.getsource(scripts["probe_n7_493_3in1_identity"])
    assert "assert_in_scope" not in source, (
        "scoping must stay in the reusable module, not be re-implemented")
    assert "build_request_plan" in source
