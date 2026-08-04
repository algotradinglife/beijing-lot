from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import importlib.util
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py"
CORE_SCRIPT = ROOT / "scripts" / "bj180_team_matchup_core.py"
PACKAGE = ROOT / "results" / "bj180_gate_a_preoutcome_v2"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def row(**overrides):
    value = {
        "match_id": "1",
        "kickoff_ts": "2019-03-01 12:00:00",
        "league": "L1",
        "home_team_id": "H",
        "away_team_id": "A",
        "handicap_line_norm": -0.5,
        "fthg": 2,
        "ftag": 0,
    }
    value.update(overrides)
    return value


def test_contract_preserves_b0_and_freezes_team_family_ablations():
    runner = load(SCRIPT, "bj180_contract")
    core = load(CORE_SCRIPT, "bj180_core_contract")
    assert runner.BASE_MAIN_COMMIT == "210a791b0793e99e72358e02c8484458c900a98b"
    assert runner.FULL_TICKETS == 2187
    assert runner.FULL_STAKE_YUAN == 4374
    assert tuple(core.FAMILIES) == runner.FAMILIES
    assert tuple(core.CONFIGURATIONS) == runner.CONFIG_NAMES
    assert all(
        sum(config["weights"].values()) == pytest.approx(1.0)
        for config in core.CONFIGURATIONS.values()
    )
    arms = [item[0] for item in runner.ARMS]
    assert arms[:3] == ["B0_BEST_FULL", "L0_QUICK_LEAGUE", "H0_LEAGUE_DIAGNOSTIC"]
    assert "T1_DEEP_TEAM" in arms
    assert "TL1_TEAM_LEAGUE" in arms
    assert {
        arm.removeprefix("TL_MINUS_") for arm in arms if arm.startswith("TL_MINUS_")
    } == {"LATENT", "HOME_AWAY", "FORM", "REST", "OPPONENT", "INITIALIZATION", "H2H"}


def test_team_state_is_chronological_and_all_vectors_normalize():
    core = load(CORE_SCRIPT, "bj180_core_chronology")
    state = core.TeamMatchupState()
    empty_digest = state.history_event_sha256
    state.update(row())
    assert state.history_event_sha256 != empty_digest
    state.update(
        row(
            match_id="2",
            kickoff_ts="2019-03-05 12:00:00",
            home_team_id="A",
            away_team_id="H",
            fthg=1,
            ftag=1,
        )
    )
    with pytest.raises(RuntimeError, match="non-chronological"):
        state.update(row(match_id="3", kickoff_ts="2019-03-04 12:00:00"))
    target = row(match_id="4", kickoff_ts="2019-03-10 12:00:00", fthg=None, ftag=None)
    cutoff = core.parse_ts(target["kickoff_ts"])
    primary, diagnostics, families = state.probabilities(target, cutoff)
    assert sum(primary) == pytest.approx(1.0)
    assert set(families) == set(core.FAMILIES)
    assert all(sum(vector) == pytest.approx(1.0) for vector in families.values())
    assert diagnostics["home_history_n"] == 2
    assert diagnostics["away_history_n"] == 2
    assert diagnostics["h2h_prior_n"] == 2
    assert diagnostics["home_matches_7d"] == 1
    assert state.summary()["history_event_sha256"] == state.history_event_sha256


def test_new_team_and_league_transition_are_explicit_and_shrunk():
    core = load(CORE_SCRIPT, "bj180_core_transition")
    state = core.TeamMatchupState()
    unseen = row(home_team_id="NEW", away_team_id="OTHER", fthg=None, ftag=None)
    _, diagnostics, _ = state.probabilities(unseen, core.parse_ts(unseen["kickoff_ts"]))
    assert diagnostics["new_team_fallback"] == 1
    state.update(row(kickoff_ts="2019-03-01 12:00:00", league="L1"))
    before = state.teams["H"].elo
    state.update(row(match_id="2", kickoff_ts="2020-03-01 12:00:00", league="L2"))
    assert state.teams["H"].league_changes == 1
    assert abs(state.teams["H"].elo - 1500.0) < abs(before - 1500.0) + 60.0


def test_h2h_is_low_weight_prior_only_and_has_an_explicit_ablation():
    core = load(CORE_SCRIPT, "bj180_core_h2h")
    state = core.TeamMatchupState()
    for index in range(4):
        state.update(
            row(
                match_id=str(index),
                kickoff_ts=f"201{5 + index}-03-01 12:00:00",
                fthg=3,
                ftag=0,
            )
        )
    target = row(kickoff_ts="2020-03-01 12:00:00", fthg=None, ftag=None)
    cutoff = core.parse_ts(target["kickoff_ts"])
    full = state.probabilities(target, cutoff, "TEAM_PRIMARY")[0]
    minus = state.probabilities(target, cutoff, "TEAM_PRIMARY", "H2H_PRIOR")[0]
    assert full != minus
    assert core.CONFIGURATIONS["TEAM_PRIMARY"]["weights"]["H2H_PRIOR"] == 0.03


def test_target_projection_never_reads_result_or_settlement_fields():
    runner = load(SCRIPT, "bj180_target_boundary")
    source = inspect.getsource(runner.read_target_rows)
    for forbidden in runner.FORBIDDEN_TARGET_FIELDS:
        assert f"mf.{forbidden}" not in source
        assert f"m.{forbidden}" not in source
    historical = inspect.getsource(runner.historical_rows)
    assert "m.kickoff_ts < ?" in historical
    assert "ORDER BY m.kickoff_ts, m.match_id" in historical


def test_completion_embargo_excludes_recent_scores_and_includes_exact_boundary():
    runner = load(SCRIPT, "bj180_completion_embargo")
    cutoff = dt.datetime.fromisoformat("2025-08-01 12:00:00")
    boundary = cutoff - dt.timedelta(minutes=180)
    assert runner.COMPLETION_EMBARGO_MINUTES == 180
    assert runner.history_available_through(cutoff) == boundary
    assert runner.history_row_is_available(boundary, cutoff)
    assert not runner.history_row_is_available(
        boundary + dt.timedelta(microseconds=1), cutoff
    )
    assert not runner.history_row_is_available(
        cutoff - dt.timedelta(minutes=120), cutoff
    )


def test_baseline_reproduction_requires_exact_identity_sets():
    runner = load(SCRIPT, "bj180_baselines")
    source = []
    target = []
    for source_arm, target_arm in (
        ("B0_BEST_FULL", "B0_BEST_FULL"),
        ("Q1_QUICK_LEAGUE", "L0_QUICK_LEAGUE"),
        ("H_MINUS_RAW_HDA", "H0_LEAGUE_DIAGNOSTIC"),
    ):
        for index in range(189):
            issue = f"I{index}"
            source.append(
                {
                    "arm": source_arm,
                    "issue_instance": issue,
                    "policy_status": "SELECTED_PREOUTCOME",
                    "selected_portfolio_id": f"P{index}",
                }
            )
            target.append(
                {
                    "arm": target_arm,
                    "issue_instance": issue,
                    "policy_status": "SELECTED_PREOUTCOME",
                    "selected_portfolio_id": f"P{index}",
                }
            )
    rows = runner.reproduce_baselines(source, target)
    assert len(rows) == 3
    assert all(item["reproduction_status"] == "PASS" for item in rows)
    target[-1]["selected_portfolio_id"] = "DRIFT"
    with pytest.raises(RuntimeError, match="baseline identity reproduction drift"):
        runner.reproduce_baselines(source, target)


def test_accepted_source_packages_and_denominators_are_readable():
    runner = load(SCRIPT, "bj180_sources")
    runner.verify_package(
        runner.SOURCE_179_DIR, runner.SOURCE_179_MANIFEST, runner.SOURCE_179_CONTENT
    )
    runner.verify_package(
        runner.SOURCE_134_DIR, runner.SOURCE_134_MANIFEST, runner.SOURCE_134_CONTENT
    )
    source = runner.load_sources()
    assert len(source["candidates"]) == 424
    assert len(source["probabilities"]) == 1558
    assert len(source["selection"]) == 4872
    assert len(source["roles"]) == 2968


def test_generated_package_is_complete_outcome_unexposed_and_immutable_if_present():
    if not PACKAGE.is_dir():
        pytest.skip("formal immutable package not generated yet")
    manifest_path = PACKAGE / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = sorted(
        path.name
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    assert sorted(manifest) == actual
    assert all(
        hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
        for name, expected in manifest.items()
    )
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["gate_b_status"] == "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW"
    assert card["candidate_universe"] == {
        "identities": 424,
        "issues": 348,
        "matches": 1558,
        "no_bet": 159,
        "participating": 189,
        "roles": 2968,
    }
    assert card["version"] == "bj180-gate-a-v2"
    embargo = card["completion_embargo"]
    assert embargo["minutes"] == 180
    assert embargo["boundary"] == "inclusive"
    assert embargo["timestamp_source"] == "UNAVAILABLE_IN_SOURCE_SCHEMA"
    audit = list(
        csv.DictReader(
            (PACKAGE / "completion_embargo_audit.csv").open(
                newline="", encoding="utf-8"
            )
        )
    )
    assert len(audit) == embargo["cutoff_count"]
    assert (
        sum(int(item["excluded_near_cutoff_rows"]) > 0 for item in audit)
        == embargo["cutoffs_with_excluded_rows"]
    )
    assert (
        sum(int(item["excluded_near_cutoff_rows"]) for item in audit)
        == embargo["sum_cutoff_level_excluded_rows"]
    )
    assert all(item["embargo_minutes"] == "180" for item in audit)
    assert all(item["inclusive_boundary"] == "1" for item in audit)
    assert all(
        int(item["cumulative_safe_history_rows"])
        <= int(item["cumulative_old_kickoff_lt_rows"])
        for item in audit
    )
    with gzip.open(
        PACKAGE / "match_probability_freeze.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1558
    assert not set(rows[0]).intersection(
        {"fthg", "ftag", "result_code", "winning_sp", "roi"}
    )
    selection = list(
        csv.DictReader(
            (PACKAGE / "selection_freeze.csv").open(newline="", encoding="utf-8")
        )
    )
    assert len(selection) == 348 * 14
    assert Counter(row["policy_status"] for row in selection) == {
        "SELECTED_PREOUTCOME": 189 * 14,
        "NO_BET_FROZEN": 159 * 14,
    }
    coverage = list(
        csv.DictReader(
            (PACKAGE / "feature_coverage.csv").open(newline="", encoding="utf-8")
        )
    )
    outer_year = list(
        csv.DictReader(
            (PACKAGE / "outer_year_registry.csv").open(newline="", encoding="utf-8")
        )
    )
    assert coverage[0]["year"] == "ALL"
    assert sum(int(row["target_match_count"]) for row in outer_year) == 1558
    assert all(row["first_state_event_sha256"] for row in outer_year)
