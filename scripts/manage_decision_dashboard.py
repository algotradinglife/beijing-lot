#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "apps/decision-dashboard"
RUNTIME_DIR = Path(os.environ.get("BEIDAN_DASHBOARD_RUNTIME_DIR", ROOT / "tmp/decision_dashboard"))
STATUS_PATH = Path(os.environ.get("BEIDAN_DASHBOARD_RUNTIME_STATUS", RUNTIME_DIR / "runtime_status.json"))
API_LOG = RUNTIME_DIR / "decision_api.log"
FRONTEND_LOG = RUNTIME_DIR / "decision_dashboard_vite.log"
FRONTEND_BUILD_LOG = RUNTIME_DIR / "decision_dashboard_build.log"
SCORE_REFRESH_LOG = RUNTIME_DIR / "live_score_refresh.log"
SP_REFRESH_LOG = RUNTIME_DIR / "live_sp_refresh.log"
DEFAULT_API_PORT = int(os.environ.get("BEIDAN_DECISION_API_PORT", "8790"))
DEFAULT_FRONTEND_PORT = int(os.environ.get("BEIDAN_DASHBOARD_FRONTEND_PORT", "4173"))
DEFAULT_API_HOST = os.environ.get("BEIDAN_DECISION_API_HOST", "127.0.0.1")
DEFAULT_FRONTEND_HOST = os.environ.get("BEIDAN_DASHBOARD_FRONTEND_HOST", "127.0.0.1")
DEFAULT_FRONTEND_MODE = os.environ.get("BEIDAN_DASHBOARD_FRONTEND_MODE", "api-static")
DEFAULT_SCORE_REFRESH_INTERVAL = float(os.environ.get("BEIDAN_SCORE_REFRESH_INTERVAL", "120"))
DEFAULT_SP_REFRESH_INTERVAL = float(os.environ.get("BEIDAN_SP_REFRESH_INTERVAL", "900"))
ENV_FILES = (
    Path.home() / ".config/beidanlot/webui.env",
    Path.home() / ".config/beidanlot/decision_dashboard.env",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def _read_cwd(pid: int) -> Path | None:
    try:
        return Path(f"/proc/{pid}/cwd").resolve()
    except OSError:
        return None


def _is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _port_processes(port: int) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(["ss", "-ltnp"], text=True, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        if f":{port}" not in line or "LISTEN" not in line:
            continue
        for pid_text in sorted(set(re.findall(r"pid=(\d+)", line))):
            pid = int(pid_text)
            rows.append(
                {
                    "pid": pid,
                    "cmdline": _read_cmdline(pid),
                    "cwd": str(_read_cwd(pid) or ""),
                    "raw": line.strip(),
                }
            )
    return rows


def _service_name_for_pid(pid: int) -> str:
    cmdline = _read_cmdline(pid)
    cwd = _read_cwd(pid)
    if "src.decision_api" in cmdline and cwd == ROOT.resolve():
        return "api"
    if "vite" in cmdline and cwd == DASHBOARD_DIR.resolve():
        return "frontend"
    if "scripts/live_score_refresh_loop.py" in cmdline and cwd == ROOT.resolve():
        return "score_refresh"
    if "scripts/live_sp_refresh_loop.py" in cmdline and cwd == ROOT.resolve():
        return "sp_refresh"
    return ""


def _load_previous_status() -> dict[str, Any]:
    try:
        loaded = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def _service_env() -> dict[str, str]:
    env = os.environ.copy()
    for path in ENV_FILES:
        env.update(_read_env_file(path))
    return env


def _previous_pid(service: str) -> int | None:
    status = _load_previous_status()
    payload = status.get(service)
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("pid") or 0)
    except (TypeError, ValueError):
        return None


def _terminate_pid(pid: int, *, timeout_sec: float = 5.0) -> None:
    if not _is_running(pid):
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return
        time.sleep(0.2)
    if _is_running(pid):
        os.kill(pid, signal.SIGKILL)


def _known_service_pids(service: str, port: int) -> list[int]:
    pids: set[int] = set()
    port_procs = _port_processes(port)
    port_pids = {int(proc["pid"]) for proc in port_procs}
    previous = _previous_pid(service)
    if previous and previous in port_pids and _service_name_for_pid(previous) == service:
        pids.add(previous)
    for proc in port_procs:
        pid = int(proc["pid"])
        if _service_name_for_pid(pid) == service:
            pids.add(pid)
    return sorted(pids)


def _known_process_pids(service: str) -> list[int]:
    pids: set[int] = set()
    previous = _previous_pid(service)
    if previous and _is_running(previous) and _service_name_for_pid(previous) == service:
        pids.add(previous)
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        if _is_running(pid) and _service_name_for_pid(pid) == service:
            pids.add(pid)
    return sorted(pids)


def _http_probe(url: str, *, host_header: str | None = None, timeout_sec: float = 5.0) -> dict[str, Any]:
    started = time.monotonic()
    headers = {"User-Agent": "beidan-decision-dashboard-health/1.0"}
    if host_header:
        headers["Host"] = host_header
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_sec) as response:
            body = response.read(256)
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "url": url,
                "host_header": host_header or "",
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "sample": body.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "host_header": host_header or "",
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "host_header": host_header or "",
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _json_probe(url: str, *, timeout_sec: float = 5.0) -> dict[str, Any]:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": "beidan-decision-dashboard-health/1.0"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_sec) as response:
            raw = response.read()
            payload = json.loads(raw.decode("utf-8", errors="replace"))
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "url": url,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "json": payload if isinstance(payload, dict) else {},
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "url": url,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": str(exc),
            "json": {},
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "json": {},
        }


def _tailscale_ip() -> str:
    try:
        proc = subprocess.run(["tailscale", "ip", "-4"], text=True, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return next((line.strip() for line in proc.stdout.splitlines() if line.strip()), "")


def _is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _urls(
    api_port: int,
    frontend_port: int,
    magic_dns: str = "",
    funnel_url: str = "",
    frontend_host: str = "127.0.0.1",
    frontend_mode: str = "api-static",
) -> dict[str, str]:
    api_static = frontend_mode == "api-static"
    direct_remote_enabled = (not api_static) and not _is_loopback_host(frontend_host)
    tailscale_ip = _tailscale_ip() if direct_remote_enabled else ""
    urls = {
        "api_local": f"http://127.0.0.1:{api_port}",
        "api_health": f"http://127.0.0.1:{api_port}/healthz",
        "frontend_local": f"http://127.0.0.1:{api_port}/" if api_static else f"http://127.0.0.1:{frontend_port}/",
        "frontend_remote": f"http://{tailscale_ip}:{frontend_port}/" if direct_remote_enabled and tailscale_ip else "",
        "tailscale_ip": tailscale_ip,
        "magic_dns": f"https://{magic_dns}/" if magic_dns and api_static else f"http://{magic_dns}:{frontend_port}/" if magic_dns else "",
        "funnel": funnel_url,
    }
    return urls


def _service_snapshot(service: str, port: int, bind_host: str, command: list[str], log_path: Path) -> dict[str, Any]:
    pids = _known_service_pids(service, port)
    pid = pids[-1] if pids else None
    return {
        "pid": pid,
        "status": "running" if pid else "missing",
        "bind_host": bind_host,
        "port": str(port),
        "command": command,
        "log": str(log_path),
        "cmdline": _read_cmdline(pid) if pid else "",
        "port_processes": _port_processes(port),
    }


def _process_snapshot(service: str, command: list[str], log_path: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    pids = _known_process_pids(service)
    pid = pids[-1] if pids else None
    return {
        "pid": pid,
        "status": "running" if pid else "missing",
        "command": command,
        "log": str(log_path),
        "cmdline": _read_cmdline(pid) if pid else "",
        **(extra or {}),
    }


def _frontend_snapshot(args: argparse.Namespace, command: list[str]) -> dict[str, Any]:
    if args.frontend_mode != "api-static":
        return _service_snapshot("frontend", args.frontend_port, args.frontend_host, command, FRONTEND_LOG)
    dist = DASHBOARD_DIR / "dist"
    index_path = dist / "index.html"
    api_running = bool(_known_service_pids("api", args.api_port))
    if api_running and index_path.exists():
        status = "served_by_api"
    elif not index_path.exists():
        status = "missing_build"
    else:
        status = "api_missing"
    return {
        "pid": None,
        "status": status,
        "mode": "api-static",
        "bind_host": args.api_host,
        "port": str(args.api_port),
        "command": command,
        "log": str(FRONTEND_BUILD_LOG),
        "cmdline": "",
        "dist": str(dist),
        "index_exists": index_path.exists(),
        "port_processes": _port_processes(args.api_port),
    }


def _health_payload(args: argparse.Namespace) -> dict[str, Any]:
    urls = _urls(
        args.api_port,
        args.frontend_port,
        args.magic_dns,
        args.funnel_url,
        args.frontend_host,
        args.frontend_mode,
    )
    api_command = [sys.executable, "-m", "src.decision_api"]
    frontend_command = (
        ["served-by", "src.decision_api", str(DASHBOARD_DIR / "dist")]
        if args.frontend_mode == "api-static"
        else [
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            str(args.frontend_host),
            "--port",
            str(args.frontend_port),
            "--strictPort",
        ]
    )
    score_refresh_command = [
        sys.executable,
        str(ROOT / "scripts/live_score_refresh_loop.py"),
        "--db",
        str(ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"),
        "--issue",
        "current",
        "--interval",
        str(args.score_refresh_interval),
        "--timeout",
        str(int(args.timeout * 4)),
    ]
    sp_refresh_command = [
        sys.executable,
        str(ROOT / "scripts/live_sp_refresh_loop.py"),
        "--db",
        str(ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"),
        "--issue",
        "current",
        "--interval",
        str(args.sp_refresh_interval),
        "--recent-count",
        str(args.sp_refresh_recent_count),
        "--open-limit",
        str(args.sp_refresh_open_limit),
        "--timeout",
        str(max(25, int(args.timeout * 6))),
    ]
    operations_probe = _json_probe(f"{urls['api_local']}/api/issues/current/operations", timeout_sec=args.timeout)
    operations_json = operations_probe.get("json") if isinstance(operations_probe.get("json"), dict) else {}
    workflow = operations_json.get("workflow") if isinstance(operations_json, dict) else {}
    review = operations_json.get("review") if isinstance(operations_json, dict) else {}
    review_task = review.get("task") if isinstance(review, dict) else {}
    operations_probe_summary = {key: value for key, value in operations_probe.items() if key != "json"}
    host_smokes = [
        _http_probe(urls["frontend_local"], host_header=host, timeout_sec=args.timeout)
        for host in args.host_smoke
    ]
    payload = {
        "schema": "decision_dashboard_runtime_v1",
        "checked_at": _now_iso(),
        "root": str(ROOT),
        "runtime_dir": str(RUNTIME_DIR),
        "status_path": str(STATUS_PATH),
        "urls": urls,
        "api": _service_snapshot("api", args.api_port, args.api_host, api_command, API_LOG),
        "frontend": _frontend_snapshot(args, frontend_command),
        "score_refresh": _process_snapshot(
            "score_refresh",
            score_refresh_command,
            SCORE_REFRESH_LOG,
            {"interval_sec": args.score_refresh_interval, "enabled": not args.no_score_refresh},
        ),
        "sp_refresh": _process_snapshot(
            "sp_refresh",
            sp_refresh_command,
            SP_REFRESH_LOG,
            {
                "interval_sec": args.sp_refresh_interval,
                "enabled": not args.no_sp_refresh,
                "recent_count": args.sp_refresh_recent_count,
                "open_limit": args.sp_refresh_open_limit,
            },
        ),
        "health": {
            "api": _http_probe(urls["api_health"], timeout_sec=args.timeout),
            "frontend_local": _http_probe(urls["frontend_local"], timeout_sec=args.timeout),
            "host_smokes": host_smokes,
            "operations": {
                **operations_probe_summary,
                "sample": "",
                "issue": operations_json.get("issue", "") if isinstance(operations_json, dict) else "",
                "workflow_status": workflow.get("status", "") if isinstance(workflow, dict) else "",
                "review_task_status": review_task.get("status", "") if isinstance(review_task, dict) else "",
            },
        },
        "logs": {
            "api": str(API_LOG),
            "frontend": str(FRONTEND_LOG),
            "frontend_build": str(FRONTEND_BUILD_LOG),
            "score_refresh": str(SCORE_REFRESH_LOG),
            "sp_refresh": str(SP_REFRESH_LOG),
        },
    }
    return payload


def _write_status(payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = STATUS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(STATUS_PATH)


def _start_api(args: argparse.Namespace) -> None:
    if _known_service_pids("api", args.api_port):
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = _service_env()
    env["BEIDAN_DECISION_API_HOST"] = args.api_host
    env["BEIDAN_DECISION_API_PORT"] = str(args.api_port)
    env["BEIDAN_DASHBOARD_RUNTIME_STATUS"] = str(STATUS_PATH)
    env["BEIDAN_DASHBOARD_STATIC_DIR"] = str(DASHBOARD_DIR / "dist")
    with API_LOG.open("ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "src.decision_api"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _build_frontend(args: argparse.Namespace) -> None:
    if args.frontend_mode != "api-static" or args.skip_frontend_build:
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["VITE_DATA_MODE"] = "fetch"
    env["VITE_API_BASE_URL"] = ""
    env.setdefault("VITE_REFRESH_MS", "60000")
    with FRONTEND_BUILD_LOG.open("ab") as log:
        log.write(f"\n[{_now_iso()}] npm run build\n".encode("utf-8"))
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=DASHBOARD_DIR,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"frontend build failed with exit code {proc.returncode}; see {FRONTEND_BUILD_LOG}")


def _start_frontend(args: argparse.Namespace) -> None:
    if args.frontend_mode == "api-static":
        return
    if _known_service_pids("frontend", args.frontend_port):
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("VITE_DATA_MODE", "fetch")
    env.setdefault("VITE_API_BASE_URL", "")
    env.setdefault("VITE_API_PROXY_TARGET", f"http://127.0.0.1:{args.api_port}")
    env.setdefault("VITE_REFRESH_MS", "60000")
    if args.magic_dns:
        env.setdefault("VITE_ALLOWED_HOSTS", args.magic_dns)
    with FRONTEND_LOG.open("ab") as log:
        subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", str(args.frontend_host), "--port", str(args.frontend_port), "--strictPort"],
            cwd=DASHBOARD_DIR,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _start_score_refresh(args: argparse.Namespace) -> None:
    if args.no_score_refresh or _known_process_pids("score_refresh"):
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    command = [
        sys.executable,
        str(ROOT / "scripts/live_score_refresh_loop.py"),
        "--db",
        str(ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"),
        "--issue",
        "current",
        "--interval",
        str(args.score_refresh_interval),
        "--timeout",
        str(int(args.timeout * 4)),
    ]
    with SCORE_REFRESH_LOG.open("ab") as log:
        subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _start_sp_refresh(args: argparse.Namespace) -> None:
    if args.no_sp_refresh or _known_process_pids("sp_refresh"):
        return
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    command = [
        sys.executable,
        str(ROOT / "scripts/live_sp_refresh_loop.py"),
        "--db",
        str(ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"),
        "--issue",
        "current",
        "--interval",
        str(args.sp_refresh_interval),
        "--recent-count",
        str(args.sp_refresh_recent_count),
        "--open-limit",
        str(args.sp_refresh_open_limit),
        "--timeout",
        str(max(25, int(args.timeout * 6))),
    ]
    with SP_REFRESH_LOG.open("ab") as log:
        subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _tailscale_serve_target(args: argparse.Namespace) -> str:
    port = args.api_port if args.frontend_mode == "api-static" else args.frontend_port
    return f"http://127.0.0.1:{port}"


def _configure_tailscale_serve(args: argparse.Namespace) -> dict[str, Any]:
    if not args.configure_tailscale_serve:
        return {"configured": False, "reason": "not_requested"}
    target = _tailscale_serve_target(args)
    try:
        proc = subprocess.run(
            ["tailscale", "serve", "--bg", target],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"configured": False, "target": target, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "configured": proc.returncode == 0,
        "target": target,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _warm_api_cache(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.skip_cache_warmup:
        return []
    base = f"http://127.0.0.1:{args.api_port}"
    probes = [
        ("issues_light", f"{base}/api/issues?limit=120&include_replay=0"),
        ("dashboard_summary", f"{base}/api/issues/current/dashboard?view=summary"),
    ]
    warmed: list[dict[str, Any]] = []
    for name, url in probes:
        result = _http_probe(url, timeout_sec=args.timeout)
        warmed.append({key: value for key, value in {"name": name, **result}.items() if key != "sample"})
    return warmed


def _wait_for_start(args: argparse.Namespace) -> None:
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        payload = _health_payload(args)
        _write_status(payload)
        if payload["health"]["api"]["ok"] and payload["health"]["frontend_local"]["ok"]:
            return
        time.sleep(0.5)


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    _build_frontend(args)
    _start_api(args)
    _start_frontend(args)
    _start_score_refresh(args)
    _start_sp_refresh(args)
    _wait_for_start(args)
    cache_warmup = _warm_api_cache(args)
    tailscale_serve = _configure_tailscale_serve(args)
    payload = _health_payload(args)
    payload["cache_warmup"] = cache_warmup
    payload["tailscale_serve"] = tailscale_serve
    _write_status(payload)
    return payload


def command_stop(args: argparse.Namespace) -> dict[str, Any]:
    stopped: list[dict[str, Any]] = []
    for service in ("sp_refresh", "score_refresh"):
        for pid in _known_process_pids(service):
            stopped.append({"service": service, "pid": pid})
            _terminate_pid(pid)
    for service, port in (("frontend", args.frontend_port), ("api", args.api_port)):
        for pid in _known_service_pids(service, port):
            stopped.append({"service": service, "pid": pid})
            _terminate_pid(pid)
    payload = _health_payload(args)
    payload["stopped"] = stopped
    _write_status(payload)
    return payload


def command_restart(args: argparse.Namespace) -> dict[str, Any]:
    command_stop(args)
    return command_start(args)


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    payload = _health_payload(args)
    _write_status(payload)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Beidan decision dashboard dev services.")
    parser.add_argument("command", choices=["start", "stop", "restart", "health"])
    parser.add_argument("--api-host", default=DEFAULT_API_HOST)
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--frontend-host", default=DEFAULT_FRONTEND_HOST)
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--frontend-mode", choices=["api-static", "vite-dev"], default=DEFAULT_FRONTEND_MODE)
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--host-smoke", action="append", default=[], help="Host header to test against the local Vite port.")
    parser.add_argument("--magic-dns", default=os.environ.get("BEIDAN_DASHBOARD_MAGICDNS_HOST", ""))
    parser.add_argument("--funnel-url", default=os.environ.get("BEIDAN_DASHBOARD_FUNNEL_URL", ""))
    parser.add_argument("--configure-tailscale-serve", action="store_true", help="Run tailscale serve --bg for the selected frontend target.")
    parser.add_argument("--skip-cache-warmup", action="store_true")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--wait", type=float, default=20.0)
    parser.add_argument("--score-refresh-interval", type=float, default=DEFAULT_SCORE_REFRESH_INTERVAL)
    parser.add_argument("--no-score-refresh", action="store_true")
    parser.add_argument("--sp-refresh-interval", type=float, default=DEFAULT_SP_REFRESH_INTERVAL)
    parser.add_argument("--sp-refresh-recent-count", type=int, default=4)
    parser.add_argument("--sp-refresh-open-limit", type=int, default=12)
    parser.add_argument("--no-sp-refresh", action="store_true")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.command == "start":
        payload = command_start(args)
    elif args.command == "stop":
        payload = command_stop(args)
    elif args.command == "restart":
        payload = command_restart(args)
    else:
        payload = command_health(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
