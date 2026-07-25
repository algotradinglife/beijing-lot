from __future__ import annotations

import csv
import json
import os
import socket
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src import betting_slip as slip
from src.segment_recovery import (
    POLICY_ID,
    manifest_sha256,
    schedule_input_sha256,
)


def _write_payload(path: Path, payload: dict[str, object]) -> str:
    claimed = slip.digest(payload)
    path.write_bytes(slip.canonical({**payload, "sha256": claimed}) + b"\n")
    return claimed


def _rewrite_payload(path: Path, mutate) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("sha256", None)
    mutate(payload)
    _write_payload(path, payload)


def _source_package(root: Path) -> Path:
    root.mkdir()
    issue = "26078"
    members = list(range(24, 64))
    published = datetime.fromisoformat("2026-07-25T00:00:00+08:00")
    included = []
    for offset, match_idx in enumerate(members):
        kickoff = datetime.fromisoformat("2026-07-25T05:50:00+08:00") + timedelta(
            minutes=30 * offset
        )
        included.append(
            {
                "match_idx": match_idx,
                "kickoff_at_hkt": kickoff.isoformat(timespec="microseconds"),
                "freeze_boundary_at_hkt": (kickoff - timedelta(minutes=25)).isoformat(
                    timespec="microseconds"
                ),
            }
        )
    recovery: dict[str, object] = {
        "schema_version": "segment_recovery_manifest_v1",
        "capability_id": "BJ-SEG-RECOVERY-001",
        "policy": POLICY_ID,
        "issue": issue,
        "parent_segment_idx": 1,
        "parent_segment_identity": "segment_1",
        "parent_segment_manifest_sha256": "a" * 64,
        "parent_status": "MISSED_FREEZE",
        "parent_match_indices": members,
        "child_identity": "segment_1_recovery_1",
        "recovery_ordinal": 1,
        "status": "PUBLISHED_RECOVERY",
        "recovery_published_at_hkt": published.isoformat(timespec="microseconds"),
        "included": included,
        "included_match_count": len(included),
        "excluded": [],
        "excluded_match_count": 0,
        "recovery_freeze_at": included[0]["freeze_boundary_at_hkt"],
        "hard_stop_at_hkt": "2026-07-25T20:25:00.000000+08:00",
        "selection_inputs": [
            "matches.issue",
            "matches.match_idx",
            "matches.end_time",
        ],
        "market_or_model_inputs_used": False,
        "immutable": True,
    }
    recovery["schedule_input_sha256"] = schedule_input_sha256(recovery)
    recovery["manifest_sha256"] = manifest_sha256(recovery)
    recovery_path = root / "recovery_manifest.json"
    recovery_path.write_bytes(slip.canonical(recovery) + b"\n")

    with (root / "structured_input.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "issue",
                "match_idx",
                "league",
                "home",
                "away",
                "handicap_line",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for match_idx in members:
            writer.writerow(
                {
                    "issue": issue,
                    "match_idx": match_idx,
                    "league": f"联赛{match_idx}",
                    "home": f"主队{match_idx}",
                    "away": f"客队{match_idx}",
                    "handicap_line": "-1.0" if match_idx % 2 else "0.0",
                }
            )
    (root / "correct_score_audit.json").write_text(
        json.dumps({"status": "UNAVAILABLE_CORRECT_SCORE_PLAN"}),
        encoding="utf-8",
    )
    plan_artifacts: list[dict[str, object]] = []
    common = {
        "issue": issue,
        "segment_idx": 1,
        "parent_segment_idx": 1,
        "segment_identity": "segment_1_recovery_1",
        "segment_match_indices": members,
        "segment_manifest_sha256": recovery["manifest_sha256"],
        "recovery_manifest_sha256": recovery["manifest_sha256"],
        "event_key": "f" * 64,
        "effective_decision_at": "2026-07-25T05:16:33+08:00",
    }
    for n in slip.N_VALUES:
        for budget in slip.BUDGETS:
            if (n, budget) == (4, 512):
                tickets = [
                    {
                        "actual_n": 4,
                        "match_indices": [50, 51, 54, 63],
                        "leg_codes": ["0+1", "0+1", "0+1", "3+1"],
                        "base_cost_yuan": 32,
                        "stake_multiplier": 2 if index == 14 else 1,
                        "cost_yuan": 64 if index == 14 else 32,
                    }
                    for index in range(15)
                ]
            else:
                tickets = [
                    {
                        "actual_n": n,
                        "match_indices": members[:n],
                        "leg_codes": ["3", "1", "0", "3+1", "0+1", "3+0", "3+1+0"][:n],
                        "base_cost_yuan": 2**n,
                        "stake_multiplier": 1,
                        "cost_yuan": 2**n,
                    }
                ]
            actual = sum(ticket["cost_yuan"] for ticket in tickets)
            payload = {
                **common,
                "requested_n": n,
                "artifact_n": n,
                "recommended_n": n,
                "requested_budget_yuan": budget,
                "actual_cost_yuan": actual,
                "unused_budget_yuan": budget - actual,
                "status": "FROZEN_EXACT_N_BUDGET",
                "tickets": tickets,
            }
            filename = f"exact_n_{n}_budget_{budget}.json"
            claimed = _write_payload(root / filename, payload)
            plan_artifacts.append({"file": filename, "sha256": claimed})
    exact_manifest = {
        **common,
        "schema_version": "exact_n_budget_matrix_freeze_v2",
        "artifacts": [
            {
                "file": "recovery_manifest.json",
                "sha256": slip.file_hash(recovery_path),
                "semantic_sha256": recovery["manifest_sha256"],
            },
            *plan_artifacts,
        ],
    }
    _write_payload(root / "manifest.json", exact_manifest)
    (root / "SHA256SUMS").write_text("synthetic verifier boundary\n", encoding="utf-8")
    return root


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        slip, "verify_exact_n_freeze", lambda _: {"status": "PASS", "cells": 15}
    )
    return _source_package(tmp_path / "source")


def test_recovery_fixture_binds_first_n4_ticket_and_chinese_mapping(
    source: Path,
) -> None:
    model = slip.load_source_model(source)
    assert len(model["plans"]) == 15
    plan = next(
        item for item in model["plans"] if item["n"] == 4 and item["budget"] == 512
    )
    assert len(plan["tickets"]) == 15
    assert plan["actual_cost"] == 512
    first = plan["tickets"][0]
    assert first["match_indices"] == [50, 51, 54, 63]
    assert first["leg_codes"] == ["0+1", "0+1", "0+1", "3+1"]
    assert [leg["selection_label"] for leg in first["legs"]] == [
        "让球负+让球平",
        "让球负+让球平",
        "让球负+让球平",
        "让球胜+让球平",
    ]
    assert all(leg["kickoff_at_hkt"].endswith("+08:00") for leg in first["legs"])
    rendered = slip._render_html(model, plan)
    assert "普通胜平负" in rendered
    assert "比分下注不可用" in rendered
    assert "overflow-x" not in rendered
    assert "break-inside: avoid" in rendered


def test_exact_n_mismatch_fails_closed(source: Path) -> None:
    path = source / "exact_n_4_budget_512.json"
    _rewrite_payload(path, lambda payload: payload.__setitem__("artifact_n", 3))
    with pytest.raises(slip.BettingSlipError, match="N/budget identity"):
        slip.load_source_model(source)


def test_missing_frozen_metadata_fails_closed(source: Path) -> None:
    path = source / "structured_input.csv"
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    rows[0]["home"] = ""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(slip.BettingSlipError, match="metadata missing"):
        slip.load_source_model(source)


def test_rehashed_recovery_membership_conflict_fails_closed(source: Path) -> None:
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("sha256")
    manifest["segment_match_indices"] = manifest["segment_match_indices"][:-1]
    _write_payload(manifest_path, manifest)
    with pytest.raises(slip.BettingSlipError, match="membership mismatch"):
        slip.load_source_model(source)


def test_unavailable_plan_is_not_rendered(source: Path) -> None:
    path = source / "exact_n_7_budget_1024.json"

    def unavailable(payload: dict[str, object]) -> None:
        payload["status"] = "UNAVAILABLE_EXACT_N_BUDGET"
        payload["tickets"] = []
        payload["actual_cost_yuan"] = 0
        payload["unused_budget_yuan"] = 1024

    _rewrite_payload(path, unavailable)
    model = slip.load_source_model(source)
    plan = next(
        item for item in model["plans"] if item["n"] == 7 and item["budget"] == 1024
    )
    assert plan["status"] == "UNAVAILABLE_EXACT_N_BUDGET"
    assert plan["tickets"] == []


def test_source_loading_does_not_use_network_or_database(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("network access attempted"),
    )
    monkeypatch.setattr(
        sqlite3,
        "connect",
        lambda *args, **kwargs: pytest.fail("database access attempted"),
    )
    assert len(slip.load_source_model(source)["plans"]) == 15


def _fake_pdf_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(slip, "_font_coverage", lambda *args: None)

    def write_pdf(
        html_text: str, target: Path, font_file: Path, identifier: str
    ) -> str:
        target.write_bytes(b"%PDF-1.4\n% synthetic test derivative\n")
        return __import__("weasyprint").__version__

    monkeypatch.setattr(slip, "_write_pdf", write_pdf)

    def pdf_text(path: Path) -> list[str]:
        html_text = path.with_suffix(".html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html_text, "html.parser")
        return [soup.body.get_text(" ")]

    monkeypatch.setattr(slip, "_pdf_text_by_page", pdf_text)


def test_append_only_bundle_is_idempotent_and_semantically_verified(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    output = tmp_path / "derived"
    generated = datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    first = slip.render_bundle(
        source_package=source,
        output_root=output,
        font_file=font,
        generated_at=generated,
    )
    assert first["status"] == "PASS"
    assert first["html_files"] == 15
    assert first["pdf_files"] == 15
    assert first["idempotent"] is False
    second = slip.render_bundle(
        source_package=source,
        output_root=output,
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T11:12:00+08:00"),
    )
    assert second["status"] == "PASS"
    assert second["idempotent"] is True
    assert second["output_id"] == first["output_id"]


def _rehash_derived(root: Path, changed_name: str) -> None:
    manifest_path = root / "betting_slip_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("sha256")
    changed_sha = slip.file_hash(root / changed_name)
    for entry in manifest["plans"]:
        if entry.get("html_file") == changed_name:
            entry["html_sha256"] = changed_sha
    for entry in manifest["artifacts"]:
        if entry.get("file") == changed_name:
            entry["sha256"] = changed_sha
    manifest["sha256"] = slip.digest(manifest)
    manifest_path.write_bytes(slip.canonical(manifest) + b"\n")
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{slip.file_hash(path)}  {path.name}\n"
            for path in sorted(root.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )


def test_rehashed_html_semantic_tamper_fails_closed(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    result = slip.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived",
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T10:12:00+08:00"),
    )
    root = Path(str(result["path"]))
    html_path = root / "betting_slip_N4_B512.html"
    html_path.write_text(
        html_path.read_text(encoding="utf-8").replace("让球负+让球平", "普通负"),
        encoding="utf-8",
    )
    _rehash_derived(root, html_path.name)
    with pytest.raises(slip.BettingSlipError, match="HTML binding/layout"):
        slip.verify_bundle(root, source, font)


def test_public_verifier_rejects_non_content_addressed_directory(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    result = slip.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived",
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T10:12:00+08:00"),
    )
    root = Path(str(result["path"]))
    renamed = root.rename(root.parent / ".not-the-content-address")
    with pytest.raises(slip.BettingSlipError, match="output identity"):
        slip.verify_bundle(renamed, source, font)


def test_real_26078_fixture_when_runtime_package_is_available() -> None:
    repository = Path(__file__).resolve().parents[2]
    source = Path(
        os.environ.get(
            "BJ_BET_SLIP_FIXTURE",
            str(
                repository
                / (
                    "results/exact_n_segment_freeze/26078/"
                    "segment_1_recovery_1/"
                    "f2526338ac3983f347335dab552604988"
                    "bada052484dbb4e141920dd714a4f21"
                )
            ),
        )
    )
    if not source.is_dir():
        pytest.skip("runtime 26078 freeze package is intentionally not tracked")
    model = slip.load_source_model(source)
    plan = next(
        item for item in model["plans"] if item["n"] == 4 and item["budget"] == 512
    )
    assert len(plan["tickets"]) == 15
    assert plan["actual_cost"] == 512
    assert plan["tickets"][0]["match_indices"] == [50, 51, 54, 63]
    assert plan["tickets"][0]["leg_codes"] == ["0+1", "0+1", "0+1", "3+1"]
