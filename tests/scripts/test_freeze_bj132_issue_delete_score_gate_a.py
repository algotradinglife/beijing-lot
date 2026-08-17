"""Integrity checks for #132's replacement complete-issue Gate-A freeze."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj132_gate_a_complete_issue_preoutcome_v1r1"
SCRIPT = ROOT / "scripts" / "freeze_bj132_issue_delete_score_gate_a.py"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def gzip_rows(name: str):
    with gzip.open(PACKAGE / name, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_complete_manifest_and_preoutcome_boundary() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert manifest == {item.name: digest(item) for item in PACKAGE.iterdir() if item.is_file() and item.name != "SHA256SUMS.json"}
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_MATCHED_FREEZE"
    assert card["denominator"] == {"eligible_matches": 47819, "issue_instances": 348, "frontier_rows": 160734, "portfolio_identities": 52534, "role_rows": 367738, "ranker_disagreements": 43120}
    assert card["complete_issue_contract"]["large_issue_cap"] == 32
    assert "Gate B is NOT_RUN and NOT_AUTHORIZED" in card["outcome_boundary"]
    source = SCRIPT.read_text(encoding="utf-8").lower()
    for forbidden in ("sqlite3", "winning_sp", "result_label", "settle_bj", "final_sp"):
        assert forbidden not in source


def test_issue_is_the_undivided_primary_unit() -> None:
    census = list(csv.DictReader((PACKAGE / "issue_census.csv").open(newline="", encoding="utf-8")))
    assert len(census) == 348
    assert {row["fold_integrity"] for row in census} == {"INTACT"}
    assert {row["selection_scope"] for row in census} == {"COMPLETE_ISSUE"}
    assert len({row["issue_instance"] for row in census}) == len(census)
    assert any(int(row["source_segment_count"]) > 1 for row in census)
    scatter = list(csv.DictReader((PACKAGE / "candidate_scatter.csv").open(newline="", encoding="utf-8")))
    assert len(scatter) == 47819
    assert len({row["match_id"] for row in scatter}) == len(scatter)
    assert {row["issue_instance"] for row in scatter} == {row["issue_instance"] for row in census}


def test_matched_arms_shared_roles_and_complete_issue_candidate_cap() -> None:
    frontier = list(gzip_rows("matched_delete_score_frontier.csv.gz"))
    assert Counter(row["arm"] for row in frontier) == {"NO_BET_CONTROL": 3132, "MATCHED_FULL_N7": 52534, "P_MIN_DELETE_N7": 52534, "Q_MIN_DELETE_N7": 52534}
    available = defaultdict(list)
    for row in frontier:
        if row["disposition"] == "AVAILABLE":
            available[(row["variant_id"], row["portfolio_id"])].append(row)
            assert int(row["candidate_search_count"]) <= 32
            assert int(row["candidate_rank_in_complete_issue"]) <= 32
            assert int(row["selected_n"]) == 7
            assert row["selection_scope"] == "COMPLETE_ISSUE"
            assert row["participation_policy"] == "ALL_FROZEN_PORTFOLIOS_RETAINED"
    assert len(available) == 52534
    for arms in available.values():
        assert {row["arm"] for row in arms} == {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"}
        assert len({row["selected_match_ids"] for row in arms}) == 1
        assert {int(row["formula_k"]) for row in arms if row["arm"] == "MATCHED_FULL_N7"} == {2187}
        assert {int(row["formula_k"]) for row in arms if row["arm"] != "MATCHED_FULL_N7"} == {1458}
    roles = defaultdict(list)
    for row in gzip_rows("portfolio_role_assignments.csv.gz"):
        roles[(row["variant_id"], row["portfolio_id"])].append(row)
        for code in ("3", "1", "0"):
            assert abs(float(row[f"q{code}"]) - float(row[f"p{code}"]) * float(row[f"predicted_sp{code}"])) < 2e-9
    assert len(roles) == 52534
    assert {len(rows) for rows in roles.values()} == {7}


def test_q_min_disagreement_and_issue_accounting_are_explicit() -> None:
    disagreements = list(gzip_rows("ranker_disagreements.csv.gz"))
    assert len(disagreements) == 43120
    for row in disagreements:
        assert (row["p_min_deleted_match_id"], row["p_min_deleted_code"]) != (row["q_min_deleted_match_id"], row["q_min_deleted_code"])
    accounting = list(csv.DictReader((PACKAGE / "issue_accounting.csv").open(newline="", encoding="utf-8")))
    assert accounting
    for row in accounting:
        assert row["tax_bucket_key"] == f"{row['issue_instance']}|{row['variant_id']}|{row['arm']}"
        assert row["loyo_unit"] == "entire issue instance held intact within its year/fold"
        assert int(row["portfolio_count"]) > 0
