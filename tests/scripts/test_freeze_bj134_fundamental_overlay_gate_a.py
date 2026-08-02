import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj134_gate_a_preoutcome_v1"
MANIFEST = "51f5323f48e8851f030e022a16e62edf46622dc01b8d2b22202b7f9b23f8ddf4"
FORBIDDEN_HEADER_TOKENS = ("outcome", "result", "score", "winning_sp", "settlement", "payout", "tax", "roi")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_manifest_is_self_consistent_and_immutable() -> None:
    assert sha256(PACKAGE / "SHA256SUMS.json") == MANIFEST
    checksums = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert set(checksums) == {path.name for path in PACKAGE.iterdir() if path.name != "SHA256SUMS.json"}
    assert all(sha256(PACKAGE / name) == value for name, value in checksums.items())


def test_gate_a_card_and_source_boundary() -> None:
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_FULL_N7_OVERLAY_FREEZE"
    assert card["output_boundary"].startswith("No target result")
    assert card["candidate_contract"]["primary_unit"] == "complete (issue, fold) issue instance"
    assert card["chronology"]["history_rule"] == "for target year y, history query is season_year < y; no target-year result is read or used"
    assert set(card["arms"]) == {"MARKET_E_SP_GM", "FUNDAMENTALS_ONLY", "DECISION_CHAIN_ONLY", "FUNDAMENTALS_PLUS_DECISION"}
    census = list(csv.DictReader((PACKAGE / "source_census.csv").open(newline="", encoding="utf-8")))
    assert all(row["sha256"] for row in census)
    assert any("season_year < target year" in row["boundary"] for row in census)


def test_frontier_is_matched_across_four_arms_without_outcome_fields() -> None:
    with (PACKAGE / "portfolio_scores.csv").open(newline="", encoding="utf-8") as handle:
        portfolio = csv.DictReader(handle)
        portfolio_fields = portfolio.fieldnames or []
        portfolio_rows = list(portfolio)
    with (PACKAGE / "selection_frontier.csv").open(newline="", encoding="utf-8") as handle:
        frontier = csv.DictReader(handle)
        frontier_fields = frontier.fieldnames or []
        frontier_rows = list(frontier)
    for fields in (portfolio_fields, frontier_fields):
        assert not any(any(token in field.lower() for token in FORBIDDEN_HEADER_TOKENS) for field in fields if field != "outcome_boundary")
    assert len(portfolio_rows) == 52534
    assert len(frontier_rows) == 59304
    assert {row["arm"] for row in frontier_rows} == {"MARKET_E_SP_GM", "FUNDAMENTALS_ONLY", "DECISION_CHAIN_ONLY", "FUNDAMENTALS_PLUS_DECISION"}
    assert {row["k"] for row in frontier_rows} == {"1", "2", "4", "8", "16", "ALL"}
    assert all(row["outcome_boundary"] == "NO_TARGET_OUTCOME_OR_SETTLEMENT" for row in frontier_rows)
