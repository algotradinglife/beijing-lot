"""REQ-BJ09 panel tests: relative-proxy M×3 ingestion, availability mask,
idempotency, tamper defense on panel cells (REQ-E06), v2 cohort split."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.bj_sp_timeseries.ingest import connect_canonical, register_sources
from src.bj_sp_timeseries.panel import (
    ingest_xlsm_panel,
    panel_support,
    relative_horizon_view_df,
    verify_panel_provenance,
)


def _mk_xlsm(tmp_path: Path, *, with_padding: bool = True) -> Path:
    """Tiny synthetic archive with two fixtures and one excluded padding row."""
    db = tmp_path / "beidan_xlsm_small.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(
        """
        CREATE TABLE matches (
            match_id INTEGER, issue TEXT, match_idx INTEGER, kickoff_ts TEXT,
            league TEXT, home TEXT, away TEXT, handicap_line_norm REAL);
        CREATE TABLE market_consensus (
            match_id INTEGER, market TEXT, snapshot TEXT,
            n_v1 INTEGER, n_v2 INTEGER, n_v3 INTEGER,
            v1_avg REAL, v2_avg REAL, v3_avg REAL);
        INSERT INTO matches VALUES
          (1, '25042', 1, '2025-06-14 19:30:00', 'L1', 'H1', 'A1', -1.0),
          (2, '25042', 2, '2025-06-14 19:45:00', 'L2', 'H2', 'A2', 0.5);
        """
    )
    if with_padding:
        con.execute(
            "INSERT INTO matches VALUES (3, NULL, NULL, NULL, NULL, NULL, NULL, NULL)"
        )
    for bucket in ("initial", "10h", "1h", "final"):
        con.execute(
            "INSERT INTO market_consensus VALUES (1,'euro_1x2',?,12,12,12,2.2,3.1,3.9)",
            (bucket,),
        )
    con.execute(
        "INSERT INTO market_consensus VALUES (2,'euro_1x2','initial',8,8,8,2.0,3.5,4.2)"
    )
    con.execute(
        "INSERT INTO market_consensus VALUES (2,'euro_1x2','1h',7,0,7,2.1,NULL,4.0)"
    )
    con.execute(
        "INSERT INTO market_consensus VALUES (2,'euro_1x2','final',9,9,9,1.9,3.2,4.5)"
    )
    con.commit()
    con.close()
    return db


def _mk_canonical(tmp_path: Path) -> sqlite3.Connection:
    con = connect_canonical(tmp_path / "canon.sqlite")
    register_sources(con)
    return con


def test_panel_ingestion_golden(tmp_path):
    xlsm = _mk_xlsm(tmp_path)
    con = _mk_canonical(tmp_path)
    c = ingest_xlsm_panel(con, xlsm)

    assert c["fixtures"] == 2
    assert c["panel_rows"] == 21
    assert c["present"] == 20
    assert c["missing"] == 1
    assert c["exclusions"] == 1

    miss = con.execute(
        """SELECT snapshot_bucket, outcome_code, availability, decimal_odds
           FROM relative_horizon_panel
           WHERE fixture_id='25042_002' AND snapshot_bucket='1h'
             AND outcome_code='1'"""
    ).fetchone()
    assert miss["availability"] == "missing"
    assert miss["decimal_odds"] is None

    p = con.execute(
        """SELECT decimal_odds, consensus_n FROM relative_horizon_panel
           WHERE fixture_id='25042_001' AND snapshot_bucket='initial'
             AND outcome_code='3'"""
    ).fetchone()
    assert p["decimal_odds"] == pytest.approx(2.2)
    assert p["consensus_n"] == 12

    line = con.execute(
        "SELECT native_handicap_line FROM relative_horizon_panel WHERE fixture_id='25042_002'"
    ).fetchone()["native_handicap_line"]
    assert line == 0.5

    cols = {r[1] for r in con.execute("PRAGMA table_info(relative_horizon_panel)")}
    assert "observed_at_utc" not in cols and "received_at_utc" not in cols


def test_panel_ingestion_idempotent(tmp_path):
    xlsm = _mk_xlsm(tmp_path)
    con = _mk_canonical(tmp_path)
    c1 = ingest_xlsm_panel(con, xlsm)
    c2 = ingest_xlsm_panel(con, xlsm)
    assert c1["panel_rows"] == c2["panel_rows"] == 21
    assert con.execute("SELECT COUNT(*) FROM relative_horizon_panel").fetchone()[0] == 21
    assert verify_panel_provenance(con)["mismatches"] == 0


def test_panel_support_and_cohort_v2(tmp_path):
    xlsm = _mk_xlsm(tmp_path)
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, xlsm)

    s = panel_support(con)
    assert s["total_fixtures"] == 2
    assert set(s["by_bucket"].keys()) == {"initial", "10h", "1h", "final"}
    init = s["by_bucket"]["initial"]
    assert init["cells"] == 6 and init["cells_present"] == 6
    tenh = s["by_bucket"]["10h"]
    assert tenh["cells"] == 3 and tenh["cells_present"] == 3
    oneh = s["by_bucket"]["1h"]
    assert oneh["cells"] == 6 and oneh["cells_present"] == 5

    from src.bj_sp_timeseries.recover import cohort_name_v2
    assert cohort_name_v2(2025, source_admissible_use="RETROSPECTIVE_PROXY") == "retrospective_proxy"
    assert cohort_name_v2(2025, source_admissible_use="STRICT_CAUSAL") == "strict_historical"
    assert cohort_name_v2(2026, source_admissible_use="STRICT_CAUSAL") == "prospective"

    vdf = relative_horizon_view_df(con)
    assert len(vdf) == 21
    assert "winning_sp" not in vdf.columns
    assert vdf["availability"].isin(["present", "missing"]).all()
    assert set(vdf["snapshot_bucket"].unique()) == {"initial", "10h", "1h", "final"}


def test_issue_support_reports_proxy_separately_from_strict(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))

    from src.bj_sp_timeseries.recover import issue_level_support

    proxy = issue_level_support(con)["by_cohort"]["retrospective_proxy"]
    assert proxy == {"issues": 1, "fixtures_total": 2, "fixtures_present": 2}


def test_export_binds_relative_horizon_view_to_v2_manifest(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))

    from src.bj_sp_timeseries.export import export_parquet

    export_parquet(con, tmp_path / "evidence")
    assert (tmp_path / "evidence" / "tables" / "relative_horizon_view.parquet").exists()


def test_proxy_only_build_emits_executed_historical_panel(tmp_path):
    data_root = tmp_path / "data"
    xlsm_dir = data_root / "derived" / "beidan_xlsm"
    xlsm_dir.mkdir(parents=True)
    _mk_xlsm(xlsm_dir, with_padding=True).replace(xlsm_dir / "beidan_xlsm.sqlite")
    out = tmp_path / "out"
    canonical = tmp_path / "canonical.sqlite"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/bj235_build.py",
            "--data-root", str(data_root),
            "--canonical", str(canonical),
            "--out", str(out),
            "--proxy-only",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = __import__("json").loads((out / "RECOVERABILITY_REPORT.json").read_text())
    assert report["execution_scope"] == "historical_proxy_only"
    assert report["panel_provenance"]["mismatches"] == 0


def test_tamper_panel_odds_detected(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))
    con.execute(
        "UPDATE relative_horizon_panel SET decimal_odds=99.0 "
        "WHERE fixture_id='25042_001' AND snapshot_bucket='initial' AND outcome_code='3'"
    )
    con.commit()
    assert verify_panel_provenance(con)["mismatches"] == 1


def test_tamper_panel_availability_detected(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))
    con.execute(
        "UPDATE relative_horizon_panel SET availability='present', decimal_odds=1.2 "
        "WHERE fixture_id='25042_002' AND snapshot_bucket='1h' AND outcome_code='1'"
    )
    con.commit()
    assert verify_panel_provenance(con)["mismatches"] == 1


def test_tamper_panel_bucket_label_detected(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))
    con.execute(
        "UPDATE relative_horizon_panel SET snapshot_bucket='10h' "
        "WHERE fixture_id='25042_002' AND snapshot_bucket='1h' AND outcome_code='3'"
    )
    con.commit()
    assert verify_panel_provenance(con)["mismatches"] == 1


def test_tamper_panel_line_detected(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))
    con.execute(
        "UPDATE relative_horizon_panel SET native_handicap_line=-2.5 "
        "WHERE fixture_id='25042_002'"
    )
    con.commit()
    assert verify_panel_provenance(con)["mismatches"] == 9


def test_panel_no_settlement_and_no_065(tmp_path):
    con = _mk_canonical(tmp_path)
    ingest_xlsm_panel(con, _mk_xlsm(tmp_path))
    assert con.execute("SELECT COUNT(*) FROM settlement").fetchone()[0] == 0
    assert con.execute(
        "SELECT COUNT(*) FROM relative_horizon_panel WHERE decimal_odds=0.65"
    ).fetchone()[0] == 0
