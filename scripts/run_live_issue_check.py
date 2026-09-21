#!/usr/bin/env python3
"""Scheduled check for newly settled issues: resolve, capture, and record what is pending.

Runs the read-only half of an update on a timer. It never writes the release: appending to a
sealed release needs an explicit approval note per batch, so this leaves the captured bundle
and a status file for the operator to act on, and prunes the backup directory to its retention
policy while it is there.

Exits 0 whether or not work is pending. The state is in the status file, so a pending update
is not reported as a service failure.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.capture_live_issues import capture_issues  # noqa: E402
from scripts.prune_settlement_backups import prune_backups, replay_anchors  # noqa: E402
from src.settlement_issue_addition import bundle_rows, issue_verdict, read_bundle  # noqa: E402

# The rules that decide what is actionable: hashed into every status so a stored verdict can
# be tied to the implementation that produced it.
_IMPLEMENTATION = ("src/settlement_issue_addition.py", "src/nowscore_settlement.py",
                   "scripts/capture_live_issues.py", "src/nowscore_live_issues.py",
                   "scripts/run_live_issue_check.py", "scripts/prune_settlement_backups.py")


def _manifest_sha256(bundle_dir) -> str | None:
    """The judged bundle's manifest hash, or None when this run judged no bundle.

    A bundle captured earlier today is bound too: the verdict is read from its bytes, so the
    status has to name which bytes those were. A manifest that cannot be parsed is a state to
    report rather than a reason to lose the status file.
    """
    if not bundle_dir:
        return None
    try:
        return read_bundle(Path(bundle_dir)).get("sha256")
    except (OSError, ValueError):
        return None


def _file_sha256(path: Path) -> str | None:
    """Content hash of `path`, or None when it cannot be read."""
    import hashlib
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def run_check(database: Path, updates_root: Path, backups_root: Path, *, keep: int,
              timeout_seconds: float, interval_seconds: float, transport=None, now=None,
              registry=None, implementation=None) -> dict:
    """Capture pending issues into a dated bundle and report the state.

    The bundle directory is named for the day it was taken, so a second run on the same day
    does not silently overwrite the first run's evidence; it is reported as already captured
    instead.
    """
    updates_root = Path(updates_root)
    updates_root.mkdir(parents=True, exist_ok=True)
    clock = now or (lambda: datetime.now(timezone.utc))
    today = clock().strftime("%Y%m%d")
    bundle = updates_root / f"bundle-{today}"
    status_path = updates_root / f"status-{today}.json"
    state: dict = {}
    if bundle.exists():
        state = {"status": "already_captured_today", "bundle": str(bundle)}
    else:
        try:
            state = capture_issues(database, bundle, timeout_seconds=timeout_seconds,
                                   interval_seconds=interval_seconds, transport=transport,
                                   now=now)
        except Exception as error:                      # noqa: BLE001 - recorded, not swallowed
            state = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    # An alert is only useful when it is actionable: a round still in progress is pending but
    # cannot be added, so it is reported with its reasons instead of asking for approval. A
    # bundle captured earlier today is judged from its own bytes rather than skipped, so a
    # second run cannot quietly clear an outstanding approval request.
    bundle_path = Path(state["bundle"]) if state.get("bundle") else None
    judgeable = (state.get("status") == "captured"
                 or (state.get("status") == "already_captured_today" and bundle_path
                     and (bundle_path / "manifest.json").is_file()))
    if judgeable:
        try:
            document = read_bundle(bundle_path)
            parsed = bundle_rows(document)
            issues = state.get("pending") or document["manifest"]["requested_issues"]
            eligible, ineligible = [], []
            for issue in issues:
                resolved, problems = issue_verdict(parsed[issue])
                if problems:
                    ineligible.append({"issue": issue, "problems": problems[:5]})
                else:
                    eligible.append(issue)
            state["pending"] = list(issues)
            state["eligible"] = eligible
            state["ineligible"] = ineligible
        except Exception as error:                      # noqa: BLE001 - recorded, not swallowed
            state["status"] = "failed"
            state["error"] = f"{type(error).__name__}: {error}"
            state["unjudged_bundle"] = state.get("bundle")
    pruned = None
    if backups_root and Path(backups_root).is_dir():
        # Retention failures are recorded like any other: the check's job is to report the
        # state, and a refusal to delete is a state, not a reason to lose the status file.
        try:
            claims, retired = replay_anchors(database, registry=registry,
                                             bundles_root=updates_root)
            pruned = prune_backups(Path(backups_root), keep=keep, apply=True,
                                   release=database, protect=claims, retired=retired)
        except Exception as error:                      # noqa: BLE001 - recorded, not swallowed
            pruned = {"status": "refused", "error": f"{type(error).__name__}: {error}"}
    state["checked_at"] = clock().isoformat()
    state["pruned"] = pruned
    if isinstance(pruned, dict):
        # A refused prune still says which directory it was asked to prune.
        pruned["directory"] = str(backups_root) if backups_root else None
    bundle_dir = state.get("bundle")
    # A status an operator can act on has to name what it judged: the bundle it read, the
    # release it compared against, and the rules that produced the verdict.
    state["bindings"] = {
        "release": {"path": str(database), "sha256": _file_sha256(database)},
        "manifest_sha256": _manifest_sha256(bundle_dir if judgeable else None),
        "implementation": {str(path): _file_sha256(Path(path))
                           for path in (implementation or _IMPLEMENTATION)},
        # The evidence the verdict and the retention decision were read from, by identity:
        # edited anchor evidence must not produce the same bindings as the original.
        "evidence": {"registry": {"path": str(registry) if registry else None,
                                  "sha256": _file_sha256(registry) if registry else None},
                     "receipts": {str(receipt): _file_sha256(receipt) for receipt in
                                  sorted(Path(updates_root).glob("*/applied.json"))}
                     if updates_root else {}},
        "parameters": {"keep_backups": keep, "timeout": timeout_seconds,
                       "request_interval": interval_seconds,
                       "database": str(database), "updates_root": str(updates_root),
                       "backups_root": str(backups_root) if backups_root else None,
                       "registry": str(registry) if registry else None},
    }
    state["needs_approval"] = bool(state.get("eligible"))
    status_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**state, "status_file": str(status_path)}


def main(argv=None):
    """One scheduled check: capture what is pending, prune backups, record the state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--updates-root", required=True, type=Path)
    parser.add_argument("--backups-root", type=Path)
    parser.add_argument("--keep-backups", type=int, default=2)
    parser.add_argument("--registry", type=Path,
                        help="registry whose corrections name further replay anchors")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--request-interval", type=float, default=2.0)
    args = parser.parse_args(argv)
    result = run_check(args.database, args.updates_root, args.backups_root,
                       keep=args.keep_backups, timeout_seconds=args.timeout,
                       interval_seconds=args.request_interval, registry=args.registry)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
