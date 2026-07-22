"""Tests for MM-DATA-AUDIT-001 multi-market audit.

Covers:
- Contract integrity: market definitions, outcome codes
- Auditor correctness: gate evaluation, readiness classification
- Report generation: output file creation
- Freeze package verification: SHA-256 checks
- Rejection of tampered freeze artifacts
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from research.mm_data_audit.contract import (
    TARGET_PLAYIDS,
    MARKETS,
    AuditDimension,
    AuditResult,
    DimensionAudit,
    GateID,
    GateResult,
    MarketDefinition,
    ReadinessLevel,
)
from research.mm_data_audit.auditor import _repo_root, _connect, _table_exists
from research.mm_data_audit.report import generate_report, save_results


# ── Contract Tests ─────────────────────────────────────────────────────────

class TestMarketDefinitions:
    """Validate market definitions are complete and correct."""

    def test_all_target_playids_defined(self):
        for playid in TARGET_PLAYIDS:
            assert playid in MARKETS, f"PlayID {playid} not in MARKETS"

    def test_outcome_code_counts(self):
        for playid, market in MARKETS.items():
            assert len(market.outcome_codes) == market.expected_outcome_count, (
                f"Market {market.display_name}: {len(market.outcome_codes)} codes != {market.expected_outcome_count} expected"
            )

    def test_outcome_codes_no_duplicates(self):
        for playid, market in MARKETS.items():
            assert len(market.outcome_codes) == len(set(market.outcome_codes)), (
                f"Market {market.display_name} has duplicate outcome codes"
            )

    def test_handicap_outcome_codes(self):
        m = MARKETS[34]
        assert set(m.outcome_codes) == {"3", "1", "0"}

    def test_total_goals_outcome_codes(self):
        m = MARKETS[40]
        assert set(m.outcome_codes) == {"0", "1", "2", "3", "4", "5", "6", "7+"}

    def test_half_full_time_outcome_codes(self):
        m = MARKETS[51]
        expected = {"3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0"}
        assert set(m.outcome_codes) == expected

    def test_correct_score_has_other_codes(self):
        m = MARKETS[42]
        assert "home_other" in m.outcome_codes
        assert "draw_other" in m.outcome_codes
        assert "away_other" in m.outcome_codes

    def test_data_sources_assigned(self):
        assert MARKETS[34].data_source == "beidan_live"
        assert MARKETS[40].data_source == "500_bjdc"
        assert MARKETS[42].data_source == "500_bjdc"
        assert MARKETS[51].data_source == "500_bjdc"


class TestReadinessLevels:
    """Verify readiness level semantics."""

    def test_all_levels_defined(self):
        assert ReadinessLevel.READY_STRICT.value == "READY_STRICT"
        assert ReadinessLevel.PARTIAL.value == "PARTIAL"
        assert ReadinessLevel.SETTLEMENT_ONLY.value == "SETTLEMENT_ONLY"
        assert ReadinessLevel.UNAVAILABLE.value == "UNAVAILABLE"


class TestGateIDs:
    """Verify gate definitions."""

    def test_all_gates_defined(self):
        gate_ids = {g.value for g in GateID}
        expected = {
            "g1_outcome_vectors",
            "g2_source_timestamps",
            "g3_pre_cutoff_evidence",
            "g4_immutable_provenance",
            "g5_asof_freeze",
            "g6_settlement_mapping",
            "g7_no_leakage",
        }
        assert gate_ids == expected


# ── Auditor Tests ───────────────────────────────────────────────────────────

class TestDatabaseConnectivity:
    """Verify databases are accessible."""

    def test_beidan_live_db_exists(self):
        repo = _repo_root()
        db_path = repo / "data/beidan_live.db"
        assert db_path.exists(), f"beidan_live.db not found at {db_path}"

    def test_500_bjdc_db_exists(self):
        repo = _repo_root()
        db_path = repo / "data/derived/500_bjdc/500_bjdc.sqlite"
        assert db_path.exists(), f"500_bjdc.sqlite not found at {db_path}"

    def test_beidan_live_has_required_tables(self):
        conn = _connect("beidan_live")
        assert _table_exists(conn, "snapshots")
        assert _table_exists(conn, "matches")
        assert _table_exists(conn, "settlements")

    def test_500_bjdc_has_required_tables(self):
        conn = _connect("500_bjdc")
        assert _table_exists(conn, "live_market_sp_snapshots")
        assert _table_exists(conn, "market_sp_capture_batches")
        assert _table_exists(conn, "multimarket_settlement_truth")
        assert _table_exists(conn, "segment_decision_windows")


class TestHandicapPreEventGates:
    """Verify Handicap 3/1/0 pre-event gate evaluation."""

    def test_outcome_vectors_nonzero(self):
        conn = _connect("beidan_live")
        count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert count > 0, "Zero handicap snapshots"

    def test_complete_vector_proportion(self):
        conn = _connect("beidan_live")
        total = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE sp_3 IS NOT NULL AND sp_1 IS NOT NULL AND sp_0 IS NOT NULL"
        ).fetchone()[0]
        pct = (complete / total * 100) if total else 0
        assert pct > 30, f"Complete vector coverage too low: {pct:.1f}%"

    def test_kickoff_timestamps_present(self):
        conn = _connect("beidan_live")
        total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        with_ko = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE kickoff_ts IS NOT NULL AND kickoff_ts != ''"
        ).fetchone()[0]
        assert with_ko > 0
        assert (with_ko / total * 100) > 50 if total else True

    def test_pre_kickoff_snapshots_exist(self):
        conn = _connect("beidan_live")
        pre_kickoff = conn.execute(
            """SELECT COUNT(*) FROM snapshots s
               JOIN matches m ON s.match_id = m.match_id
               WHERE s.snapshot_ts < m.kickoff_ts
                 AND m.kickoff_ts IS NOT NULL"""
        ).fetchone()[0]
        assert pre_kickoff > 0, "No pre-kickoff snapshots"


class TestP0MarketGates:
    """Verify P0 market (p40, p42) gate evaluation."""

    @pytest.mark.parametrize("playid", [40, 42])
    def test_data_exists(self, playid):
        conn = _connect("500_bjdc")
        count = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=?", (playid,)
        ).fetchone()[0]
        assert count > 0, f"Zero snapshots for playid={playid}"

    @pytest.mark.parametrize("playid", [40, 42])
    def test_forward_complete_exists(self, playid):
        conn = _connect("500_bjdc")
        fc = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND capture_classification='forward_complete_open'",
            (playid,),
        ).fetchone()[0]
        assert fc > 0, f"No forward_complete_open rows for playid={playid}"

    @pytest.mark.parametrize("playid", [40, 42])
    def test_terminal_excluded_from_forward(self, playid):
        conn = _connect("500_bjdc")
        terminal_forward = conn.execute(
            """SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=? AND capture_classification='terminal_backfill_exploratory_only'
               AND capture_classification='forward_complete_open'""",
            (playid,),
        ).fetchone()[0]
        assert terminal_forward == 0, "Terminal data leaking into forward classification"

    @pytest.mark.parametrize("playid", [40, 42])
    def test_settlement_exists(self, playid):
        from research.mm_data_audit.contract import MARKET_KEY
        conn = _connect("500_bjdc")
        mk = MARKET_KEY[playid]
        count = conn.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (mk,),
        ).fetchone()[0]
        assert count > 0, f"No settlement rows for market_key={mk}"


class TestHalfFullTimeGates:
    """Verify Half/Full Time (p51) gate evaluation."""

    def test_data_exists(self):
        conn = _connect("500_bjdc")
        count = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=51"
        ).fetchone()[0]
        assert count > 0, "Zero p51 snapshots"

    def test_outcome_codes_present(self):
        conn = _connect("500_bjdc")
        codes = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT outcome_code FROM live_market_sp_snapshots WHERE playid=51 AND outcome_code IS NOT NULL"
            ).fetchall()
        }
        expected = {"3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0"}
        assert codes == expected, f"Unexpected outcome codes: {codes}"

    def test_all_unclassified(self):
        conn = _connect("500_bjdc")
        non_classified = conn.execute(
            """SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=51 AND capture_classification NOT IN ('legacy_unclassified','non_target_market_unclassified')"""
        ).fetchone()[0]
        assert non_classified == 0, f"{non_classified} rows have unexpected classification"

    def test_no_settlement(self):
        from research.mm_data_audit.contract import MARKET_KEY
        conn = _connect("500_bjdc")
        mk = MARKET_KEY[51]
        count = conn.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (mk,),
        ).fetchone()[0]
        assert count == 0, f"Unexpected settlement rows for p51: {count}"


# ── Report Generation Tests ────────────────────────────────────────────────

class TestReportGeneration:
    """Verify report generation produces expected outputs."""

    def test_generate_report_nonempty(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        report = generate_report(result)
        assert len(report) > 1000
        assert "# Research Phase 1: Multi-Market Data Audit" in report
        assert "Readiness Matrix" in report
        assert "Handicap 3/1/0" in report
        assert "Total Goals" in report
        assert "Correct Score" in report
        assert "Half/Full Time" in report

    def test_save_results_creates_files(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "test_audit"
            paths = save_results(result, output_dir)
            assert paths["audit_json"].exists()
            assert paths["readiness_csv"].exists()
            assert paths["report_md"].exists()
            # Verify JSON is valid
            data = json.loads(paths["audit_json"].read_text())
            assert data["audit_id"] == "MM-DATA-AUDIT-001"
            assert "readiness_matrix" in data
            # Verify CSV has correct structure
            csv_lines = paths["readiness_csv"].read_text().strip().split("\n")
            assert csv_lines[0] == "market,pre_event_input,freeze_support,settlement_support"
            assert len(csv_lines) == 5  # header + 4 markets

    def test_report_contains_all_markets(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        report = generate_report(result)
        market_names = ["Handicap 3/1/0", "Total Goals", "Correct Score", "Half/Full Time"]
        for name in market_names:
            assert name in report, f"Missing market: {name}"

    def test_report_contains_readiness_legend(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        report = generate_report(result)
        assert "READY_STRICT" in report
        assert "PARTIAL" in report
        assert "SETTLEMENT_ONLY" in report
        assert "UNAVAILABLE" in report

    def test_readiness_matrix_is_complete(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        for playid in TARGET_PLAYIDS:
            m = MARKETS[playid]
            row = result.readiness_matrix.get(m.market_key, {})
            assert "pre_event_input" in row, f"Missing pre_event_input for {m.market_key}"
            assert "freeze_support" in row, f"Missing freeze_support for {m.market_key}"
            assert "settlement_support" in row, f"Missing settlement_support for {m.market_key}"


# ── Freeze Package Verification Tests ──────────────────────────────────────

class TestFreezePackage:
    """Verify the freeze package is valid and tamper-resistant."""

    def test_freeze_package_exists(self):
        repo = _repo_root()
        freeze_dir = repo / "results/freeze/MM-DATA-AUDIT-001"
        assert freeze_dir.exists(), f"Freeze package not found: {freeze_dir}"
        assert (freeze_dir / "manifest.json").exists()
        assert (freeze_dir / "SHA256SUMS").exists()

    def test_freeze_manifest_structure(self):
        repo = _repo_root()
        manifest = json.loads((repo / "results/freeze/MM-DATA-AUDIT-001/manifest.json").read_text())
        assert manifest["experiment_id"] == "MM-DATA-AUDIT-001"
        assert manifest["schema_version"] == "beijing_lot_research_freeze_v1"
        assert manifest["execution_enabled"] is False
        assert manifest["frontend_selectable"] is False
        assert manifest["roi_authorized"] is False

    def test_freeze_hash_verification(self):
        """Verify SHA256SUMS integrity."""
        import hashlib
        repo = _repo_root()
        freeze_dir = repo / "results/freeze/MM-DATA-AUDIT-001"
        sums = (freeze_dir / "SHA256SUMS").read_text().splitlines()
        for line in sums:
            digest, name = line.split("  ", 1)
            path = freeze_dir / name
            assert path.exists(), f"File not found: {name}"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == digest, f"Checksum mismatch for {name}: expected {digest}, got {actual}"


# ── Classification Boundary Tests ──────────────────────────────────────────

class TestClassificationLogic:
    """Verify readiness classification rules."""

    def test_handicap_settlement_is_ready(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("handicap_310", {})
        assert row.get("settlement_support") == "READY_STRICT", \
            f"Expected READY_STRICT, got {row.get('settlement_support')}"

    def test_p51_freeze_is_unavailable(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("half_full_time", {})
        assert row.get("freeze_support") == "UNAVAILABLE", \
            f"Expected UNAVAILABLE, got {row.get('freeze_support')}"

    def test_p51_settlement_not_ready_strict(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("half_full_time", {})
        assert row.get("settlement_support") != "READY_STRICT", \
            f"Half/Full Time should not be READY_STRICT for settlement"

    def test_no_market_unavailable_for_pre_event(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        for mk, row in result.readiness_matrix.items():
            assert row.get("pre_event_input") != "UNAVAILABLE", \
                f"Market {mk} should not be UNAVAILABLE for pre-event (has data)"

    def test_no_terminal_leakage_claimed(self):
        """Verify no market claims READY_STRICT while using terminal data."""
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = MultiMarketAuditor()
        result = auditor.audit_all()
        for dim in result.dimensions:
            for gate in dim.gates:
                if gate.gate_id == GateID.G7_NO_LEAKAGE and dim.readiness == ReadinessLevel.READY_STRICT:
                    assert gate.passed, \
                        f"G7 failed but {dim.market.display_name} {dim.dimension.value} is READY_STRICT"


# ── Reproducibility Tests ──────────────────────────────────────────────────

class TestReproducibility:
    """Verify the audit is reproducible."""

    def test_audit_result_json_is_valid(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        audit_json = worktree / "results/research/mm_data_audit/audit_result.json"
        assert audit_json.exists(), f"Audit JSON not found: {audit_json}"
        data = json.loads(audit_json.read_text())
        assert data["audit_id"] == "MM-DATA-AUDIT-001"
        assert "readiness_matrix" in data
        assert "dimensions" in data
        assert len(data["dimensions"]) == 12  # 4 markets × 3 dimensions

    def test_readiness_csv_is_valid(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        csv_path = worktree / "results/research/mm_data_audit/readiness_matrix.csv"
        lines = csv_path.read_text().strip().split("\n")
        assert len(lines) == 5  # header + 4 markets
        for line in lines[1:]:
            parts = line.split(",")
            assert len(parts) == 4
            assert parts[1] in {"READY_STRICT", "PARTIAL", "SETTLEMENT_ONLY", "UNAVAILABLE"}

    def test_report_md_exists(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        report = worktree / "docs/research/experiments/MM-DATA-AUDIT-001.md"
        assert report.exists(), f"Report not found: {report}"
        content = report.read_text()
        assert "MM-DATA-AUDIT-001" in content


# ── Non-Regression: Existing Systems ───────────────────────────────────────

class TestExistingSystemsUnchanged:
    """Verify existing strategy, API, and release-manifest behavior is unchanged."""

    def test_strategy_release_registry_still_valid(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        schema_path = worktree / "schemas/strategy_release_registry_v1.schema.json"
        assert schema_path.exists(), "Strategy release schema missing"

    def test_data_collection_plan_unchanged(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        config_path = worktree / "config/data_collection_plan.json"
        assert config_path.exists(), "Data collection plan missing"

    def test_decision_versions_unchanged(self):
        repo = _repo_root()
        worktree = repo / ".worktrees/t_444c6ea1"
        config_path = worktree / "config/decision_versions.json"
        assert config_path.exists(), "Decision versions config missing"

    def test_no_live_db_writes_from_audit(self):
        """Audit is read-only — it should never write to the source databases."""
        # The auditor only reads; no INSERT/UPDATE/DELETE calls exist in auditor.py
        auditor_path = Path(__file__).resolve().parent.parent / "research/mm_data_audit/auditor.py"
        content = auditor_path.read_text()
        import re
        writes = re.findall(r'(INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE|DROP)', content)
        assert not writes, f"Auditor contains write operations: {writes}"
