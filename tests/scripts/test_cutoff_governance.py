import json
from pathlib import Path

from scripts.check_cutoff_governance import baseline_payload, violations


ROOT = Path(__file__).resolve().parents[2]


def test_repository_cutoff_governance_static_gate() -> None:
    assert violations(ROOT) == []


def test_templates_and_inventory_are_present() -> None:
    assert (ROOT / "docs/research/templates/cutoff-learning-contract.md").is_file()
    assert (ROOT / "docs/research/templates/cutoff-learning-review.md").is_file()
    inventory = ROOT / "docs/research/temporal-function-inventory.csv"
    assert "src/cutoff_mapping/api.py" in inventory.read_text(encoding="utf-8")


def _minimal_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "docs/research").mkdir(parents=True)
    (tmp_path / "docs/research/temporal-function-inventory.csv").write_text(
        "path,function,learned_operation,cutoff_interface,status,source_or_label_max,receipt_replay,migration_priority\n"
        "src/temporal_learning/core.py,prepare_learning_context,test,explicit,MIGRATED,strict,replay,P0\n",
        encoding="utf-8",
    )
    return tmp_path


def _freeze_baseline(root: Path) -> None:
    payload = baseline_payload(root)
    (root / "config/cutoff_governance_legacy_allowlist.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_scripts_direct_fit_is_scanned_and_rejected(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    _freeze_baseline(root)
    (root / "scripts/bad.py").write_text(
        "def train(model, x):\n    return model.fit(x)\n"
    )
    assert any(
        "scripts/bad.py" in item and "direct_historical_fit" in item
        for item in violations(root)
    )


def test_shared_import_does_not_authorize_unrelated_fit(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    _freeze_baseline(root)
    (root / "src/bad.py").write_text(
        "from src.temporal_learning import prepare_learning_context\n\n"
        "def unrelated(model, x):\n    return model.fit(x)\n",
        encoding="utf-8",
    )
    assert any(
        "src/bad.py" in item and "direct_historical_fit" in item
        for item in violations(root)
    )


def test_new_occurrence_in_legacy_file_exceeds_exact_baseline(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    legacy = root / "src/legacy.py"
    legacy.write_text("def old(model, x):\n    return model.fit(x)\n", encoding="utf-8")
    _freeze_baseline(root)
    legacy.write_text(
        "def old(model, x):\n    model.fit(x)\n    return model.fit(x)\n",
        encoding="utf-8",
    )
    assert any(
        "legacy direct_historical_fit occurrence count" in item
        for item in violations(root)
    )


def test_hard_coded_temporal_global_in_script_is_rejected(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    _freeze_baseline(root)
    (root / "scripts/bad.py").write_text("TUNE_YEAR = 2024\n", encoding="utf-8")
    assert any("hidden_temporal_global" in item for item in violations(root))
