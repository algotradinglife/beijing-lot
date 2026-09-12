"""Verify the full five-play batch-to-database boundary offline."""
import json
import sqlite3

import pytest

from tests.test_nowscore_history_capture import inputs as capture_inputs, capture, transport
from src.nowscore_history_assembly import assemble_history_batches
from src.nowscore_settlement import build_database

TIME = "2026-09-06T03:00:00+00:00"
inputs = capture_inputs


def test_assembly_preserves_evidence_and_rebuilds_database(inputs, tmp_path):
    root = tmp_path / "batch"
    original = capture(inputs, root)
    bundle = tmp_path / "bundle"
    manifest = assemble_history_batches(*inputs, [root], bundle, generated_at=TIME)
    assert len(manifest["captures"]) == 5
    assert manifest["captures"] == original["captures"]
    assert (bundle / "evidence/plays-0001/manifest.json").read_bytes() == (root / "manifest.json").read_bytes()
    assert (bundle / "evidence/plays-0001/capture_log.jsonl").read_bytes() == (root / "capture_log.jsonl").read_bytes()
    assert str(tmp_path) not in json.dumps(manifest)
    first = build_database(bundle, tmp_path / "first.sqlite")
    second = build_database(bundle, tmp_path / "second.sqlite")
    assert first == second
    assert first["observations"] == 5 and first["options"] == 49
    assert first["capture_failures"] == []
    with sqlite3.connect(tmp_path / "first.sqlite") as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 5
    with pytest.raises(FileExistsError):
        assemble_history_batches(*inputs, [root], bundle, generated_at=TIME)


def test_empty_play_is_source_gap_not_parser_failure(inputs, tmp_path):
    def empty(url, timeout):
        if "TypeID=6&" in url:
            return {"status": 200, "final_url": url, "payload": b""}
        return transport(url, timeout)

    root = tmp_path / "batch"
    capture(inputs, root, transport=empty)
    bundle = tmp_path / "bundle"
    assemble_history_batches(*inputs, [root], bundle, generated_at=TIME)
    receipt = build_database(bundle, tmp_path / "data.sqlite")
    assert receipt["capture_failures"] == []
    assert receipt["observations"] == 4
    assert len(receipt["source_empty_pages"]) == 1
    assert receipt["source_empty_pages"][0]["typeid"] == 6
    assert receipt["findings_by_code"]["missing_play_coverage"] >= 1


def test_archive_five_play_bundle_preserves_partial_vectors(inputs, tmp_path):
    from tests.test_nowscore_archive import archive_page
    from src.nowscore_history_plan import make_history_capture_plan
    from src.nowscore_history_capture import verify_history_batch
    from src.nowscore_settlement import ARCHIVE_SLUGS, TITLE, canonical, digest
    from src.nowscore_replay import compare_nowscore_databases

    _, inventory = inputs
    inventory = dict(inventory, issues=["090919"])
    inventory.pop("inventory_sha256")
    inventory["inventory_sha256"] = digest(canonical(inventory).encode())
    plan = make_history_capture_plan(
        inventory, issues_per_batch=1, control_issue="090919",
        interval_seconds=2, generated_at="2026-09-06T01:00:00+00:00")
    labels = {6: "2", 7: "下双", 8: "1:1", 9: "负-平"}
    requests = []

    def archive_transport(url, timeout):
        requests.append(url)
        typeid = int(url.split("kaijiang_dc_")[1].split("_")[0])
        html = archive_page()
        if typeid != 5:
            title = "单场进球数" if typeid == 6 else TITLE[typeid]
            html = html.replace("单场让球胜平负开奖信息", title + "开奖信息")
            html = html.replace(ARCHIVE_SLUGS[5], ARCHIVE_SLUGS[typeid])
            html = html.replace("kaijiang_dc_5_", f"kaijiang_dc_{typeid}_")
            html = html.replace("090919_1_5", f"090919_1_{typeid}")
            html = html.replace("主队(让球)", "主队").replace(" (<b>+2</b>)", "")
            html = html.replace('spitems">胜', f'spitems">{labels[typeid]}')
            html = html.replace("2.40285", "")
        return {"status": 200, "final_url": url, "payload": html.encode()}

    root = tmp_path / "batch"
    original = capture((plan, inventory), root, transport=archive_transport)
    assert len(requests) == 7
    assert verify_history_batch(plan, inventory, root) == original
    bundle = tmp_path / "bundle"
    assemble_history_batches(plan, inventory, [root], bundle, generated_at=TIME)
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    receipt = build_database(bundle, first)
    assert build_database(bundle, second) == receipt
    compare_nowscore_databases(first, second)
    assert receipt["five_play_task_coverage_complete"] is True
    assert receipt["observations"] == receipt["options"] == 5
    assert receipt["capture_failures"] == receipt["source_empty_pages"] == []
    assert receipt["findings_by_code"]["archive_partial_option_coverage"] == 5
    assert receipt["findings_by_code"]["archive_result_missing_sp"] == 4
    assert "option_score_mismatch" not in receipt["findings_by_code"]
    with sqlite3.connect(first) as con:
        assert con.execute("SELECT COUNT(*) FROM option_sp WHERE raw_sp = ''").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM observation WHERE status = ''").fetchone()[0] == 5


def test_incomplete_duplicate_and_early_assembly_rejected(inputs, tmp_path):
    root = tmp_path / "batch"
    capture(inputs, root)
    for roots, time, message in [([], TIME, "completely cover"),
                                  ([root, root], TIME, "duplicate"),
                                  ([root], "2026-09-06T01:00:00+00:00", "precedes")]:
        with pytest.raises(ValueError, match=message):
            assemble_history_batches(*inputs, roots, tmp_path / "rejected", generated_at=time)
        assert not (tmp_path / "rejected").exists()


def test_assembly_cli(inputs, tmp_path, capsys):
    from scripts.assemble_nowscore_history import main

    plan, inventory = inputs
    root = tmp_path / "batch"
    capture(inputs, root)
    plan_path, inventory_path = tmp_path / "plan.json", tmp_path / "inventory.json"
    plan_path.write_text(json.dumps(plan))
    inventory_path.write_text(json.dumps(inventory))
    main(["--plan", str(plan_path), "--inventory", str(inventory_path),
          "--batch-root", str(root), "--output", str(tmp_path / "bundle"), "--generated-at", TIME])
    assert json.loads(capsys.readouterr().out) == {"requested_issues": 1, "data_pages": 5, "batches": 1}


@pytest.mark.parametrize("damage", ["control_only_raw", "event_log", "batch_manifest", "ledger", "missing_batch", "missing_plan"])
def test_database_revalidates_all_assembled_evidence(inputs, tmp_path, damage):
    from tests.test_nowscore_settlement import page

    calls = 0

    def distinct_control(url, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": 200, "final_url": url, "payload": page(5, ft="4-1")}
        return transport(url, timeout)

    root = tmp_path / "batch"
    original = capture(inputs, root, transport=distinct_control)
    bundle = tmp_path / "bundle"
    manifest = assemble_history_batches(*inputs, [root], bundle, generated_at=TIME)
    if damage == "control_only_raw":
        sha = original["controls"][0]["sha256"]
        assert sha not in {row["sha256"] for row in manifest["captures"]}
        (bundle / "raw" / f"{sha}.html").unlink()
    elif damage == "event_log":
        (bundle / "evidence/plays-0001/capture_log.jsonl").write_bytes(b"changed")
    elif damage == "batch_manifest":
        (bundle / "evidence/plays-0001/manifest.json").write_bytes(b"{}")
    elif damage == "ledger":
        manifest["captures"][0]["match_count"] = 900
    elif damage == "missing_batch":
        manifest["batch_receipts"] = {}
    else:
        del manifest["history_plan"]
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "must-not-exist.sqlite"
    with pytest.raises((ValueError, FileNotFoundError, KeyError)):
        build_database(bundle, output)
    assert not output.exists()


def test_clean_bounded_history_qmd(inputs, tmp_path):
    import os
    import shutil
    import subprocess
    from pathlib import Path
    from bs4 import BeautifulSoup

    quarto = os.environ.get("QUARTO_BIN") or shutil.which("quarto")
    if not quarto:
        pytest.skip("Quarto unavailable; CI installs required runtime")
    root = tmp_path / "batch"
    capture(inputs, root)
    bundle = tmp_path / "bundle"
    assemble_history_batches(*inputs, [root], bundle, generated_at=TIME)
    database = tmp_path / "data.sqlite"
    receipt = build_database(bundle, database)
    assert sum(receipt["findings_by_code"].values()) > 1
    output = tmp_path / "html"
    result = subprocess.run([
        quarto, "render", "quarto/08_nowscore_history_audit.qmd", "--execute", "--no-cache",
        "--output-dir", str(output), "-P", "audit_db:" + str(database), "-P", "detail_limit:1",
    ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    files = list(output.rglob("08_nowscore_history_audit.html"))
    assert len(files) == 1
    soup = BeautifulSoup(files[0].read_text(), "html.parser")
    assert "明细展示：" in soup.get_text() and "未展示：" in soup.get_text()
    assert receipt["data_sha256"] in soup.get_text()
    detail_table = next(table for table in soup.select("table") if "具体期号" in table.get_text())
    assert len(detail_table.select("tbody tr")) == 1
