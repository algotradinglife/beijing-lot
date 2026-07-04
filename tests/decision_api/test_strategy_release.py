from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(value) for value in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _minimal_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                fid INTEGER,
                winning_sp REAL,
                PRIMARY KEY (issue, match_idx)
            );
            CREATE TABLE IF NOT EXISTS issues (
                issue TEXT PRIMARY KEY,
                ordinal INTEGER,
                label TEXT,
                is_current INTEGER,
                first_seen_at TEXT,
                last_seen_at TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _clear_strategy_caches() -> None:
    appmod._strategy_release_registry.cache_clear()
    appmod._read_csv_cached.cache_clear()
    appmod._main_issue_rows_cached.cache_clear()
    appmod._selected_ticket_rows_for_issue.cache_clear()
    appmod._joint_leg_meta_for_issue.cache_clear()


def _build_release_fixture(tmp_path: Path) -> tuple[Path, Path]:
    main_dir = tmp_path / "results/main_strategy_custom"
    ticket_dir = tmp_path / "results/ticket_pool_custom"
    joint_dir = tmp_path / "results/joint_custom"
    drift_dir = tmp_path / "results/drift_custom"
    shadow_dir = tmp_path / "results/shadow_custom"
    issue = "99123"
    arm_id = "custom_release_arm"

    _write_csv(
        main_dir / "sleeve_mix_summary.csv",
        [
            "portfolio",
            "issue_budget",
            "extra_budget",
            "stake_units",
            "profit_units",
            "profit_per_256",
            "roi",
            "issue_win_rate",
            "non_full_loss_rate",
            "full_loss_rate",
            "max_drawdown_units",
            "max_drawdown_per_256",
            "max_drawdown_budget_equiv",
            "max_loss_streak",
            "max_dead_streak",
            "best_issue_profit_units",
            "roi_ex_best_issue",
            "recent_profit_per_256",
            "recent_roi",
            "avg_tickets_per_issue",
            "allocation",
            "rationale",
        ],
        [[arm_id, 384, 128, 3840, 768, 51.2, 0.2, 0.45, 0.65, 0.35, -512, -34.1, 1.3, 2, 1, 1000, 0.12, 20, 0.08, 12, "fixture", "manifest routed"]],
    )
    _write_csv(
        main_dir / "sleeve_mix_annual.csv",
        ["portfolio", "year", "n_issues", "stake_units", "profit_units", "roi", "issue_win_rate", "non_full_loss_rate", "max_drawdown_units"],
        [[arm_id, 2026, 1, 384, 76.8, 0.2, 1, 1, 0]],
    )
    _write_csv(
        main_dir / "sleeve_mix_issue_profit.csv",
        ["portfolio", "issue", "issue_order", "calendar_year", "issue_close_ts", "stake_units", "profit_units", "roi", "tickets", "hits", "parts", "state", "allocation"],
        [[arm_id, issue, 99123, 2026, "2026-07-04 12:00:00", 384, 76.8, 0.2, 1, 1, "fixture", "ok", "fixture"]],
    )
    _write_csv(
        ticket_dir / "high_n_selector_selected_tickets.csv",
        [
            "issue",
            "source_strategy",
            "strategy",
            "selector",
            "ticket_idx",
            "legs",
            "n_legs",
            "selected_stake_units",
            "stake_units",
            "selected_profit_units",
            "profit_units",
            "selected_payout_units",
            "payout_units",
            "pred_ev_per_stake",
            "pred_hit_prob",
            "pred_factor_product",
            "hit",
            "topology",
            "avg_q_score",
            "avg_conf_weight",
            "line_gap_support_net",
            "avg_abs_line_gap",
            "selector_score",
        ],
        [[issue, arm_id, arm_id, "all", 1, "1:3@0", 7, 2, 2, 10, 10, 12, 12, 1.2, 0.1, 2.0, 1, "fixture", 1.8, 0.7, 0, 0, 1.5]],
    )
    _write_csv(
        joint_dir / "joint_leg_rows.csv",
        [
            "issue",
            "match_id",
            "action_code",
            "q_score",
            "conf_weight",
            "drift_bucket",
            "q_bucket",
            "confidence_bucket",
            "pred_sp_multiplier",
            "selected_model_p",
            "selected_market_p",
        ],
        [[issue, 1, 3, 1.8, 0.7, "flat", "high", "high", 1.0, 0.55, 0.48]],
    )
    _write_csv(
        drift_dir / "paper_arm_summary.csv",
        ["arm", "issues", "stake_units", "profit_units", "profit_per_256", "roi", "issue_win_rate", "non_full_loss_rate", "max_drawdown_units", "max_loss_streak", "recent_roi"],
        [["baseline_384_smooth", 1, 384, 1, 1, 0.01, 1, 1, 0, 0, 0.01]],
    )
    shadow_dir.mkdir(parents=True, exist_ok=True)

    config_path = tmp_path / "strategy_release.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "strategy_release_registry_v1",
                "active_release_id": "fixture_release",
                "releases": {
                    "fixture_release": {
                        "release_id": "fixture_release",
                        "status": "active",
                        "owner": "strategy",
                        "strategy_family": "fixture family",
                        "model_versions": {
                            "probability_model": "prob_fixture",
                            "q_model": "q_fixture",
                            "decision_chain": "chain_fixture",
                            "shadow_decision_chain": "shadow_fixture",
                        },
                        "decision_variants": [
                            {"variant_id": "active_v3", "kind": "active", "source": "active_snapshot", "is_default": True, "selectable": True},
                            {"variant_id": "shadow_fixture", "kind": "shadow", "source": "structured_shadow_csv", "artifact_key": "structured_shadow_dir", "is_default": False, "selectable": True},
                        ],
                        "main_strategy_arms": [
                            {"arm_id": arm_id, "label": "Fixture Arm", "role": "stable", "recommended_for": "test"}
                        ],
                        "artifacts": {
                            "main_strategy_dir": str(main_dir),
                            "ticket_pool_dir": str(ticket_dir),
                            "ticket_pool_csv": str(ticket_dir / "high_n_selector_selected_tickets.csv"),
                            "linegap_drift_dir": str(drift_dir),
                            "joint_leg_rows_csv": str(joint_dir / "joint_leg_rows.csv"),
                            "structured_shadow_dir": str(shadow_dir),
                        },
                        "required_artifacts": [
                            "main_strategy_dir/sleeve_mix_summary.csv",
                            "main_strategy_dir/sleeve_mix_annual.csv",
                            "main_strategy_dir/sleeve_mix_issue_profit.csv",
                            "ticket_pool_csv",
                            "joint_leg_rows_csv",
                        ],
                        "promotion": {"validated": True},
                        "validation": {"no_future_leakage": True},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return config_path, tmp_path / "500.sqlite"


def test_strategy_release_endpoint_exposes_manifest(monkeypatch, tmp_path: Path) -> None:
    config_path, db_path = _build_release_fixture(tmp_path)
    _minimal_db(db_path)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", config_path)
    _clear_strategy_caches()

    try:
        app = appmod.create_app(sqlite_db=db_path)
        with app.test_client() as client:
            response = client.get("/api/strategy-release")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["release_id"] == "fixture_release"
        assert payload["strategy_family"] == "fixture family"
        assert payload["main_strategy_arms"][0]["arm_id"] == "custom_release_arm"
        assert any(variant["kind"] == "shadow" for variant in payload["decision_variants"])
        assert payload["artifact_health"]["missing_required"] == []
    finally:
        _clear_strategy_caches()


def test_main_strategy_reads_release_artifacts(monkeypatch, tmp_path: Path) -> None:
    config_path, db_path = _build_release_fixture(tmp_path)
    _minimal_db(db_path)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", config_path)
    _clear_strategy_caches()

    try:
        app = appmod.create_app(sqlite_db=db_path)
        with app.test_client() as client:
            response = client.get("/api/issues/99123/main-strategy")

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["strategy_release"]["release_id"] == "fixture_release"
        assert payload["candidates"][0]["arm_id"] == "custom_release_arm"
        assert payload["ev_pool"]["available"] is True
        assert payload["ev_pool"]["tickets"][0]["source_strategy"] == "custom_release_arm"
        assert payload["source"]["main_strategy_dir"].endswith("results/main_strategy_custom")
    finally:
        _clear_strategy_caches()
