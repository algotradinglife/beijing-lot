from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/generate_bj_n7_structured.py"


def load():
    spec = importlib.util.spec_from_file_location("n7_structured", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_structured_pool_sizes_and_top256_constraints():
    mod = load()
    legs = tuple(
        mod.base.Leg("26071", i, f"s{i}", "k", "d", "s", (3.0, 3.0, 3.0))
        for i in range(1, 8)
    )
    options = {pair.excluded: pair for pair in mod.pair_options(legs[0], 0.60)}
    assignment = {
        "full_positions": (0, 1),
        "double_positions": (2, 3, 4, 5, 6),
        "pairs": tuple(options[code] for code in ("3", "1", "0", "3", "1")),
    }
    pool = mod.physical_pool(legs, assignment)
    assert len(pool) == 288
    retained = mod.top256(pool)
    assert retained and len(retained) == 256
    assert len({item.sequence for item in retained}) == 256
    counts = [sum(item.counts[i] for item in retained) for i in range(3)]
    assert 0.30 <= counts[0] / (7 * 256) <= 0.40
    assert 0.30 <= counts[1] / (7 * 256) <= 0.40
    assert 0.25 <= counts[2] / (7 * 256) <= 0.35


def test_pair_threshold_and_repeatability():
    mod = load()
    leg = mod.base.Leg("26071", 1, "s1", "k", "d", "s", (2.6, 3.2, 4.2))
    assert all(pair.coverage >= 0.75 for pair in mod.pair_options(leg, 0.75))
    legs = [
        mod.base.Leg("26071", i, f"s{i}", "k", "d", "s", (2.6, 3.2, 4.2))
        for i in range(1, 8)
    ]
    first = mod.generate(legs)
    second = mod.generate(legs)
    assert first == second


def test_top256_summary_uses_retained_not_parent_coverage():
    mod = load()
    legs = tuple(
        mod.base.Leg("26071", i, f"s{i}", "k", "d", "s", (3.0, 3.0, 3.0))
        for i in range(1, 8)
    )
    options = {pair.excluded: pair for pair in mod.pair_options(legs[0], 0.60)}
    assignment = {
        "full_positions": (0, 1),
        "double_positions": (2, 3, 4, 5, 6),
        "pairs": tuple(options[code] for code in ("3", "1", "0", "3", "1")),
        "excluded_codes": ("3", "1", "0", "3", "1"),
        "package_coverage": 0.0,
    }
    parent = mod.physical_pool(legs, assignment)
    retained = mod.top256(parent)
    assert retained
    row = mod._summary(
        "26071", 0.75, "STRUCTURED_2F_5D_TOP256", 512, assignment, parent, retained
    )
    assert float(row["package_coverage"]) == pytest.approx(
        sum(item.coverage for item in retained)
    )
    assert float(row["parent_package_coverage"]) - float(
        row["package_coverage"]
    ) == pytest.approx(float(row["probability_mass_lost"]), abs=2e-12)
    assert float(row["package_coverage"]) < float(row["parent_package_coverage"])


def test_top256_wrong_count_fails_closed(monkeypatch: pytest.MonkeyPatch):
    mod = load()
    legs = tuple(
        mod.base.Leg("26071", i, f"s{i}", "k", "d", "s", (3.0, 3.0, 3.0))
        for i in range(1, 8)
    )
    options = {pair.excluded: pair for pair in mod.pair_options(legs[0], 0.60)}
    assignment = {
        "full_positions": (0, 1),
        "double_positions": (2, 3, 4, 5, 6),
        "pairs": tuple(options[code] for code in ("3", "1", "0", "3", "1")),
    }
    pool = mod.physical_pool(legs, assignment)

    class Result:
        success = True
        status = 0
        x = np.zeros(len(pool))

    monkeypatch.setattr("scipy.optimize.milp", lambda **_kwargs: Result())
    with pytest.raises(mod.base.FreezeError, match="selected count mismatch"):
        mod.top256(pool)
