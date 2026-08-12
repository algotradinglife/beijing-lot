"""Integrity checks for #132's outcome-unexposed p-min/q-min freeze."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj132_delete_score_n7_gate_a.py"
PACKAGE = ROOT / "results" / "bj132_gate_a_preoutcome_v1"
SOURCE = ROOT / "results" / "bj127_gate_a_preoutcome_v2"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def module():
    spec = importlib.util.spec_from_file_location("bj132_gatea", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def rows(name: str):
    with gzip.open(PACKAGE / name, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_complete_manifest_and_portable_replay_identity(tmp_path: Path) -> None:
    loaded = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert manifest == {item.name: digest(item) for item in PACKAGE.iterdir() if item.is_file() and item.name != "SHA256SUMS.json"}
    replay = tmp_path / "replay"
    loaded.write_package(replay)
    assert json.loads((replay / "CONTENT_IDENTITY.json").read_text()) == json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text())


def test_exactly_inherits_bj127_portfolios_and_p_min_delete() -> None:
    source = [row for row in rows_from_source() if row["arm"] == "MATCHED_FULL_N7"]
    frozen = [row for row in rows("matched_delete_score_frontier.csv.gz") if row["arm"] == "MATCHED_FULL_N7"]
    assert len(source) == len(frozen) == 90_215
    by_key = {(row["variant_id"], row["portfolio_id"]): row for row in frozen}
    for row in source:
        frozen_row = by_key[(row["variant_id"], row["portfolio_id"])]
        assert frozen_row["selected_match_ids"] == row["selected_match_ids"]
        assert frozen_row["p_min_deleted_match_id"] == row["deleted_match_id"]
        assert frozen_row["p_min_deleted_code"] == row["deleted_code"]


def rows_from_source():
    with gzip.open(SOURCE / "matched_frontier.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_three_matched_arms_and_explicit_no_bet_denominator() -> None:
    all_rows = list(rows("matched_delete_score_frontier.csv.gz"))
    assert Counter(row["arm"] for row in all_rows) == {"NO_BET_CONTROL": 23_931, "MATCHED_FULL_N7": 90_215, "P_MIN_DELETE_N7": 90_215, "Q_MIN_DELETE_N7": 90_215}
    available = defaultdict(list)
    for row in all_rows:
        if row["disposition"] == "AVAILABLE":
            available[(row["variant_id"], row["portfolio_id"])].append(row)
    assert len(available) == 90_215
    for group in available.values():
        assert {row["arm"] for row in group} == {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"}
        assert len({row["selected_match_ids"] for row in group}) == 1
        assert {int(row["formula_k"]) for row in group if row["arm"] == "MATCHED_FULL_N7"} == {2187}
        assert {int(row["formula_k"]) for row in group if row["arm"] != "MATCHED_FULL_N7"} == {1458}


def test_q_is_preoutcome_product_and_disagreements_are_complete() -> None:
    roles = defaultdict(list)
    for row in rows("portfolio_role_assignments.csv.gz"):
        roles[(row["variant_id"], row["portfolio_id"], row["arm"])].append(row)
        for code in ("3", "1", "0"):
            assert abs(float(row[f"q{code}"]) - float(row[f"p{code}"]) * float(row[f"predicted_sp{code}"])) < 2e-9
    for group in roles.values():
        assert len(group) == 7
    disagreements = list(rows("ranker_disagreements.csv.gz"))
    frontier = [row for row in rows("matched_delete_score_frontier.csv.gz")
                if row["rankers_disagree"] == "1" and row["arm"] == "P_MIN_DELETE_N7"]
    assert len(disagreements) == len(frontier) > 0
    for row in disagreements:
        assert (row["p_min_deleted_match_id"], row["p_min_deleted_code"]) != (row["q_min_deleted_match_id"], row["q_min_deleted_code"])


def test_gate_a_has_no_outcome_or_settlement_dependency() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("canonical_outcome_join", "bj127_gate_b", "bj131_gate_b", "results/bj95", "sqlite3.connect"):
        assert forbidden not in source.lower()
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["outcome_boundary"].startswith("No result")
    assert card["denominator"]["frontier_rows"] == 294_576
