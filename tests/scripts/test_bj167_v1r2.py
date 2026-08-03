"""Durability checks for the corrected #167 Gate-B v1r2 package."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj167_gate_b_outcome_settlement_v1r2"
MANIFEST = "6946ea6c92a871fe97159980e5a8440e5927cf789b272c227b7d3c4175e96758"
CONTENT = "6a86977a004b3a96c3b0eb9c488d4da2f272157af02051e01d4ff928f9dcee2f"


def manifest_check() -> None:
    manifest_path = PACKAGE / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() for name in manifest}
    assert manifest == actual
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == MANIFEST
    assert hashlib.sha256((PACKAGE / "CONTENT_IDENTITY.json").read_bytes()).hexdigest() == CONTENT


def rows(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_v1r2_manifest_and_required_controls() -> None:
    manifest_check()
    card = json.loads((PACKAGE / "validation_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_B_OUTCOME_SETTLEMENT_N7_SEED_ENSEMBLE"
    assert card["n"] == 7
    assert card["seed_panel"] == [f"137{i:03d}" for i in range(1, 101)]
    assert card["identity_settlement_rows"] == 301500
    assert card["issue_settlement_rows"] == 104400
    assert card["slice_summary_rows"] == 6300
    assert card["loyo_rows"] == 2100
    assert card["bootstrap_replicates"] == 2000
    for filename in ("seed_summary.csv", "slice_summary.csv", "loyo_summary.csv", "year_fold_summary.csv", "concentration_hhi.svg", "drawdown.svg"):
        assert (PACKAGE / filename).is_file()


def test_seed_rows_expose_risk_and_concentration_contract() -> None:
    seed_rows = rows("seed_summary.csv")
    assert len(seed_rows) == 300
    required = {
        "drawdown_no_tax_yuan", "drawdown_tax_adjusted_yuan", "longest_miss_streak",
        "largest_signed_issue", "largest_signed_year", "ex_largest_issue_no_tax_roi",
        "ex_largest_year_no_tax_roi", "gross_issue_hhi", "duplicate_ticket_count",
    }
    assert required <= set(seed_rows[0])
    assert all(int(row["duplicate_ticket_count"]) == 0 for row in seed_rows)
    assert {row["scope"] for row in rows("loyo_summary.csv")} == {"LOYO"}
    assert {row["scope"] for row in rows("year_fold_summary.csv")} == {"YEAR", "FOLD"}


def test_v1r2_keeps_no_promotion_and_no_pooling_boundary() -> None:
    card = json.loads((PACKAGE / "validation_card.json").read_text(encoding="utf-8"))
    assert card["promotion_authorized"] is False
    assert "no pooling" in card["tax_rule"]
    text = (PACKAGE / "interpretation.md").read_text(encoding="utf-8")
    assert "not 100 independent football histories" in text
    assert "YEAR and FOLD" in text and "LOYO" in text
