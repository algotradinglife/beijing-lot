from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader

import src.adhoc_betting as adhoc_module
from src.adhoc_betting import (
    AdhocBettingError,
    AdhocBettingStore,
    DEFAULT_FONT_FILE,
    HKT,
    REQUIRED_PACKAGE_FILES,
    _make_portfolio,
    _normalize_match,
    _package_identity,
    _validate_request,
    canonical,
    digest,
    file_hash,
    verify_package,
)
from src.structured_input_receipt import write_receipt
from scripts.estimate_segment_betting_plan import PUBLISHED_EXACT_N_SAMPLE_ATTEMPTS


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=HKT)


@pytest.fixture(autouse=True)
def _formal_artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit-test formal artifacts outside the repository worktree."""

    monkeypatch.setattr(adhoc_module, "PROJECT_ROOT", tmp_path)


def _formal_fixture(*, count: int = 38) -> tuple[Path, Path]:
    path = (
        adhoc_module.PROJECT_ROOT
        / "results"
        / "structured_decision_chain_shadow"
        / "26078_fixture_active_v3.3.3"
        / "structured_shadow_26078.csv"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["issue", "match_idx", "shadow_arm", "shadow_selection_codes"],
        )
        writer.writeheader()
        for idx in range(1, count + 1):
            writer.writerow(
                {
                    "issue": "26078",
                    "match_idx": idx,
                    "shadow_arm": "active_v3.3.3",
                    "shadow_selection_codes": "3",
                }
            )
    receipt = write_receipt(path, issue="26078", generated_at=NOW, source={"fixture": "adhoc"})
    return path, receipt


def _source_snapshot(
    *,
    now: datetime = NOW,
    count: int = 8,
    mutate: dict[int, dict[str, object]] | None = None,
) -> dict[str, object]:
    formal_csv, formal_receipt = _formal_fixture()
    matches: list[dict[str, object]] = []
    for match_idx in range(1, count + 1):
        row: dict[str, object] = {
            "match_idx": match_idx,
            "match_id": f"26078_{match_idx:03d}",
            "league": "合成联赛",
            "home": f"主队{match_idx}",
            "away": f"客队{match_idx}",
            "handicap_line": "0",
            "kickoff_at_hkt": (now + timedelta(hours=4 + match_idx)).isoformat(),
            "sale_cutoff_hkt": (now + timedelta(hours=3 + match_idx)).isoformat(),
            "source_observed_at_hkt": now.isoformat(),
            "sale_status": "OPEN",
            "pass_allowed": True,
            "match_status": "SCHEDULED",
            "decision_input_status": "READY",
            "selection_codes": ["3"],
            "probabilities": {"3": 0.50, "1": 0.25, "0": 0.25},
            "sp": {"3": 3.0, "1": 3.0, "0": 3.0},
            "source_provenance": {
                "formal_decision_generated_at_hkt": now.isoformat(),
                "match_html_fetched_at_hkt": now.isoformat(),
                "nowscore_fetched_at_hkt": now.isoformat(),
                "live_sp_source_updated_at_hkt": now.isoformat(),
                "live_sp_fetched_at_hkt": now.isoformat(),
                "live_sp_snapshot_sha256": "a" * 64,
                "market_source_observed_at_hkt": now.isoformat(),
                "market_fetched_at_hkt": now.isoformat(),
                "market_latest_observed_at_hkt": now.isoformat(),
                "market_outcome_source_clocks_hkt": {
                    "3": now.isoformat(), "1": now.isoformat(), "0": now.isoformat(),
                },
                "market_outcome_fetched_clocks_hkt": {
                    "3": now.isoformat(), "1": now.isoformat(), "0": now.isoformat(),
                },
                "market_snapshot_sha256": "b" * 64,
                "market_sale_status": "OPEN",
                "market_parlay_allowed": True,
                "market_sale_cutoff_hkt": (now + timedelta(hours=3 + match_idx)).isoformat(),
            },
        }
        row.update((mutate or {}).get(match_idx, {}))
        matches.append(row)
    observed_clocks = [
        datetime.fromisoformat(str(row["source_observed_at_hkt"]))
        for row in matches
        if str(row.get("source_observed_at_hkt") or "")
    ]
    return {
        "issue": "26078",
        "input_asof_hkt": min(observed_clocks, default=now).isoformat(),
        "decision_variant_id": "active_v3.3.3",
        "source_metadata": {
            "fixture": "adhoc-betting-v1",
            "source_builder": "decision_api._build_adhoc_source_snapshot_v1",
            "snapshot_clock_hkt": now.isoformat(),
            "request_clock_hkt": now.isoformat(),
            "input_asof_policy": "oldest_required_observation_clock",
            "formal_decision_input": {
                "status": "VERIFIED_FORMAL_INPUT",
                "decision_variant_id": "active_v3.3.3",
                "binding_schema_version": "adhoc_formal_selection_binding_v1",
                "formal_selection_column": "shadow_selection_codes",
                "formal_selection_codes_sha256": adhoc_module._formal_selection_digest(
                    {idx: ("3",) for idx in range(1, 39)}
                ),
                "structured_csv": str(formal_csv),
                "structured_receipt": str(formal_receipt),
                "generated_at_hkt": now.isoformat(),
                "structured_csv_sha256": file_hash(formal_csv),
                "structured_receipt_sha256": file_hash(formal_receipt),
            },
        },
        "matches": matches,
    }


def _store(tmp_path: Path) -> AdhocBettingStore:
    assert DEFAULT_FONT_FILE.is_file(), "the reviewed portable CJK font is required"
    return AdhocBettingStore(
        db_path=tmp_path / "adhoc.sqlite",
        root=tmp_path / "adhoc-packages",
        font_file=DEFAULT_FONT_FILE,
        canonical_source_authorizer=lambda _source, _issue, _clock: None,
    )


def _create(store: AdhocBettingStore, source: dict[str, object], *, key: str = "test-key-0001") -> dict[str, object]:
    return store.create_or_get(
        issue="26078",
        requested_n=3,
        requested_budget_yuan=512,
        idempotency_key=key,
        source_snapshot=source,
        now=NOW,
    )


def _rehash_package(package: Path) -> Path:
    """Model an attacker who recomputes every mutable package hash."""

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename in ("eligible_denominator.json", "decision_input.json", "exact_n_plan.json"):
        path = package / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("sha256", None)
        payload["sha256"] = digest(payload)
        path.write_bytes(canonical(payload) + b"\n")
    manifest["eligible_denominator_sha256"] = json.loads(
        (package / "eligible_denominator.json").read_text(encoding="utf-8")
    )["sha256"]
    manifest["decision_input_sha256"] = json.loads(
        (package / "decision_input.json").read_text(encoding="utf-8")
    )["sha256"]
    manifest["exact_n_plan_sha256"] = json.loads(
        (package / "exact_n_plan.json").read_text(encoding="utf-8")
    )["sha256"]
    for artifact in manifest["artifacts"]:
        artifact["sha256"] = file_hash(package / artifact["file"])
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")
    rehashed = package.with_name(manifest["package_id"])
    package.rename(rehashed)
    (rehashed / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )
    return rehashed


@pytest.mark.parametrize("n_value", [3, 4, 5, 6, 7])
def test_each_allowed_exact_n_stays_exact_without_a_fallback(n_value: int) -> None:
    source = _source_snapshot()
    normalized = [
        _normalize_match(
            dict(row),
            requested_at=NOW,
            max_source_age=timedelta(minutes=15),
            safety_margin=timedelta(seconds=120),
        )
        for row in source["matches"]  # type: ignore[index]
    ]
    tickets, _base_cost, actual_cost, _reason = _make_portfolio(
        eligible=normalized,
        issue="26078",
        n_value=n_value,
        budget_yuan=512,
        seed=42 + n_value,
    )
    assert tickets
    assert 0 < actual_cost <= 512
    assert all(ticket["actual_n"] == n_value for ticket in tickets)
    assert all(len(ticket["match_indices"]) == n_value for ticket in tickets)
    occurrence_counts = Counter(
        int(match_idx)
        for ticket in tickets
        for match_idx in ticket["match_indices"]
    )
    assert max(occurrence_counts.values(), default=0) <= 2
    assert all(ticket["stake_multiplier"] == 1 for ticket in tickets)


@pytest.mark.parametrize("n_value", [3, 4, 5, 6, 7])
@pytest.mark.parametrize("budget", [512, 768, 1024])
def test_concentration_matrix_returns_compliant_smaller_plans(
    n_value: int, budget: int
) -> None:
    source = _source_snapshot(count=38)
    normalized = [
        _normalize_match(
            dict(row),
            requested_at=NOW,
            max_source_age=timedelta(minutes=15),
            safety_margin=timedelta(seconds=120),
        )
        for row in source["matches"]  # type: ignore[index]
    ]
    tickets, _base_cost, actual_cost, reason = _make_portfolio(
        eligible=normalized,
        issue="26078",
        n_value=n_value,
        budget_yuan=budget,
        seed=42 + n_value,
    )
    counts = Counter(
        int(match_idx)
        for ticket in tickets
        for match_idx in ticket["match_indices"]
    )
    assert tickets
    assert max(counts.values(), default=0) <= 2
    assert len(tickets) <= (38 * 2) // n_value
    assert actual_cost < budget
    assert reason == "adhoc_concentration_capped_unit_once"


def test_fixed_38_match_capacity_examples_are_deterministic() -> None:
    source = _source_snapshot(count=38)
    normalized = [
        _normalize_match(
            dict(row),
            requested_at=NOW,
            max_source_age=timedelta(minutes=15),
            safety_margin=timedelta(seconds=120),
        )
        for row in source["matches"]  # type: ignore[index]
    ]
    n3 = _make_portfolio(
        eligible=normalized, issue="26078", n_value=3, budget_yuan=1024, seed=45
    )[0]
    n4 = _make_portfolio(
        eligible=normalized, issue="26078", n_value=4, budget_yuan=1024, seed=46
    )[0]
    assert len(n3) <= 25
    assert len(n4) <= 19


def test_no_compliant_exact_n_ticket_is_the_only_selector_unavailable_case() -> None:
    source = _source_snapshot(
        mutate={
            idx: {
                "probabilities": {"3": 0.05, "1": 0.475, "0": 0.475},
                "sp": {"3": 1.01, "1": 2.0, "0": 2.0},
            }
            for idx in range(1, 9)
        }
    )
    normalized = [
        _normalize_match(
            dict(row),
            requested_at=NOW,
            max_source_age=timedelta(minutes=15),
            safety_margin=timedelta(seconds=120),
        )
        for row in source["matches"]  # type: ignore[index]
    ]
    tickets, base_cost, actual_cost, reason = _make_portfolio(
        eligible=normalized, issue="26078", n_value=3, budget_yuan=512, seed=42
    )
    assert tickets == []
    assert base_cost == actual_cost == 0
    assert reason == "no_compliant_exact_n_ticket"


def test_legacy_v1_replay_path_preserves_released_scaled_portfolio() -> None:
    source = _source_snapshot()
    normalized = [
        _normalize_match(
            dict(row),
            requested_at=NOW,
            max_source_age=timedelta(minutes=15),
            safety_margin=timedelta(seconds=120),
        )
        for row in source["matches"]  # type: ignore[index]
    ]
    first = _make_portfolio(
        eligible=normalized,
        issue="26078",
        n_value=3,
        budget_yuan=512,
        seed=42,
        concentration_enforced=False,
    )
    second = _make_portfolio(
        eligible=normalized,
        issue="26078",
        n_value=3,
        budget_yuan=512,
        seed=42,
        concentration_enforced=False,
    )
    assert first == second
    assert first[0]
    assert any(ticket["stake_multiplier"] > 1 for ticket in first[0])
    assert first[2] <= 512


@pytest.mark.parametrize("n_value", [3, 4, 5, 6, 7])
@pytest.mark.parametrize("budget", [512, 768, 1024])
def test_all_ui_exact_n_and_budget_choices_are_explicitly_accepted(n_value: int, budget: int) -> None:
    issue, checked_n, checked_budget, key = _validate_request(
        issue="26078",
        requested_n=n_value,
        requested_budget_yuan=budget,
        idempotency_key=f"matrix-{n_value}-{budget}",
    )
    assert (issue, checked_n, checked_budget, key) == (
        "26078", n_value, budget, f"matrix-{n_value}-{budget}",
    )


def test_current_exact_n_package_is_verified_content_addressed_and_separate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())

    assert result["current_status"] == "DOWNLOADABLE_CURRENT"
    assert result["package_schema_version"] == "adhoc_betting_package_v3"
    assert result["concentration_contract_applied"] is True
    assert result["current_status_recheck_scope"] == "VALID_UNTIL_SERVER_CLOCK_ONLY"
    assert result["sale_eligibility_scope"] == "GENERATION_TIME_SNAPSHOT_ONLY"
    assert result["shop_sale_confirmation_required"] is True
    assert result["status"] == "READY_FOR_REVIEW"
    assert result["operational_downloads_enabled"] is True
    assert result["research_evidence_eligible"] is False
    assert result["scheduled_freeze_event_id"] is None
    assert result["ticket_count"] > 0
    assert result["max_ticket_occurrences_per_match"] == 2
    assert result["max_actual_ticket_occurrences_per_match"] <= 2
    assert result["total_match_occurrence_capacity"] == 16
    assert result["theoretical_ticket_count_cap"] == 5
    assert len(result["match_occurrences"]) == 8
    assert 0 < float(result["actual_cost_yuan"]) <= 512
    assert all(ticket["actual_n"] == 3 for ticket in result["tickets"])
    assert len(result["denominator"]) == 8
    assert all(row["eligible"] is True for row in result["denominator"])
    assert all("sp" not in row and "probabilities" not in row for row in result["denominator"])

    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    assert package.is_dir()
    assert {path.name for path in package.iterdir() if path.is_file()} == REQUIRED_PACKAGE_FILES
    verified = verify_package(package)
    assert verified["status"] == "PASS"
    assert verified["request_id"] == result["request_id"]
    assert verified["immutable_request_id"] == result["request_id"]
    assert verified["published_package_count"] == 1
    assert verified["generation_batch_count"] == 1
    assert verified["total_match_occurrence_capacity"] == 16
    assert verified["theoretical_ticket_count_cap"] == 5
    assert verified["unused_budget_yuan"] == result["unused_budget_yuan"]
    assert verified["match_occurrences_sha256"]
    assert verified["match_occurrences"] == result["match_occurrences"]
    assert len(verified["match_occurrences"]) == verified["eligible_match_count"]
    assert all(
        row["distinct_ticket_occurrence_count"] <= 2
        for row in verified["match_occurrences"]
    )
    assert verified["portfolio_contract_sha256"]
    assert verified["decision_input_sha256"]

    manifest = json.loads((package / "adhoc_request_manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((package / "exact_n_plan.json").read_text(encoding="utf-8"))
    assert manifest["research_evidence_eligible"] is False
    assert manifest["scheduled_freeze_event_id"] is None
    assert manifest["base_cost_yuan"] == plan["base_cost_yuan"]
    assert manifest["actual_cost_yuan"] == plan["actual_cost_yuan"]
    assert manifest["budget_utilization"] == plan["budget_utilization"]
    assert manifest["portfolio_contract"] == plan["portfolio_contract"]
    assert manifest["portfolio_contract_sha256"] == plan["portfolio_contract_sha256"]
    assert manifest["concentration_contract"] == plan["concentration_contract"]
    assert plan["concentration_contract"]["max_ticket_occurrences_per_match"] == 2
    assert plan["concentration_contract"]["immutable_request_id"] == result["request_id"]
    assert plan["concentration_contract"]["published_package_count"] == 1
    assert plan["concentration_contract"]["generation_batch_count"] == 1
    assert plan["concentration_contract"]["match_identity_field"] == "match_id"
    assert plan["concentration_contract"]["stake_mode"] == "unit_once"
    assert plan["concentration_contract"]["duplicate_equivalent_tickets_allowed"] is False
    assert plan["concentration_contract"]["max_actual_ticket_occurrences_per_match"] <= 2
    assert plan["concentration_contract"]["match_occurrences_sha256"]
    assert plan["portfolio_contract"]["sample_attempts"] == PUBLISHED_EXACT_N_SAMPLE_ATTEMPTS
    assert plan["portfolio_contract"]["max_overlap"] == 1
    assert plan["portfolio_contract"]["positive_ev_only"] is True
    assert plan["portfolio_contract"]["stake_mode"] == "scale_to_budget"
    assert len(plan["portfolio_contract"]["portfolio_core_source_sha256"]) == 64
    assert all(item["actual_n"] == manifest["requested_n"] for item in plan["tickets"])
    assert manifest["pdf_font_reference"].startswith("external://adhoc-font/sha256/")
    assert len(manifest["pdf_font_sha256"]) == 64

    html_view = (package / "adhoc_betting_view.html").read_text(encoding="utf-8")
    assert "@page { size:A4" in html_view
    assert "break-inside:avoid" in html_view
    assert "不可变请求 / 发布包数 / 生成批次数" in html_view
    assert "逐场集中度证据哈希" in html_view
    assert result["match_occurrences_sha256"] in html_view
    assert "单场票数硬上限 / 实际最大值" in html_view
    assert "集中度或组合约束造成的未用预算" in html_view
    reader = PdfReader(str(package / "adhoc_betting_slip.pdf"))
    assert len(reader.pages) >= 1
    pdf_text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "北单即时方案" in pdf_text
    assert str(result["request_id"]) in pdf_text
    assert "不可变请求 / 发布包数 / 生成批次数" in pdf_text
    assert "逐场集中度证据哈希" in pdf_text
    assert result["match_occurrences_sha256"] in pdf_text
    assert "单场票数硬上限 / 实际最大值" in pdf_text
    assert "总容量 / 理论票数上限" in pdf_text
    assert "集中度或组合约束造成的未用预算" in pdf_text


def test_legacy_v1_package_without_concentration_fields_still_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_make_portfolio = adhoc_module._make_portfolio
    original_verify_package = adhoc_module.verify_package

    def legacy_make_portfolio(**kwargs):
        kwargs["concentration_enforced"] = False
        return original_make_portfolio(**kwargs)

    def pre_upgrade_verify_package(root, **kwargs):
        return adhoc_module._verify_package(
            root,
            _legacy_ledger_binding=adhoc_module._LEGACY_LEDGER_BINDING,
            **kwargs,
        )

    monkeypatch.setattr(
        adhoc_module, "PACKAGE_SCHEMA_VERSION", "adhoc_betting_package_v1"
    )
    monkeypatch.setattr(adhoc_module, "_make_portfolio", legacy_make_portfolio)
    monkeypatch.setattr(
        adhoc_module, "verify_package", pre_upgrade_verify_package
    )
    store = _store(tmp_path)
    result = _create(store, _source_snapshot(), key="legacy-v1-package")
    monkeypatch.setattr(adhoc_module, "verify_package", original_verify_package)
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(
        result["package_id"]
    )

    plan_path = package / "exact_n_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan.pop("concentration_contract", None)
    plan.pop("concentration_contract_sha256", None)
    plan.pop("sha256", None)
    plan["sha256"] = digest(plan)
    plan_path.write_bytes(canonical(plan) + b"\n")

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("concentration_contract", None)
    manifest.pop("concentration_contract_sha256", None)
    manifest["exact_n_plan_sha256"] = plan["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "exact_n_plan.json":
            artifact["sha256"] = file_hash(plan_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    legacy_package = package.with_name(manifest["package_id"])
    package.rename(legacy_package)
    (legacy_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(legacy_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        AdhocBettingError, match="requires trusted ledger binding"
    ):
        verify_package(legacy_package)
    conn = sqlite3.connect(tmp_path / "adhoc.sqlite")
    try:
        conn.execute(
            """
            UPDATE adhoc_betting_request_ledger
            SET package_id=?, manifest_sha256=?, package_path=?
            WHERE request_id=?
            """,
            (
                str(manifest["package_id"]),
                str(manifest["sha256"]),
                str(legacy_package.resolve()),
                str(result["request_id"]),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    replayed = store.get(str(result["request_id"]), now=NOW)
    assert replayed["package_id"] == str(manifest["package_id"])
    assert replayed["package_schema_version"] == "adhoc_betting_package_v1"
    assert replayed["concentration_contract_applied"] is False
    assert replayed["current_status"] == "HISTORICAL_NO_CONCENTRATION_CONTRACT"
    assert replayed["operational_downloads_enabled"] is False
    with pytest.raises(AdhocBettingError, match="HISTORICAL_NO_CONCENTRATION_CONTRACT"):
        store.artifact_path(str(result["request_id"]), fmt="pdf", now=NOW)
    audit_path, audit_payload = store.artifact_path(
        str(result["request_id"]), fmt="pdf", now=NOW, audit_only=True
    )
    assert audit_path.name == "adhoc_betting_slip.pdf"
    assert audit_payload["audit_only_download"] is True


def test_fail_closed_exclusions_cannot_produce_n_fallback(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _source_snapshot(
        mutate={
            1: {"kickoff_at_hkt": (NOW - timedelta(minutes=1)).isoformat()},
            2: {"sale_status": "UNKNOWN"},
            3: {"source_observed_at_hkt": (NOW - timedelta(hours=1)).isoformat()},
            4: {"pass_allowed": None},
            5: {"sale_cutoff_hkt": ""},
            6: {"match_status": "CANCELLED"},
        }
    )
    result = _create(store, source)

    assert result["status"] == "UNAVAILABLE_ADHOC_PLAN"
    assert result["current_status"] == "UNAVAILABLE_ADHOC_PLAN"
    assert result["ticket_count"] == 0
    assert result["eligible_match_count"] == 2
    assert "eligible_match_count_below_requested_n" in result["unavailable_reasons"]
    assert result["exclusion_counts"]["STARTED_OR_KICKED_OFF"] == 1
    assert result["exclusion_counts"]["UNKNOWN_SALE_STATE"] == 1
    assert result["exclusion_counts"]["STALE_INPUT"] == 1
    assert result["exclusion_counts"]["UNKNOWN_PASS_ALLOWED"] == 1
    assert result["exclusion_counts"]["MISSING_SALE_CUTOFF"] == 1
    assert result["exclusion_counts"]["MATCH_CANCELLED"] == 1
    with pytest.raises(AdhocBettingError, match="operational download disabled"):
        store.artifact_path(str(result["request_id"]), fmt="pdf", now=NOW)


def test_duplicate_match_id_cannot_evade_concentration_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _source_snapshot(mutate={2: {"match_id": "26078_001"}})
    with pytest.raises(AdhocBettingError, match="duplicate match IDs"):
        _create(store, source)


def test_identical_retry_is_idempotent_and_changed_bound_input_is_new_request(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _create(store, _source_snapshot(), key="same-bound-request")
    retry = _create(store, _source_snapshot(), key="same-bound-request")
    changed = _create(
        store,
        _source_snapshot(mutate={1: {"probabilities": {"3": 0.60, "1": 0.20, "0": 0.20}}}),
        key="changed-input-request",
    )
    later = store.create_or_get(
        issue="26078",
        requested_n=3,
        requested_budget_yuan=512,
        idempotency_key="later-request-time",
        source_snapshot=_source_snapshot(now=NOW + timedelta(seconds=10)),
        now=NOW + timedelta(seconds=10),
    )

    assert retry["request_id"] == first["request_id"]
    assert retry["package_id"] == first["package_id"]
    assert retry["idempotent"] is True
    assert changed["request_id"] != first["request_id"]
    assert changed["package_id"] != first["package_id"]
    assert later["request_id"] != first["request_id"]
    for result in (first, changed, later):
        package = (
            tmp_path
            / "adhoc-packages"
            / "packages"
            / "26078"
            / str(result["package_id"])
        )
        plan = json.loads(
            (package / "exact_n_plan.json").read_text(encoding="utf-8")
        )
        concentration = plan["concentration_contract"]
        assert concentration["immutable_request_id"] == result["request_id"]
        assert concentration["published_package_count"] == 1
        assert concentration["generation_batch_count"] == 1


def test_expiry_blocks_operational_download_but_preserves_audit_record(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    valid_until = datetime.fromisoformat(str(result["valid_until_hkt"]))

    expired = store.get(str(result["request_id"]), now=valid_until)
    assert expired["current_status"] == "EXPIRED_NOT_PURCHASABLE"
    assert expired["operational_downloads_enabled"] is False
    with pytest.raises(AdhocBettingError, match="operational download disabled"):
        store.artifact_path(str(result["request_id"]), fmt="html", now=valid_until)
    audit_path, audit_payload = store.artifact_path(
        str(result["request_id"]), fmt="html", now=valid_until, audit_only=True
    )
    assert audit_path.name == "adhoc_betting_view.html"
    assert audit_payload["audit_only_download"] is True


def test_fully_rehashed_wrong_formal_column_is_rejected(tmp_path: Path) -> None:
    """Internal package hashes cannot replace CSV-to-leg semantic binding."""

    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    denominator_path = package / "eligible_denominator.json"
    decision_path = package / "decision_input.json"
    plan_path = package / "exact_n_plan.json"
    denominator = json.loads(denominator_path.read_text(encoding="utf-8"))
    decision_input = json.loads(decision_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for row in [*denominator["included"], *decision_input["matches"]]:
        row["selection_codes"] = ["1"]
    for ticket in plan["tickets"]:
        ticket["leg_codes"] = ["1"] * len(ticket["leg_codes"])
    denominator_path.write_bytes(canonical(denominator) + b"\n")
    decision_path.write_bytes(canonical(decision_input) + b"\n")
    plan_path.write_bytes(canonical(plan) + b"\n")
    rehashed = _rehash_package(package)

    with pytest.raises(AdhocBettingError, match="formal shadow_selection_codes"):
        verify_package(rehashed)


def test_formal_csv_byte_change_with_old_receipt_fails_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    decision_input = json.loads((package / "decision_input.json").read_text(encoding="utf-8"))
    csv_path = Path(decision_input["source_metadata"]["formal_decision_input"]["structured_csv"])
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8").replace(",3\n", ",1\n", 1),
        encoding="utf-8",
    )

    with pytest.raises(AdhocBettingError, match="formal artifact hash"):
        verify_package(package)


def test_missing_formal_artifact_fails_closed_before_publication(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _source_snapshot()
    source["source_metadata"]["formal_decision_input"]["structured_csv"] = (  # type: ignore[index]
        "results/structured_decision_chain_shadow/missing/structured_shadow_26078.csv"
    )
    with pytest.raises(AdhocBettingError, match="trusted formal artifact root"):
        _create(store, source)


def test_spoofed_source_builder_cannot_authorize_wrong_issue(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _source_snapshot()
    source["source_metadata"]["source_builder"] = "manual.runtime.copy"  # type: ignore[index]
    source["source_metadata"]["operator_candidate_filter"] = {  # type: ignore[index]
        "authorized_issue": 28
    }

    with pytest.raises(AdhocBettingError, match="not authorized for the request issue"):
        _create(store, source)


def test_manual_snapshot_with_correct_issue_cannot_publish_operational_v3(
    tmp_path: Path,
) -> None:
    manual_store = AdhocBettingStore(
        db_path=tmp_path / "manual.sqlite",
        root=tmp_path / "manual-packages",
        font_file=DEFAULT_FONT_FILE,
    )
    source = _source_snapshot()
    source["source_metadata"]["source_builder"] = "manual.runtime.copy"  # type: ignore[index]
    source["source_metadata"]["operator_candidate_filter"] = {  # type: ignore[index]
        "authorized_issue": "26078"
    }

    with pytest.raises(AdhocBettingError, match="requires the canonical source resolver"):
        _create(manual_store, source)


def test_receipt_valid_retired_formal_variant_fails_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    source = _source_snapshot()
    formal_input = source["source_metadata"]["formal_decision_input"]  # type: ignore[index]
    csv_path = Path(formal_input["structured_csv"])
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8").replace(
            "active_v3.3.3", "retired_v3.2.0"
        ),
        encoding="utf-8",
    )
    receipt = write_receipt(csv_path, issue="26078", generated_at=NOW, source={"fixture": "retired"})
    formal_input["structured_csv_sha256"] = file_hash(csv_path)
    formal_input["structured_receipt_sha256"] = file_hash(receipt)

    with pytest.raises(AdhocBettingError, match="variant is not mapped"):
        _create(store, source)


def test_pre_formal_binding_v2_package_is_audit_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "adhoc_betting_package_v2"
    manifest_path.write_bytes(canonical(manifest) + b"\n")
    historical = _rehash_package(package)
    historical_manifest = json.loads(
        (historical / "adhoc_request_manifest.json").read_text(encoding="utf-8")
    )
    connection = sqlite3.connect(tmp_path / "adhoc.sqlite")
    try:
        connection.execute(
            "UPDATE adhoc_betting_request_ledger SET package_id=?, manifest_sha256=?, package_path=? WHERE request_id=?",
            (
                historical.name,
                historical_manifest["sha256"],
                str(historical.resolve()),
                result["request_id"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    replayed = store.get(str(result["request_id"]), now=NOW)
    assert replayed["package_schema_version"] == "adhoc_betting_package_v2"
    assert replayed["current_status"] == "HISTORICAL_NO_CONCENTRATION_CONTRACT"
    assert replayed["operational_downloads_enabled"] is False


def test_rehashed_tampering_is_rejected_by_semantic_verifier(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    plan_path = package / "exact_n_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["requested_n"] = 4
    plan["artifact_n"] = 4
    plan.pop("sha256", None)
    plan["sha256"] = digest(plan)
    plan_path.write_bytes(canonical(plan) + b"\n")

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["requested_n"] = 4
    manifest["exact_n_plan_sha256"] = plan["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "exact_n_plan.json":
            artifact["sha256"] = file_hash(plan_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(AdhocBettingError, match="portfolio contract does not bind the request"):
        verify_package(rehashed_package)


def test_duplicate_selection_code_cannot_evade_scale_a_rehashed_ticket(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = (
        tmp_path
        / "adhoc-packages"
        / "packages"
        / "26078"
        / str(result["package_id"])
    )
    plan_path = package / "exact_n_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    original_code = str(plan["tickets"][0]["leg_codes"][0])
    plan["tickets"][0]["leg_codes"][0] = f"{original_code}+{original_code}"
    plan.pop("sha256", None)
    plan["sha256"] = digest(plan)
    plan_path.write_bytes(canonical(plan) + b"\n")

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exact_n_plan_sha256"] = plan["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "exact_n_plan.json":
            artifact["sha256"] = file_hash(plan_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        AdhocBettingError, match="duplicate selection codes"
    ):
        verify_package(rehashed_package)


def test_fully_rehashed_pdf_without_concentration_evidence_is_rejected(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(
        result["package_id"]
    )
    pdf_path = package / "adhoc_betting_slip.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\nNO CONCENTRATION EVIDENCE\n%%EOF\n"
    )

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "adhoc_betting_slip.pdf":
            artifact["sha256"] = file_hash(pdf_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        AdhocBettingError, match="PDF concentration view"
    ):
        verify_package(rehashed_package)


def test_rehashed_v2_to_v1_schema_downgrade_cannot_skip_replay(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(
        result["package_id"]
    )
    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "adhoc_betting_package_v1"
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        AdhocBettingError, match="requires trusted ledger binding"
    ):
        verify_package(rehashed_package)
    with pytest.raises(
        TypeError, match="unexpected keyword argument"
    ):
        verify_package(
            rehashed_package,
            trusted_legacy_package_id=str(result["package_id"]),
        )


def test_fully_rehashed_third_match_occurrence_is_rejected(tmp_path: Path) -> None:
    """Changing codes, hashes, or ticket composition cannot hide a third occurrence."""

    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    plan_path = package / "exact_n_plan.json"
    manifest_path = package / "adhoc_request_manifest.json"
    denominator = json.loads((package / "eligible_denominator.json").read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    counts = Counter(
        int(match_idx)
        for ticket in plan["tickets"]
        for match_idx in ticket["match_indices"]
    )
    target = next(idx for idx, count in counts.items() if count == 2)
    unused = [
        int(row["match_idx"])
        for row in denominator["included"]
        if int(row["match_idx"]) not in counts
    ]
    assert len(unused) >= 2
    changed_ticket = next(
        ticket for ticket in plan["tickets"] if target not in ticket["match_indices"]
    )
    # The two unused matches keep every pair overlap within the released limit,
    # while target becomes a third distinct-ticket occurrence.
    changed_ticket["match_indices"] = [target, unused[0], unused[1]]
    changed_ticket["leg_codes"] = ["3", "3", "3"]
    plan.pop("sha256", None)
    plan["sha256"] = digest(plan)
    plan_path.write_bytes(canonical(plan) + b"\n")

    included_by_idx = {int(row["match_idx"]): row for row in denominator["included"]}
    selected_indices = {
        int(match_idx)
        for ticket in plan["tickets"]
        for match_idx in ticket["match_indices"]
    }
    safety_margin = int(denominator["safety_margin_seconds"])
    manifest["valid_until_hkt"] = min(
        datetime.fromisoformat(str(included_by_idx[idx]["sale_cutoff_hkt"]))
        - timedelta(seconds=safety_margin)
        for idx in selected_indices
    ).isoformat()
    manifest["exact_n_plan_sha256"] = plan["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "exact_n_plan.json":
            artifact["sha256"] = file_hash(plan_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(AdhocBettingError, match="two-ticket concentration cap"):
        verify_package(rehashed_package)


def test_rehashed_request_clock_disagreement_is_rejected_by_semantic_verifier(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])

    decision_path = package / "decision_input.json"
    decision_input = json.loads(decision_path.read_text(encoding="utf-8"))
    decision_input["source_metadata"]["request_clock_hkt"] = (NOW - timedelta(seconds=1)).isoformat()
    decision_input.pop("sha256", None)
    decision_input["sha256"] = digest(decision_input)
    decision_path.write_bytes(canonical(decision_input) + b"\n")

    manifest_path = package / "adhoc_request_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["decision_input_sha256"] = decision_input["sha256"]
    for artifact in manifest["artifacts"]:
        if artifact["file"] == "decision_input.json":
            artifact["sha256"] = file_hash(decision_path)
    manifest.pop("sha256", None)
    manifest["package_id"] = _package_identity(manifest)
    manifest["sha256"] = digest(manifest)
    manifest_path.write_bytes(canonical(manifest) + b"\n")

    rehashed_package = package.with_name(manifest["package_id"])
    package.rename(rehashed_package)
    (rehashed_package / "SHA256SUMS").write_text(
        "".join(
            f"{file_hash(path)}  {path.name}\n"
            for path in sorted(rehashed_package.iterdir())
            if path.is_file() and path.name != "SHA256SUMS"
        ),
        encoding="utf-8",
    )

    with pytest.raises(AdhocBettingError, match="source request clock is not bound"):
        verify_package(rehashed_package)


def test_ledger_request_identity_must_match_the_verified_package(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _create(store, _source_snapshot(), key="ledger-first-request")
    second = _create(
        store,
        _source_snapshot(mutate={1: {"probabilities": {"3": 0.60, "1": 0.20, "0": 0.20}}}),
        key="ledger-second-request",
    )
    conn = sqlite3.connect(tmp_path / "adhoc.sqlite")
    try:
        conn.execute(
            "UPDATE adhoc_betting_request_ledger SET package_id=? WHERE request_id=?",
            (str(second["package_id"]), str(first["request_id"])),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(AdhocBettingError, match="ledger/package binding mismatch: request_id"):
        store.get(str(first["request_id"]))
