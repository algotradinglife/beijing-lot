from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import a9_coordination as a9  # noqa: E402


BASE_NOW = datetime.fromisoformat("2026-07-16T12:00:00+08:00")


def write_bundle(path: Path, payloads: Mapping[str, str]) -> None:
    path.mkdir(parents=True)
    for name, content in payloads.items():
        (path / name).write_text(content, encoding="utf-8")
    (path / "SHA256SUMS").write_text(
        "".join(f"{a9.sha256_file(path / name)}  {name}\n" for name in sorted(payloads)),
        encoding="utf-8",
    )


def make_overlap(path: Path, *, cutoff_minutes: int = 30, issue: str = "DRY001") -> Path:
    fields = ["issue", "match_idx", "sale_end_at_hkt", "strict_three_market_overlap"]
    rows = [
        {
            "issue": issue,
            "match_idx": 1,
            "sale_end_at_hkt": (BASE_NOW + timedelta(minutes=cutoff_minutes)).isoformat(),
            "strict_three_market_overlap": 1,
        },
        {
            "issue": issue,
            "match_idx": 2,
            "sale_end_at_hkt": (BASE_NOW + timedelta(minutes=cutoff_minutes + 5)).isoformat(),
            "strict_three_market_overlap": 1,
        },
        {
            "issue": issue,
            "match_idx": 3,
            "sale_end_at_hkt": (BASE_NOW + timedelta(minutes=cutoff_minutes + 10)).isoformat(),
            "strict_three_market_overlap": 0,
        },
    ]
    path.mkdir(parents=True)
    with (path / "overlap_matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (path / "manifest.json").write_text(
        json.dumps({"schema_version": "non_live_overlap_fixture_v1"}) + "\n",
        encoding="utf-8",
    )
    (path / "summary.json").write_text(
        json.dumps({"issue": issue, "matches": 3, "strict_three_market_matches": 2}) + "\n",
        encoding="utf-8",
    )
    payloads = ["manifest.json", "overlap_matrix.csv", "summary.json"]
    (path / "SHA256SUMS").write_text(
        "".join(f"{a9.sha256_file(path / name)}  {name}\n" for name in payloads),
        encoding="utf-8",
    )
    return path


class FakeResearch:
    def __init__(self, root: Path, *, settlement_ready: bool = True) -> None:
        self.root = root
        self.settlement_ready = settlement_ready
        self.freeze_calls = 0
        self.settle_calls = 0

    @staticmethod
    def suffix(event: Mapping[str, Any]) -> str:
        return str(event["overlap_sha256s_sha256"])[:12]

    def freeze_path(self, event: Mapping[str, Any]) -> Path:
        return self.root / f"freeze-{event['issue']}-{self.suffix(event)}"

    def settlement_path(self, event: Mapping[str, Any]) -> Path:
        return self.root / f"settlement-{event['issue']}-{self.suffix(event)}"

    def freeze(self, event: Mapping[str, Any]) -> Path:
        self.freeze_calls += 1
        output = self.freeze_path(event)
        write_bundle(
            output,
            {
                "manifest.json": json.dumps(
                    {
                        "issue": event["issue"],
                        "overlap_sha256s_sha256": event["overlap_sha256s_sha256"],
                        "production_promotion_allowed": False,
                    }
                )
                + "\n"
            },
        )
        return output

    def verify_freeze(self, path: Path, event: Mapping[str, Any]) -> None:
        a9.verify_checksum_bundle(path, {"manifest.json"})
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["issue"] == event["issue"]
        assert manifest["overlap_sha256s_sha256"] == event["overlap_sha256s_sha256"]
        assert manifest["production_promotion_allowed"] is False

    def status(self, path: Path) -> Mapping[str, Any]:
        del path
        return {
            "frozen_rows": 2,
            "settled_rows": 2 if self.settlement_ready else 1,
            "settlement_ready": self.settlement_ready,
        }

    def settle(self, path: Path, event: Mapping[str, Any]) -> Path:
        del path
        self.settle_calls += 1
        output = self.settlement_path(event)
        write_bundle(
            output,
            {
                "summary.json": json.dumps(
                    {"issue": event["issue"], "production_promotion_allowed": False}
                )
                + "\n"
            },
        )
        return output

    def verify_settlement(self, path: Path) -> None:
        a9.verify_checksum_bundle(path, {"summary.json"})
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
        assert summary["production_promotion_allowed"] is False


def publish_fixture(tmp_path: Path, *, cutoff_minutes: int = 30) -> tuple[Path, Path]:
    overlap = make_overlap(tmp_path / "non-live-overlap", cutoff_minutes=cutoff_minutes)
    coordination = tmp_path / "coordination"
    published = a9.publish_input_ready(
        coordination,
        "DRY001",
        overlap,
        emitted_at=BASE_NOW,
    )
    assert published["created"] is True
    return coordination, Path(published["event_path"])


def test_dry_run_rejects_bad_event_digest(tmp_path: Path) -> None:
    _, event = publish_fixture(tmp_path)
    manifest = event / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8") + " ", encoding="utf-8")

    research = FakeResearch(tmp_path / "research")
    with pytest.raises(a9.A9CoordinationError, match="checksum mismatch"):
        a9.process_freeze(event, research, now=BASE_NOW)
    assert research.freeze_calls == 0


def test_dry_run_duplicate_event_is_idempotent_and_freezes_once(tmp_path: Path) -> None:
    coordination, event = publish_fixture(tmp_path)
    overlap = tmp_path / "non-live-overlap"
    duplicate = a9.publish_input_ready(
        coordination,
        "DRY001",
        overlap,
        emitted_at=BASE_NOW + timedelta(minutes=1),
    )
    assert duplicate["created"] is False

    research = FakeResearch(tmp_path / "research")
    first = a9.process_freeze(event, research, now=BASE_NOW)
    second = a9.process_freeze(event, research, now=BASE_NOW + timedelta(minutes=1))
    assert first["state"] == second["state"] == "FROZEN"
    assert first["artifact_path"] == second["artifact_path"]
    assert research.freeze_calls == 1
    assert len(list((tmp_path / "research").glob("freeze-*"))) == 1


def test_dry_run_rejects_expired_cutoff_without_snapshot(tmp_path: Path) -> None:
    _, event = publish_fixture(tmp_path, cutoff_minutes=9)
    research = FakeResearch(tmp_path / "research")

    result = a9.process_freeze(event, research, now=BASE_NOW)
    assert result["state"] == "FREEZE_EXPIRED"
    assert result["time_to_cutoff_seconds"] == 9 * 60
    assert research.freeze_calls == 0
    assert not (tmp_path / "research").exists()


def test_dry_run_rejects_partial_settlement_without_artifact(tmp_path: Path) -> None:
    _, event = publish_fixture(tmp_path)
    research = FakeResearch(tmp_path / "research", settlement_ready=False)
    a9.process_freeze(event, research, now=BASE_NOW)

    result = a9.process_settlement(event, research)
    assert result["state"] == "SETTLEMENT_REJECTED"
    assert result["settlement_count"] == "1/2"
    assert research.settle_calls == 0
    assert not research.settlement_path(a9.verify_input_ready(event)).exists()


def test_dry_run_non_live_fixture_success_chain(tmp_path: Path) -> None:
    coordination, event = publish_fixture(tmp_path)
    research = FakeResearch(tmp_path / "research")

    frozen = a9.scan_ready_events(coordination, research, now=BASE_NOW)
    assert len(frozen) == 1
    assert frozen[0]["state"] == "FROZEN"
    assert set(frozen[0]) == {
        "event_id",
        "artifact_path",
        "artifact_sha256",
        "state",
        "time_to_cutoff_seconds",
    }
    settled = a9.process_settlement(event, research)
    assert settled["state"] == "SETTLED"
    assert settled["settlement_count"] == "2/2"
    assert research.freeze_calls == 1
    assert research.settle_calls == 1
    assert Path(frozen[0]["artifact_path"]).is_relative_to(tmp_path / "research")
    assert Path(settled["artifact_path"]).is_relative_to(tmp_path / "research")
