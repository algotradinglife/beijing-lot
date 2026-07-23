"""Production-owned immutable coordination for the paper-only A9 monitor."""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol


HKT = timezone(timedelta(hours=8))
EVENT_SCHEMA = "strategy_parallel_forward_event_v1"
EVENT_TYPE = "A9_INPUT_READY"
EVENT_DIR_NAME = "A9_INPUT_READY_v1"
PRODUCER = "beijing-lot-production-session"
MIN_FREEZE_MARGIN = timedelta(minutes=10)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class A9CoordinationError(ValueError):
    """Raised when an A9 coordination invariant is violated."""


@dataclass(frozen=True)
class OverlapFacts:
    issue: str
    overlap_dir: Path
    overlap_sha256s_sha256: str
    earliest_sale_cutoff_hkt: datetime
    issue_rows: int
    eligible_rows: int
    excluded_match_indices: tuple[int, ...]

    @property
    def coverage(self) -> float:
        return self.eligible_rows / self.issue_rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _fsync_file(path)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def parse_hkt(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise A9CoordinationError(f"invalid HKT timestamp: {value}") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def verify_checksum_bundle(path: Path, required: set[str] | None = None) -> dict[str, str]:
    sums = path / "SHA256SUMS"
    if not sums.is_file():
        raise A9CoordinationError(f"SHA256SUMS missing: {path}")
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as error:
            raise A9CoordinationError(f"invalid SHA256SUMS line: {line!r}") from error
        relative = Path(name)
        if not SHA256_RE.fullmatch(digest) or relative.is_absolute() or ".." in relative.parts:
            raise A9CoordinationError(f"invalid SHA256SUMS entry: {line!r}")
        if name in entries:
            raise A9CoordinationError(f"duplicate SHA256SUMS entry: {name}")
        target = path / relative
        if not target.is_file() or sha256_file(target) != digest:
            raise A9CoordinationError(f"checksum mismatch: {target}")
        entries[name] = digest
    if not entries:
        raise A9CoordinationError(f"empty SHA256SUMS: {path}")
    if required is not None and not required.issubset(entries):
        missing = sorted(required - entries.keys())
        raise A9CoordinationError(f"checksum manifest missing required files: {missing}")
    return entries


def load_overlap_facts(overlap_dir: Path, issue: str) -> OverlapFacts:
    overlap = overlap_dir.expanduser().resolve()
    if not overlap.is_dir():
        raise A9CoordinationError(f"overlap directory missing: {overlap}")
    verify_checksum_bundle(overlap, {"overlap_matrix.csv", "manifest.json", "summary.json"})
    with (overlap / "overlap_matrix.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_fields = {
            "issue",
            "match_idx",
            "sale_end_at_hkt",
            "strict_three_market_overlap",
        }
        if not required_fields.issubset(reader.fieldnames or ()):
            raise A9CoordinationError("overlap matrix schema is incomplete")
        rows = [dict(row) for row in reader if row["issue"] == issue]
    if not rows:
        raise A9CoordinationError(f"overlap contains no rows for issue {issue}")
    try:
        indices = [int(row["match_idx"]) for row in rows]
    except ValueError as error:
        raise A9CoordinationError("overlap match_idx must be an integer") from error
    if len(indices) != len(set(indices)) or any(index <= 0 for index in indices):
        raise A9CoordinationError("overlap match indices are duplicated or invalid")
    eligible = [row for row in rows if row["strict_three_market_overlap"] == "1"]
    invalid_flags = sorted(
        {row["strict_three_market_overlap"] for row in rows} - {"0", "1"}
    )
    if invalid_flags:
        raise A9CoordinationError(f"invalid strict overlap flags: {invalid_flags}")
    if not eligible:
        raise A9CoordinationError("overlap has no eligible strict three-market rows")
    earliest = min(parse_hkt(row["sale_end_at_hkt"]) for row in eligible)
    selected_indices = {int(row["match_idx"]) for row in eligible}
    excluded = tuple(sorted(set(indices) - selected_indices))

    summary = json.loads((overlap / "summary.json").read_text(encoding="utf-8"))
    if str(summary.get("issue")) != issue:
        raise A9CoordinationError("overlap summary issue disagrees with requested issue")
    if int(summary.get("matches", -1)) != len(rows):
        raise A9CoordinationError("overlap summary row count disagrees with matrix")
    if int(summary.get("strict_three_market_matches", -1)) != len(eligible):
        raise A9CoordinationError("overlap summary eligibility disagrees with matrix")
    return OverlapFacts(
        issue=issue,
        overlap_dir=overlap,
        overlap_sha256s_sha256=sha256_file(overlap / "SHA256SUMS"),
        earliest_sale_cutoff_hkt=earliest,
        issue_rows=len(rows),
        eligible_rows=len(eligible),
        excluded_match_indices=excluded,
    )


def event_id_for(issue: str, overlap_sha256s_sha256: str) -> str:
    if not issue or any(character in issue for character in "/\\"):
        raise A9CoordinationError(f"invalid issue: {issue!r}")
    if not SHA256_RE.fullmatch(overlap_sha256s_sha256):
        raise A9CoordinationError("invalid overlap SHA-256")
    return f"A9:{issue}:{overlap_sha256s_sha256}"


def event_path(coordination_root: Path, issue: str) -> Path:
    return coordination_root.expanduser().resolve() / "a9" / issue / EVENT_DIR_NAME


def _write_bundle(stage: Path, filename: str, payload: Mapping[str, Any]) -> None:
    write_json(stage / filename, payload)
    sums = stage / "SHA256SUMS"
    sums.write_text(f"{sha256_file(stage / filename)}  {filename}\n", encoding="utf-8")
    _fsync_file(sums)
    verify_checksum_bundle(stage, {filename})


def _atomic_publish(final: Path, filename: str, payload: Mapping[str, Any]) -> Path:
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    try:
        _write_bundle(stage, filename, payload)
        _fsync_dir(stage)
        try:
            stage.rename(final)
        except OSError:
            if not final.is_dir():
                raise
        _fsync_dir(final.parent)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return final


def publish_input_ready(
    coordination_root: Path,
    issue: str,
    overlap_dir: Path,
    *,
    emitted_at: datetime | None = None,
) -> dict[str, Any]:
    facts = load_overlap_facts(overlap_dir, issue)
    emitted = (emitted_at or datetime.now(HKT)).astimezone(HKT)
    manifest = {
        "schema_version": EVENT_SCHEMA,
        "event_type": EVENT_TYPE,
        "event_id": event_id_for(issue, facts.overlap_sha256s_sha256),
        "issue": issue,
        "status": "READY",
        "emitted_at_hkt": emitted.isoformat(),
        "overlap_dir": str(facts.overlap_dir),
        "overlap_sha256s_sha256": facts.overlap_sha256s_sha256,
        "earliest_sale_cutoff_hkt": facts.earliest_sale_cutoff_hkt.isoformat(),
        "issue_rows": facts.issue_rows,
        "eligible_rows": facts.eligible_rows,
        "coverage": facts.coverage,
        "excluded_match_indices": list(facts.excluded_match_indices),
        "producer": PRODUCER,
    }
    final = event_path(coordination_root, issue)
    if final.exists():
        existing = verify_input_ready(final)
        if existing["event_id"] != manifest["event_id"]:
            raise A9CoordinationError(
                f"issue {issue} already has a different immutable A9 event"
            )
        return {**existing, "event_path": str(final), "created": False}
    _atomic_publish(final, "manifest.json", manifest)
    verified = verify_input_ready(final)
    return {**verified, "event_path": str(final), "created": True}


def verify_input_ready(path: Path) -> dict[str, Any]:
    event_dir = path.expanduser().resolve()
    if {item.name for item in event_dir.iterdir()} != {"manifest.json", "SHA256SUMS"}:
        raise A9CoordinationError("event bundle must contain only manifest.json and SHA256SUMS")
    entries = verify_checksum_bundle(event_dir, {"manifest.json"})
    if set(entries) != {"manifest.json"}:
        raise A9CoordinationError("event SHA256SUMS must cover only manifest.json")
    manifest = json.loads((event_dir / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "event_type",
        "event_id",
        "issue",
        "status",
        "emitted_at_hkt",
        "overlap_dir",
        "overlap_sha256s_sha256",
        "earliest_sale_cutoff_hkt",
        "issue_rows",
        "eligible_rows",
        "coverage",
        "excluded_match_indices",
        "producer",
    }
    if not required.issubset(manifest):
        raise A9CoordinationError(f"event manifest fields missing: {sorted(required - manifest.keys())}")
    if (
        manifest["schema_version"] != EVENT_SCHEMA
        or manifest["event_type"] != EVENT_TYPE
        or manifest["status"] != "READY"
        or manifest["producer"] != PRODUCER
    ):
        raise A9CoordinationError("event identity or status is invalid")
    emitted = datetime.fromisoformat(str(manifest["emitted_at_hkt"]))
    if emitted.utcoffset() != timedelta(hours=8):
        raise A9CoordinationError("event emitted_at_hkt must use +08:00")
    issue = str(manifest["issue"])
    expected_id = event_id_for(issue, str(manifest["overlap_sha256s_sha256"]))
    if manifest["event_id"] != expected_id:
        raise A9CoordinationError("event_id does not match issue and overlap digest")
    overlap = Path(str(manifest["overlap_dir"]))
    if not overlap.is_absolute() or str(overlap.resolve()) != str(overlap):
        raise A9CoordinationError("overlap_dir must be an absolute canonical path")
    facts = load_overlap_facts(overlap, issue)
    expected = {
        "overlap_sha256s_sha256": facts.overlap_sha256s_sha256,
        "earliest_sale_cutoff_hkt": facts.earliest_sale_cutoff_hkt.isoformat(),
        "issue_rows": facts.issue_rows,
        "eligible_rows": facts.eligible_rows,
        "excluded_match_indices": list(facts.excluded_match_indices),
    }
    for field, value in expected.items():
        if manifest[field] != value:
            raise A9CoordinationError(f"event {field} disagrees with overlap")
    if abs(float(manifest["coverage"]) - facts.coverage) > 1e-12:
        raise A9CoordinationError("event coverage disagrees with overlap")
    manifest["event_sha256s_sha256"] = sha256_file(event_dir / "SHA256SUMS")
    return manifest


class ResearchAdapter(Protocol):
    def freeze_path(self, event: Mapping[str, Any]) -> Path: ...

    def settlement_path(self, event: Mapping[str, Any]) -> Path: ...

    def freeze(self, event: Mapping[str, Any]) -> Path: ...

    def verify_freeze(self, path: Path, event: Mapping[str, Any]) -> None: ...

    def status(self, path: Path) -> Mapping[str, Any]: ...

    def settle(self, path: Path, event: Mapping[str, Any]) -> Path: ...

    def verify_settlement(self, path: Path) -> None: ...


class SubprocessResearchAdapter:
    """Invoke the research-owned A9 CLI without interpreting strategy output."""

    def __init__(self, research_root: Path, python: Path | None = None) -> None:
        self.root = research_root.expanduser().resolve()
        self.python = (python or self.root / ".venv/bin/python").expanduser().resolve()
        self.script = self.root / "scripts/monitor_strategy_parallel_simple_runner_forward.py"
        if not self.root.is_dir() or not self.python.is_file() or not self.script.is_file():
            raise A9CoordinationError(f"research A9 runtime is incomplete: {self.root}")

    @staticmethod
    def _suffix(event: Mapping[str, Any]) -> str:
        return str(event["overlap_sha256s_sha256"])[:12]

    def freeze_path(self, event: Mapping[str, Any]) -> Path:
        return self.root / "results/strategy_parallel" / (
            f"S13_A9_{event['issue']}_{self._suffix(event)}_freeze_v1"
        )

    def settlement_path(self, event: Mapping[str, Any]) -> Path:
        return self.root / "results/strategy_parallel" / (
            f"S13_A9_{event['issue']}_{self._suffix(event)}_settlement_v1"
        )

    def _run(self, *arguments: str) -> Mapping[str, Any]:
        completed = subprocess.run(
            [str(self.python), str(self.script), *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise A9CoordinationError(f"research A9 command failed: {detail[-2000:]}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise A9CoordinationError("research A9 command returned invalid JSON") from error

    def freeze(self, event: Mapping[str, Any]) -> Path:
        output = self.freeze_path(event)
        self._run(
            "freeze",
            "--issue",
            str(event["issue"]),
            "--overlap-dir",
            str(event["overlap_dir"]),
            "--output-dir",
            str(output),
        )
        return output

    def verify_freeze(self, path: Path, event: Mapping[str, Any]) -> None:
        self._run("verify", "--snapshot-dir", str(path))
        verify_checksum_bundle(path, {"manifest.json", "frozen_predictions.csv"})
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if str(manifest.get("issue")) != str(event["issue"]):
            raise A9CoordinationError("research freeze issue disagrees with event")
        if manifest.get("inputs", {}).get("overlap_sha256s_sha256") != event["overlap_sha256s_sha256"]:
            raise A9CoordinationError("research freeze overlap digest disagrees with event")
        if manifest.get("production_promotion_allowed") is not False:
            raise A9CoordinationError("research freeze is not paper-only")

    def status(self, path: Path) -> Mapping[str, Any]:
        return self._run("status", "--snapshot-dir", str(path))

    def settle(self, path: Path, event: Mapping[str, Any]) -> Path:
        output = self.settlement_path(event)
        self._run(
            "settle",
            "--snapshot-dir",
            str(path),
            "--output-dir",
            str(output),
        )
        return output

    def verify_settlement(self, path: Path) -> None:
        self._run("verify-settlement", "--output-dir", str(path))
        verify_checksum_bundle(path, {"summary.json"})
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        if summary.get("production_promotion_allowed") is not False:
            raise A9CoordinationError("research settlement is not paper-only")


@contextmanager
def event_lock(event_dir: Path, event_id: str) -> Iterator[None]:
    lock_root = event_dir.parent / ".orchestration" / "locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(event_id.encode("utf-8")).hexdigest() + ".lock"
    with (lock_root / name).open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _notification_dir(event_dir: Path, state: str) -> Path:
    return event_dir.parent / ".orchestration" / "notifications" / f"{state}_v1"


def _read_notification(path: Path) -> dict[str, Any]:
    verify_checksum_bundle(path, {"notification.json"})
    return json.loads((path / "notification.json").read_text(encoding="utf-8"))


def publish_notification(
    event_dir: Path,
    *,
    event_id: str,
    artifact_path: Path,
    artifact_sha256: str,
    state: str,
    time_to_cutoff_seconds: int | None = None,
    settlement_count: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_id": event_id,
        "artifact_path": str(artifact_path.resolve()),
        "artifact_sha256": artifact_sha256,
        "state": state,
    }
    if time_to_cutoff_seconds is not None:
        payload["time_to_cutoff_seconds"] = time_to_cutoff_seconds
    if settlement_count is not None:
        payload["settlement_count"] = settlement_count
    final = _notification_dir(event_dir, state)
    if final.exists():
        existing = _read_notification(final)
        stable_fields = {"event_id", "artifact_path", "artifact_sha256", "state"}
        if any(existing.get(field) != payload.get(field) for field in stable_fields):
            raise A9CoordinationError(f"immutable {state} notification conflicts with current result")
        return existing
    _atomic_publish(final, "notification.json", payload)
    return _read_notification(final)


def process_freeze(
    event_dir: Path,
    research: ResearchAdapter,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    event = verify_input_ready(event_dir)
    current = (now or datetime.now(HKT)).astimezone(HKT)
    cutoff = parse_hkt(str(event["earliest_sale_cutoff_hkt"]))
    margin = cutoff - current
    with event_lock(event_dir, str(event["event_id"])):
        expired_notification = _notification_dir(event_dir, "FREEZE_EXPIRED")
        if expired_notification.exists():
            return _read_notification(expired_notification)
        if margin < MIN_FREEZE_MARGIN:
            return publish_notification(
                event_dir,
                event_id=str(event["event_id"]),
                artifact_path=event_dir,
                artifact_sha256=str(event["event_sha256s_sha256"]),
                state="FREEZE_EXPIRED",
                time_to_cutoff_seconds=int(margin.total_seconds()),
            )
        snapshot = research.freeze_path(event)
        if not snapshot.exists():
            snapshot = research.freeze(event)
        research.verify_freeze(snapshot, event)
        return publish_notification(
            event_dir,
            event_id=str(event["event_id"]),
            artifact_path=snapshot,
            artifact_sha256=sha256_file(snapshot / "SHA256SUMS"),
            state="FROZEN",
            time_to_cutoff_seconds=int(margin.total_seconds()),
        )


def process_settlement(event_dir: Path, research: ResearchAdapter) -> dict[str, Any]:
    event = verify_input_ready(event_dir)
    with event_lock(event_dir, str(event["event_id"])):
        snapshot = research.freeze_path(event)
        if not snapshot.exists():
            raise A9CoordinationError("cannot settle before a frozen research snapshot exists")
        research.verify_freeze(snapshot, event)
        status = research.status(snapshot)
        settled = int(status.get("settled_rows", 0))
        frozen = int(status.get("frozen_rows", 0))
        if frozen <= 0 or settled < 0 or settled > frozen:
            raise A9CoordinationError("research settlement status counts are invalid")
        if status.get("settlement_ready") is not True or settled != frozen:
            return publish_notification(
                event_dir,
                event_id=str(event["event_id"]),
                artifact_path=snapshot,
                artifact_sha256=sha256_file(snapshot / "SHA256SUMS"),
                state="SETTLEMENT_REJECTED",
                settlement_count=f"{settled}/{frozen}",
            )
        output = research.settlement_path(event)
        if not output.exists():
            output = research.settle(snapshot, event)
        research.verify_settlement(output)
        return publish_notification(
            event_dir,
            event_id=str(event["event_id"]),
            artifact_path=output,
            artifact_sha256=sha256_file(output / "SHA256SUMS"),
            state="SETTLED",
            settlement_count=f"{settled}/{frozen}",
        )


def scan_ready_events(
    coordination_root: Path,
    research: ResearchAdapter,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    a9_root = coordination_root.expanduser().resolve() / "a9"
    if not a9_root.exists():
        return []
    events = sorted(
        path
        for path in a9_root.glob(f"*/{EVENT_DIR_NAME}")
        if path.is_dir()
    )
    return [process_freeze(path, research, now=now) for path in events]
