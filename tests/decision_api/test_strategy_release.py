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


def test_shadow_variant_options_are_manifest_allowlisted(tmp_path: Path) -> None:
    issue = "99123"
    shadow_dir = tmp_path / "results/shadow_custom"
    header = [
        "match_idx",
        "shadow_arm",
        "shadow_version",
        "shadow_selection_codes",
        "shadow_primary",
        "shadow_judgment",
        "shadow_stop_flag",
    ]
    _write_csv(
        shadow_dir / f"{issue}_old" / f"structured_shadow_{issue}.csv",
        header,
        [[1, "shadow_v3.3.1", "llm_chain_bet_protect_stop_v3.3.1_shadow", "3", "3", "胜", "0"]],
    )
    _write_csv(
        shadow_dir / f"{issue}_current" / f"structured_shadow_{issue}.csv",
        header,
        [[1, "shadow_v3.3.3", "llm_chain_bet_protect_stop_v3.3.3_shadow", "1", "1", "平", "0"]],
    )
    release = {
        "schema_version": "strategy_release_registry_v1",
        "active_release_id": "main_n7_384_2026_07_04",
        "release_id": "main_n7_384_2026_07_04",
        "decision_variants": [
            {"variant_id": "active_v3", "version_id": "3.0.0", "kind": "active", "label": "v3 retired", "source": "active_snapshot", "is_default": False, "selectable": False},
            {
                "variant_id": "active_v3.3.3",
                "version_id": "3.3.3",
                "kind": "shadow",
                "label": "正式版 v3.3.3",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "artifact_variant_ids": ["shadow_v3.3.3"],
                "legacy_variant_ids": ["shadow_v3.3.3"],
                "is_default": True,
                "selectable": True,
                "legacy_aliases": ["shadow_v3.3.3"],
                "readiness": {"artifact_required": True, "defaultable_when": "available", "missing_behavior": "artifact_missing", "late_refresh": "not_applicable"},
            },
        ],
        "artifacts": {"structured_shadow_dir": str(shadow_dir)},
        "required_artifacts": [],
        "promotion": {"validated": True},
        "validation": {"no_future_leakage": True},
    }

    variants, suppressed = appmod._structured_shadow_variant_scan(issue, release)
    options = appmod._decision_variant_options(variants, release=release)
    unavailable = appmod._strategy_version_context(
        release,
        options,
        "shadow_v3.3.1",
        suppressed_shadow_variant_ids=suppressed,
    )
    available = appmod._strategy_version_context(release, options, "shadow_v3.3.3")

    assert [item["variant_id"] for item in options] == ["active_v3.3.3"]
    assert options[0]["source_variant_id"] == "shadow_v3.3.3"
    assert options[0]["legacy_variant_id"] == "shadow_v3.3.3"
    assert options[0]["legacy_aliases"] == ["shadow_v3.3.3"]
    assert suppressed == ["shadow_v3.3.1"]
    assert unavailable["selection_status"] == "unavailable"
    assert unavailable["selected_variant_id"] == "active_v3.3.3"
    assert unavailable["contract_warnings"][0]["variant_ids"] == ["shadow_v3.3.1"]
    assert available["selection_status"] == "ok"
    assert available["resolved_requested_variant_id"] == "active_v3.3.3"
    assert available["requested_canonical_variant_id"] == "active_v3.3.3"
    assert available["selected_variant_id"] == "active_v3.3.3"


def test_shadow_variant_version_key_supports_four_digit_fix_numbers() -> None:
    assert appmod._decision_variant_version_key("shadow_v3.3.0010") > appmod._decision_variant_version_key("shadow_v3.3.0009")
    assert appmod._decision_variant_version_key("shadow_v3.4.0000") > appmod._decision_variant_version_key("shadow_v3.3.9999")
    assert appmod._decision_variant_version_key("shadow_v4.0.0000") > appmod._decision_variant_version_key("shadow_v3.999.9999")
    assert appmod._decision_variant_version_key("shadow_v3.3.3")[:3] == appmod._decision_variant_version_key("shadow_v3.3.0003")[:3]


def test_incomplete_shadow_variant_is_suppressed_from_options() -> None:
    release = {
        "decision_variants": [
            {"variant_id": "active_v3", "kind": "active", "source": "active_snapshot", "is_default": False, "selectable": False},
            {
                "variant_id": "active_v3.3.3",
                "kind": "shadow",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "artifact_variant_ids": ["shadow_v3.3.3"],
                "legacy_variant_ids": ["shadow_v3.3.3"],
                "is_default": True,
                "selectable": True,
                "legacy_aliases": ["shadow_v3.3.3"],
                "readiness": {"artifact_required": True, "defaultable_when": "available", "missing_behavior": "artifact_missing", "late_refresh": "not_applicable"},
            },
        ]
    }
    shadow_variants = [
        (
            {
                1: {
                    "match_idx": "1",
                    "shadow_arm": "shadow_v3.3.3",
                    "_manifest_variant_id": "active_v3.3.3",
                    "_source_shadow_arm": "shadow_v3.3.3",
                    "shadow_version": "fixture",
                    "shadow_selection_codes": "3+1",
                    "shadow_primary": "3",
                    "shadow_stop_flag": "0",
                }
            },
            "results/structured_decision_chain_shadow/26072_fixture/structured_shadow_26072.csv",
        )
    ]

    complete, incomplete = appmod._complete_shadow_variants("26072", shadow_variants, {1, 2}, release=release)
    options = appmod._decision_variant_options(complete, release=release)
    context = appmod._strategy_version_context(
        release,
        options,
        "active_v3.3.3",
        incomplete_shadow_variants=incomplete,
    )

    assert complete == []
    assert incomplete[0]["variant_id"] == "active_v3.3.3"
    assert incomplete[0]["artifact_variant_id"] == "shadow_v3.3.3"
    assert incomplete[0]["missing_match_idx"] == [2]
    assert [item["variant_id"] for item in options] == ["active_v3.3.3"]
    assert options[0]["available"] is False
    assert options[0]["readiness_status"] == "unavailable"
    assert context["selection_status"] == "degraded"
    assert context["selected_variant_id"] == "active_v3.3.3"
    assert context["contract_warnings"][0]["type"] == "structured_shadow_artifacts_incomplete"
    assert context["contract_warnings"][0]["artifacts"][0]["missing_match_idx"] == [2]


def test_shadow_execution_variant_exposes_sp_repricing_fields() -> None:
    variant = appmod._shadow_decision_variant(
        {
            "shadow_arm": "shadow_v4.2.0000_execution_late_proxy_fullcap2",
            "shadow_version": "fixture",
            "shadow_selection_codes": "1+0",
            "shadow_primary": "1",
            "shadow_stop_flag": "0",
            "source_sp_3": "14.84",
            "source_sp_1": "1.08",
            "source_sp_0": "70.94",
            "source_q_3": "5.936",
            "source_q_1": "0.3024",
            "source_q_0": "23.09",
            "execution_sp_3": "2.37",
            "execution_sp_1": "3.26",
            "execution_sp_0": "3.65",
            "execution_q_3": "0.948",
            "execution_q_1": "0.9128",
            "execution_q_0": "1.1881",
            "execution_sp_source": "live_sp_snapshots",
            "execution_sp_snapshot_ts": "2026-07-05T12:00:00+00:00",
            "execution_sp_repriced": "1",
            "execution_sp_reprice_ratio_max": "19.4356",
            "execution_sp_missing": "0",
        },
        "fixture.csv",
    )
    compact = appmod._compact_decision_variant(variant)

    assert compact["source_sp"]["0"] == 70.94
    assert compact["execution_sp"]["0"] == 3.65
    assert compact["execution_q"]["0"] == 1.1881
    assert compact["execution_sp_source"] == "live_sp_snapshots"
    assert compact["execution_sp_repriced"] is True
    assert compact["execution_sp_missing"] is False


def test_manifest_default_stays_default_over_higher_shadow_versions() -> None:
    options = [
        {"variant_id": "active_v3", "kind": "active", "is_default": False, "defaultable": False, "available": True, "selectable": False},
        {"variant_id": "active_v3.3.3", "kind": "shadow", "is_default": True, "defaultable": True, "available": True, "selectable": True, "legacy_aliases": ["shadow_v3.3.3"]},
        {"variant_id": "shadow_v4.2.0000_execution_late_proxy_fullcap2", "kind": "shadow", "is_default": False, "defaultable": True, "available": True, "selectable": True},
    ]

    normalized = appmod._normalize_decision_variant_defaults(options)

    defaults = [item["variant_id"] for item in normalized if item["is_default"]]
    assert defaults == ["active_v3.3.3"]


def _execution_release(shadow_dir: Path) -> dict[str, object]:
    return {
        "release_id": "fixture_execution_release",
        "decision_variants": [
            {
                "variant_id": "active_v3",
                "version_id": "3.0.0",
                "kind": "active",
                "source": "active_snapshot",
                "is_default": False,
                "selectable": False,
                "production_status": "retired",
                "readiness": {
                    "artifact_required": False,
                    "defaultable_when": "never",
                    "missing_behavior": "builtin_active",
                    "late_refresh": "not_applicable",
                },
            },
            {
                "variant_id": "active_v3.3.3",
                "version_id": "3.3.3",
                "kind": "shadow",
                "label": "正式版 v3.3.3",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "artifact_variant_ids": ["shadow_v3.3.3"],
                "legacy_variant_ids": ["shadow_v3.3.3"],
                "is_default": True,
                "selectable": True,
                "legacy_aliases": ["shadow_v3.3.3"],
                "readiness": {
                    "artifact_required": True,
                    "defaultable_when": "available",
                    "missing_behavior": "artifact_missing",
                    "late_refresh": "not_applicable",
                    "missing_reason": "structured_shadow_artifact_missing_for_issue",
                },
            },
            {
                "variant_id": "shadow_v4.2.0000_execution_late_proxy_fullcap2",
                "version_id": "4.2.0000",
                "kind": "shadow",
                "source": "structured_shadow_csv",
                "artifact_key": "structured_shadow_dir",
                "is_default": False,
                "selectable": True,
                "readiness": {
                    "artifact_required": True,
                    "defaultable_when": "never",
                    "missing_behavior": "hidden_until_artifact",
                    "late_refresh": "unlock_after_valid_live_sp_refresh",
                    "missing_reason": "late_proxy_execution_artifact_missing_or_not_refreshed",
                },
            },
        ],
        "required_artifacts": [],
        "artifacts": {"structured_shadow_dir": str(shadow_dir)},
    }


def test_execution_variant_readiness_defaults_only_real_artifacts(tmp_path: Path) -> None:
    issue = "99125"
    shadow_dir = tmp_path / "shadow"
    release = _execution_release(shadow_dir)
    header = [
        "match_idx",
        "shadow_arm",
        "shadow_version",
        "shadow_selection_codes",
        "shadow_primary",
        "shadow_judgment",
        "shadow_stop_flag",
        "execution_unlock_state",
    ]
    _write_csv(
        shadow_dir / f"{issue}_v3" / f"structured_shadow_{issue}.csv",
        header,
        [[1, "shadow_v3.3.3", "llm_chain_bet_protect_stop_v3.3.3_shadow", "3+1", "3", "胜保平", "0", "not_applicable"]],
    )

    variants, suppressed = appmod._structured_shadow_variant_scan(issue, release)
    options = appmod._decision_variant_options(variants, release=release)
    assert suppressed == []
    assert [item["variant_id"] for item in options] == ["active_v3.3.3"]
    assert next(item["variant_id"] for item in options if item["is_default"]) == "active_v3.3.3"
    assert not any(item["variant_id"] == "shadow_v4.2.0000_execution_late_proxy_fullcap2" for item in options)

    _write_csv(
        shadow_dir / f"{issue}_strict" / f"structured_shadow_{issue}.csv",
        header,
        [[1, "shadow_v4.2.0000_execution_strict_fullcap2", "v4.2.0000", "", "", "等待晚盘", "1", "waiting_late_refresh"]],
    )
    variants, _suppressed = appmod._structured_shadow_variant_scan(issue, release)
    options = appmod._decision_variant_options(variants, release=release)
    assert [item["variant_id"] for item in options] == ["active_v3.3.3"]
    assert next(item["variant_id"] for item in options if item["is_default"]) == "active_v3.3.3"

    _write_csv(
        shadow_dir / f"{issue}_late" / f"structured_shadow_{issue}.csv",
        header,
        [[1, "shadow_v4.2.0000_execution_late_proxy_fullcap2", "v4.2.0000", "3+1", "3", "胜保平", "0", "unlocked_after_late_refresh"]],
    )
    variants, _suppressed = appmod._structured_shadow_variant_scan(issue, release)
    options = appmod._decision_variant_options(variants, release=release)
    late_option = next(item for item in options if item["variant_id"] == "shadow_v4.2.0000_execution_late_proxy_fullcap2")
    assert late_option["available"] is True
    assert late_option["defaultable"] is False
    assert late_option["readiness_status"] == "available"
    assert next(item["variant_id"] for item in options if item["is_default"]) == "active_v3.3.3"


def test_unavailable_execution_variant_does_not_become_default(tmp_path: Path) -> None:
    issue = "99124"
    shadow_dir = tmp_path / "shadow"
    _write_csv(
        shadow_dir / f"{issue}_current" / f"structured_shadow_{issue}.csv",
        [
            "match_idx",
            "shadow_arm",
            "shadow_version",
            "shadow_selection_codes",
            "shadow_primary",
            "shadow_judgment",
            "shadow_stop_flag",
        ],
        [[1, "shadow_v3.3.3", "llm_chain_bet_protect_stop_v3.3.3_shadow", "3+1", "3", "胜为押，保平", "0"]],
    )
    release = _execution_release(shadow_dir)

    variants, suppressed = appmod._structured_shadow_variant_scan(issue, release)
    options = appmod._decision_variant_options(variants, release=release)
    option_ids = [item["variant_id"] for item in options]
    context = appmod._strategy_version_context(release, options, None, suppressed_shadow_variant_ids=suppressed)
    strict_context = appmod._strategy_version_context(
        release,
        options,
        "shadow_v4.2.0000_execution_strict_fullcap2",
        suppressed_shadow_variant_ids=suppressed,
    )
    matches = [{
        "match_idx": 1,
        "llm_selection_codes": ["3"],
        "llm_judgment": "胜",
        "llm_stop_flag": False,
        "result_code": "",
    }]
    appmod._attach_decision_variants(matches, variants, release=release)
    appmod._attach_selected_decision_variant(matches, context["selected_variant_id"])
    selected = matches[0]["selected_decision_variant"]
    appmod._attach_selected_decision_variant(matches, strict_context["selected_variant_id"])

    assert suppressed == []
    assert option_ids == ["active_v3.3.3"]
    assert "shadow_v4.2.0000_execution_late_proxy_fullcap2" not in option_ids
    assert context["selection_status"] == "ok"
    assert context["selected_variant_id"] == "active_v3.3.3"
    assert selected["variant_id"] == "active_v3.3.3"
    assert selected["source_variant_id"] == "shadow_v3.3.3"
    assert selected["selection_codes"] == ["3", "1"]
    assert selected["stop_flag"] is False

    assert strict_context["selection_status"] == "unavailable"
    assert strict_context["selected_variant_id"] == "active_v3.3.3"


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
