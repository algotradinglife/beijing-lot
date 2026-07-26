"""Verified, immutable B0/B1 runner for SCORE-HCAP-HIST-001.

The CLI is intentionally a thin adapter around this module so the exact
G0-bound run-and-freeze path is testable twice from clean output roots.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import walkforward
from .binding import (
    G0Binding,
    require_bound_panel,
    verified_g0_binding,
    verify_b0_b1_package_binding,
)
from src.research_freeze_protocol import create_freeze_package, verify_freeze_package


ROOT = Path(__file__).resolve().parents[2]
SOURCE_LOGICAL_ID = "historical_xlsm"
RESEARCH_QUESTION = (
    "Does the frozen score-history independent-Poisson model improve 3/1/0 "
    "log loss over the frozen handicap-only prior?"
)


def frozen_b0_b1_config(binding: G0Binding) -> dict[str, Any]:
    """Return the sole formal configuration, bound to verified G0 bytes."""

    return {
        "experiment_id": "SCORE-HCAP-HIST-001",
        "experiment_type": "retrospective_walk_forward",
        "outcome_visibility": "historical_known",
        "execution_enabled": False,
        "frontend_selectable": False,
        "roi_authorized": False,
        "release_authorized": False,
        "g0_freeze_id": binding.g0_freeze_id,
        "g0_binding": binding.as_config(),
        "test_seasons": list(walkforward.TEST_SEASONS),
        "b0": "per-integer-handicap Dirichlet(1,1,1), global fallback",
        "b1": {
            "type": "independent_poisson",
            "prior_exposure": walkforward.PRIOR_EXPOSURE,
            "mapping": "exact_skellam",
        },
        "bootstrap": {
            "seed": walkforward.BOOTSTRAP_SEED,
            "replicates": walkforward.BOOTSTRAP_REPLICATES,
            "block": "issue",
            "stratified_by": "season",
        },
        "persisted_float_codec": walkforward.persistence_contract(),
        "runtime_environment_receipt": "runtime_environment.json",
    }


def run_and_freeze(
    *,
    g0_freeze_dir: Path,
    source_db: Path,
    output_dir: Path,
    freeze_dir: Path,
    frozen_at_utc: str,
    git_commit: str,
) -> dict[str, Any]:
    """Run the only legal B0/B1 replay and publish its immutable package."""

    binding = verified_g0_binding(g0_freeze_dir=g0_freeze_dir, source_db=source_db)
    panel = require_bound_panel(binding.panel, binding)
    config = frozen_b0_b1_config(binding)
    result = walkforward.run_walkforward(
        panel=panel, output_dir=output_dir, frozen_config=config
    )
    # Re-check both immutable sources after metric generation and before B0/B1
    # packaging, so a changed G0 package or source snapshot cannot be published.
    if verified_g0_binding(g0_freeze_dir=g0_freeze_dir, source_db=source_db) != binding:
        raise RuntimeError("G0 binding changed while B0/B1 was running")
    require_bound_panel(panel, binding)
    config_path = output_dir / "frozen_b0_b1_config.json"
    decision = output_dir / "final_decision.json"
    outputs = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name not in {"final_decision.json", "frozen_b0_b1_config.json"}
    )
    package = create_freeze_package(
        freeze_dir,
        experiment_id="SCORE-HCAP-HIST-001-B0-B1",
        research_question=RESEARCH_QUESTION,
        model_version="score-hcap-hist-b1-v1",
        input_files=[panel],
        input_datasets=[source_db],
        input_dataset_labels=[SOURCE_LOGICAL_ID],
        prediction_files=outputs,
        decision_files=[decision],
        config_file=config_path,
        metadata_files=[ROOT / "docs/research/experiments/SCORE-HCAP-HIST-001-preregistration.md"],
        git_commit=git_commit,
        frozen_at_utc=frozen_at_utc,
    )
    verify_b0_b1_package_binding(freeze_dir, binding)
    return {
        "summary": result["summary"],
        "g0_binding": binding.as_config(),
        "freeze": package,
        "verification": verify_freeze_package(freeze_dir),
    }
