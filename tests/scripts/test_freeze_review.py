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

from src import freeze_review as review
from src.segment_recovery import (
    POLICY_ID,
    manifest_sha256,
    schedule_input_sha256,
)


def _write_payload(path: Path, payload: dict[str, object]) -> str:
    claimed = review.digest(payload)
    path.write_bytes(review.canonical({**payload, "sha256": claimed}) + b"\n")
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
    recovery_path.write_bytes(review.canonical(recovery) + b"\n")

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
    for n in review.N_VALUES:
        for budget in review.BUDGETS:
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
                "sha256": review.file_hash(recovery_path),
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
        review, "verify_exact_n_freeze", lambda _: {"status": "PASS", "cells": 15}
    )
    return _source_package(tmp_path / "source")


def test_recovery_fixture_binds_first_n4_ticket_and_chinese_mapping(
    source: Path,
) -> None:
    model = review.load_source_model(source)
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
    review.bind_review_context(
        model, datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    )
    rendered = review._render_html(model, plan)
    assert "普通胜平负" in rendered
    assert "比分冻结计划不可用" in rendered
    assert "研究冻结审计视图 / NOT FOR PURCHASE" in rendered
    assert review.USAGE_BOUNDARY in rendered
    assert "SOURCE_INTEGRITY_PASS" in rendered
    assert "下注单" not in rendered
    assert "购买状态" not in rendered
    assert "销售资格" not in rendered
    assert "可执行金额" not in rendered
    assert "校验状态：PASS" not in rendered
    assert "仅按已验证 exact-N 冻结录入" not in rendered
    assert "overflow-x" not in rendered
    assert "break-inside: avoid" in rendered


def test_exact_n_mismatch_fails_closed(source: Path) -> None:
    path = source / "exact_n_4_budget_512.json"
    _rewrite_payload(path, lambda payload: payload.__setitem__("artifact_n", 3))
    with pytest.raises(review.FreezeReviewError, match="N/budget identity"):
        review.load_source_model(source)


def test_missing_frozen_metadata_fails_closed(source: Path) -> None:
    path = source / "structured_input.csv"
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    rows[0]["home"] = ""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(review.FreezeReviewError, match="metadata missing"):
        review.load_source_model(source)


def test_rehashed_recovery_membership_conflict_fails_closed(source: Path) -> None:
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("sha256")
    manifest["segment_match_indices"] = manifest["segment_match_indices"][:-1]
    _write_payload(manifest_path, manifest)
    with pytest.raises(review.FreezeReviewError, match="membership mismatch"):
        review.load_source_model(source)


def test_unavailable_plan_is_not_rendered(source: Path) -> None:
    path = source / "exact_n_7_budget_1024.json"

    def unavailable(payload: dict[str, object]) -> None:
        payload["status"] = "UNAVAILABLE_EXACT_N_BUDGET"
        payload["tickets"] = []
        payload["actual_cost_yuan"] = 0
        payload["unused_budget_yuan"] = 1024

    _rewrite_payload(path, unavailable)
    model = review.load_source_model(source)
    plan = next(
        item for item in model["plans"] if item["n"] == 7 and item["budget"] == 1024
    )
    review.bind_review_context(
        model, datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    )
    assert plan["status"] == "UNAVAILABLE_EXACT_N_BUDGET"
    assert plan["tickets"] == []
    assert "view_binding_sha256" not in plan


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
    assert len(review.load_source_model(source)["plans"]) == 15


def _fake_pdf_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review, "_font_coverage", lambda *args: None)

    def write_pdf(
        html_text: str, target: Path, font_file: Path, identifier: str
    ) -> str:
        target.write_bytes(b"%PDF-1.4\n% synthetic test derivative\n")
        return __import__("weasyprint").__version__

    monkeypatch.setattr(review, "_write_pdf", write_pdf)

    def pdf_text(path: Path) -> list[str]:
        html_text = path.with_suffix(".html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html_text, "html.parser")
        return [soup.body.get_text(" ")]

    monkeypatch.setattr(review, "_pdf_text_by_page", pdf_text)


def test_pdf_revision_identifier_is_canonicalized(tmp_path: Path) -> None:
    identifier = "a" * 64
    target = tmp_path / "fixture.pdf"
    target.write_bytes(
        b"%PDF-1.7\n/ID [("
        + identifier.encode("ascii")
        + b") (0123456789abcdef0123456789abcdef)]\n%%EOF\n"
    )
    original_size = target.stat().st_size
    review._canonicalize_pdf_identifier(target, identifier)
    assert target.stat().st_size == original_size
    expected = review.digest({"pdf_identifier": identifier, "revision": 1})[:32]
    assert expected.encode("ascii") in target.read_bytes()
    assert b"0123456789abcdef0123456789abcdef" not in target.read_bytes()


def test_real_pdf_bytes_are_deterministic_and_restore_source_date_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[2]
    font = (
        repository
        / "evidence/bj_freeze_review_001/assets/fonts/FreezeReviewCJKSubset.otf"
    )
    if not font.is_file():
        pytest.skip("portable PDF font has not been staged")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "123456789")
    html_text = (
        "<!doctype html><meta charset=utf-8>"
        "<body>研究冻结审计视图 NOT FOR PURCHASE 123</body>"
    )
    identifier = "b" * 64
    first = tmp_path / "a" / "fixture.pdf"
    second = tmp_path / "b" / "fixture.pdf"
    first.parent.mkdir()
    second.parent.mkdir()
    review._write_pdf(html_text, first, font, identifier)
    review._write_pdf(html_text, second, font, identifier)
    assert first.read_bytes() == second.read_bytes()
    assert os.environ["SOURCE_DATE_EPOCH"] == "123456789"


def test_append_only_bundle_is_idempotent_and_semantically_verified(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    output = tmp_path / "derived"
    generated = datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    first = review.render_bundle(
        source_package=source,
        output_root=output,
        font_file=font,
        generated_at=generated,
    )
    assert first["status"] == "PASS"
    assert first["html_files"] == 15
    assert first["pdf_files"] == 15
    assert first["idempotent"] is False
    second = review.render_bundle(
        source_package=source,
        output_root=output,
        font_file=font,
        generated_at=generated,
    )
    assert second["status"] == "PASS"
    assert second["idempotent"] is True
    assert second["output_id"] == first["output_id"]
    later = review.render_bundle(
        source_package=source,
        output_root=output,
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T11:12:00+08:00"),
    )
    assert later["status"] == "PASS"
    assert later["idempotent"] is False
    assert later["output_id"] != first["output_id"]


def _directory_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_same_canonical_inputs_are_byte_identical_across_output_roots(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    generated = datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    first = review.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived-a",
        font_file=font,
        generated_at=generated,
    )
    second = review.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived-b",
        font_file=font,
        generated_at=generated,
    )
    assert first["output_id"] == second["output_id"]
    assert _directory_bytes(Path(str(first["path"]))) == _directory_bytes(
        Path(str(second["path"]))
    )


def test_audit_boundary_keeps_every_frozen_ticket_without_restaking(
    source: Path,
) -> None:
    model = review.load_source_model(source)
    original = {
        (plan["n"], plan["budget"]): [
            (ticket["ticket_number"], ticket["match_indices"], ticket["cost_yuan"])
            for ticket in plan["tickets"]
        ]
        for plan in model["plans"]
    }
    review.bind_review_context(
        model, datetime.fromisoformat("2026-07-25T10:12:00+08:00")
    )
    assert {
        (plan["n"], plan["budget"]): [
            (ticket["ticket_number"], ticket["match_indices"], ticket["cost_yuan"])
            for ticket in plan["tickets"]
        ]
        for plan in model["plans"]
    } == original
    assert model["usage_boundary"] == review.USAGE_BOUNDARY
    assert all(
        "purchase_status" not in plan and "expired_ticket_count" not in plan
        for plan in model["plans"]
    )
    for plan in model["plans"]:
        if plan["status"] != "FROZEN_EXACT_N_BUDGET":
            continue
        html_text = review._render_html(model, plan)
        assert "研究冻结审计视图 / NOT FOR PURCHASE" in html_text
        assert "下注单" not in html_text
        assert "购买状态" not in html_text


def _rehash_derived(root: Path, changed_name: str) -> None:
    manifest_path = root / "freeze_review_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("sha256")
    changed_sha = review.file_hash(root / changed_name)
    for entry in manifest["plans"]:
        if entry.get("html_file") == changed_name:
            entry["html_sha256"] = changed_sha
    for entry in manifest["artifacts"]:
        if entry.get("file") == changed_name:
            entry["sha256"] = changed_sha
    manifest["sha256"] = review.digest(manifest)
    manifest_path.write_bytes(review.canonical(manifest) + b"\n")
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{review.file_hash(path)}  {path.name}\n"
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
    result = review.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived",
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T10:12:00+08:00"),
    )
    root = Path(str(result["path"]))
    html_path = root / "freeze_review_N4_B512.html"
    html_path.write_text(
        html_path.read_text(encoding="utf-8").replace("让球负+让球平", "普通负"),
        encoding="utf-8",
    )
    _rehash_derived(root, html_path.name)
    with pytest.raises(review.FreezeReviewError, match="output identity"):
        review.verify_bundle(root, source, font)


def test_public_verifier_rejects_non_content_addressed_directory(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pdf_install(monkeypatch)
    font = tmp_path / "fixture.ttf"
    font.write_bytes(b"fixture-font")
    result = review.render_bundle(
        source_package=source,
        output_root=tmp_path / "derived",
        font_file=font,
        generated_at=datetime.fromisoformat("2026-07-25T10:12:00+08:00"),
    )
    root = Path(str(result["path"]))
    renamed = root.rename(root.parent / ".not-the-content-address")
    with pytest.raises(review.FreezeReviewError, match="output identity"):
        review.verify_bundle(renamed, source, font)


def test_real_26078_fixture_is_complete_and_audit_only() -> None:
    repository = Path(__file__).resolve().parents[2]
    source = Path(
        os.environ.get(
            "BJ_FREEZE_REVIEW_FIXTURE",
            str(
                repository
                / (
                    "evidence/bj_freeze_review_001/source_packages/26078/"
                    "segment_1_recovery_1/"
                    "f2526338ac3983f347335dab552604988"
                    "bada052484dbb4e141920dd714a4f21"
                )
            ),
        )
    )
    if not source.is_dir():
        pytest.skip("portable 26078 freeze package has not been staged")
    model = review.load_source_model(source)
    review.bind_review_context(
        model, datetime.fromisoformat("2026-07-25T10:37:05+08:00")
    )
    plan = next(
        item for item in model["plans"] if item["n"] == 4 and item["budget"] == 512
    )
    assert len(plan["tickets"]) == 15
    assert plan["actual_cost"] == 512
    assert len(review._ticket_leg_rows(model)) == 937
    assert model["source_integrity_status"] == review.SOURCE_INTEGRITY_PASS
    assert model["usage_boundary"] == review.USAGE_BOUNDARY
    ticket_13 = plan["tickets"][12]
    assert 26 in ticket_13["match_indices"]
    assert plan["tickets"][0]["match_indices"] == [50, 51, 54, 63]
    assert plan["tickets"][0]["leg_codes"] == ["0+1", "0+1", "0+1", "3+1"]
    rendered = review._render_html(model, plan)
    assert "#26" in rendered
    assert "研究冻结审计视图 / NOT FOR PURCHASE" in rendered
    assert "下注单" not in rendered
