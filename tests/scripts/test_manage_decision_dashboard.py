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


def test_service_name_detects_refresh_loops(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "_read_cwd", lambda pid: ROOT)

    monkeypatch.setattr(mod, "_read_cmdline", lambda pid: "python3 scripts/live_score_refresh_loop.py --issue current")
    assert mod._service_name_for_pid(1001) == "score_refresh"

    monkeypatch.setattr(mod, "_read_cmdline", lambda pid: "python3 scripts/live_sp_refresh_loop.py --issue current")
    assert mod._service_name_for_pid(1002) == "sp_refresh"


def test_previous_pid_must_still_listen_on_requested_port(monkeypatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "_previous_pid", lambda service: 111 if service == "api" else None)
    monkeypatch.setattr(mod, "_service_name_for_pid", lambda pid: "api" if pid == 111 else "")

    def fake_port_processes(port: int):
        return [{"pid": 111, "cmdline": "python3 -m src.decision_api"}] if port == 8790 else []

    monkeypatch.setattr(mod, "_port_processes", fake_port_processes)

    assert mod._known_service_pids("api", 18790) == []
    assert mod._known_service_pids("api", 8790) == [111]


def test_health_payload_includes_sp_refresh(monkeypatch) -> None:
    mod = _load_module()
    parser = mod._build_parser()
    args = parser.parse_args(["health"])

    monkeypatch.setattr(mod, "_urls", lambda *a, **k: {"api_local": "http://127.0.0.1:8790", "api_health": "http://127.0.0.1:8790/healthz", "frontend_local": "http://127.0.0.1:8790/", "frontend_remote": "", "tailscale_ip": "", "magic_dns": "", "funnel": ""})
    monkeypatch.setattr(mod, "_service_snapshot", lambda *a, **k: {"status": "running"})
    monkeypatch.setattr(mod, "_frontend_snapshot", lambda *a, **k: {"status": "served_by_api"})
    monkeypatch.setattr(mod, "_process_snapshot", lambda service, command, log_path, extra=None: {"status": "running", "command": command, **(extra or {})})
    monkeypatch.setattr(mod, "_json_probe", lambda *a, **k: {"ok": True, "status": 200, "json": {}})
    monkeypatch.setattr(mod, "_http_probe", lambda *a, **k: {"ok": True, "status": 200})

    payload = mod._health_payload(args)

    assert payload["sp_refresh"]["status"] == "running"
    assert "scripts/live_sp_refresh_loop.py" in " ".join(payload["sp_refresh"]["command"])
    assert payload["logs"]["sp_refresh"].endswith("live_sp_refresh.log")
