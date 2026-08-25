"""Focused verifier tests for BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1 (#394).

Covers: exact parity to accepted #392 R3/C1E3 EXPANDING_EQUAL evidence on the
2022-2024 overlap; budget/support/ticket identities for standalone arms, the
fixed 50/50 mixed portfolio and the fractional counterfactual; temporal
discipline (frozen pre-extension mapping, evidence cutoff); and REQ-E06
tamper resistance of the package verifier (settlement tamper, ledger tamper,
manifest forgery, source-trace tamper).
"""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.n7_mixed_full_history.contract import (
    CORE_YEARS,
    EVIDENCE_QUERY_CUTOFF_TS,
    EXTENSION_YEARS,
    ISSUE_STAKE_CNY,
    MIXED_C1E3_FUNDED_UNITS,
    MIXED_R3_UNITS_PER_TICKET,
    MIXED_TOTAL_CNY,
    PRIMARY_ARM,
    PRIMARY_TICKETS,
    SECONDARY_ARM,
    SECONDARY_TICKETS,
    CONTRACT_ID,
)
from src.n7_mixed_full_history.pipeline import (
    build_package,
    construct_surface,
    evaluate_all,
    prepare_actions_years,
    _action_surface,
    _extension_settlement,
    _fit_extension_mapping,
    _load_core_mapped,
    _load_core_settlement,
    _pre_extension_boundary,
    _ticket_units_flexible,
    verify_package,
    ContractError,
)
from src.qeu_threshold_n7.pipeline import prepare_match_actions


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot/data")
RESULT = REPO_ROOT / "results/n7_mixed_full_history"


# ---------------------------------------------------------------------------
# Parity helpers
# ---------------------------------------------------------------------------

def _accepted_392_bundles():
    return pd.read_parquet(
        REPO_ROOT / "results/n7_cutoff_walkforward/issue_bundles.parquet"
    )


def _accepted_392_tickets():
    return pd.read_parquet(
        REPO_ROOT / "results/n7_cutoff_walkforward/tickets.parquet"
    )


def _core_surface_frames():
    mapped = _load_core_mapped(REPO_ROOT)
    settlement = _load_core_settlement(REPO_ROOT)
    action = _action_surface(mapped, settlement)
    return mapped, settlement, construct_surface(action)["bundles"]


# ---------------------------------------------------------------------------
# 1. #392 parity on the 2022-2024 exact overlap
# ---------------------------------------------------------------------------

def test_core_parity_to_accepted_392_bundles():
    """My reconstructed core R3/C1E3 EXPANDING_EQUAL bundles must exactly equal
    accepted #392 bundles (issues, PnL, hit, profitable) on the exact overlap
    of native-included issues."""
    _, _, bundles = _core_surface_frames()
    accepted = _accepted_392_bundles()
    accepted = accepted[accepted["policy"].eq("EXPANDING_EQUAL")].copy()
    mine = bundles[
        bundles["schedule"].isin(["R3_STANDALONE", "C1E3_STANDALONE"])
    ].copy()
    # Native-included issues only: NaN pnl on both sides would trivially pass.
    accepted = accepted[accepted["native_included"].astype(bool)].copy()
    mine = mine[mine["native_included"].astype(bool)].copy()
    my = mine.copy()
    my["arm392"] = np.where(
        my["support_arm"].eq("R3_CONTROL"), "R3_CONTROL", "C1E3_SECONDARY"
    )
    acc = accepted.copy()
    acc["arm392"] = acc["support_arm"]
    common_issues = set(acc["issue"]) & set(my["issue"])
    assert len(common_issues) > 0, "no overlapping core issues with #392"
    assert not my["pnl_cny"].isna().any(), "my core bundles contain NaN pnl"
    assert not acc["pnl_cny"].isna().any(), "accepted core bundles contain NaN pnl"
    acc = acc[acc["issue"].isin(common_issues)]
    own = my[my["issue"].isin(common_issues)]
    paired = acc.merge(
        own,
        left_on=["issue", "arm392"],
        right_on=["issue", "arm392"],
        suffixes=("_392", "_394"),
    )
    # Exact PnL identity on the overlapping native-included issues.
    assert np.allclose(
        paired["pnl_cny_392"], paired["pnl_cny_394"], rtol=0, atol=1e-9
    ), "core issue PnL differs from accepted #392"
    assert np.allclose(
        paired["gross_cny_392"], paired["gross_cny_394"], rtol=0, atol=1e-9
    ), "core issue gross differs from accepted #392"
    assert np.array_equal(
        paired["ticket_hit_392"].astype(bool),
        paired["ticket_hit_394"].astype(bool),
    ), "core ticket_hit differs from accepted #392"


def test_core_action_transform_matches_frozen_prepare_match_actions():
    """The year-flexible action transform must reproduce the frozen
    prepare_match_actions on core-year rows (no semantic drift)."""
    mapped = _load_core_mapped(REPO_ROOT)
    long_frozen_input = _mapped_long_for(mapped)
    frozen = prepare_match_actions(long_frozen_input)
    extended = prepare_actions_years(long_frozen_input, tuple(CORE_YEARS))
    key = [
        "issue", "issue_year", "issue_anchor_ts", "match_idx",
        "baseline_support", "qeu_support", "retained_mass", "support_pressure",
    ]
    merged = frozen[key].merge(extended[key], on=key[:4], suffixes=("_f", "_e"))
    assert np.allclose(
        merged["retained_mass_f"], merged["retained_mass_e"], rtol=0, atol=1e-12
    )
    assert np.allclose(
        merged["support_pressure_f"], merged["support_pressure_e"], rtol=0, atol=1e-12
    )
    assert (merged["baseline_support_f"] == merged["baseline_support_e"]).all()


def _mapped_long_for(mapped: pd.DataFrame) -> pd.DataFrame:
    parts = []
    anchor = mapped.groupby(["issue_code"], observed=True)["fixture_decision_ts"].transform("min")
    for outcome in ("3", "1", "0"):
        parts.append(
            pd.DataFrame(
                {
                    "issue": mapped["issue_code"].astype(str),
                    "issue_year": mapped["issue_year"].astype(int),
                    "issue_anchor_ts": anchor,
                    "match_idx": mapped["match_idx"].astype(int),
                    "outcome": outcome,
                    "q_eu": mapped[f"q_effective_{outcome}"].astype(float),
                    "q_line": mapped[f"q_line_{outcome}"].astype(float),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# 2. Budget / ticket identities
# ---------------------------------------------------------------------------

def test_mixed_portfolio_budget_identity():
    """Mixed 50/50 must be exactly CNY1,024 per issue (CNY512 per arm);
    R3 128 tickets x 2 units; C1E3 216 tickets with 1 + extra on first 40."""
    _, _, bundles = _core_surface_frames()
    mixed = bundles[bundles["schedule"].eq("MIXED_50_50")]
    # Per-arm stake is CNY512; the portfolio total per issue is CNY1,024.
    assert np.isclose(
        mixed["stake_cny"], MIXED_TOTAL_CNY / 2, rtol=0, atol=1e-9
    ).all()
    per_issue_total = mixed.groupby("issue", observed=True)["stake_cny"].sum()
    assert np.isclose(
        per_issue_total, MIXED_TOTAL_CNY, rtol=0, atol=1e-9
    ).all()
    r3 = mixed[mixed["support_arm"].eq(PRIMARY_ARM)]
    assert r3["ticket_count"].eq(PRIMARY_TICKETS).all()
    c1 = mixed[mixed["support_arm"].eq(SECONDARY_ARM)]
    assert c1["ticket_count"].eq(SECONDARY_TICKETS).all()


def test_c1e3_unit_schedule_matches_accepted_residual_order():
    """The flexible unit allocator reproduces the accepted #373/#392 residual
    order for the standalone 512-unit schedule, and the 256-unit mixed
    schedule (1 base + 40 extra)."""
    codes = [f"c{i:03d}" for i in range(SECONDARY_TICKETS)]
    standalone = _ticket_units_flexible("24011", "C1E3", codes, 512)
    assert sum(standalone.values()) == 512
    base, residual = divmod(512, SECONDARY_TICKETS)
    assert set(standalone.values()) <= {base, base + 1}
    assert sum(1 for v in standalone.values() if v == base + 1) == residual
    mixed = _ticket_units_flexible("24011", "C1E3", codes, MIXED_C1E3_FUNDED_UNITS)
    assert sum(mixed.values()) == MIXED_C1E3_FUNDED_UNITS
    assert set(mixed.values()) <= {1, 2}
    assert sum(1 for v in mixed.values() if v == 2) == 40


# ---------------------------------------------------------------------------
# 3. Temporal discipline
# ---------------------------------------------------------------------------

def test_evidence_cutoff_frozen_and_extension_bounded():
    assert pd.Timestamp(EVIDENCE_QUERY_CUTOFF_TS, tz="UTC").tz is not None
    # Extension settlement must be strictly before the cutoff.
    ext_settle = _extension_settlement(DATA_ROOT)
    cutoff = pd.Timestamp(EVIDENCE_QUERY_CUTOFF_TS, tz="UTC")
    assert (
        ext_settle.loc[ext_settle["settlement_available"], "availability_ts"]
        .lt(cutoff)
        .all()
    )


def test_extension_mapping_learning_capped_at_pre_extension_boundary(frames):
    receipts = frames["extension_receipts"]
    boundary = pd.Timestamp(frames["source"]["pre_extension_boundary_ts"], tz="UTC")
    for item in receipts:
        r = item["receipt"]
        assert r.get("frozen_pre_extension_artifact") is True
        assert pd.Timestamp(r["learning_cutoff_ts"], tz="UTC") == boundary
        max_train = pd.Timestamp(
            r["maximum_training_label_timestamp"], tz="UTC"
        )
        assert max_train < boundary


# ---------------------------------------------------------------------------
# 4. Source-bound verifier: tamper resistance (REQ-E06)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frames():
    from src.n7_mixed_full_history.pipeline import scientific_frames

    return scientific_frames(REPO_ROOT, DATA_ROOT, verify_upstreams=False)


@pytest.fixture(scope="module")
def stored_and_replay(frames):
    """Stored package frames + the honest deterministic replay, computed once
    so tamper tests compare pure frames without re-fitting."""
    from src.n7_mixed_full_history.pipeline import _assert_frame

    stored = {
        key: frames[key] for key in frames if key in PACKAGE_KEYS
    }
    _assert_frame(frames["bundles"], frames["bundles"], "self")
    return stored, frames


PACKAGE_KEYS = {
    "source",
    "extension_receipts",
    "history",
    "extension_settlement",
    "bundles",
    "ledger",
    "performance",
    "paths",
    "contrasts",
    "correlations",
    "reconciliation",
    "gates",
    "decision",
}


def test_scientific_frames_produce_all_schedules(frames):
    bundles = frames["bundles"]
    for schedule in (
        "R3_STANDALONE", "C1E3_STANDALONE", "R0_COMPARATOR",
        "MIXED_50_50", "FRACTIONAL_50_50",
    ):
        assert bundles["schedule"].isin([schedule]).any(), schedule


def test_verifier_rejects_settlement_tamper(stored_and_replay):
    """EV-04/05: coordinate tampering of settlement PnL must fail."""
    from src.n7_mixed_full_history.pipeline import _semantic_checks, ContractError

    stored, replay = stored_and_replay
    bundles = stored["bundles"].copy()
    mask = (
        bundles["schedule"].eq("MIXED_50_50")
        & bundles["support_arm"].eq(PRIMARY_ARM)
        & bundles["native_included"].astype(bool)
    )
    idx = bundles.index[mask][0]
    bundles.loc[idx, "pnl_cny"] = bundles.loc[idx, "pnl_cny"] + 12345.0
    tampered = {**stored, "bundles": bundles}
    with pytest.raises(ContractError):
        _semantic_checks(tampered, replay)


def test_verifier_rejects_ledger_line_tamper(stored_and_replay):
    """A tampered ledger row that keeps the accounting equation cannot pass."""
    from src.n7_mixed_full_history.pipeline import _semantic_checks, ContractError

    stored, replay = stored_and_replay
    ledger = stored["ledger"].copy()
    if ledger.empty:
        pytest.skip("no ledger rows")
    ledger = ledger.copy()
    ledger["inclusion_status"] = "INCLUDED"
    ledger["reason"] = "INCLUDED_TRUSTED_SETTLEMENT_COMPLETE"
    tampered = {**stored, "ledger": ledger}
    with pytest.raises(ContractError):
        _semantic_checks(tampered, replay)


def test_manifest_forgery_fails():
    """A forged manifest hash must fail verification."""
    if not (RESULT / "MANIFEST.json").is_file():
        pytest.skip("result package not committed in test tree")
    original = json.loads((RESULT / "MANIFEST.json").read_text(encoding="utf-8"))
    forged = copy.deepcopy(original)
    forged["files"]["bundles.parquet"]["sha256"] = "0" * 64
    try:
        (RESULT / "MANIFEST.json.forged").write_text(
            json.dumps(forged), encoding="utf-8"
        )
        # verify_package reads the normal manifest; swap temporarily
        (RESULT / "MANIFEST.json").rename(RESULT / "MANIFEST.json.bak")
        (RESULT / "MANIFEST.json.forged").rename(RESULT / "MANIFEST.json")
        try:
            checks = verify_package(REPO_ROOT, RESULT, DATA_ROOT)
            assert checks.get("hash_bundles.parquet", True) is False
        finally:
            (RESULT / "MANIFEST.json").rename(RESULT / "MANIFEST.json.forged")
            (RESULT / "MANIFEST.json.bak").rename(RESULT / "MANIFEST.json")
    finally:
        (RESULT / "MANIFEST.json.forged").unlink(missing_ok=True)


def test_source_trace_tamper_fails(stored_and_replay):
    """A fake source trace (extension settlement claimed from an impossible
    source) must fail the history/extension-exclusion invariants."""
    from src.n7_mixed_full_history.pipeline import _semantic_checks, ContractError

    stored, replay = stored_and_replay
    history = stored["history"].copy()
    fake = history.iloc[0].copy()
    fake["issue_code"] = "25011"
    tampered_history = pd.concat([history, pd.DataFrame([fake])], ignore_index=True)
    tampered = {**stored, "history": tampered_history}
    with pytest.raises(ContractError):
        _semantic_checks(tampered, replay)


def test_decision_promotion_tamper_fails(stored_and_replay):
    """A decision file claiming promotion must fail."""
    from src.n7_mixed_full_history.pipeline import _semantic_checks, ContractError

    stored, replay = stored_and_replay
    decision = copy.deepcopy(stored["decision"])
    decision["strategy_promoted"] = True
    tampered = {**stored, "decision": decision}
    with pytest.raises(ContractError):
        _semantic_checks(tampered, replay)


# ---------------------------------------------------------------------------
# 5. Decision vocabulary and no-promotion
# ---------------------------------------------------------------------------

def test_decision_vocabulary(frames):
    assert frames["decision"]["verdict"] in (
        "MIXED_N7_EXTENSION_HISTORICAL_SIGNAL_NO_PROMOTION",
        "NO_MIXED_N7_EXTENSION_INCREMENT",
        "FAIL_CLOSED",
    )
    assert frames["decision"]["strategy_promoted"] is False
    assert frames["decision"]["prospective_authorized"] is False
    assert frames["decision"]["evidence_cutoff_ts"] is not None