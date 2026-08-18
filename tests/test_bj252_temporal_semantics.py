"""Contract tests for #252 temporal semantics.

The tests deliberately use compact in-memory inputs: no production data source
is mutated.  They cover strict/proxy separation, exact UTC cutoff selection,
deterministic segment fallback, and tamper-resistant package semantics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from temporal_semantics import (  # noqa: E402
    TemporalSemanticsError,
    build_issue_view,
    build_segment_views,
    validate_observations,
)
from bj252_temporal_package import (  # noqa: E402
    rehash_package,
    verify_package,
    write_package,
)


def _strict_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fixture_id": ["I1_01", "I1_01", "I1_02"],
            "issue_code": ["I1", "I1", "I1"],
            "match_idx": [1, 1, 2],
            "snapshot_horizon": ["observed", "observed", "observed"],
            "time_semantics": ["OBSERVED_AT_UTC"] * 3,
            "causal_grade": ["OBSERVED_AGAINST_CURRENT_SCHEDULE_REFERENCE"] * 3,
            "source_id": ["beidan_live_db"] * 3,
            "availability_mask": [True] * 3,
            "available_cell_count": [3] * 3,
            "observed_at_utc": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T01:30:00Z",
                "2026-01-01T00:30:00Z",
            ],
            "kickoff_at_utc": [
                "2026-01-01T03:00:00Z",
                "2026-01-01T03:00:00Z",
                "2026-01-02T03:00:00Z",
            ],
        }
    )


def test_strict_and_proxy_namespaces_cannot_pool_silently() -> None:
    strict = _strict_rows()
    proxy = strict.iloc[[0]].copy()
    proxy["snapshot_horizon"] = "10h"
    proxy["time_semantics"] = "SOURCE_RELATIVE_LABEL"
    proxy["causal_grade"] = "HISTORICAL_PROXY_LABEL_ONLY"
    proxy["source_id"] = "beidan_xlsm_workbook"
    proxy["observed_at_utc"] = pd.NaT

    strict_valid = validate_observations(strict, namespace="strict_forward")
    proxy_valid = validate_observations(proxy, namespace="historical_proxy")
    assert strict_valid["observed_at_utc"].notna().all()
    assert proxy_valid["observed_at_utc"].isna().all()

    with pytest.raises(TemporalSemanticsError, match="cannot pool"):
        validate_observations(pd.concat([strict, proxy]), namespace="strict_forward")


def test_issue_cutoff_selects_latest_available_not_future_and_reports_staleness() -> None:
    view = build_issue_view(
        _strict_rows(),
        issue_code="I1",
        decision_at_utc="2026-01-01T01:00:00Z",
    )
    selected = view.set_index("fixture_id")
    # The 01:30 row is future at the 01:00 decision epoch, so 00:00 wins.
    assert selected.loc["I1_01", "selected_observed_at_utc"] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert selected.loc["I1_01", "staleness_minutes"] == 60.0
    assert selected.loc["I1_02", "drop_reason"] == "AVAILABLE"
    assert (selected["selected_observed_at_utc"] <= pd.Timestamp("2026-01-01T01:00:00Z")).all()


def test_segment_fallback_uses_each_segment_cutoff_without_later_fixture_leakage() -> None:
    strict = _strict_rows()
    segments = build_segment_views(
        strict,
        issue_code="I1",
        lead_minutes=60,
        timezone_name="Asia/Shanghai",
    )
    # I1_01 starts on Jan 1 and I1_02 on Jan 2 UTC; each gets an independent
    # local-date segment.  Segment 0's 02:00 cutoff cannot consume 01:30 only
    # if it is beyond the declared cutoff, and segment 1 has its own cutoff.
    assert segments["segment_idx"].nunique() == 2
    assert (segments["selected_observed_at_utc"] <= segments["decision_at_utc"]).all()
    assert (segments["decision_at_utc"] < segments["kickoff_at_utc"]).all()


def test_boundary_inputs_fail_closed() -> None:
    bad = _strict_rows()
    bad.loc[0, "observed_at_utc"] = "2026-01-01 00:00:00"  # timezone-less
    with pytest.raises(TemporalSemanticsError, match="UTC"):
        validate_observations(bad, namespace="strict_forward")

    proxy = _strict_rows().iloc[[0]].copy()
    proxy["snapshot_horizon"] = "initial"
    proxy["time_semantics"] = "SOURCE_RELATIVE_LABEL"
    proxy["causal_grade"] = "HISTORICAL_PROXY_LABEL_ONLY"
    proxy["source_id"] = "beidan_xlsm_workbook"
    proxy["observed_at_utc"] = pd.NaT
    proxy.loc[proxy.index[0], "snapshot_horizon"] = "final"
    with pytest.raises(TemporalSemanticsError, match="accepted proxy horizons"):
        validate_observations(proxy, namespace="historical_proxy")

    string_mask = _strict_rows()
    string_mask["availability_mask"] = ["False", "True", "True"]
    with pytest.raises(TemporalSemanticsError, match="exact boolean"):
        validate_observations(string_mask, namespace="strict_forward")


def test_incomplete_snapshot_is_distinct_from_no_snapshot() -> None:
    strict = _strict_rows()
    strict.loc[strict["fixture_id"].eq("I1_02"), "availability_mask"] = False
    strict.loc[strict["fixture_id"].eq("I1_02"), "available_cell_count"] = 2
    view = build_issue_view(
        strict, issue_code="I1", decision_at_utc="2026-01-01T01:00:00Z"
    ).set_index("fixture_id")
    assert view.loc["I1_02", "drop_reason"] == "OBSERVATION_UNAVAILABLE_OR_INCOMPLETE"
    assert view.loc["I1_02", "observed_cell_count_by_cutoff"] == 2

    early = build_issue_view(
        _strict_rows(), issue_code="I1", decision_at_utc="2025-12-31T23:00:00Z"
    )
    assert set(early["drop_reason"]) == {"NO_OBSERVATION_BY_CUTOFF"}


def test_semantic_verifier_rejects_remanifested_selection_ledger_and_manifest_tampering(tmp_path: Path) -> None:
    """REQ-E06: SHA rehash cannot launder a changed causal selection receipt."""
    package = write_package(
        tmp_path / "package",
        strict_rows=_strict_rows(),
        proxy_coverage=pd.DataFrame(
            {"snapshot_horizon": ["initial", "10h", "1h"], "fixture_count": [2, 2, 2]}
        ),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    assert verify_package(package)["status"] == "PASS"

    selection = package / "tables" / "strict_selection.csv"
    original = selection.read_text(encoding="utf-8")
    selection.write_text(original.replace("AVAILABLE", "NO_OBSERVATION_BY_CUTOFF", 1), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(AssertionError, match="dropped selection retains observation|coverage"):
        verify_package(package)

    selection.write_text(original, encoding="utf-8")
    rehash_package(package)
    manifest = package / "MANIFEST.json"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace("BJ-UNIFIED-TEMPORAL-SEMANTICS-001", "FORGED"), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(AssertionError, match="contract"):
        verify_package(package)


def test_verifier_rejects_remanifested_decision_table_mutations(tmp_path: Path) -> None:
    package = write_package(
        tmp_path / "package",
        strict_rows=_strict_rows(),
        proxy_coverage=pd.DataFrame(
            {
                "snapshot_horizon": ["initial", "10h", "1h"],
                "fixture_count": [2, 2, 2],
                "issue_count": [1, 1, 1],
                "market_row_count": [6, 6, 6],
                "complete_consensus_rows": [6, 6, 6],
                "available_value_cells": [18, 18, 18],
            }
        ),
        source_receipt={"beidan_live_db": "a" * 64},
    )

    cutoff_path = package / "tables" / "cutoff_coverage.csv"
    cutoff = pd.read_csv(cutoff_path)
    cutoff.loc[0, "available_fixture_count"] = 999
    cutoff.to_csv(cutoff_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="cutoff coverage"):
        verify_package(package)


def test_verifier_rejects_remanifested_proxy_and_boolean_mutations(tmp_path: Path) -> None:
    package = write_package(
        tmp_path / "package",
        strict_rows=_strict_rows(),
        proxy_coverage=pd.DataFrame(
            {"snapshot_horizon": ["initial", "10h", "1h"], "fixture_count": [2, 2, 2]}
        ),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    proxy_path = package / "tables" / "proxy_horizon_summary.csv"
    proxy = pd.read_csv(proxy_path)
    proxy.loc[0, "fixture_count"] = 999999
    proxy.to_csv(proxy_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="proxy summary"):
        verify_package(package)

    # Rebuild, then attack the serialized boolean domain.
    package = write_package(
        tmp_path / "package",
        strict_rows=_strict_rows(),
        proxy_coverage=pd.DataFrame(
            {"snapshot_horizon": ["initial", "10h", "1h"], "fixture_count": [2, 2, 2]}
        ),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    selection_path = package / "tables" / "cutoff_selection.csv"
    selection = pd.read_csv(selection_path)
    selection["availability_mask"] = selection["availability_mask"].astype(object)
    selection.loc[0, "availability_mask"] = "NOT_A_BOOLEAN"
    selection.to_csv(selection_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="canonical boolean"):
        verify_package(package)
