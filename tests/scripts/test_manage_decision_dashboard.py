from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/manage_decision_dashboard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("manage_decision_dashboard", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_service_name_requires_project_cwd_for_api(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "_read_cmdline", lambda pid: "/usr/bin/python3 -m src.decision_api")

    monkeypatch.setattr(mod, "_read_cwd", lambda pid: ROOT)
    assert mod._service_name_for_pid(12345) == "api"

    monkeypatch.setattr(mod, "_read_cwd", lambda pid: Path("/tmp/other-beidan-project"))
    assert mod._service_name_for_pid(12345) == ""


def test_previous_pid_must_still_listen_on_requested_port(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "_previous_pid", lambda service: 111 if service == "api" else None)
    monkeypatch.setattr(mod, "_service_name_for_pid", lambda pid: "api" if pid == 111 else "")

    def fake_port_processes(port: int):
        return [{"pid": 111, "cmdline": "python3 -m src.decision_api"}] if port == 8790 else []

    monkeypatch.setattr(mod, "_port_processes", fake_port_processes)

    assert mod._known_service_pids("api", 18790) == []
    assert mod._known_service_pids("api", 8790) == [111]
