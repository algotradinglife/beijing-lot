from pathlib import Path

from scripts.check_cutoff_governance import violations


ROOT = Path(__file__).resolve().parents[2]


def test_repository_cutoff_governance_static_gate() -> None:
    assert violations(ROOT) == []


def test_templates_and_inventory_are_present() -> None:
    assert (ROOT / "docs/research/templates/cutoff-learning-contract.md").is_file()
    assert (ROOT / "docs/research/templates/cutoff-learning-review.md").is_file()
    inventory = ROOT / "docs/research/temporal-function-inventory.csv"
    assert "src/cutoff_mapping/api.py" in inventory.read_text(encoding="utf-8")
