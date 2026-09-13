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
