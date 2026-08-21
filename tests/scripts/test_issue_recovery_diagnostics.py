from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_function(script_name: str):
    path = ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._recovery_diagnostics


@pytest.mark.parametrize(
    "script_name",
    ["analyze_bj286_joint_policy.py", "analyze_bj291_rare_event_value.py"],
)
def test_recovery_diagnostics_separate_completed_and_open_episodes(
    script_name: str,
) -> None:
    diagnostics = _load_function(script_name)
    capital = np.array([99_990.0, 100_000.0, 100_010.0, 100_005.0, 100_004.0])
    assert diagnostics(capital) == (1, 2)


@pytest.mark.parametrize(
    "script_name",
    ["analyze_bj286_joint_policy.py", "analyze_bj291_rare_event_value.py"],
)
def test_recovery_diagnostics_report_no_open_episode_at_new_peak(
    script_name: str,
) -> None:
    diagnostics = _load_function(script_name)
    capital = np.array([99_990.0, 100_000.0, 100_020.0])
    assert diagnostics(capital) == (1, 0)
