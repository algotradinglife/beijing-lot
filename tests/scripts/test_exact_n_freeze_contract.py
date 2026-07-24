from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import publish_exact_n_segment_freeze as publisher
from scripts.verify_exact_n_freeze import verify_directory


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def payload_hash(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def write_payload(path: Path, value: dict[str, object]) -> str:
    claimed = payload_hash(value)
    path.write_bytes(canonical({**value, "sha256": claimed}) + b"\n")
    return claimed


def package(root: Path) -> Path:
    root.mkdir()
    common = {
        "segment_match_indices": [1, 2, 3],
        "segment_manifest_sha256": "a" * 64,
        "decision_input_sha256": "b" * 64,
        "scheduled_freeze_at": "2026-07-26T00:55:00+08:00",
        "effective_decision_at": "2026-07-26T00:50:00+08:00",
        "event_key": "c" * 64,
    }
    input_payload = {
        "schema_version": "exact_n_decision_input_v1",
        "issue": "26078",
        "segment_idx": 2,
        "segment_manifest_sha256": common["segment_manifest_sha256"],
        "structured_csv_sha256": common["decision_input_sha256"],
        "structured_csv_size_bytes": 100,
        "input_generated_at": "2026-07-26T00:40:00+08:00",
        "input_observed_at": common["effective_decision_at"],
        "final_refresh_opens_at": "2026-07-26T00:25:00+08:00",
        "effective_decision_at": common["effective_decision_at"],
    }
    input_sha = write_payload(root / "decision_input_manifest.json", input_payload)
    common["decision_input_manifest_sha256"] = input_sha
    artifacts: list[dict[str, object]] = [
        {
            "file": "decision_input_manifest.json",
            "sha256": input_sha,
            "artifact_type": "decision_input",
        }
    ]
    for n in (3, 4, 5, 6, 7):
        for budget in (512, 768, 1024):
            name = f"exact_n_{n}_budget_{budget}.json"
            value = {
                **common,
                "exact_n": True,
                "plan_id": f"26078_s2_n{n}_b{budget}",
                "requested_n": n,
                "artifact_n": n,
                "recommended_n": n,
                "requested_budget_yuan": budget,
                "base_cost_yuan": 0,
                "actual_cost_yuan": 0,
                "unused_budget_yuan": budget,
                "budget_utilization": 0,
                "status": "UNAVAILABLE_EXACT_N_BUDGET",
                "tickets": [],
            }
            claimed = write_payload(root / name, value)
            artifacts.append({"file": name, "sha256": claimed})
    score = {
        **common,
        "status": "UNAVAILABLE_CORRECT_SCORE_PLAN",
        "execution_enabled": False,
        "frontend_selectable": False,
        "roi_authorized": False,
        "budget_statuses": [
            {
                "requested_budget_yuan": budget,
                "status": "UNAVAILABLE_SCORE_STAKING_RULE",
            }
            for budget in (512, 768, 1024)
        ],
    }
    score_sha = write_payload(root / "correct_score_audit.json", score)
    artifacts.append({"file": "correct_score_audit.json", "sha256": score_sha})
    manifest = {
        **common,
        "schema_version": "exact_n_budget_matrix_freeze_v2",
        "artifacts": artifacts,
    }
    write_payload(root / "manifest.json", manifest)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in sorted(root.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )
    return root


def rehash_package(root: Path, changed_file: Path) -> None:
    changed = json.loads(changed_file.read_text(encoding="utf-8"))
    changed.pop("sha256", None)
    changed_sha = write_payload(changed_file, changed)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("sha256")
    for entry in manifest["artifacts"]:
        if entry["file"] == changed_file.name:
            entry["sha256"] = changed_sha
    write_payload(manifest_path, manifest)
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in sorted(root.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )


def test_verifier_proves_complete_exact_n_contract(tmp_path: Path) -> None:
    report = verify_directory(package(tmp_path / "package"))
    assert report["status"] == "PASS"
    assert report["cells"] == 15
    assert len(report["grid"]) == 15


def test_verifier_rejects_requested_n_4_to_recommended_n_3(tmp_path: Path) -> None:
    root = package(tmp_path / "package")
    target = root / "exact_n_4_budget_512.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["recommended_n"] = 3
    target.write_text(json.dumps(payload), encoding="utf-8")
    rehash_package(root, target)
    with pytest.raises(ValueError, match="identity/N mismatch"):
        verify_directory(root)


def test_score_audit_selects_latest_match_snapshot_across_verified_bundles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    issue_root = tmp_path / "26078"
    bundles = [issue_root / "old", issue_root / "new"]
    for bundle in bundles:
        bundle.mkdir(parents=True)
        for name in (
            "manifest.json",
            "snapshots.csv",
            "prices.csv",
            "mapping_inventory.csv",
            "page_inventory.csv",
            "SHA256SUMS",
        ):
            (bundle / name).write_text("fixture", encoding="utf-8")
        (bundle / "SHA256SUMS").write_text(
            "".join(
                f"{'0' * 64}  {name}\n"
                for name in (
                    "manifest.json",
                    "snapshots.csv",
                    "prices.csv",
                    "mapping_inventory.csv",
                    "page_inventory.csv",
                )
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        publisher,
        "verify_correct_score_bundle",
        lambda path, expected_schema: {
            "manifest": {
                "provider": "nowscore",
                "bookmaker_key": "crown",
                "capture_batch_id": path.name,
            },
            "sha256s_sha256": path.name * 8,
        },
    )
    older = {
        "issue": "26078",
        "match_idx": "1",
        "complete": "1",
        "phase": "pregame",
        "snapshot_ts_hkt": "2026-07-26T00:30:00+08:00",
        "snapshot_id": "older",
        "outcome_count": "1",
    }
    newer = {
        **older,
        "snapshot_ts_hkt": "2026-07-26T00:45:00+08:00",
        "snapshot_id": "newer",
        "source_time_raw": "00:45",
        "source_timestamp_scope": "market_specific",
        "fetched_at_utc": "2026-07-25T16:45:01+00:00",
        "raw_payload_sha256": "d" * 64,
        "raw_row_sha256": "e" * 64,
        "capture_batch_id": "new",
        "outcome_schema_sha256": "f" * 64,
        "_capture_bundle": str(bundles[1]),
        "_capture_bundle_sha": "new" * 8,
    }
    price = {
        "snapshot_id": "newer",
        "_capture_bundle": str(bundles[1]),
        "outcome_code": "home_1-0",
        "outcome_group": "exact",
        "outcome_label": "1-0",
        "sp": "7.5",
    }
    monkeypatch.setattr(
        publisher,
        "read_capture_bundles",
        lambda _bundles: ([older, newer], [price], [], []),
    )
    meta, audits = publisher.score_audit(
        tmp_path,
        "26078",
        (1,),
        publisher.hkt("2026-07-26T00:50:00+08:00"),
    )
    assert meta["capture_status"] == "verified_cross_bundle_asof"
    assert audits[0]["snapshot_id"] == "newer"
    assert audits[0]["complete_price_vector"][0]["sp"] == "7.5"
    assert audits[0]["correct_score_model_input_sha256"]
