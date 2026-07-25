from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader

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
from scripts.estimate_segment_betting_plan import PUBLISHED_EXACT_N_SAMPLE_ATTEMPTS


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=HKT)


def _source_snapshot(
    *,
    now: datetime = NOW,
    count: int = 8,
    mutate: dict[int, dict[str, object]] | None = None,
) -> dict[str, object]:
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
            "snapshot_clock_hkt": now.isoformat(),
            "request_clock_hkt": now.isoformat(),
            "input_asof_policy": "oldest_required_observation_clock",
            "formal_decision_input": {
                "status": "VERIFIED_FORMAL_INPUT",
                "decision_variant_id": "active_v3.3.3",
                "generated_at_hkt": now.isoformat(),
                "structured_csv_sha256": "c" * 64,
                "structured_receipt_sha256": "d" * 64,
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
    assert result["current_status_recheck_scope"] == "VALID_UNTIL_SERVER_CLOCK_ONLY"
    assert result["sale_eligibility_scope"] == "GENERATION_TIME_SNAPSHOT_ONLY"
    assert result["shop_sale_confirmation_required"] is True
    assert result["status"] == "READY_FOR_REVIEW"
    assert result["operational_downloads_enabled"] is True
    assert result["research_evidence_eligible"] is False
    assert result["scheduled_freeze_event_id"] is None
    assert result["ticket_count"] > 0
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

    manifest = json.loads((package / "adhoc_request_manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((package / "exact_n_plan.json").read_text(encoding="utf-8"))
    assert manifest["research_evidence_eligible"] is False
    assert manifest["scheduled_freeze_event_id"] is None
    assert manifest["base_cost_yuan"] == plan["base_cost_yuan"]
    assert manifest["actual_cost_yuan"] == plan["actual_cost_yuan"]
    assert manifest["budget_utilization"] == plan["budget_utilization"]
    assert manifest["portfolio_contract"] == plan["portfolio_contract"]
    assert manifest["portfolio_contract_sha256"] == plan["portfolio_contract_sha256"]
    assert plan["portfolio_contract"]["sample_attempts"] == PUBLISHED_EXACT_N_SAMPLE_ATTEMPTS
    assert plan["portfolio_contract"]["max_overlap"] == 1
    assert plan["portfolio_contract"]["positive_ev_only"] is True
    assert plan["portfolio_contract"]["stake_mode"] == "scale_to_budget"
    assert len(plan["portfolio_contract"]["portfolio_core_source_sha256"]) == 64
    assert all(item["actual_n"] == manifest["requested_n"] for item in plan["tickets"])
    assert manifest["pdf_font_reference"] == "evidence/bj_adhoc_bet_001/assets/fonts/NotoSansCJKsc-Regular.otf"
    assert len(manifest["pdf_font_sha256"]) == 64

    html_view = (package / "adhoc_betting_view.html").read_text(encoding="utf-8")
    assert "@page { size:A4" in html_view
    assert "break-inside:avoid" in html_view
    reader = PdfReader(str(package / "adhoc_betting_slip.pdf"))
    assert len(reader.pages) >= 1
    pdf_text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "北单即时方案" in pdf_text
    assert str(result["request_id"]) in pdf_text


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


def test_fully_rehashed_ticket_replacement_is_rejected_by_portfolio_replay(tmp_path: Path) -> None:
    """A self-consistent package cannot substitute a valid-looking ticket set."""

    store = _store(tmp_path)
    result = _create(store, _source_snapshot())
    package = tmp_path / "adhoc-packages" / "packages" / "26078" / str(result["package_id"])
    plan_path = package / "exact_n_plan.json"
    manifest_path = package / "adhoc_request_manifest.json"
    denominator = json.loads((package / "eligible_denominator.json").read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert plan["tickets"]
    changed_ticket = plan["tickets"][0]
    old_indices = {int(value) for value in changed_ticket["match_indices"]}
    replacement = next(
        int(row["match_idx"])
        for row in denominator["included"]
        if int(row["match_idx"]) not in old_indices
    )
    changed_ticket["match_indices"][-1] = replacement
    # The fixture gives every leg the same code/price, so this replacement
    # remains structurally valid and cost-consistent before the replay check.
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

    with pytest.raises(AdhocBettingError, match="Exact-N portfolio replay mismatch"):
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
