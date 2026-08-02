"""Contract tests for #127's outcome-unexposed matched N7 Gate-A package."""
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
SCRIPT = ROOT / "scripts" / "freeze_bj127_global_prune_n7_gate_a.py"
PACKAGE = ROOT / "results" / "bj127_gate_a_preoutcome_v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load():
    spec = importlib.util.spec_from_file_location("bj127_gatea", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def frontiers():
    with gzip.open(PACKAGE / "matched_frontier.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_complete_manifest_and_portable_replay_identity(tmp_path: Path) -> None:
    module = load()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in PACKAGE.iterdir()
              if item.is_file() and item.name != "SHA256SUMS.json"}
    assert manifest == actual
    replay = tmp_path / "replay"
    module.freeze(replay)
    assert json.loads((replay / "CONTENT_IDENTITY.json").read_text()) == json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text())


def test_native_pool_denominator_and_matched_ticket_identity() -> None:
    module = load()
    rows = list(frontiers())
    assert len(rows) == 204_361
    assert Counter(row["arm"] for row in rows) == {
        "NO_BET_CONTROL": 23_931,
        "MATCHED_FULL_N7": 90_215,
        "PRUNE_ONE_GLOBAL_N7": 90_215,
    }
    no_bets = Counter((row["variant_id"], row["pool_id"]) for row in rows if row["arm"] == "NO_BET_CONTROL")
    assert len(no_bets) == len(module.VARIANTS) * 2659
    assert set(no_bets.values()) == {1}
    for row in rows:
        if row["arm"] == "MATCHED_FULL_N7":
            assert int(row["formula_k"]) == 2187 and int(row["stake_yuan"]) == 4374
        if row["arm"] == "PRUNE_ONE_GLOBAL_N7":
            assert int(row["formula_k"]) == 1458 and int(row["stake_yuan"]) == 2916
            assert row["stake_reduction_fraction"] == "0.333333333333"


def test_one_global_deletion_and_no_unavailable_window_portfolios() -> None:
    module = load()
    arms: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in frontiers():
        if row["disposition"] == "AVAILABLE":
            assert row["pool_disposition"] == "AVAILABLE"
            arms[(row["variant_id"], row["portfolio_id"])].append(row)
    assert len(arms) == 90_215
    for pair in arms.values():
        assert {row["arm"] for row in pair} == {"MATCHED_FULL_N7", "PRUNE_ONE_GLOBAL_N7"}
        assert {row["selected_match_ids"] for row in pair}.__len__() == 1
        assert {row["deleted_match_id"] for row in pair}.__len__() == 1
        assert {row["deleted_code"] for row in pair}.__len__() == 1
    roles: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(PACKAGE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle): roles[(row["variant_id"], row["portfolio_id"])].append(row)
    for key, values in roles.items():
        assert len(values) == 7
        deleted = [row for row in values if row["is_global_deleted_code_match"] == "1"]
        assert len(deleted) == 1
        code = deleted[0]["global_deleted_code"]
        assert all(row["prune_allowed_codes"] == "310" for row in values if row is not deleted[0])
        assert code not in deleted[0]["prune_allowed_codes"]
        expected = min((float(row[f"p{candidate_code}"]), int(row["match_idx"]), module.CODES.index(candidate_code),
                        row["match_id"], candidate_code)
                       for row in values for candidate_code in module.CODES)
        assert (deleted[0]["match_id"], code) == (expected[3], expected[4])


def test_low_esp_candidate_is_retained_while_only_companions_take_match_floor() -> None:
    module = load()

    def match(match_id: str, match_idx: int, e_sp: float, p: dict[str, float]) -> dict[str, object]:
        return {"match_id": match_id, "match_idx": str(match_idx), "e_sp": e_sp, "p_min": min(p.values()), "p": p}

    candidate = match("candidate", 1, 2.50, {"3": .01, "1": .49, "0": .50})
    companions = [match(f"companion-{index}", index + 1, 3.20, {"3": .34, "1": .33, "0": .33})
                  for index in range(6)]
    assembled = module.assemble_selection(candidate, [candidate, *companions], 3.00, 3.05)
    assert assembled is not None
    selected, gm = assembled
    assert candidate in selected
    assert candidate["e_sp"] < 3.00 <= min(float(row["e_sp"]) for row in selected if row is not candidate)
    assert gm >= 3.05
    deleted_match, deleted_code, _ = module.global_minimum(selected)
    assert (deleted_match["match_id"], deleted_code) == ("candidate", "3")


def test_role_separation_expands_the_frozen_low_probability_frontier() -> None:
    with (PACKAGE / "threshold_census.csv").open(newline="", encoding="utf-8") as handle:
        census = {row["variant_id"]: int(row["deduplicated_portfolios"]) for row in csv.DictReader(handle)}
    assert census["ESP280_GM290_LOWP20"] == 1_135
    assert census["ESP290_GM300_LOWP20"] == 1_011
    assert census["ESP300_GM305_LOWP20"] == 371
    assert census["ESP300_GM305_LOWP30"] == 17_330

    saw_low_esp_candidate = False
    for values in _role_groups().values():
        candidate = next(row for row in values if row["is_deletion_candidate"] == "1")
        variant = candidate["variant_id"]
        e_sp_floor = {"ESP280": 2.80, "ESP290": 2.90, "ESP300": 3.00}[variant[:6]]
        if float(candidate["e_sp"]) < e_sp_floor:
            saw_low_esp_candidate = True
    assert saw_low_esp_candidate


def _role_groups() -> dict[tuple[str, str], list[dict[str, str]]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(PACKAGE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            groups[(row["variant_id"], row["portfolio_id"])].append(row)
    return groups


def test_gate_a_has_no_settlement_dependency_and_emits_scatter_evidence() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("bj95_gate_b", "canonical_outcome_join", "winning_sp", "tax_adjusted", "settlement_runner"):
        assert forbidden not in source
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["outcome_boundary"].startswith("No result")
    assert card["denominator"]["role_rows"] == 631_505
    assert (PACKAGE / "scatter_hexbin_density.csv").stat().st_size > 0
    assert len(list(PACKAGE.glob("scatter_issue_*.svg"))) == 3
    svg = next(PACKAGE.glob("scatter_issue_*.svg")).read_text(encoding="utf-8")
    assert "orange=candidate, red=global delete, green=companions" in svg
