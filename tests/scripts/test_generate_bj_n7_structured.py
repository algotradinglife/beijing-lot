from __future__ import annotations

import importlib.util
import itertools
import math
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


def test_top256_has_no_bet_row_when_parent_threshold_is_unavailable():
    mod = load()
    legs = [
        mod.base.Leg(issue, index, f"{issue}_{index}", "k", "d", "s", (4.5, 4.5, 2.0))
        for issue in mod.base.ISSUES
        for index in range(1, 8)
    ]

    combinations, summary = mod.generate(legs)

    assert combinations == []
    assert len(summary) == len(mod.base.ISSUES) * len(mod.THRESHOLDS) * 4
    for issue in mod.base.ISSUES:
        for threshold in mod.THRESHOLDS:
            rows = [
                row
                for row in summary
                if row["issue"] == issue and row["threshold"] == f"{threshold:.2f}"
            ]
            assert {row["arm"] for row in rows} == {
                "STRUCTURED_2F_5D_288",
                "STRUCTURED_2F_5D_TOP256",
                "STRUCTURED_3F_4D_432",
                "STRUCTURED_4F_3D_648",
            }
            top256 = next(
                row for row in rows if row["arm"] == "STRUCTURED_2F_5D_TOP256"
            )
            assert top256 == {
                "issue": issue,
                "threshold": f"{threshold:.2f}",
                "arm": "STRUCTURED_2F_5D_TOP256",
                "disposition": "NO_BET_PARENT_THRESHOLD_UNAVAILABLE",
                "combinations": "0",
                "stake_yuan": "512",
            }


def test_assignment_uses_coverage_frontier_not_equal_value_float_noise():
    mod = load()
    prices = (
        (2.7903412434671564, 2.762895179109697, 4.3354035081808),
        (2.675349020827538, 4.422857112960257, 2.6978038902579584),
        (2.782950234665716, 4.317034857117581, 2.7291922656021774),
        (2.5869637812212964, 4.256836598967818, 2.5818634470648423),
        (2.664478519182561, 4.231131417140891, 2.7217063607248893),
        (4.288757518388379, 2.528929714203542, 2.5452073790507064),
        (2.5670123328790226, 2.6517463235640215, 4.237717031911586),
    )
    legs = tuple(
        mod.base.Leg("26071", index, f"s{index}", "k", "d", "s", sp)
        for index, sp in enumerate(prices, 1)
    )
    chosen = mod.choose_assignment(legs, full_count=2, threshold=0.75)
    assert chosen is not None

    feasible_coverages = []
    for full_positions in itertools.combinations(range(7), 2):
        double_positions = tuple(
            index for index in range(7) if index not in full_positions
        )
        options = [mod.pair_options(legs[index], 0.75) for index in double_positions]
        if any(not values for values in options):
            continue
        feasible_coverages.extend(
            math.prod(pair.coverage for pair in pairs)
            for pairs in itertools.product(*options)
        )

    assert chosen["package_coverage"] == pytest.approx(
        max(feasible_coverages), rel=0.0, abs=1e-15
    )


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
