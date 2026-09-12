"""Freeze persistent collector inputs and copy its ledger while old writers are stopped.

This command does not start services or delete source data. It requires exclusive
old worker/ledger locks and refuses to overwrite a published bundle or ledger.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.fundamentals_market_history import index_market_captures, market_key
from src.market_storage import _copy_verified, _publish_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-root", "mountpoint", "live-output", "old-ledger"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    root, mount = Path(args.data_root).resolve(strict=True), Path(args.mountpoint).resolve(strict=True)
    if not mount.is_mount() or not root.is_relative_to(mount):
        raise ValueError("persistent data volume is not mounted")
    live, old_ledger = Path(args.live_output).resolve(strict=True), Path(args.old_ledger).resolve(strict=True)
    stage = root / "markets/manifests/persistent-forward-v1"
    final = root / "markets/manifests/market-forward-persistent-v1"
    ledger = root / "runtime/state/request_ledger.sqlite"
    if (final / "ready.json").exists() or ledger.exists():
        raise FileExistsError("cutover bundle or persistent ledger already exists")
    with (live / "worker.lock").open("a+b") as worker_lock, Path(str(old_ledger) + ".lock").open("a+b") as ledger_lock:
        fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(ledger_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready = json.loads((stage / "ready.json").read_text())
        for name, key in (("plan.json", "plan_sha256"), ("existing-captures.json", "index_sha256")):
            if hashlib.sha256((stage / name).read_bytes()).hexdigest() != ready[key]:
                raise ValueError("staged input changed")
        cache = json.loads((stage / "existing-captures.json").read_text())
        manifests = sorted((live / "responses").glob("*/attempt-*/capture-manifest.json"))
        additional = index_market_captures(manifests)
        if cache.keys() & additional.keys():
            raise ValueError("old collector unexpectedly recaptured a staged cache key")
        for key, value in additional.items():
            for item in [*value["attempts"], value["selected"]]:
                target = root / "markets/raw/verified-responses" / (item["sha256"] + ".json")
                _copy_verified(item["path"], target, item["sha256"])
                item["path"] = str(target)
        interrupted = []
        for reservation in sorted((live / "responses").glob("*/attempt-*.json")):
            if (reservation.parent / reservation.stem / "capture-manifest.json").exists():
                continue
            content = reservation.read_bytes()
            record = json.loads(content)
            key = market_key(record["url"])
            if key is None or key in cache or not record.get("error"):
                raise ValueError("invalid interrupted reservation")
            digest = hashlib.sha256(content).hexdigest()
            target = root / "markets/raw/verified-responses" / (digest + ".json")
            _copy_verified(reservation, target, digest)
            item = {"path": str(target), "sha256": digest, "state": "INTERRUPTED", "status": None,
                    "received_at_utc": record["received_at_utc"]}
            value = additional.setdefault(key, {"attempts": []})
            value["attempts"].append(item)
            if value.get("selected", {}).get("status") != 200:
                value["selected"] = item
            interrupted.append({"source": str(reservation), "sha256": digest})
        cache.update(additional)
        for value in cache.values():
            for item in [*value["attempts"], value["selected"]]:
                if not Path(item["path"]).resolve(strict=True).is_relative_to(root):
                    raise ValueError("cache still depends on external workspace data")
        ledger.parent.mkdir(parents=True, exist_ok=True)
        temporary_ledger = ledger.with_suffix(".sqlite.partial")
        if temporary_ledger.exists():
            raise FileExistsError("unfinished ledger copy requires inspection")
        with contextlib.closing(sqlite3.connect(old_ledger.as_uri() + "?mode=ro", uri=True)) as source:
            with contextlib.closing(sqlite3.connect(temporary_ledger)) as destination:
                source.backup(destination)
                if destination.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("copied ledger integrity failed")
                ledger_rows = {}
                for table in ("budgets", "source_clock"):
                    rows = source.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                    if rows != destination.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall():
                        raise ValueError("ledger values changed during copy")
                    ledger_rows[table] = rows
        temporary_ledger.rename(ledger)
        _publish_json(final / "plan.json", json.loads((stage / "plan.json").read_text()))
        _publish_json(final / "existing-captures.json", cache)
        evidence = {"state": "CUTOVER_READY_NOT_STARTED", "historical_admission": False,
                    "staged_cache_keys": ready["cache_keys"], "additional_cache_keys": len(additional),
                    "total_cache_keys": len(cache), "interrupted_reservations": interrupted,
                    "ledger_rows": ledger_rows, "previous_output": str(live),
                    "source_manifests": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in manifests},
                    "pending_roster_issues": ready.get("pending_roster_issues", [])}
        for name, key in (("plan.json", "plan_sha256"), ("existing-captures.json", "index_sha256")):
            evidence[key] = hashlib.sha256((final / name).read_bytes()).hexdigest()
        _publish_json(final / "ready.json", evidence)
        print(json.dumps({k: v for k, v in evidence.items() if k not in ("source_manifests", "ledger_rows", "pending_roster_issues")}))
