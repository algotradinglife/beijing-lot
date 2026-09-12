from __future__ import annotations

from datetime import datetime, timezone
import json
import http.client
from pathlib import Path

import pytest

from scripts.discover_nowscore_issues import main
from src.nowscore_issue_inventory import (
    archive_url,
    canonical,
    capture_batch,
    digest,
    fetch_archive,
    legacy_candidates,
    make_plan,
    merge_batches,
    modern_candidates,
    parse_archive,
    rate_limited_transport,
    replay_sealed_batch,
    validate_plan,
    verify_batch,
)


NOW = "2026-09-05T23:00:00+08:00"


def archive_page(
    issue: str,
    slots: tuple[int, ...] = (1, 3),
    *,
    selected: bool = True,
) -> bytes:
    links = "".join(
        f'<a href="/sp/danchang/{issue}_{slot}_5.html">SP</a>' for slot in slots
    )
    return (
        f"<html><title>单场让球胜平负开奖信息</title>"
        f'<select id="dropIssue"><option {"selected" if selected else ""} value="{issue}">{issue}</option></select>'
        f'<ul id="mymenu"><li class="myons"><a href="/beijingdanchang/rangqiushengpingfu/kaijiang_dc_5_{issue}.html">SPF</a></li></ul>'
        f"{links}</html>"
    ).encode()


def small_plan(batch_size: int = 10) -> dict:
    return make_plan(
        legacy_start_year=2019,
        legacy_end_year=2019,
        legacy_max_monthly_serial=1,
        modern_start_year=2020,
        modern_end_year=2020,
        modern_max_serial=2,
        batch_size=batch_size,
        control_issue="26089",
        generated_at=NOW,
        request_interval_seconds=2,
    )


@pytest.mark.parametrize("include_result", [False, True])
def test_inventory_quarto_renders_actual_tables_and_scope(tmp_path, include_result):
    import os
    import shutil
    import subprocess
    from bs4 import BeautifulSoup

    quarto = os.environ.get("QUARTO_BIN") or shutil.which("quarto")
    if not quarto:
        pytest.skip("Quarto unavailable; CI installs required runtime")
    plan = make_plan(legacy_start_year=2009, legacy_end_year=2009, legacy_max_monthly_serial=1,
                     modern_start_year=2020, modern_end_year=2020, modern_max_serial=3,
                     batch_size=20, control_issue="26089", generated_at=NOW, request_interval_seconds=2)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(canonical(plan))
    output = tmp_path / "html"
    args = [quarto, "render", "quarto/07_nowscore_history_inventory.qmd", "--execute", "--no-cache",
            "--output-dir", str(output), "-P", "plan_json:" + str(plan_path)]
    if include_result:
        roots = capture_all(plan, tmp_path / "batches", {"20001", "20003"})
        inventory_path = tmp_path / "inventory.json"
        merge_batches(plan, roots, inventory_path, generated_at=NOW)
        args.extend(["-P", "inventory_json:" + str(inventory_path), "-P",
                     "inventory_file_sha256:" + digest(inventory_path.read_bytes())])
    rendered = subprocess.run(args, cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True, timeout=180)
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    files = list(output.rglob("07_nowscore_history_inventory.html"))
    assert len(files) == 1
    soup = BeautifulSoup(files[0].read_bytes(), "html.parser")
    assert not soup.select(".cell-output-error")
    tables = soup.select("table")
    assert len(tables) == (4 if include_result else 2)
    if include_result:
        assert len(tables[2].select("tbody tr")) == 2
        assert [cell.get_text(strip=True) for cell in tables[2].select("tbody tr")[0].select("td")] == ["2009", "YYMMNN", "12", "0", "12"]
        assert "20002" in tables[3].get_text()
        assert "不能据此断言该期从未发行" in soup.get_text()
    else:
        assert "未提供封存发现结果" in soup.get_text()


def test_candidate_domains_and_plan_receipt():
    legacy = legacy_candidates(2019, 2019, 2)
    assert legacy[:4] == ["190101", "190102", "190201", "190202"]
    assert legacy[-2:] == ["191201", "191202"]
    assert len(legacy) == 24
    assert "190299" in legacy_candidates(2019, 2019, 99)
    assert modern_candidates(2020, 2021, 2) == ["20001", "20002", "21001", "21002"]
    plan = small_plan()
    assert plan["candidate_count"] == 14 and plan["batch_count"] == 2
    assert plan["planned_archive_requests"] == 18
    assert plan["minimum_inventory_request_seconds"] == 32
    assert plan["candidates_sha256"] == digest(canonical(plan["candidates"]).encode())
    assert not plan["historical_coverage_claimed"] and not plan["production_enabled"]
    validate_plan(plan)


@pytest.mark.parametrize(
    "call",
    [
        lambda: legacy_candidates(2020, 2020, 1),
        lambda: legacy_candidates(2019, 2018, 1),
        lambda: legacy_candidates(2019, 2019, 100),
        lambda: modern_candidates(2019, 2020, 1),
        lambda: modern_candidates(2020, 2020, 1000),
        lambda: archive_url("bad"),
        lambda: make_plan(
            legacy_start_year=2019,
            legacy_end_year=2019,
            legacy_max_monthly_serial=1,
            modern_start_year=2020,
            modern_end_year=2020,
            modern_max_serial=1,
            batch_size=1,
            control_issue="26089",
            generated_at="2026-09-05",
            request_interval_seconds=2,
        ),
    ],
)
def test_invalid_candidate_contracts(call):
    with pytest.raises(ValueError):
        call()


def test_archive_empty_present_and_identity_failures():
    assert parse_archive(b"", "20001")["classification"] == "source_empty"
    parsed = parse_archive(archive_page("20001"), "20001")
    assert parsed == {
        "classification": "present",
        "issue": "20001",
        "match_count": 2,
        "first_slot": 1,
        "last_slot": 3,
    }
    assert parse_archive(archive_page("20001", selected=False), "20001") == parsed
    with pytest.raises(ValueError, match="selected"):
        parse_archive(archive_page("20002"), "20001")
    with pytest.raises(ValueError, match="duplicated"):
        parse_archive(archive_page("20001", (1, 1)), "20001")


@pytest.mark.parametrize("damage", [None, "row", "header", "duplicate", "missing"])
def test_archive_header_only_requires_complete_empty_table(damage):
    headers = ["场次", "赛事", "开赛时间", "主队(让球)", "比分", "客队", "半场",
               "彩果", "开奖SP", "平均欧*", "Crow*", "数据"]
    table = '<table class="socai"><tr class="ttis">' + "".join(
        f"<td>{label}</td>" for label in headers
    ) + "</tr></table>"
    if damage == "row":
        table = table.replace("</table>", '<tr id="row_1"><td>1</td></tr></table>')
    elif damage == "header":
        table = table.replace("开奖SP", "unknown")
    elif damage == "duplicate":
        table *= 2
    elif damage == "missing":
        table = ""
    payload = archive_page("20127", ()).replace(b"</html>", table.encode() + b"</html>")
    if damage is None:
        assert parse_archive(payload, "20127") == {
            "classification": "source_empty", "issue": "20127", "match_count": 0,
            "first_slot": None, "last_slot": None,
        }
    else:
        with pytest.raises(ValueError):
            parse_archive(payload, "20127")


def test_fetch_retry_and_empty_are_distinct():
    calls = []

    def transport(url, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise TimeoutError("temporary")
        return {"status": 200, "final_url": url, "payload": archive_page("20001")}

    def fixed():
        return datetime(2026, 9, 5, tzinfo=timezone.utc)

    sleeps = []
    result, payloads = fetch_archive(
        "20001",
        timeout_seconds=3,
        max_attempts=2,
        transport=transport,
        now=fixed,
        sleep=sleeps.append,
    )
    assert result["classification"] == "present" and len(result["attempts"]) == 2
    assert payloads == [archive_page("20001")] and sleeps == [2]
    empty, payloads = fetch_archive(
        "20001",
        timeout_seconds=3,
        max_attempts=2,
        transport=lambda url, timeout: {"status": 200, "final_url": url, "payload": b""},
        now=fixed,
    )
    assert empty["classification"] == "source_empty" and len(empty["attempts"]) == 1
    assert payloads == [b""]


def transport_for(present: set[str], failures: set[str] = set()):
    def transport(url: str, timeout: float) -> dict:
        issue = url.rsplit("_", 1)[-1].removesuffix(".html")
        if issue in failures:
            return {"status": 503, "final_url": url, "payload": b"busy"}
        payload = archive_page(issue) if issue in present or issue == "26089" else b""
        return {"status": 200, "final_url": url, "payload": payload}

    return transport


def capture_all(plan: dict, root: Path, present: set[str]) -> list[Path]:
    roots = []
    for batch in plan["batches"]:
        batch_root = root / batch["batch_id"]
        capture_batch(
            plan,
            batch["batch_id"],
            batch_root,
            timeout_seconds=2,
            max_attempts=2,
            transport=transport_for(present),
            sleep=lambda seconds: None,
            now=lambda: datetime.fromisoformat(NOW),
        )
        roots.append(batch_root)
    return roots


def test_capture_merge_replay_and_no_overwrite(tmp_path):
    plan = small_plan()
    roots = capture_all(plan, tmp_path / "batches", {"191201", "20002"})
    inventory = merge_batches(plan, roots, tmp_path / "inventory.json", generated_at=NOW)
    assert inventory["issues"] == ["191201", "20002"]
    assert len(inventory["source_empty_candidates"]) == 12
    assert inventory["source_empty_candidates"][-1] == "20001"
    assert inventory["candidate_coverage_complete"]
    assert inventory["five_play_pages_to_capture"] == 10
    assert inventory["modern_internal_gaps"] == []
    persisted = json.loads((tmp_path / "inventory.json").read_text())
    assert persisted == inventory
    with pytest.raises(FileExistsError):
        merge_batches(plan, roots, tmp_path / "inventory.json", generated_at=NOW)
    with pytest.raises(FileExistsError):
        capture_batch(
            plan,
            "batch-0001",
            roots[0],
            timeout_seconds=2,
            max_attempts=1,
            transport=transport_for(set()),
            sleep=lambda seconds: None,
        )


def test_merge_requires_complete_batches_and_resolved_failures(tmp_path):
    plan = small_plan()
    roots = capture_all(plan, tmp_path / "batches", {"20002"})
    with pytest.raises(ValueError, match="completely cover"):
        merge_batches(plan, roots[:1], tmp_path / "partial.json", generated_at=NOW)
    manifest_path = roots[0] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["captures"][0]["classification"] = "fetch_or_parse_failure"
    manifest_path.write_text(canonical(manifest))
    with pytest.raises(ValueError, match="unresolved"):
        merge_batches(plan, roots, tmp_path / "failed.json", generated_at=NOW)


@pytest.mark.parametrize("prior_implementation", [False, True])
def test_offline_replay_preserves_receipts_and_merges(tmp_path, prior_implementation):
    source_plan = small_plan()
    sources = capture_all(source_plan, tmp_path / "original", {"20002"})
    current_implementation = source_plan["implementation_sha256"]
    if prior_implementation:
        source_plan["implementation_sha256"] = "1" * 64
        for source in sources:
            manifest_path = source / "manifest.json"
            receipt = json.loads(manifest_path.read_bytes())
            receipt["implementation_sha256"] = source_plan["implementation_sha256"]
            receipt["plan_sha256"] = digest(canonical(source_plan).encode())
            manifest_path.write_text(canonical(receipt))
    source_plan_path = tmp_path / "original-plan.json"
    source_plan_path.write_text(canonical(source_plan))
    later = "2026-09-06T12:00:00+08:00"
    plan = {**source_plan, "generated_at": later, "implementation_sha256": current_implementation}
    outputs = []
    for source in sources:
        before = (source / "manifest.json").read_bytes()
        output = tmp_path / "replayed" / source.name
        result = replay_sealed_batch(plan, source_plan_path, source, output, generated_at=later)
        assert result["replay_origin"]["manifest.json"] == digest(before)
        assert result["captures"] == json.loads(before)["captures"]
        assert (source / "manifest.json").read_bytes() == before
        assert verify_batch(plan, output) == result
        with pytest.raises(FileExistsError):
            replay_sealed_batch(plan, source_plan_path, source, output, generated_at=later)
        outputs.append(output)
    inventory = merge_batches(plan, outputs, tmp_path / "inventory.json", generated_at=later)
    assert inventory["issues"] == ["20002"]
    assert inventory["candidate_coverage_complete"]


def test_replay_batch_cli(tmp_path, capsys):
    source_plan = small_plan()
    sources = capture_all(source_plan, tmp_path / "original", {"20002"})
    source_plan_path = tmp_path / "original-plan.json"
    source_plan_path.write_text(canonical(source_plan))
    later = "2026-09-06T12:00:00+08:00"
    plan_path = tmp_path / "plan.json"
    plan = {**source_plan, "generated_at": later}
    plan_path.write_text(canonical(plan))
    output = tmp_path / "output"
    main(["replay-batch", "--plan", str(plan_path), "--source-plan", str(source_plan_path),
          "--source-root", str(sources[0]), "--output-root", str(output), "--generated-at", later])
    assert json.loads(capsys.readouterr().out)["classification_counts"] == {"source_empty": 10}
    assert verify_batch(plan, output)["replay_origin"]


@pytest.mark.parametrize("damage", ["raw", "contract", "old_seal", "source_binding", "observation", "unsealed", "time"])
def test_offline_replay_rejects_invalid_input_without_seal(tmp_path, damage):
    source_plan = small_plan()
    sources = capture_all(source_plan, tmp_path / "original", {"20002"})
    source = sources[0]
    source_plan_path = tmp_path / "original-plan.json"
    source_plan_path.write_text(canonical(source_plan))
    later = "2026-09-06T12:00:00+08:00"
    plan = {**source_plan, "generated_at": later}
    manifest_path = source / "manifest.json"
    original = json.loads(manifest_path.read_bytes())
    if damage == "raw":
        (source / "raw" / (original["captures"][0]["raw_sha256"] + ".html")).write_bytes(b"tampered")
    elif damage == "contract":
        plan["control_issue"] = "26088"
    elif damage == "old_seal":
        original["sealed_at"] = "2026-09-07T00:00:00+08:00"
    elif damage == "source_binding":
        original["plan_sha256"] = "0" * 64
    elif damage == "observation":
        original["captures"][0]["match_count"] = 99
    elif damage == "time":
        later = NOW
    if damage == "unsealed":
        manifest_path.unlink()
    else:
        manifest_path.write_text(canonical(original))
    output = tmp_path / "output"
    with pytest.raises((ValueError, FileNotFoundError)):
        replay_sealed_batch(plan, source_plan_path, source, output, generated_at=later)
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("damage", ["provenance", "log", "observations", "chronology", "nested"])
def test_replayed_batch_verifier_rejects_tampering(tmp_path, damage):
    source_plan = small_plan()
    sources = capture_all(source_plan, tmp_path / "original", {"20002"})
    source_plan_path = tmp_path / "original-plan.json"
    source_plan_path.write_text(canonical(source_plan))
    later = "2026-09-06T12:00:00+08:00"
    plan = {**source_plan, "generated_at": later}
    output = tmp_path / "output"
    result = replay_sealed_batch(plan, source_plan_path, sources[0], output, generated_at=later)
    if damage == "provenance":
        (output / "provenance" / "plan.json").write_bytes(b"{}")
    elif damage == "log":
        (output / "capture_log.jsonl").write_bytes(b"changed")
    elif damage == "observations":
        result["captures"][0]["attempts"][0]["received_at"] = later
        (output / "manifest.json").write_text(canonical(result))
    elif damage == "chronology":
        result["sealed_at"] = NOW
        (output / "manifest.json").write_text(canonical(result))
    elif damage == "nested":
        with pytest.raises(ValueError, match="nested"):
            replay_sealed_batch(plan, source_plan_path, output, tmp_path / "nested", generated_at=later)
        return
    with pytest.raises(ValueError):
        verify_batch(plan, output)


def test_control_failure_leaves_unsealed_evidence(tmp_path):
    plan = small_plan()
    root = tmp_path / "failed-control"
    with pytest.raises(ValueError, match="control"):
        capture_batch(
            plan,
            "batch-0001",
            root,
            timeout_seconds=2,
            max_attempts=1,
            transport=transport_for(set(), {"26089"}),
            sleep=lambda seconds: None,
        )
    assert root.is_dir() and (root / "raw").is_dir()
    assert not (root / "manifest.json").exists()


def test_plan_validation_rejects_tampering():
    plan = small_plan()
    plan["candidates"][0] = "99999"
    with pytest.raises(ValueError, match="contract"):
        validate_plan(plan)


@pytest.mark.parametrize("damage", ["missing", "corrupt", "identity", "metadata", "hash-path"])
def test_merge_replays_control_evidence(tmp_path, damage):
    plan = small_plan()
    roots = capture_all(plan, tmp_path / "batches", set())
    path = roots[0] / "manifest.json"
    manifest = json.loads(path.read_text())
    row = manifest["controls"][0]
    raw = roots[0] / "raw" / f"{row['raw_sha256']}.html"
    if damage == "missing":
        raw.unlink()
    elif damage == "corrupt":
        raw.write_bytes(b"changed")
    elif damage == "identity":
        row["issue"] = "20001"
    elif damage == "metadata":
        row["match_count"] = 999
    else:
        row["raw_sha256s"] = ["../../outside"]
        row["raw_sha256"] = "../../outside"
        row["attempts"][-1]["sha256"] = "../../outside"
    path.write_text(canonical(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        merge_batches(plan, roots, tmp_path / "inventory.json", generated_at=NOW)
    assert not (tmp_path / "inventory.json").exists()


def test_inventory_identity_survives_directory_move(tmp_path):
    import shutil

    plan = small_plan()
    roots = capture_all(plan, tmp_path / "first", {"20002"})
    first = merge_batches(plan, roots, tmp_path / "first.json", generated_at=NOW)
    shutil.copytree(tmp_path / "first", tmp_path / "copied")
    copied = [tmp_path / "copied" / root.name for root in reversed(roots)]
    second = merge_batches(plan, copied, tmp_path / "second.json", generated_at=NOW)
    assert first == second
    assert str(tmp_path) not in canonical(first)


def test_single_batch_verification_cli_and_stale_implementation(tmp_path, capsys):
    plan = small_plan()
    roots = capture_all(plan, tmp_path / "batches", set())
    path = tmp_path / "plan.json"
    path.write_text(canonical(plan))
    main(["verify-batch", "--plan", str(path), "--batch-root", str(roots[0])])
    assert json.loads(capsys.readouterr().out)["classification_counts"] == {"source_empty": 10}
    plan["implementation_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="implementation"):
        verify_batch(plan, roots[0])


def test_future_plan_cannot_start_capture(tmp_path):
    plan = small_plan()
    plan["generated_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="timestamp"):
        capture_batch(plan, "batch-0001", tmp_path / "future", timeout_seconds=2,
                      max_attempts=1, transport=transport_for(set()))
    assert not (tmp_path / "future").exists()


@pytest.mark.parametrize("damage", ["counts", "timestamp", "attempt_hash", "http_status"])
def test_batch_receipt_contract_rejects_tampering(tmp_path, damage):
    plan = small_plan()
    roots = capture_all(plan, tmp_path / "batches", set())
    path = roots[0] / "manifest.json"
    manifest = json.loads(path.read_text())
    attempt = manifest["captures"][0]["attempts"][-1]
    if damage == "counts":
        manifest["classification_counts"] = {"source_empty": 999}
    elif damage == "timestamp":
        attempt["received_at"] = "2099-01-01T00:00:00+00:00"
    elif damage == "attempt_hash":
        attempt["sha256"] = "0" * 64
    else:
        attempt["status"] = 503
    path.write_text(canonical(manifest))
    with pytest.raises(ValueError):
        verify_batch(plan, roots[0])


def test_interruption_during_parse_preserves_received_body(tmp_path, monkeypatch):
    import src.nowscore_issue_inventory as inventory_module

    def interrupted(payload, issue):
        raise KeyboardInterrupt()

    monkeypatch.setattr(inventory_module, "parse_archive", interrupted)
    root = tmp_path / "interrupted"
    with pytest.raises(KeyboardInterrupt):
        capture_batch(small_plan(), "batch-0001", root, timeout_seconds=2,
                      max_attempts=1, transport=transport_for(set()), sleep=lambda _: None)
    event = json.loads((root / "capture_log.jsonl").read_text())
    assert event["event"] == "response" and event["role"] == "pre_control"
    assert event["status"] == 200
    assert (root / "raw" / f"{event['sha256']}.html").read_bytes() == archive_page("26089")
    assert not (root / "manifest.json").exists()


@pytest.mark.parametrize("role", ["pre_control", "post_control", "candidate"])
def test_failed_requests_have_receipts_and_no_manifest(tmp_path, role):
    calls = 0
    plan = small_plan()

    def transport(url, timeout):
        nonlocal calls
        calls += 1
        fail_at = {"pre_control": 1, "post_control": 12, "candidate": 2}[role]
        if calls == fail_at:
            return {"status": 503, "final_url": url, "payload": b"busy"}
        return transport_for(set())(url, timeout)

    root = tmp_path / "failed"
    with pytest.raises(ValueError):
        capture_batch(plan, "batch-0001", root, timeout_seconds=2,
                      max_attempts=1, transport=transport, sleep=lambda _: None)
    events = [json.loads(line) for line in (root / "capture_log.jsonl").read_text().splitlines()]
    failures = [row for row in events if row.get("error")]
    assert len(failures) == 1
    assert failures[0]["role"] == role
    assert failures[0]["status"] == 503
    assert failures[0]["sha256"] == digest(b"busy")
    assert failures[0]["received_at"] and failures[0]["url"]
    assert (root / "raw" / f"{digest(b'busy')}.html").read_bytes() == b"busy"
    assert not (root / "manifest.json").exists()


def test_truncated_and_invalid_responses_preserve_receipts_before_retry():
    calls = []
    events = []

    def transport(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"partial", 20)
        if len(calls) == 2:
            return {"status": 200, "final_url": url, "payload": b"invalid"}
        return {"status": 200, "final_url": url, "payload": archive_page("20001")}

    def sleep(_):
        assert events[-1][0].get("error")

    row, payloads = fetch_archive("20001", timeout_seconds=2, max_attempts=3,
                                 transport=transport, sleep=sleep,
                                 record_attempt=lambda record, body: events.append((record, body)))
    assert row["classification"] == "present"
    assert payloads[:2] == [b"partial", b"invalid"]
    assert row["attempts"][0]["partial"]
    assert row["attempts"][1]["status"] == 200
    assert row["attempts"][1]["sha256"] == digest(b"invalid")


def test_shared_rate_limit_survives_transport_failure(tmp_path):
    current = [100.0]
    calls = []

    def transport(url, timeout):
        calls.append(current[0])
        if len(calls) == 1:
            raise TimeoutError("temporary")
        return {"status": 200, "final_url": url, "payload": b""}

    def sleep(delay):
        current[0] += delay

    options = dict(lock_path=tmp_path / "rate.lock", interval=2,
                   transport=transport, clock=lambda: current[0], sleep=sleep)
    with pytest.raises(TimeoutError):
        rate_limited_transport(archive_url("20001"), 2, **options)
    rate_limited_transport(archive_url("20001"), 2, **options)
    assert calls == [100.0, 102.0]


def test_rate_limit_serializes_independent_processes(tmp_path):
    import subprocess
    import sys

    code = """
from pathlib import Path
import sys, time
from src.nowscore_issue_inventory import rate_limited_transport
def transport(url, timeout):
    print(time.time(), flush=True)
    return {}
rate_limited_transport('synthetic', 2, lock_path=Path(sys.argv[1]),
                       interval=2, transport=transport)
"""
    processes = [subprocess.Popen([sys.executable, "-c", code, str(tmp_path / "shared.lock")],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for _ in range(2)]
    times = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        times.append(float(stdout.strip()))
    assert abs(times[1] - times[0]) >= 1.95


def test_cli_plan_capture_and_merge(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    main(
        [
            "plan",
            "--output",
            str(plan_path),
            "--legacy-start-year",
            "2019",
            "--legacy-end-year",
            "2019",
            "--legacy-max-monthly-serial",
            "1",
            "--modern-start-year",
            "2020",
            "--modern-end-year",
            "2020",
            "--modern-max-serial",
            "2",
            "--batch-size",
            "2",
            "--control-issue",
            "26089",
            "--generated-at",
            NOW,
            "--request-interval",
            "2",
        ]
    )
    assert json.loads(capsys.readouterr().out)["candidate_count"] == 14
    with pytest.raises(FileExistsError):
        main(
            [
                "plan",
                "--output",
                str(plan_path),
                "--legacy-start-year",
                "2019",
                "--legacy-end-year",
                "2019",
                "--legacy-max-monthly-serial",
                "1",
                "--modern-start-year",
                "2020",
                "--modern-end-year",
                "2020",
                "--modern-max-serial",
                "2",
                "--batch-size",
                "2",
                "--control-issue",
                "26089",
                "--generated-at",
                NOW,
                "--request-interval",
                "2",
            ]
        )
