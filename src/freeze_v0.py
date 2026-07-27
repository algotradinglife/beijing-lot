"""Research-only hourly snapshot freeze for BJ-ADHOC-CALIBRATION-001.

This deliberately small v0 store has no operational-package, database, API,
or settlement capability.  It only captures immutable pre-result snapshots and
selects one already-captured snapshot at cutoff.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


HKT = ZoneInfo("Asia/Hong_Kong")
SCHEMA_VERSION = "freeze_v0"
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "results" / "freeze_v0"
PAYLOAD_FILES = (
    "decision_input.json",
    "candidate_ticket_pool.json",
    "plans.json",
    "source_receipt.json",
)
REQUIRED_FILES = {"manifest.json", *PAYLOAD_FILES, "SHA256SUMS"}
FORBIDDEN_OUTCOME_PARTS = ("result", "final_score", "winning_sp", "settlement", "fthg", "ftag")


class FreezeV0Error(ValueError):
    """A snapshot does not meet the pre-result research contract."""


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe(value: object, label: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", text):
        raise FreezeV0Error(f"unsafe {label}")
    return text


def _as_hkt(value: datetime | str, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
        except ValueError as exc:
            raise FreezeV0Error(f"{label} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise FreezeV0Error(f"{label} must include a timezone")
    return parsed.astimezone(HKT)


def _iso(value: datetime | str, label: str) -> str:
    return _as_hkt(value, label).isoformat(timespec="seconds")


def _dump(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(canonical(value) + b"\n")


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeV0Error(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise FreezeV0Error(f"JSON artifact must be an object: {path.name}")
    return value


def _has_outcome(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            any(part in str(key).lower() for part in FORBIDDEN_OUTCOME_PARTS) or _has_outcome(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_has_outcome(item) for item in value)
    return False


def _files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def _sha_sums(root: Path) -> str:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    return "".join(f"{file_hash(path)}  {path.relative_to(root).as_posix()}\n" for path in paths)


def _verify_sha_sums(root: Path) -> None:
    sums = root / "SHA256SUMS"
    if not sums.is_file() or not sums.read_text(encoding="utf-8").strip():
        raise FreezeV0Error("SHA256SUMS is missing or empty")
    recorded: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        if not match:
            raise FreezeV0Error("SHA256SUMS is malformed")
        checksum, relative = match.groups()
        if relative in recorded or relative.startswith("/") or ".." in Path(relative).parts:
            raise FreezeV0Error("SHA256SUMS contains an unsafe or duplicate path")
        recorded[relative] = checksum
    actual = _files(root) - {"SHA256SUMS"}
    if set(recorded) != actual:
        raise FreezeV0Error("SHA256SUMS does not exactly cover snapshot files")
    if any(file_hash(root / relative) != checksum for relative, checksum in recorded.items()):
        raise FreezeV0Error("SHA256SUMS payload mismatch")


def hourly_attempt_times(*, available_at: datetime, cutoff_at: datetime, safety_margin: timedelta) -> list[datetime]:
    """Return hourly triggers plus a forced trigger before the completion cutoff."""
    available = _as_hkt(available_at, "available_at")
    cutoff = _as_hkt(cutoff_at, "cutoff_at")
    if safety_margin <= timedelta(0) or available >= cutoff:
        raise FreezeV0Error("invalid availability/cutoff schedule")
    forced_trigger = cutoff - safety_margin
    times: list[datetime] = []
    current = available
    while current <= forced_trigger:
        times.append(current)
        current += timedelta(hours=1)
    if forced_trigger >= available and (not times or times[-1] != forced_trigger):
        times.append(forced_trigger)
    return times


class FreezeV0Store:
    """Append-only issue snapshot series with a write-once cutoff selection."""

    def __init__(
        self,
        root: str | os.PathLike[str] = DEFAULT_ROOT,
        *,
        replay_candidate_pool: Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]] | None = None,
    ) -> None:
        self.root = Path(root)
        self.replay_candidate_pool = replay_candidate_pool

    def _issue_root(self, issue: str) -> Path:
        return self.root / _safe(issue, "issue")

    def _failure_path(self, issue: str, captured_at: datetime) -> Path:
        return self._issue_root(issue) / "failures" / f"{captured_at.strftime('%Y%m%dT%H%M%S%z')}.json"

    @staticmethod
    def _validate_input(
        *,
        issue: str,
        membership: list[dict[str, Any]],
        decision_input: dict[str, Any],
        candidate_ticket_pool: dict[str, Any],
        plans: dict[str, Any],
        source_receipt: dict[str, Any],
        captured_at: datetime,
        cutoff_at: datetime,
        replay_candidate_pool: Callable[[dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]] | None,
    ) -> None:
        if any(_has_outcome(value) for value in (decision_input, candidate_ticket_pool, plans, source_receipt)):
            raise FreezeV0Error("pre-result snapshot contains an outcome field")
        if not membership or not all(isinstance(item, dict) for item in membership):
            raise FreezeV0Error("complete issue membership is required")
        member_ids = [str(item.get("match_idx") or "") for item in membership]
        if not all(member_ids) or len(set(member_ids)) != len(member_ids):
            raise FreezeV0Error("issue membership needs unique match_idx values")
        matches = decision_input.get("matches")
        if not isinstance(matches, list) or not all(isinstance(item, dict) for item in matches) or {str(item.get("match_idx") or "") for item in matches} != set(member_ids):
            raise FreezeV0Error("decision input does not cover complete issue membership")
        if decision_input.get("formal_contract_version") != "v3.3.3":
            raise FreezeV0Error("formal v3.3.3 decision contract is required")
        if not decision_input.get("formal_input_sha256") or not source_receipt.get("source_sha256"):
            raise FreezeV0Error("formal input and source hashes are required")
        for match in matches:
            if set((match.get("p") or {})) != {"3", "1", "0"} or set((match.get("sp") or {})) != {"3", "1", "0"}:
                raise FreezeV0Error("complete 3/1/0 p and SP are required for every match")
            if not match.get("sale_cutoff_hkt") or not match.get("source_observed_at_hkt") or not match.get("sp_provenance_sha256"):
                raise FreezeV0Error("complete decision/SP provenance is required for every match")
            _as_hkt(match["sale_cutoff_hkt"], "sale_cutoff_hkt")
            if _as_hkt(match["source_observed_at_hkt"], "source_observed_at_hkt") > captured_at:
                raise FreezeV0Error("match source observation is after trusted capture")
        if source_receipt.get("issue") != issue or source_receipt.get("issue_membership") != membership:
            raise FreezeV0Error("source receipt does not bind issue membership")
        if not source_receipt.get("trusted_clock_provenance") or not source_receipt.get("source_observed_at_hkt"):
            raise FreezeV0Error("trusted capture/source clocks are required")
        if _as_hkt(source_receipt["source_observed_at_hkt"], "source_observed_at_hkt") > captured_at:
            raise FreezeV0Error("source receipt observation is after trusted capture")
        source_cutoff = _as_hkt(source_receipt.get("cutoff_at_hkt"), "source_receipt.cutoff_at_hkt")
        earliest_kickoff = _as_hkt(source_receipt.get("earliest_kickoff_at_hkt"), "source_receipt.earliest_kickoff_at_hkt")
        if source_cutoff != cutoff_at or source_cutoff > earliest_kickoff:
            raise FreezeV0Error("caller cutoff disagrees with frozen source receipt")
        if captured_at > cutoff_at:
            raise FreezeV0Error("snapshot capture completed after cutoff")
        if candidate_ticket_pool.get("input_sha256") != digest(decision_input) or not candidate_ticket_pool.get("generator_version") or not candidate_ticket_pool.get("generator_contract") or candidate_ticket_pool.get("seed") is None:
            raise FreezeV0Error("candidate pool generator contract is incomplete")
        if not isinstance(candidate_ticket_pool.get("candidates"), list):
            raise FreezeV0Error("complete candidate_ticket_pool is required")
        if not plans.get("contract_version") or plans.get("input_sha256") != digest(decision_input) or plans.get("candidate_pool_sha256") != digest(candidate_ticket_pool):
            raise FreezeV0Error("deterministic plans must bind the complete candidate pool")
        if not all(isinstance(plans.get(name), dict) and plans[name].get("status") for name in ("actual", "disjoint_unit", "disjoint_equal_yuan", "disjoint_risk_parity")):
            raise FreezeV0Error("deterministic four-arm plans are required")
        if replay_candidate_pool is None:
            raise FreezeV0Error("independent candidate-pool replayer is required")
        replayed_pool, replayed_plans = replay_candidate_pool(decision_input, source_receipt)
        if canonical(replayed_pool) != canonical(candidate_ticket_pool) or canonical(replayed_plans) != canonical(plans):
            raise FreezeV0Error("candidate pool or plans fail deterministic replay")

    def capture_attempt(
        self,
        *,
        issue: str,
        membership: list[dict[str, Any]],
        decision_input: dict[str, Any],
        candidate_ticket_pool: dict[str, Any],
        plans: dict[str, Any],
        source_receipt: dict[str, Any],
        captured_at: datetime,
        cutoff_at: datetime,
    ) -> dict[str, Any]:
        """Publish one PASS snapshot or a failure receipt; never raise partial bytes."""
        safe_issue = _safe(issue, "issue")
        captured = _as_hkt(captured_at, "captured_at")
        cutoff = _as_hkt(cutoff_at, "cutoff_at")
        try:
            self._validate_input(
                issue=safe_issue, membership=membership, decision_input=decision_input,
                candidate_ticket_pool=candidate_ticket_pool, plans=plans, source_receipt=source_receipt,
                captured_at=captured, cutoff_at=cutoff,
                replay_candidate_pool=self.replay_candidate_pool,
            )
            return self._publish_attempt(
                issue=safe_issue, membership=membership, decision_input=decision_input,
                candidate_ticket_pool=candidate_ticket_pool, plans=plans, source_receipt=source_receipt,
                captured_at=captured, cutoff_at=cutoff,
            )
        except FreezeV0Error as exc:
            return self._publish_failure(issue=safe_issue, captured_at=captured, reason=str(exc))

    def _publish_attempt(self, **payload: Any) -> dict[str, Any]:
        issue = payload["issue"]
        captured: datetime = payload["captured_at"]
        cutoff: datetime = payload["cutoff_at"]
        issue_root = self._issue_root(issue)
        staging = issue_root / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix="attempt-", dir=staging))
        try:
            for name in PAYLOAD_FILES:
                key = name.removesuffix(".json")
                _dump(stage / name, payload[key])
            content = {
                "schema_version": SCHEMA_VERSION,
                "issue": issue,
                "captured_at_hkt": _iso(captured, "captured_at"),
                "cutoff_at_hkt": _iso(cutoff, "cutoff_at"),
                "earliest_kickoff_at_hkt": payload["source_receipt"]["earliest_kickoff_at_hkt"],
                "issue_membership": payload["membership"],
                "payload_sha256": {name: file_hash(stage / name) for name in PAYLOAD_FILES},
                "research_only": True,
                "research_evidence_eligible": False,
                "operational_execution_enabled": False,
                "downloadable_for_purchase": False,
                "verifier_receipt": "PASS",
            }
            snapshot_id = digest(content)
            manifest = {**content, "snapshot_id": snapshot_id}
            _dump(stage / "manifest.json", manifest)
            (stage / "SHA256SUMS").write_text(_sha_sums(stage), encoding="utf-8")
            if _files(stage) != REQUIRED_FILES:
                raise FreezeV0Error("snapshot file layout mismatch")
            self._verify_dir(stage, expected_issue=issue, expected_snapshot_id=snapshot_id, require_final_path=False)
            final = issue_root / "attempts" / f"{captured.strftime('%Y%m%dT%H%M%S%z')}_{snapshot_id}"
            if final.exists():
                raise FreezeV0Error("snapshot identity already exists")
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, final)
            self._verify_dir(final, expected_issue=issue, expected_snapshot_id=snapshot_id)
            return {"status": "PASS", "snapshot_id": snapshot_id, "path": str(final)}
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    def _publish_failure(self, *, issue: str, captured_at: datetime, reason: str) -> dict[str, Any]:
        path = self._failure_path(issue, captured_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FreezeV0Error("failure receipt already exists for capture clock")
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "issue": issue,
            "captured_at_hkt": _iso(captured_at, "captured_at"),
            "status": "FAIL",
            "reason": reason,
            "research_evidence_eligible": False,
            "operational_execution_enabled": False,
            "downloadable_for_purchase": False,
        }
        _dump(path, receipt)
        return {"status": "FAIL", "path": str(path), "reason": reason}

    def _verify_dir(self, path: Path, *, expected_issue: str, expected_snapshot_id: str, require_final_path: bool = True) -> dict[str, Any]:
        if _files(path) != REQUIRED_FILES:
            raise FreezeV0Error("snapshot has missing or extra files")
        _verify_sha_sums(path)
        manifest = _load(path / "manifest.json")
        content = {key: value for key, value in manifest.items() if key != "snapshot_id"}
        if digest(content) != expected_snapshot_id or manifest.get("snapshot_id") != expected_snapshot_id:
            raise FreezeV0Error("snapshot content identity mismatch")
        if manifest.get("issue") != expected_issue or (require_final_path and path.name.rsplit("_", 1)[-1] != expected_snapshot_id):
            raise FreezeV0Error("snapshot issue/path identity mismatch")
        if manifest.get("research_only") is not True or manifest.get("research_evidence_eligible") is not False or manifest.get("operational_execution_enabled") is not False or manifest.get("downloadable_for_purchase") is not False or manifest.get("verifier_receipt") != "PASS":
            raise FreezeV0Error("snapshot research boundary violation")
        captured = _as_hkt(manifest.get("captured_at_hkt"), "captured_at_hkt")
        cutoff = _as_hkt(manifest.get("cutoff_at_hkt"), "cutoff_at_hkt")
        if captured > cutoff:
            raise FreezeV0Error("snapshot completed after cutoff")
        payload_hashes = manifest.get("payload_sha256")
        if not isinstance(payload_hashes, dict) or set(payload_hashes) != set(PAYLOAD_FILES):
            raise FreezeV0Error("snapshot payload contract mismatch")
        artifacts = {name: _load(path / name) for name in PAYLOAD_FILES}
        if any(_has_outcome(value) for value in artifacts.values()):
            raise FreezeV0Error("verified snapshot contains outcome data")
        for name, checksum in payload_hashes.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(checksum)) or file_hash(path / name) != checksum:
                raise FreezeV0Error("snapshot payload hash mismatch")
        self._validate_input(
            issue=expected_issue, membership=manifest.get("issue_membership"),
            decision_input=artifacts["decision_input.json"], candidate_ticket_pool=artifacts["candidate_ticket_pool.json"],
            plans=artifacts["plans.json"], source_receipt=artifacts["source_receipt.json"],
            captured_at=captured, cutoff_at=cutoff,
            replay_candidate_pool=self.replay_candidate_pool,
        )
        return manifest

    def verify_attempt(self, *, issue: str, snapshot_id: str) -> dict[str, Any]:
        safe_issue = _safe(issue, "issue")
        safe_snapshot_id = _safe(snapshot_id, "snapshot_id")
        matches = list((self._issue_root(safe_issue) / "attempts").glob(f"*_{safe_snapshot_id}"))
        if len(matches) != 1:
            raise FreezeV0Error("snapshot path is absent or ambiguous")
        return self._verify_dir(matches[0], expected_issue=safe_issue, expected_snapshot_id=safe_snapshot_id)

    def finalize_cutoff(self, *, issue: str, cutoff_at: datetime, finalized_at: datetime) -> dict[str, Any]:
        safe_issue = _safe(issue, "issue")
        cutoff = _as_hkt(cutoff_at, "cutoff_at")
        finalized = _as_hkt(finalized_at, "finalized_at")
        if finalized < cutoff:
            raise FreezeV0Error("FINAL cannot be written before cutoff")
        final_path = self._issue_root(safe_issue) / "FINAL.json"
        if final_path.exists():
            raise FreezeV0Error("FINAL.json is write-once")
        candidates: list[tuple[datetime, str, Path]] = []
        for path in (self._issue_root(safe_issue) / "attempts").glob("*_*"):
            snapshot_id = path.name.rsplit("_", 1)[-1]
            try:
                manifest = self._verify_dir(path, expected_issue=safe_issue, expected_snapshot_id=snapshot_id)
                captured = _as_hkt(manifest["captured_at_hkt"], "captured_at_hkt")
                if _as_hkt(manifest["cutoff_at_hkt"], "cutoff_at_hkt") == cutoff and captured <= cutoff:
                    candidates.append((captured, snapshot_id, path))
            except FreezeV0Error:
                continue
        if candidates:
            captured, snapshot_id, path = max(candidates, key=lambda value: value[0])
            final = {
                "schema_version": SCHEMA_VERSION, "issue": safe_issue, "status": "PASS",
                "snapshot_id": snapshot_id, "snapshot_path": str(path.relative_to(self._issue_root(safe_issue))),
                "snapshot_sha256": file_hash(path / "SHA256SUMS"), "captured_at_hkt": _iso(captured, "captured_at"),
                "cutoff_at_hkt": _iso(cutoff, "cutoff_at"), "finalized_at_hkt": _iso(finalized, "finalized_at"),
                "verifier_receipt": "PASS", "research_evidence_eligible": True,
            }
        else:
            final = {
                "schema_version": SCHEMA_VERSION, "issue": safe_issue, "status": "MISSED_FREEZE",
                "cutoff_at_hkt": _iso(cutoff, "cutoff_at"), "finalized_at_hkt": _iso(finalized, "finalized_at"),
                "verifier_receipt": "NO_VERIFIER_PASS", "research_evidence_eligible": False,
            }
        final_path.parent.mkdir(parents=True, exist_ok=True)
        _dump(final_path, final)
        return final
