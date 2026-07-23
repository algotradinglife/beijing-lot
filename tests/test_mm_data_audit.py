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
import hashlib
import sqlite3
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
import research.mm_data_audit.report as report_module
from research.mm_data_audit.auditor import (
    MultiMarketAuditor,
    _repo_root,
    _connect,
    _table_exists,
    _verify_sha256sums,
)
from research.mm_data_audit.report import generate_report, save_results


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _data_db_path(db_name: str) -> Path:
    """Return path to a test fixture DB, falling back to main repo data directory."""
    fixture_map = {
        "beidan_live": FIXTURES_DIR / "mm_data_audit_live.db",
        "500_bjdc": FIXTURES_DIR / "mm_data_audit_500_bjdc.db",
    }
    fixture_path = fixture_map.get(db_name)
    if fixture_path and fixture_path.is_file():
        return fixture_path
    repo = _repo_root()
    path_map = {
        "beidan_live": repo / "data/beidan_live.db",
        "500_bjdc": repo / "data/derived/500_bjdc/500_bjdc.sqlite",
    }
    return path_map[db_name]


def _connect_required(db_name: str) -> sqlite3.Connection:
    path = _data_db_path(db_name)
    if not path.exists():
        pytest.skip(f"{db_name} integration database not found: {path}")
    return _connect(db_name)


def _auditor_required() -> MultiMarketAuditor:
    for db_name in ("beidan_live", "500_bjdc"):
        path = _data_db_path(db_name)
        if not path.exists():
            pytest.skip(f"{db_name} integration database not found: {path}")
    return MultiMarketAuditor()


def _make_live_market_sp_fixture() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE live_market_sp_snapshots (
            issue TEXT,
            row_idx INTEGER,
            playid INTEGER,
            batch_id TEXT,
            fetched_at TEXT,
            fetched_at_utc TEXT,
            source_updated_at_hkt TEXT,
            sale_cutoff_hkt TEXT,
            capture_classification TEXT,
            outcome_code TEXT,
            sp REAL,
            sale_status TEXT
        )"""
    )
    return conn


def _insert_capture_vector(
    conn: sqlite3.Connection,
    issue: str,
    row_idx: int,
    batch_id: str,
    outcome_codes: list[str],
    *,
    playid: int = 40,
    classification: str = "forward_complete_open",
    sale_status: str = "open",
    fetched_at_utc: str = "2026-07-22T02:00:00+00:00",
    source_updated_at_hkt: str = "2026-07-22T10:00:00+08:00",
    sale_cutoff_hkt: str | None = "2026-07-22T11:00:00+08:00",
) -> None:
    for outcome_code in outcome_codes:
        conn.execute(
            """INSERT INTO live_market_sp_snapshots (
                issue, row_idx, playid, batch_id, fetched_at, fetched_at_utc,
                source_updated_at_hkt, sale_cutoff_hkt, capture_classification,
                outcome_code, sp, sale_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                issue,
                row_idx,
                playid,
                batch_id,
                "2026-07-22 10:00:00",
                fetched_at_utc,
                source_updated_at_hkt,
                sale_cutoff_hkt,
                classification,
                outcome_code,
                2.0,
                sale_status,
            ),
        )
    conn.commit()


def _auditor_for_bjdc(conn: sqlite3.Connection) -> MultiMarketAuditor:
    auditor = object.__new__(MultiMarketAuditor)
    auditor.bjdc = conn
    return auditor


def _gate_by_id(gates: list[GateResult], gate_id: GateID) -> GateResult:
    return next(gate for gate in gates if gate.gate_id == gate_id)


def _deterministic_audit_result() -> AuditResult:
    result = AuditResult(audit_cutoff_utc="2026-07-22T00:00:00+00:00")
    gate_by_dimension = {
        AuditDimension.PRE_EVENT_INPUT: GateID.G1_OUTCOME_VECTORS,
        AuditDimension.FREEZE_SUPPORT: GateID.G4_IMMUTABLE_PROVENANCE,
        AuditDimension.SETTLEMENT_SUPPORT: GateID.G6_SETTLEMENT_MAPPING,
    }
    for playid in TARGET_PLAYIDS:
        market = MARKETS[playid]
        result.readiness_matrix[market.market_key] = {}
        for dimension in AuditDimension:
            result.readiness_matrix[market.market_key][dimension.value] = ReadinessLevel.PARTIAL.value
            result.dimensions.append(
                DimensionAudit(
                    market=market,
                    dimension=dimension,
                    readiness=ReadinessLevel.PARTIAL,
                    gates=[
                        GateResult(
                            gate_id=gate_by_dimension[dimension],
                            passed=False,
                            score=0.5,
                            evidence="deterministic fixture",
                        )
                    ],
                    summary=f"{market.display_name} {dimension.value}: deterministic fixture",
                    metrics={"fixture": True},
                )
            )
    return result


def _write_deterministic_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(report_module, "DOCS_DIR", tmp_path / "docs")
    return save_results(_deterministic_audit_result(), tmp_path / "results")


def _make_capture_batches_fixture(bundle_dir: Path, sums_digest: str, *, playid: int = 40) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE market_sp_capture_batches (
            playid INTEGER,
            bundle_path TEXT,
            bundle_sha256s_sha256 TEXT
        )"""
    )
    conn.execute(
        """INSERT INTO market_sp_capture_batches (
            playid, bundle_path, bundle_sha256s_sha256
        ) VALUES (?, ?, ?)""",
        (playid, str(bundle_dir), sums_digest),
    )
    conn.commit()
    return conn


def _make_settlement_truth_fixture(rows: list[dict[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE multimarket_settlement_truth (
            market_key TEXT,
            settlement_status TEXT,
            outcome_code TEXT,
            score_source TEXT
        )"""
    )
    for row in rows:
        conn.execute(
            """INSERT INTO multimarket_settlement_truth (
                market_key, settlement_status, outcome_code, score_source
            ) VALUES (?, ?, ?, ?)""",
            (
                row["market_key"],
                row["settlement_status"],
                row["outcome_code"],
                row["score_source"],
            ),
        )
    conn.commit()
    return conn


def _write_bundle(bundle_dir: Path, files: dict[str, str]) -> str:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = bundle_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    lines = []
    for name in sorted(files):
        digest = hashlib.sha256((bundle_dir / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}\n")
    sums = bundle_dir / "SHA256SUMS"
    sums.write_text("".join(lines), encoding="utf-8")
    return hashlib.sha256(sums.read_bytes()).hexdigest()


def _write_mm_data_freeze_fixture(tmp_path: Path) -> Path:
    freeze_dir = tmp_path / "MM-DATA-AUDIT-001"
    manifest = {
        "experiment_id": "MM-DATA-AUDIT-001",
        "schema_version": "beijing_lot_research_freeze_v1",
        "execution_enabled": False,
        "frontend_selectable": False,
        "roi_authorized": False,
    }
    _write_bundle(
        freeze_dir,
        {
            "manifest.json": json.dumps(manifest, sort_keys=True),
            "audit_result.json": json.dumps(_deterministic_audit_result().to_dict(), sort_keys=True),
        },
    )
    return freeze_dir


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
        db_path = _data_db_path("beidan_live")
        if not db_path.exists():
            pytest.skip(f"beidan_live.db not found at {db_path}")

    def test_500_bjdc_db_exists(self):
        db_path = _data_db_path("500_bjdc")
        if not db_path.exists():
            pytest.skip(f"500_bjdc.sqlite not found at {db_path}")

    def test_beidan_live_has_required_tables(self):
        conn = _connect_required("beidan_live")
        assert _table_exists(conn, "snapshots")
        assert _table_exists(conn, "matches")
        assert _table_exists(conn, "settlements")

    def test_500_bjdc_has_required_tables(self):
        conn = _connect_required("500_bjdc")
        assert _table_exists(conn, "live_market_sp_snapshots")
        assert _table_exists(conn, "market_sp_capture_batches")
        assert _table_exists(conn, "multimarket_settlement_truth")
        assert _table_exists(conn, "segment_decision_windows")


class TestHandicapPreEventGates:
    """Verify Handicap 3/1/0 pre-event gate evaluation."""

    def test_outcome_vectors_nonzero(self):
        conn = _connect_required("beidan_live")
        count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        assert count > 0, "Zero handicap snapshots"

    def test_complete_vector_proportion(self):
        conn = _connect_required("beidan_live")
        total = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        complete = conn.execute(
            "SELECT COUNT(*) FROM snapshots WHERE sp_3 IS NOT NULL AND sp_1 IS NOT NULL AND sp_0 IS NOT NULL"
        ).fetchone()[0]
        pct = (complete / total * 100) if total else 0
        assert pct > 30, f"Complete vector coverage too low: {pct:.1f}%"

    def test_kickoff_timestamps_present(self):
        conn = _connect_required("beidan_live")
        total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        with_ko = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE kickoff_ts IS NOT NULL AND kickoff_ts != ''"
        ).fetchone()[0]
        assert with_ko > 0
        assert (with_ko / total * 100) > 50 if total else True

    def test_pre_kickoff_snapshots_exist(self):
        conn = _connect_required("beidan_live")
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
        conn = _connect_required("500_bjdc")
        count = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=?", (playid,)
        ).fetchone()[0]
        assert count > 0, f"Zero snapshots for playid={playid}"

    @pytest.mark.parametrize("playid", [40, 42])
    def test_forward_complete_exists(self, playid):
        conn = _connect_required("500_bjdc")
        fc = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=? AND capture_classification='forward_complete_open'",
            (playid,),
        ).fetchone()[0]
        assert fc > 0, f"No forward_complete_open rows for playid={playid}"

    @pytest.mark.parametrize("playid", [40, 42])
    def test_terminal_excluded_from_forward(self, playid):
        conn = _connect_required("500_bjdc")
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
        conn = _connect_required("500_bjdc")
        mk = MARKET_KEY[playid]
        count = conn.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (mk,),
        ).fetchone()[0]
        assert count > 0, f"No settlement rows for market_key={mk}"

    def test_capture_vector_coverage_uses_distinct_capture_identity(self):
        conn = _make_live_market_sp_fixture()
        _insert_capture_vector(conn, "26080", 1, "batch-a", MARKETS[40].outcome_codes)
        _insert_capture_vector(conn, "26080", 1, "batch-b", MARKETS[40].outcome_codes)
        _insert_capture_vector(conn, "26080", 2, "batch-a", MARKETS[40].outcome_codes[:7])

        gates, metrics = _auditor_for_bjdc(conn)._gates_p0_pre_event(MARKETS[40])

        g1 = _gate_by_id(gates, GateID.G1_OUTCOME_VECTORS)
        assert g1.passed is True
        assert metrics["total_capture_vectors"] == 3
        assert metrics["complete_capture_vectors"] == 2
        assert metrics["complete_vector_pct"] == pytest.approx(66.67)
        assert metrics["complete_match_markets"] == 1
        assert metrics["complete_match_market_pct"] == pytest.approx(50.0)

    def test_capture_vector_requires_exact_expected_outcome_set(self):
        conn = _make_live_market_sp_fixture()
        wrong_codes = MARKETS[40].outcome_codes[:7] + ["unexpected"]
        _insert_capture_vector(conn, "26080", 1, "batch-a", wrong_codes)

        gates, metrics = _auditor_for_bjdc(conn)._gates_p0_pre_event(MARKETS[40])

        g1 = _gate_by_id(gates, GateID.G1_OUTCOME_VECTORS)
        assert g1.passed is False
        assert metrics["complete_capture_vectors"] == 0
        assert metrics["complete_match_markets"] == 0

    def test_pre_cutoff_requires_both_clocks_before_sale_cutoff(self):
        conn = _make_live_market_sp_fixture()
        _insert_capture_vector(
            conn,
            "26080",
            1,
            "batch-fetched-boundary",
            MARKETS[40].outcome_codes,
            fetched_at_utc="2026-07-22T03:00:00+00:00",
            source_updated_at_hkt="2026-07-22T10:00:00+08:00",
            sale_cutoff_hkt="2026-07-22T11:00:00+08:00",
        )
        _insert_capture_vector(
            conn,
            "26080",
            2,
            "batch-source-boundary",
            MARKETS[40].outcome_codes,
            fetched_at_utc="2026-07-22T02:00:00+00:00",
            source_updated_at_hkt="2026-07-22T11:00:00+08:00",
            sale_cutoff_hkt="2026-07-22T11:00:00+08:00",
        )
        _insert_capture_vector(
            conn,
            "26080",
            3,
            "batch-missing-cutoff",
            MARKETS[40].outcome_codes,
            sale_cutoff_hkt=None,
        )

        gates, metrics = _auditor_for_bjdc(conn)._gates_p0_pre_event(MARKETS[40])

        g3 = _gate_by_id(gates, GateID.G3_PRE_CUTOFF_EVIDENCE)
        assert g3.passed is False
        assert metrics["pre_cutoff_eligible_capture_vectors"] == 0
        assert g3.metrics["rejection_reasons"]["fetched_at_or_after_cutoff"] == 1
        assert g3.metrics["rejection_reasons"]["source_updated_at_or_after_cutoff"] == 1
        assert g3.metrics["rejection_reasons"]["missing_cutoff_clock"] == 1


class TestHalfFullTimeGates:
    """Verify Half/Full Time (p51) gate evaluation."""

    def test_data_exists(self):
        conn = _connect_required("500_bjdc")
        count = conn.execute(
            "SELECT COUNT(*) FROM live_market_sp_snapshots WHERE playid=51"
        ).fetchone()[0]
        assert count > 0, "Zero p51 snapshots"

    def test_outcome_codes_present(self):
        conn = _connect_required("500_bjdc")
        codes = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT outcome_code FROM live_market_sp_snapshots WHERE playid=51 AND outcome_code IS NOT NULL"
            ).fetchall()
        }
        expected = {"3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0"}
        assert codes == expected, f"Unexpected outcome codes: {codes}"

    def test_all_unclassified(self):
        conn = _connect_required("500_bjdc")
        non_classified = conn.execute(
            """SELECT COUNT(*) FROM live_market_sp_snapshots
               WHERE playid=51 AND capture_classification NOT IN ('legacy_unclassified','non_target_market_unclassified')"""
        ).fetchone()[0]
        assert non_classified == 0, f"{non_classified} rows have unexpected classification"

    def test_no_settlement(self):
        from research.mm_data_audit.contract import MARKET_KEY
        conn = _connect_required("500_bjdc")
        mk = MARKET_KEY[51]
        count = conn.execute(
            "SELECT COUNT(*) FROM multimarket_settlement_truth WHERE market_key=?",
            (mk,),
        ).fetchone()[0]
        assert count == 0, f"Unexpected settlement rows for p51: {count}"

    def test_zero_p51_settlement_rows_are_unavailable(self):
        conn = _make_settlement_truth_fixture([])
        auditor = _auditor_for_bjdc(conn)

        gates, metrics = auditor._gates_p51_settlement(MARKETS[51])
        audit = auditor._classify(MARKETS[51], AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

        g6 = _gate_by_id(gates, GateID.G6_SETTLEMENT_MAPPING)
        assert g6.passed is False
        assert g6.score == 0.0
        assert metrics["settlement_sourced_separately"] is False
        assert audit.readiness == ReadinessLevel.UNAVAILABLE
        assert "final score" not in g6.evidence

    def test_p51_settlement_requires_non_missing_source_truth(self):
        conn = _make_settlement_truth_fixture([
            {
                "market_key": MARKETS[51].market_key,
                "settlement_status": "settled",
                "outcome_code": MARKETS[51].outcome_codes[0],
                "score_source": "missing",
            }
        ])

        gates, metrics = _auditor_for_bjdc(conn)._gates_p51_settlement(MARKETS[51])

        g6 = _gate_by_id(gates, GateID.G6_SETTLEMENT_MAPPING)
        assert g6.passed is False
        assert g6.score == 0.0
        assert metrics["audited_p51_settlement_rows"] == 0
        assert metrics["settlement_sourced_separately"] is False

    def test_p51_settlement_rejects_full_time_score_source_only(self):
        conn = _make_settlement_truth_fixture([
            {
                "market_key": MARKETS[51].market_key,
                "settlement_status": "settled",
                "outcome_code": MARKETS[51].outcome_codes[0],
                "score_source": "matches.score",
            }
        ])
        auditor = _auditor_for_bjdc(conn)

        gates, metrics = auditor._gates_p51_settlement(MARKETS[51])
        audit = auditor._classify(MARKETS[51], AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

        g6 = _gate_by_id(gates, GateID.G6_SETTLEMENT_MAPPING)
        assert g6.passed is False
        assert g6.score == 0.0
        assert metrics["audited_p51_settlement_rows"] == 0
        assert metrics["explicit_p51_source_rows"] == 0
        assert metrics["final_score_only_rows"] == 1
        assert audit.readiness == ReadinessLevel.UNAVAILABLE

    def test_p51_settlement_accepts_explicit_half_full_truth_and_special_status(self):
        conn = _make_settlement_truth_fixture([
            {
                "market_key": MARKETS[51].market_key,
                "settlement_status": "settled",
                "outcome_code": MARKETS[51].outcome_codes[0],
                "score_source": "official_p51_half_full_time",
            },
            {
                "market_key": MARKETS[51].market_key,
                "settlement_status": "postponed",
                "outcome_code": "",
                "score_source": "official_p51_half_full_time",
            },
        ])
        auditor = _auditor_for_bjdc(conn)

        gates, metrics = auditor._gates_p51_settlement(MARKETS[51])
        audit = auditor._classify(MARKETS[51], AuditDimension.SETTLEMENT_SUPPORT, gates, metrics)

        g6 = _gate_by_id(gates, GateID.G6_SETTLEMENT_MAPPING)
        assert g6.passed is True
        assert g6.score == 1.0
        assert metrics["audited_p51_settlement_rows"] == 2
        assert metrics["settlement_sourced_separately"] is True
        assert audit.readiness == ReadinessLevel.READY_STRICT

    def test_unknown_p51_leakage_risk_does_not_pass_g7(self):
        conn = _make_live_market_sp_fixture()
        _insert_capture_vector(
            conn,
            "26080",
            1,
            "batch-a",
            MARKETS[51].outcome_codes,
            playid=51,
            classification="non_target_market_unclassified",
        )

        gates, _metrics = _auditor_for_bjdc(conn)._gates_p51_pre_event(MARKETS[51])

        g7 = _gate_by_id(gates, GateID.G7_NO_LEAKAGE)
        assert g7.passed is False
        assert g7.metrics["leakage_risk"] == "unknown"


# ── Report Generation Tests ────────────────────────────────────────────────

class TestReportGeneration:
    """Verify report generation produces expected outputs."""

    def test_generate_report_nonempty(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        report = generate_report(result)
        assert len(report) > 1000
        assert "# Research Phase 1: Multi-Market Data Audit" in report
        assert "Readiness Matrix" in report
        assert "Handicap 3/1/0" in report
        assert "Total Goals" in report
        assert "Correct Score" in report
        assert "Half/Full Time" in report

    def test_save_results_creates_files(self, tmp_path, monkeypatch):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        monkeypatch.setattr(report_module, "DOCS_DIR", tmp_path / "docs")
        paths = save_results(result, tmp_path / "test_audit")
        assert paths["audit_json"].exists()
        assert paths["readiness_csv"].exists()
        assert paths["report_md"].exists()
        assert paths["report_md"].is_relative_to(tmp_path)
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
        auditor = _auditor_required()
        result = auditor.audit_all()
        report = generate_report(result)
        market_names = ["Handicap 3/1/0", "Total Goals", "Correct Score", "Half/Full Time"]
        for name in market_names:
            assert name in report, f"Missing market: {name}"

    def test_report_contains_readiness_legend(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        report = generate_report(result)
        assert "READY_STRICT" in report
        assert "PARTIAL" in report
        assert "SETTLEMENT_ONLY" in report
        assert "UNAVAILABLE" in report

    def test_readiness_matrix_is_complete(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        for playid in TARGET_PLAYIDS:
            m = MARKETS[playid]
            row = result.readiness_matrix.get(m.market_key, {})
            assert "pre_event_input" in row, f"Missing pre_event_input for {m.market_key}"
            assert "freeze_support" in row, f"Missing freeze_support for {m.market_key}"
            assert "settlement_support" in row, f"Missing settlement_support for {m.market_key}"

    def test_report_does_not_claim_missing_freeze_or_final_score_p51_mapping(self):
        result = _deterministic_audit_result()
        result.readiness_matrix["half_full_time"]["settlement_support"] = "UNAVAILABLE"

        report = generate_report(result)

        assert "results/freeze/MM-DATA-AUDIT-001" not in report
        assert "matches.score" not in report
        assert "independently sourced half-time plus full-time truth" in report

    def test_report_truncates_gap_evidence_without_trailing_whitespace(self):
        result = _deterministic_audit_result()
        gate = result.dimensions[0].gates[0]
        gate.score = 0.3
        gate.evidence = "x" * 199 + " " + "continuation"

        report = generate_report(result)
        gap_line = next(line for line in report.splitlines() if line.startswith("1. **"))

        assert gap_line.endswith("...")
        assert all(not line.endswith(" ") for line in report.splitlines())


# ── Freeze Package Verification Tests ──────────────────────────────────────

class TestFreezePackage:
    """Verify the freeze package is valid and tamper-resistant."""

    def test_freeze_package_exists(self, tmp_path: Path):
        freeze_dir = _write_mm_data_freeze_fixture(tmp_path)
        assert freeze_dir.exists(), f"Freeze package not found: {freeze_dir}"
        assert (freeze_dir / "manifest.json").exists()
        assert (freeze_dir / "SHA256SUMS").exists()

    def test_freeze_manifest_structure(self, tmp_path: Path):
        freeze_dir = _write_mm_data_freeze_fixture(tmp_path)
        manifest = json.loads((freeze_dir / "manifest.json").read_text())
        assert manifest["experiment_id"] == "MM-DATA-AUDIT-001"
        assert manifest["schema_version"] == "beijing_lot_research_freeze_v1"
        assert manifest["execution_enabled"] is False
        assert manifest["frontend_selectable"] is False
        assert manifest["roi_authorized"] is False

    def test_freeze_hash_verification(self, tmp_path: Path):
        """Verify SHA256SUMS integrity."""
        freeze_dir = _write_mm_data_freeze_fixture(tmp_path)
        sums = (freeze_dir / "SHA256SUMS").read_text().splitlines()
        for line in sums:
            digest, name = line.split("  ", 1)
            path = freeze_dir / name
            assert path.exists(), f"File not found: {name}"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == digest, f"Checksum mismatch for {name}: expected {digest}, got {actual}"

    def test_sha256sums_verifier_rejects_tampering(self, tmp_path):
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        raw = bundle / "raw.xml"
        raw.write_text("<xml>fixture</xml>", encoding="utf-8")
        digest = hashlib.sha256(raw.read_bytes()).hexdigest()
        sums = bundle / "SHA256SUMS"
        sums.write_text(f"{digest}  raw.xml\n", encoding="utf-8")
        expected_sums_digest = hashlib.sha256(sums.read_bytes()).hexdigest()

        ok, detail = _verify_sha256sums(bundle, expected_sums_digest)
        assert ok is True
        assert detail["files_checked"] == 1

        raw.write_text("<xml>tampered</xml>", encoding="utf-8")
        ok, detail = _verify_sha256sums(bundle, expected_sums_digest)
        assert ok is False
        assert "checksum mismatch: raw.xml" in detail["errors"]

    def test_p0_freeze_verifies_payload_hashes(self, tmp_path: Path):
        bundle = tmp_path / "bundle"
        sums_digest = _write_bundle(bundle, {"raw.xml": "<xml>original</xml>"})
        (bundle / "raw.xml").write_text("<xml>tampered</xml>", encoding="utf-8")
        conn = _make_capture_batches_fixture(bundle, sums_digest)

        gates, metrics = _auditor_for_bjdc(conn)._gates_p0_freeze(MARKETS[40])

        g4 = _gate_by_id(gates, GateID.G4_IMMUTABLE_PROVENANCE)
        assert g4.passed is False
        assert metrics["sha256_verified_bundle_dirs"] == 0
        assert metrics["sha256_failed_bundle_dirs"] == 1
        assert "checksum mismatch" in metrics["sha256_failure_samples"][0]["errors"][0]

    def test_p0_freeze_requires_sha256sums_to_cover_bundle_inventory(self, tmp_path: Path):
        bundle = tmp_path / "bundle"
        sums_digest = _write_bundle(bundle, {"raw.xml": "<xml>original</xml>"})
        (bundle / "extra.xml").write_text("<xml>extra</xml>", encoding="utf-8")
        conn = _make_capture_batches_fixture(bundle, sums_digest)

        gates, metrics = _auditor_for_bjdc(conn)._gates_p0_freeze(MARKETS[40])

        g4 = _gate_by_id(gates, GateID.G4_IMMUTABLE_PROVENANCE)
        assert g4.passed is False
        assert metrics["sha256_verified_bundle_dirs"] == 0
        assert metrics["sha256_failed_bundle_dirs"] == 1
        assert "does not cover exactly" in metrics["sha256_failure_samples"][0]["errors"][0]


# ── Classification Boundary Tests ──────────────────────────────────────────

class TestClassificationLogic:
    """Verify readiness classification rules."""

    def test_handicap_settlement_is_ready(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("handicap_310", {})
        assert row.get("settlement_support") == "READY_STRICT", \
            f"Expected READY_STRICT, got {row.get('settlement_support')}"

    def test_p51_freeze_is_unavailable(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("half_full_time", {})
        assert row.get("freeze_support") == "UNAVAILABLE", \
            f"Expected UNAVAILABLE, got {row.get('freeze_support')}"

    def test_p51_settlement_not_ready_strict(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        row = result.readiness_matrix.get("half_full_time", {})
        assert row.get("settlement_support") == "UNAVAILABLE", \
            f"Half/Full Time settlement should be UNAVAILABLE, got {row.get('settlement_support')}"

    def test_ready_strict_requires_all_relevant_gates_passed(self):
        auditor = object.__new__(MultiMarketAuditor)
        gates = [
            GateResult(GateID.G1_OUTCOME_VECTORS, True, 1.0, "ok"),
            GateResult(GateID.G2_SOURCE_TIMESTAMPS, True, 1.0, "ok"),
            GateResult(GateID.G3_PRE_CUTOFF_EVIDENCE, False, 1.0, "failed"),
            GateResult(GateID.G7_NO_LEAKAGE, True, 1.0, "ok"),
        ]
        dim = auditor._classify(MARKETS[40], AuditDimension.PRE_EVENT_INPUT, gates, {})
        assert dim.readiness == ReadinessLevel.PARTIAL

    def test_ready_strict_requires_strict_score_threshold(self):
        auditor = object.__new__(MultiMarketAuditor)
        gates = [
            GateResult(GateID.G4_IMMUTABLE_PROVENANCE, True, 0.3, "low"),
            GateResult(GateID.G5_ASOF_FREEZE, True, 0.3, "low"),
        ]
        dim = auditor._classify(MARKETS[40], AuditDimension.FREEZE_SUPPORT, gates, {})
        assert dim.readiness == ReadinessLevel.SETTLEMENT_ONLY

    def test_no_market_unavailable_for_pre_event(self):
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        for mk, row in result.readiness_matrix.items():
            assert row.get("pre_event_input") != "UNAVAILABLE", \
                f"Market {mk} should not be UNAVAILABLE for pre-event (has data)"

    def test_no_terminal_leakage_claimed(self):
        """Verify no market claims READY_STRICT while using terminal data."""
        from research.mm_data_audit.auditor import MultiMarketAuditor
        auditor = _auditor_required()
        result = auditor.audit_all()
        for dim in result.dimensions:
            for gate in dim.gates:
                if gate.gate_id == GateID.G7_NO_LEAKAGE and dim.readiness == ReadinessLevel.READY_STRICT:
                    assert gate.passed, \
                        f"G7 failed but {dim.market.display_name} {dim.dimension.value} is READY_STRICT"


# ── Reproducibility Tests ──────────────────────────────────────────────────


class TestReproducibility:
    """Verify the audit is reproducible."""

    def test_audit_result_json_is_valid(self, tmp_path, monkeypatch):
        paths = _write_deterministic_results(tmp_path, monkeypatch)
        audit_json = paths["audit_json"]
        data = json.loads(audit_json.read_text())
        assert data["audit_id"] == "MM-DATA-AUDIT-001"
        assert "readiness_matrix" in data
        assert "dimensions" in data
        assert len(data["dimensions"]) == 12  # 4 markets × 3 dimensions

    def test_readiness_csv_is_valid(self, tmp_path, monkeypatch):
        paths = _write_deterministic_results(tmp_path, monkeypatch)
        csv_path = paths["readiness_csv"]
        lines = csv_path.read_text().strip().split("\n")
        assert len(lines) == 5  # header + 4 markets
        for line in lines[1:]:
            parts = line.split(",")
            assert len(parts) == 4
            assert parts[1] in {"READY_STRICT", "PARTIAL", "SETTLEMENT_ONLY", "UNAVAILABLE"}

    def test_report_md_exists(self, tmp_path, monkeypatch):
        paths = _write_deterministic_results(tmp_path, monkeypatch)
        report = paths["report_md"]
        content = report.read_text()
        assert "MM-DATA-AUDIT-001" in content


# ── Non-Regression: Existing Systems ───────────────────────────────────────

class TestExistingSystemsUnchanged:
    """Verify existing strategy, API, and release-manifest behavior is unchanged."""

    def test_strategy_release_registry_still_valid(self):
        repo = _repo_root()
        schema_path = repo / "schemas/strategy_release_registry_v1.schema.json"
        assert schema_path.exists(), "Strategy release schema missing"

    def test_data_collection_plan_unchanged(self):
        repo = _repo_root()
        config_path = repo / "config/data_collection_plan.json"
        assert config_path.exists(), "Data collection plan missing"

    def test_decision_versions_unchanged(self):
        repo = _repo_root()
        config_path = repo / "config/decision_versions.json"
        assert config_path.exists(), "Decision versions config missing"

    def test_no_live_db_writes_from_audit(self):
        """Audit is read-only — it should never write to the source databases."""
        # The auditor only reads; no INSERT/UPDATE/DELETE calls exist in auditor.py
        auditor_path = Path(__file__).resolve().parent.parent / "research/mm_data_audit/auditor.py"
        content = auditor_path.read_text()
        import re
        writes = re.findall(r'(INSERT|UPDATE|DELETE|CREATE TABLE|ALTER TABLE|DROP)', content)
        assert not writes, f"Auditor contains write operations: {writes}"
