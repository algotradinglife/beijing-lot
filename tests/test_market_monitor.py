import json
import os
import subprocess


def test_monitor_reports_exited_process_and_finished_capture(tmp_path):
    capture, report = tmp_path / "capture", tmp_path / "report"
    capture.mkdir()
    state = {"pid": os.getpid(), "state": "RUNNING", "active_issue": "001", "completed_issues": 2,
             "new_responses": 4, "blocked_streak": 0, "updated_at_utc": "2026-01-01T00:00:00Z"}
    (capture / "progress.json").write_text(json.dumps(state))
    command = ["bash", "scripts/monitor_market_capture.sh", str(capture), str(report)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    assert json.loads(first.stdout)["status"] == "PROCESS_EXITED"
    state.update(state="OBSERVED_INVENTORY_ATTEMPTED", new_responses=6, completed_issues=3)
    (capture / "progress.json").write_text(json.dumps(state))
    second = subprocess.run(command, check=True, capture_output=True, text=True)
    result = json.loads(second.stdout)
    assert result["status"] == "FINISHED"
    assert result["response_delta"] == 2 and result["issue_delta"] == 1
    assert json.loads((report / "latest.json").read_text()) == result


def test_monitor_requires_both_explicit_paths():
    result = subprocess.run(["bash", "scripts/monitor_market_capture.sh"], capture_output=True)
    assert result.returncode == 2


def test_monitor_does_not_compare_different_epochs(tmp_path):
    report = tmp_path/'report'
    for number in (100, 1):
        capture = tmp_path/str(number)
        capture.mkdir()
        (capture/'progress.json').write_text(json.dumps(dict(pid=os.getpid(), state='RUNNING',
            active_issue='001', completed_issues=number, new_responses=number, blocked_streak=0)))
        result = subprocess.run(['bash', 'scripts/monitor_market_capture.sh', str(capture), str(report)],
            check=True, capture_output=True, text=True)
        assert json.loads(result.stdout)['response_delta'] is None


def test_monitor_live_supervisor_cooldown(tmp_path):
    import sys
    capture, report = tmp_path/'capture', tmp_path/'report'
    capture.mkdir()
    process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)',
                                'supervise_market_history.py',str(capture)])
    try:
        (capture/'progress.json').write_text(json.dumps(dict(pid=999999999,state='CIRCUIT_OPEN',new_responses=4,completed_issues=1)))
        (capture/'supervisor.json').write_text(json.dumps(dict(pid=process.pid)))
        (capture/'recovery.json').write_text(json.dumps(dict(state='COOLDOWN',reason='HTTP_429',next_probe_at=12345,attempt=2)))
        result=subprocess.run(['bash','scripts/monitor_market_capture.sh',str(capture),str(report)],check=True,capture_output=True,text=True)
        row=json.loads(result.stdout)
        assert row['process_alive'] and row['status']=='COOLDOWN'
        assert row['next_probe_at']==12345 and row['recovery_attempt']==2
    finally:
        process.terminate();process.wait()


def test_monitor_missing_progress_is_unknown_and_never_zero(tmp_path):
    capture, report = tmp_path / "capture", tmp_path / "report"
    capture.mkdir()
    command = ["bash", "scripts/monitor_market_capture.sh", str(capture), str(report)]
    for _ in range(2):
        row = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        assert row["status"] == "NO_PROGRESS_RECORD"
        assert row["completed_issues"] is None and row["new_responses"] is None
        assert row["issue_delta"] is None and row["response_delta"] is None
    (capture / "progress.json").write_text(json.dumps(dict(pid=os.getpid(), state="RUNNING", completed_issues=2, new_responses=3)))
    row = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
    assert row["issue_delta"] is None and row["response_delta"] is None


def test_monitor_missing_directory_and_corrupt_progress_fail(tmp_path):
    capture, report = tmp_path / "capture", tmp_path / "report"
    command = ["bash", "scripts/monitor_market_capture.sh", str(capture), str(report)]
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert not report.exists()
    capture.mkdir()
    (capture / "progress.json").write_text("not json")
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert not (report / "latest.json").exists()
