"""Adversarial regression tests for BJ-UNIFIED-SOURCE-CENSUS-001 R5."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from source_census import census  # noqa: E402


def _remanifest(package: Path) -> None:
    """Attack model: adversary controls both artifact bytes and checksum list."""
    census.rewrite_checksums(package)


def test_data_root_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEIJING_LOT_DATA_ROOT", raising=False)
    with pytest.raises(census.DataRootError):
        census.resolve_data_root()


def test_strict_forward_requires_both_complete_clocks() -> None:
    assert (
        census.strict_forward_role(
            source_clock_complete=True, capture_clock_complete=True, mutable=False
        )
        == "STRICT_FORWARD_CANDIDATE"
    )
    assert (
        census.strict_forward_role(
            source_clock_complete=False, capture_clock_complete=True, mutable=True
        )
        == "RAW_ONLY"
    )
    assert (
        census.strict_forward_role(
            source_clock_complete=True, capture_clock_complete=False, mutable=True
        )
        == "RAW_ONLY"
    )


def test_required_periods_expose_gap_and_null_anomaly_strata() -> None:
    periods = census.profiling_periods()
    assert "GAP_2025_01_TO_03" in periods
    assert "NULL_OR_UNPARSEABLE_DATE" in periods
    assert "EARLIER_YEAR" in periods


def test_native_intersection_is_exact_not_candidate_mapping() -> None:
    assert census.native_key_intersection([("25001", 1)], [("x", 1)]) == 0
    assert census.canonical_causal_intersection() == "NOT_YET_EVALUATED"


def test_lineage_deduplicates_same_root() -> None:
    rows = census.lineage_decisions(
        [
            {"source_id": "raw", "lineage_root": "raw", "role": "HISTORICAL_PROXY"},
            {"source_id": "derived", "lineage_root": "raw", "role": "EXCLUDE"},
        ]
    )
    assert rows[0]["independent_evidence"] is True
    assert rows[1]["independent_evidence"] is False


def test_p34_capture_full_match_key_uses_row_idx_not_playid() -> None:
    columns = {"issue", "playid", "row_idx", "fetched_at", "match_id", "outcome_code"}
    assert census.capture_match_key_columns(columns) == (
        "issue",
        "fetched_at",
        "row_idx",
    )


def test_historical_proxy_role_fails_closed_without_profiled_proxy_surface() -> None:
    spec = next(item for item in census.SOURCES if item.source_id == "beidan_xlsm")
    assert (
        census.role_from_profile(
            spec,
            coverage_status="TABLE_MISSING",
            proxy_gate_valid_matches=0,
            proxy_gate_bucket_count=0,
            source_clock_complete=False,
            capture_clock_complete=False,
        )
        == "RECOVER"
    )
    assert (
        census.role_from_profile(
            spec,
            coverage_status="PROFILED",
            proxy_gate_valid_matches=0,
            proxy_gate_bucket_count=0,
            source_clock_complete=False,
            capture_clock_complete=False,
        )
        == "RAW_ONLY"
    )
    assert (
        census.role_from_profile(
            spec,
            coverage_status="PROFILED",
            proxy_gate_valid_matches=1,
            proxy_gate_bucket_count=2,
            source_clock_complete=False,
            capture_clock_complete=False,
        )
        == "RAW_ONLY"
    )
    assert (
        census.role_from_profile(
            spec,
            coverage_status="PROFILED",
            proxy_gate_valid_matches=1,
            proxy_gate_bucket_count=3,
            source_clock_complete=False,
            capture_clock_complete=False,
        )
        == "HISTORICAL_PROXY"
    )


def test_historical_proxy_field_requires_explicit_r8_eligibility() -> None:
    ineligible = {
        "pre_match_feature_eligible": "false",
        "terminal_value": "false",
        "admissible_use": "descriptive_only",
        "timestamp_grade": "UNCLASSIFIED",
    }
    eligible = {
        "pre_match_feature_eligible": "true",
        "terminal_value": "false",
        "admissible_use": "historical_proxy;descriptive_only",
        "timestamp_grade": "HISTORICAL_PROXY",
    }
    terminal = {
        **ineligible,
        "terminal_value": "true",
        "admissible_use": "settlement_only",
    }

    assert (
        census.field_admissible_use(
            "market_snapshots",
            "v1",
            source_role="HISTORICAL_PROXY",
            baseline=ineligible,
        )
        == "RAW_ONLY"
    )
    assert (
        census.field_admissible_use(
            "market_snapshots", "v1", source_role="HISTORICAL_PROXY", baseline=eligible
        )
        == "HISTORICAL_PROXY_CANDIDATE"
    )
    assert (
        census.field_admissible_use(
            "matches",
            "unknown_future_field",
            source_role="HISTORICAL_PROXY",
            baseline=None,
        )
        == "RAW_ONLY"
    )
    assert (
        census.field_admissible_use(
            "anything", "anything", source_role="HISTORICAL_PROXY", baseline=terminal
        )
        == "SETTLEMENT_ONLY"
    )


def test_r8_crosswalk_exposes_existing_field_as_ineligible_without_upgrade() -> None:
    row = census.hist40_baseline_record("beidan_xlsm", "market_snapshots", "v1")
    assert row is not None
    assert row["pre_match_feature_eligible"] == "false"
    assert (
        census.field_admissible_use(
            "market_snapshots", "v1", source_role="HISTORICAL_PROXY", baseline=row
        )
        == "RAW_ONLY"
    )


def test_r8_crosswalk_requires_the_bound_asset_hash_before_inheritance() -> None:
    row = census.hist40_baseline_record("beidan_xlsm", "matches", "handicap_line")
    assert row is not None
    assert (
        census.hist40_baseline_applies("beidan_xlsm", row["r8_content_sha256"]) is True
    )
    assert census.hist40_baseline_applies("beidan_xlsm", "0" * 64) is False
    assert (
        census.hist40_baseline_applies("bjdc_500_capture", row["r8_content_sha256"])
        is False
    )
    assert census.hist40_field_baseline_applies(row, row["r8_content_sha256"]) is True
    changed_field_hash = {**row, "r8_content_sha256": "different-field-asset"}
    assert (
        census.hist40_field_baseline_applies(
            changed_field_hash, row["r8_content_sha256"]
        )
        is False
    )


def test_profile_lane_uses_r8_row_only_when_the_asset_hash_is_bound() -> None:
    row = census.hist40_baseline_record("beidan_xlsm", "matches", "handicap_line")
    assert row is not None
    assert (
        census.profile_field_lane(
            "beidan_xlsm",
            "matches",
            "handicap_line",
            "HISTORICAL_PROXY",
            row["r8_content_sha256"],
        )
        == "HISTORICAL_PROXY_CANDIDATE"
    )
    assert (
        census.profile_field_lane(
            "beidan_xlsm", "matches", "handicap_line", "HISTORICAL_PROXY", "changed"
        )
        == "RAW_ONLY"
    )


def test_source_feature_availability_consumes_field_level_lanes() -> None:
    inventory = [{"source_id": "fixture", "role": "HISTORICAL_PROXY"}]
    fields = [
        {
            "source_id": "fixture",
            "field_family": "market_feature",
            "admissible_use": "HISTORICAL_PROXY_CANDIDATE",
        },
        {
            "source_id": "fixture",
            "field_family": "market_feature",
            "admissible_use": "RAW_ONLY",
        },
        {
            "source_id": "fixture",
            "field_family": "label_settlement",
            "admissible_use": "SETTLEMENT_ONLY",
        },
    ]
    rows = census.source_feature_availability(fields, inventory, [])
    market = next(row for row in rows if row["field_family"] == "market_feature")
    label = next(row for row in rows if row["field_family"] == "label_settlement")
    assert market["observed_field_count"] == 2
    assert market["r8_generic_admissible_field_count"] == 1
    assert market["issue250_scoped_surface_evidence_count"] == 0
    assert market["present"] is True
    assert label["observed_field_count"] == 1
    assert label["r8_generic_admissible_field_count"] == 0
    assert label["present"] is False


def test_source_routing_truth_table_covers_every_registered_source() -> None:
    inventory = [
        {
            "source_id": spec.source_id,
            "lane": spec.lane,
            "role": spec.intended_role,
        }
        for spec in census.SOURCES
    ]
    rows = {row["source_id"]: row for row in census._roles(inventory)}

    assert rows["beidan_xlsm"]["advance_to_251"] is True
    assert rows["beidan_xlsm"]["advance_to_252"] is True
    assert rows["beidan_features"]["advance_to_251"] is True
    assert rows["beidan_features"]["advance_to_252"] is False
    assert rows["beidan_history"]["advance_to_251"] is False
    assert rows["beidan_history"]["advance_to_252"] is False
    # bjdc_500_capture used to sit beside beidan_live here; that source is retired, so the
    # census no longer registers it and there is no routing row to assert.
    assert rows["beidan_live"]["advance_to_251"] is True
    assert rows["beidan_live"]["advance_to_252"] is True
    assert "bjdc_500_capture" not in rows
    for source_id in ("beidan_modeling_plus", "beidan_nowscore"):
        assert rows[source_id]["advance_to_251"] is False
        assert rows[source_id]["advance_to_252"] is False

    unknown = census._roles(
        [{"source_id": "unknown", "lane": "unknown", "role": "RAW_ONLY"}]
    )[0]
    assert unknown["advance_to_251"] is False
    assert unknown["advance_to_252"] is False
    assert unknown["decision"] == "UNMAPPED_LANE_NO_ROUTING"


def test_source_routing_verifier_rejects_tampered_historical_proxy() -> None:
    inventory = [
        {
            "source_id": spec.source_id,
            "lane": spec.lane,
            "role": spec.intended_role,
        }
        for spec in census.SOURCES
    ]
    roles = census._roles(inventory)
    assert census.verify_source_routing(inventory, roles) == []
    historical = next(row for row in roles if row["source_id"] == "beidan_xlsm")
    historical["advance_to_252"] = False
    assert census.verify_source_routing(inventory, roles) == [
        "source routing mismatch: beidan_xlsm:advance_to_252"
    ]


def test_field_lane_crosswalk_verifier_recomputes_against_r8_binding() -> None:
    baseline = census.hist40_baseline_record("beidan_xlsm", "matches", "handicap_line")
    assert baseline is not None
    inventory = [
        {
            "source_id": "beidan_xlsm",
            "content_sha256": baseline["r8_content_sha256"],
            "role": "HISTORICAL_PROXY",
        }
    ]
    fields = [
        {
            "source_id": "beidan_xlsm",
            "table": "matches",
            "column": "handicap_line",
            "admissible_use": "HISTORICAL_PROXY_CANDIDATE",
        }
    ]
    assert census.verify_field_lane_crosswalk(fields, inventory) == []
    fields[0]["admissible_use"] = "RAW_ONLY"
    assert census.verify_field_lane_crosswalk(fields, inventory) == [
        "field lane recomputation mismatch: beidan_xlsm.matches.handicap_line"
    ]


def test_decision_field_profiles_use_the_same_field_lane() -> None:
    profiles = [{"source_id": "fixture", "table": "matches", "field": "price"}]
    inventory = [
        {
            "source_id": "fixture",
            "table": "matches",
            "column": "price",
            "admissible_use": "RAW_ONLY",
        }
    ]
    census.annotate_decision_field_profiles(profiles, inventory)
    assert profiles == [
        {
            "source_id": "fixture",
            "table": "matches",
            "field": "price",
            "admissible_use": "RAW_ONLY",
            "availability_used_for_role": False,
        }
    ]


@pytest.mark.parametrize(
    "table,column",
    [
        ("official_500_settlements", "sp_home"),
        ("match_features", "official_sp_3"),
        ("match_features", "winning_sp"),
        ("match_features", "finalsp"),
        ("final_results", "home"),
        ("settlements", "sp_home"),
        ("outcome_features", "euro_final_p"),
        ("matches", "is_winner"),
        ("action_candidates", "net_return"),
        ("matches", "total_goals"),
        ("matches", "result_label"),
    ],
)
def test_terminal_and_final_sp_fields_are_never_inference_admissible(
    table: str, column: str
) -> None:
    assert census.field_admissible_use(table, column) == "SETTLEMENT_ONLY"


def test_clean_fixture_requires_and_accepts_external_anchor(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    anchor = census.package_anchor(package)
    assert anchor["crosswalk_sha256"] == census.sha256_file(census.HIST40_CROSSWALK)
    assert census.verify_package(package)["verified"] is False
    assert census.verify_package(package)["problems"] == [
        "external trusted anchor required"
    ]
    assert census.verify_package(package, trusted_anchor=anchor)["verified"] is True


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    [
        (
            "tables/source_role_matrix.csv",
            "RAW_ONLY",
            "HISTORICAL_PROXY",
            "role recomputation mismatch",
        ),
        (
            "tables/intersection_levels.csv",
            "CANDIDATE_MAPPED_RANGE",
            "FORGED_INTERSECTION",
            "semantic hash mismatch: tables/intersection_levels.csv",
        ),
        (
            "tables/field_profile.csv",
            "fixture",
            "forged",
            "semantic hash mismatch: tables/field_profile.csv",
        ),
        (
            "tables/coverage_by_period.csv",
            "fixture",
            "forged",
            "semantic hash mismatch: tables/coverage_by_period.csv",
        ),
        (
            "tables/m_per_issue_distribution.csv",
            "fixture",
            "forged",
            "semantic hash mismatch: tables/m_per_issue_distribution.csv",
        ),
        (
            "tables/proxy_surface_profile.csv",
            "fixture",
            "forged",
            "semantic hash mismatch: tables/proxy_surface_profile.csv",
        ),
    ],
)
def test_remanifested_decision_artifact_tamper_fails(
    tmp_path: Path, relative: str, old: str, new: str, expected: str
) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / relative
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8"
    )
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert expected in verdict["problems"]


def test_remanifested_source_trace_tamper_fails(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / "tables/source_inventory.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("fixture", "forged", 1),
        encoding="utf-8",
    )
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert "semantic hash mismatch: tables/source_inventory.csv" in verdict["problems"]


def test_remanifested_manifest_issue_tamper_fails(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / "MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["issue"] = 999
    path.write_text(json.dumps(data), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert "manifest issue mismatch" in verdict["problems"]


def test_manifest_cannot_claim_a_different_producer_implementation(
    tmp_path: Path,
) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["implementation_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _remanifest(package)
    verdict = census.verify_package(
        package, trusted_anchor=census.package_anchor(package)
    )
    assert verdict["verified"] is False
    assert "producer implementation hash mismatch" in verdict["problems"]


def test_re_signed_manifest_attack_requires_external_trusted_anchor(
    tmp_path: Path,
) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    anchor = census.package_anchor(package)
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    artifact = attacked / "tables" / "intersection_levels.csv"
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace(
            "RAW_PRESENT", "FORGED_PRESENT", 1
        ),
        encoding="utf-8",
    )
    manifest_path = attacked / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantic_hashes"]["tables/intersection_levels.csv"] = census.sha256_file(
        artifact
    )
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked, trusted_anchor=anchor)
    assert verdict["verified"] is False
    assert "trusted anchor manifest mismatch" in verdict["problems"]
    assert "trusted anchor payload hash inventory mismatch" in verdict["problems"]


def test_scoped_proxy_semantics_do_not_misclassify_two_price_markets() -> None:
    assert census.PROXY_SURFACES["euro_1x2"]["role_gate_eligible"] is True
    for market in ("asian_handicap", "over_under"):
        policy = census.PROXY_SURFACES[market]
        assert policy["role_gate_eligible"] is False
        assert "NOT" in str(policy["vector_semantics"])


def test_r8_field_market_overrides_are_exact_and_fail_on_tamper() -> None:
    rows = [dict(row) for row in census.HIST40_SCOPE_OVERRIDES]
    assert census.verify_hist40_scope_overrides(rows) == []
    rows[0]["admissible_use"] = "RAW_ONLY"
    assert census.verify_hist40_scope_overrides(rows) == [
        "R8 field-market override mismatch: beidan_xlsm.exotic_odds.odds.correct_score:admissible_use"
    ]


@pytest.mark.parametrize(
    "relative",
    [
        "tables/source_feature_availability.csv",
        "tables/duplicate_profile.csv",
        "tables/unresolved_question_ledger.csv",
        "evidence/req_sc_evidence.csv",
        "REPORT.md",
        "figures/source_feature_heatmap.svg",
    ],
)
def test_all_payloads_are_bound_to_external_anchor(
    tmp_path: Path, relative: str
) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    anchor = census.package_anchor(package)
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    target = attacked / relative
    target.write_text(target.read_text(encoding="utf-8") + "forged\n", encoding="utf-8")
    manifest_path = attacked / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantic_hashes"][relative] = census.sha256_file(target)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked, trusted_anchor=anchor)
    assert verdict["verified"] is False
    assert "trusted anchor manifest mismatch" in verdict["problems"]
    assert "trusted anchor payload hash inventory mismatch" in verdict["problems"]


def test_write_once_publication_refuses_replacement(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    original = (package / "REPORT.md").read_bytes()
    with pytest.raises(FileExistsError):
        census.build_fixture_package(package)
    assert (package / "REPORT.md").read_bytes() == original


def test_intersection_levels_have_one_definition(tmp_path: Path) -> None:
    """The verifier, the fixture and the producer must agree on the level set.

    They were written out separately once. When the native-key overlap went away with the retired
    500 store, the producer stopped emitting it while the verifier still demanded it, so every
    production package failed verification -- and the fixture, which agreed with itself, kept the
    tests green. These examples pin the single definition to what each side actually uses.
    """
    import csv

    package = census.build_fixture_package(tmp_path / "package")
    with (package / "tables/intersection_levels.csv").open(encoding="utf-8") as handle:
        emitted = {row["level"] for row in csv.DictReader(handle)}
    assert emitted == set(census.INTERSECTION_LEVELS), (
        "the fixture must emit exactly the levels the package contract declares")
    assert "NATIVE_KEY_INTERSECTION" not in emitted, (
        "the native-key overlap was computed against the retired 500 store and has no producer")
    # a package built to the contract verifies, so the two sides cannot drift apart silently
    anchor = census.package_anchor(package)
    assert census.verify_package(package, trusted_anchor=anchor)["verified"] is True, (
        census.verify_package(package, trusted_anchor=anchor)["problems"])


def test_the_producer_emits_every_declared_intersection_level(tmp_path: Path) -> None:
    """Call the emitter itself, not the fixture that agrees with the verifier.

    The earlier example checked the fixture against the verifier and inherited the blind spot it
    was meant to close: the producer's levels were still literals, so omitting one left it green
    while production packages failed verification. These examples read the emitter's own output,
    on the path where no source is present and on the path where the stores exist but hold
    nothing.
    """
    rows = census._intersections(tmp_path)                       # no sources at all
    assert {row["level"] for row in rows} == set(census.INTERSECTION_LEVELS)

    # stores present but empty: the levels must not depend on finding rows
    (tmp_path / "beidan_live.db").write_bytes(b"")
    (tmp_path / "derived/500_bjdc").mkdir(parents=True, exist_ok=True)
    (tmp_path / "derived/500_bjdc/500_bjdc.sqlite").write_bytes(b"")
    rows = census._intersections(tmp_path)
    assert {row["level"] for row in rows} == set(census.INTERSECTION_LEVELS)
    assert "NATIVE_KEY_INTERSECTION" not in {row["level"] for row in rows}


def test_the_emitter_names_its_levels_from_the_contract() -> None:
    """No level literal in the emitter: the contract is the only place they are written.

    Hard-coded names in the emitter are what let it drift from the verifier once already.
    """
    import ast

    source = (Path(census.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == "_intersections")
    literals = [
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value.isupper() and node.value.endswith(("PRESENT", "RANGE", "INTERSECTION"))
    ]
    assert literals == [], f"the emitter still names levels literally: {literals}"
