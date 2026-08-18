"""Contract tests for #252 temporal semantics.

The tests deliberately use compact in-memory inputs: no production data source
is mutated.  They cover strict/proxy separation, exact UTC cutoff selection,
deterministic segment fallback, and tamper-resistant package semantics.
"""
from __future__ import annotations

import hashlib
import json
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


def _poll_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fixture_id": ["I1_01", "I1_01", "I1_02"],
            "issue_code": ["I1", "I1", "I1"],
            "match_idx": [1, 1, 2],
            "snapshot_horizon": ["poll", "poll", "poll"],
            "time_semantics": ["POLL_STARTED_AT_UTC"] * 3,
            "causal_grade": ["POLL_STARTED_AGAINST_CURRENT_SCHEDULE_REFERENCE"] * 3,
            "source_id": ["beidan_live_db_merged_unknown_cell_lineage"] * 3,
            "availability_mask": [True] * 3,
            "storage_present_cell_count": [3] * 3,
            "valid_sp_cell_count": [3] * 3,
            "poll_started_at_utc": [
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


def _proxy_summary() -> pd.DataFrame:
    rows = []
    roles = {
        "euro_1x2": "EURO_1X2_OUTCOME_PROXY",
        "kelly_1x2": "KELLY_1X2_DIAGNOSTIC",
    }
    for horizon in ("initial", "10h", "1h"):
        for market, role in roles.items():
            rows.append(
                {
                    "snapshot_horizon": horizon,
                    "market": market,
                    "field_role": role,
                    "p34_m3_compatible": market == "euro_1x2",
                    "fixture_count": 2,
                    "issue_count": 1,
                    "market_row_count": 2,
                    "complete_consensus_rows": 2,
                    "available_value_cells": 6,
                }
            )
    return pd.DataFrame(rows)


def test_strict_and_proxy_namespaces_cannot_pool_silently() -> None:
    strict = _poll_rows()
    proxy = strict.iloc[[0]].copy()
    proxy["snapshot_horizon"] = "10h"
    proxy["time_semantics"] = "SOURCE_RELATIVE_LABEL"
    proxy["causal_grade"] = "HISTORICAL_PROXY_LABEL_ONLY"
    proxy["source_id"] = "beidan_xlsm_workbook"
    proxy["poll_started_at_utc"] = pd.NaT

    strict_valid = validate_observations(strict, namespace="poll_start_forward")
    proxy_valid = validate_observations(proxy, namespace="historical_proxy")
    assert strict_valid["poll_started_at_utc"].notna().all()
    assert proxy_valid["poll_started_at_utc"].isna().all()

    with pytest.raises(TemporalSemanticsError, match="cannot pool"):
        validate_observations(pd.concat([strict, proxy]), namespace="poll_start_forward")


def test_issue_cutoff_selects_latest_available_not_future_and_reports_staleness() -> None:
    view = build_issue_view(
        _poll_rows(),
        issue_code="I1",
        decision_at_utc="2026-01-01T01:00:00Z",
    )
    selected = view.set_index("fixture_id")
    # The 01:30 row is future at the 01:00 decision epoch, so 00:00 wins.
    assert selected.loc["I1_01", "selected_poll_started_at_utc"] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert selected.loc["I1_01", "poll_start_age_minutes"] == 60.0
    assert selected.loc["I1_02", "drop_reason"] == "AVAILABLE"
    assert (selected["selected_poll_started_at_utc"] <= pd.Timestamp("2026-01-01T01:00:00Z")).all()


def test_segment_fallback_uses_each_segment_cutoff_without_later_fixture_leakage() -> None:
    strict = _poll_rows()
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
    assert (segments["selected_poll_started_at_utc"] <= segments["decision_at_utc"]).all()
    assert (segments["decision_at_utc"] < segments["kickoff_at_utc"]).all()


def test_boundary_inputs_fail_closed() -> None:
    bad = _poll_rows()
    bad.loc[0, "poll_started_at_utc"] = "2026-01-01 00:00:00"  # timezone-less
    with pytest.raises(TemporalSemanticsError, match="UTC"):
        validate_observations(bad, namespace="poll_start_forward")

    proxy = _poll_rows().iloc[[0]].copy()
    proxy["snapshot_horizon"] = "initial"
    proxy["time_semantics"] = "SOURCE_RELATIVE_LABEL"
    proxy["causal_grade"] = "HISTORICAL_PROXY_LABEL_ONLY"
    proxy["source_id"] = "beidan_xlsm_workbook"
    proxy["poll_started_at_utc"] = pd.NaT
    proxy.loc[proxy.index[0], "snapshot_horizon"] = "final"
    with pytest.raises(TemporalSemanticsError, match="accepted proxy horizons"):
        validate_observations(proxy, namespace="historical_proxy")

    string_mask = _poll_rows()
    string_mask["availability_mask"] = ["False", "True", "True"]
    with pytest.raises(TemporalSemanticsError, match="exact boolean"):
        validate_observations(string_mask, namespace="poll_start_forward")


def test_incomplete_snapshot_is_distinct_from_no_snapshot() -> None:
    strict = _poll_rows()
    strict.loc[strict["fixture_id"].eq("I1_02"), "availability_mask"] = False
    strict.loc[strict["fixture_id"].eq("I1_02"), "storage_present_cell_count"] = 2
    strict.loc[strict["fixture_id"].eq("I1_02"), "valid_sp_cell_count"] = 2
    view = build_issue_view(
        strict, issue_code="I1", decision_at_utc="2026-01-01T01:00:00Z"
    ).set_index("fixture_id")
    assert view.loc["I1_02", "drop_reason"] == "OBSERVATION_UNAVAILABLE_OR_INCOMPLETE"
    assert view.loc["I1_02", "latest_storage_present_cell_count_by_cutoff"] == 2

    early = build_issue_view(
        _poll_rows(), issue_code="I1", decision_at_utc="2025-12-31T23:00:00Z"
    )
    assert set(early["drop_reason"]) == {"NO_OBSERVATION_BY_CUTOFF"}


def test_invalid_decimal_sp_is_not_model_available_and_earlier_valid_poll_can_win() -> None:
    rows = _poll_rows()
    fixture_two = rows["fixture_id"].eq("I1_02")
    rows.loc[fixture_two, "availability_mask"] = False
    rows.loc[fixture_two, "storage_present_cell_count"] = 3
    rows.loc[fixture_two, "valid_sp_cell_count"] = 2
    view = build_issue_view(
        rows, issue_code="I1", decision_at_utc="2026-01-01T01:00:00Z"
    ).set_index("fixture_id")
    assert view.loc["I1_02", "drop_reason"] == "INVALID_VALUE"

    later_invalid = rows.iloc[[0]].copy()
    later_invalid["poll_started_at_utc"] = "2026-01-01T00:30:00Z"
    later_invalid["availability_mask"] = False
    later_invalid["storage_present_cell_count"] = 3
    later_invalid["valid_sp_cell_count"] = 2
    combined = pd.concat([rows, later_invalid], ignore_index=True)
    view = build_issue_view(
        combined, issue_code="I1", decision_at_utc="2026-01-01T01:00:00Z"
    ).set_index("fixture_id")
    assert view.loc["I1_01", "drop_reason"] == "AVAILABLE"
    assert view.loc["I1_01", "selected_poll_started_at_utc"] == pd.Timestamp(
        "2026-01-01T00:00:00Z"
    )


def test_semantic_verifier_rejects_remanifested_selection_ledger_and_manifest_tampering(tmp_path: Path) -> None:
    """REQ-E06: SHA rehash cannot launder a changed causal selection receipt."""
    package = write_package(
        tmp_path / "package",
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    assert verify_package(package)["status"] == "PASS"

    selection = package / "tables" / "poll_start_selection.csv"
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
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
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
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    proxy_path = package / "tables" / "proxy_horizon_market_summary.csv"
    proxy = pd.read_csv(proxy_path)
    proxy.loc[0, "fixture_count"] = 999999
    proxy.to_csv(proxy_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="proxy summary"):
        verify_package(package)

    # Rebuild, then attack the serialized boolean domain.
    package = write_package(
        tmp_path / "package",
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
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


def test_verifier_rejects_resigned_source_snapshot_and_proxy_role_tampering(
    tmp_path: Path,
) -> None:
    package = write_package(
        tmp_path / "package",
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    snapshot_path = package / "tables" / "poll_start_input_snapshot.parquet"
    snapshot = pd.read_parquet(snapshot_path)
    snapshot.loc[0, "valid_sp_cell_count"] = 2
    snapshot.to_parquet(snapshot_path, index=False)
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["poll_start_input_snapshot_sha256"] = hashlib.sha256(
        snapshot_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(
        (AssertionError, TemporalSemanticsError),
        match="available observations|source replay",
    ):
        verify_package(package)

    package = write_package(
        tmp_path / "package",
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    proxy_path = package / "tables" / "proxy_horizon_market_summary.csv"
    proxy = pd.read_csv(proxy_path)
    target = proxy.index[proxy["market"].eq("kelly_1x2")][0]
    proxy.loc[target, "field_role"] = "EURO_1X2_OUTCOME_PROXY"
    proxy.to_csv(proxy_path, index=False)
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["proxy_summary_records"] = proxy.assign(
        p34_m3_compatible=proxy["p34_m3_compatible"].astype(str)
    ).to_dict(orient="records")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(AssertionError, match="field role"):
        verify_package(package)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("valid_sp_cell_count", 999, "cell count"),
        ("source_id", "beidan_history_db", "merged-source"),
        (
            "latest_poll_started_at_utc_by_cutoff",
            "2099-01-01T00:00:00Z",
            "after decision",
        ),
    ],
)
def test_verifier_rejects_dropped_row_domain_role_and_clock_tamper(
    tmp_path: Path, column: str, value: object, message: str
) -> None:
    package = write_package(
        tmp_path / "package",
        poll_rows=_poll_rows(),
        proxy_coverage=_proxy_summary(),
        source_receipt={"beidan_live_db": "a" * 64},
    )
    path = package / "tables" / "segment_selection.csv"
    frame = pd.read_csv(path)
    dropped = frame.index[frame["drop_reason"].ne("AVAILABLE")]
    if len(dropped) == 0:
        frame.loc[0, "drop_reason"] = "INVALID_VALUE"
        frame.loc[0, "availability_mask"] = False
        frame.loc[0, "selected_poll_started_at_utc"] = ""
        frame.loc[0, "poll_start_age_minutes"] = float("nan")
        frame.loc[0, "storage_present_cell_count"] = 0
        frame.loc[0, "valid_sp_cell_count"] = 0
        frame.loc[0, "model_available_cell_count"] = 0
        dropped = pd.Index([0])
    frame.loc[dropped[0], column] = value
    frame.to_csv(path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match=message):
        verify_package(package)
