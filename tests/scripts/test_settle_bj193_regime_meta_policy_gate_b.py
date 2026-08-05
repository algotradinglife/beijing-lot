from __future__ import annotations

import importlib.util
import ctypes
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


C = load("bj193_core_test", ROOT / "scripts" / "bj193_gate_b_core.py")
R = load(
    "bj193_runner_test",
    ROOT / "scripts" / "settle_bj193_regime_meta_policy_gate_b.py",
)


def test_selector_screen_uses_roi_support_stake_and_lexical_ties():
    selector = ["B", "A", "C", "D"]
    stake = np.full((4, 20), 2.0)
    net = np.zeros_like(stake)
    net[2] = 1.0
    stake[3, 19] = 0.0
    chosen = C.selector_rank(net, stake, selector, list(range(20)), 4)
    assert chosen == [2, 1, 0, 3]
    # Below 20 active rows is fail-closed even if the observed ROI is huge.
    net[3] = 1_000.0
    assert C.selector_rank(net, stake, selector, list(range(20)), 1) == [2]


def test_seed_economics_are_mean_not_summed_exposure():
    values = np.array([8000.0, 100.0])
    assert np.array_equal(
        C.normalize_seed_aggregated(values, "ENSEMBLE_100"),
        np.array([80.0, 1.0]),
    )
    assert np.array_equal(
        C.normalize_seed_aggregated(values, "DETERMINISTIC"), values
    )


def test_train_only_transform_does_not_refit_on_query_extreme():
    train = np.arange(40, dtype=float).reshape(20, 2)
    query = np.array([[1_000_000.0, np.nan]])
    transform = C.FeatureTransform.fit(train)
    transformed = transform.apply(query)
    assert transformed.shape == (1, 4)
    assert transformed[0, 1] <= (
        transform.high[1] - transform.means[1]
    ) / transform.scales[1] + 1e-12
    assert transformed[0, 3] == 1.0


def test_model_families_are_deterministic_and_min_support_is_enforced():
    x = np.column_stack([np.linspace(-1, 1, 30), np.arange(30) % 3])
    y = np.column_stack([x[:, 0] * 0.5, np.ones(30)])
    active = np.ones_like(y, dtype=bool)
    active[19:, 1] = False
    groups = {"POOL_VALUE": [0], "UNCERTAINTY_DIVERGENCE": [1]}
    cases = [
        ("PRIOR_ONLY_FIXED", {}),
        ("BINNED_REGIME_RULE", {"quantile_bins": 3, "min_leaf": 10}),
        ("SHALLOW_TREE", {"max_depth": 2, "min_leaf": 10}),
        (
            "MONOTONE_REGULARIZED_SCORE",
            {"monotone_feature_group": "POOL_VALUE", "l2": 0.1},
        ),
        ("NEAREST_HISTORICAL_REGIME", {"k": 5, "weighting": "UNIFORM"}),
    ]
    for family, parameters in cases:
        one = C.predict_model(family, parameters, x, x[:3], y, active, groups)
        two = C.predict_model(family, parameters, x, x[:3], y, active, groups)
        assert np.array_equal(one, two, equal_nan=True)
        assert np.isfinite(one[:, 0]).all()
        assert np.isnan(one[:, 1]).all()


def test_canonical_status_fails_closed_across_split_instances():
    census = [
        {
            "selector_id": "S",
            "issue": "23011",
            "issue_instance": "23011@A",
            "selected_identity_count": "1",
        },
        {
            "selector_id": "S",
            "issue": "23011",
            "issue_instance": "23011@B",
            "selected_identity_count": "1",
        },
        {
            "selector_id": "S",
            "issue": "20031",
            "issue_instance": "20031@A",
            "selected_identity_count": "0",
        },
    ]
    statuses = {
        (0, "23011@A"): "SETTLED",
        (0, "23011@B"): "UNAVAILABLE_CANONICAL_OUTCOME",
        (0, "20031@A"): "NO_BET_FROZEN",
    }
    actual = R.atlas_canonical_status(census, statuses, {"S": 0})
    assert actual[(0, "23011")] == "UNAVAILABLE"
    assert actual[(0, "20031")] == "NO_BET"


def test_holding_calendar_and_active_sequences_are_distinct():
    rows = [
        {"net": -2.0, "stake": 2.0, "gross": 0.0},
        {"net": 0.0, "stake": 0.0, "gross": 0.0},
        {"net": -2.0, "stake": 2.0, "gross": 0.0},
        {"net": 8.0, "stake": 2.0, "gross": 10.0},
    ]
    metrics = C.holding_metrics(rows, reference_capital=100.0)
    assert metrics["max_negative_pnl_streak_calendar"] == 1
    assert metrics["max_negative_pnl_streak_active"] == 2
    assert metrics["max_miss_streak_calendar"] == 1
    assert metrics["max_miss_streak_active"] == 2
    assert metrics["roi"] == 2 / 3


def test_native_wrapper_compiles_without_changing_frozen_allocator(tmp_path):
    before = R.sha(R.FROZEN_ALLOCATOR)
    library, binary = R.compile_replay(tmp_path)
    assert library is not None
    assert binary.exists()
    assert R.sha(R.FROZEN_ALLOCATOR) == before == R.EXPECTED_ALLOCATOR_SHA256


def test_native_production_path_captures_issue_and_exact_seed_pool(tmp_path):
    lib, _binary = R.compile_replay(tmp_path)
    total = R.SCIENCE_CELLS
    tmp = [np.zeros(total) for _ in range(6)]
    totals = [np.zeros(total) for _ in range(7)]
    mark = np.zeros(total, dtype=np.uint8)
    touched = np.zeros(total, dtype=np.int32)
    cumulative = np.zeros(total)
    peak = np.zeros(total)
    drawdown = np.zeros(total)
    miss = np.zeros(total, dtype=np.int32)
    longest = np.zeros(total, dtype=np.int32)
    year_net = np.zeros((total, 1))
    year_stake = np.zeros((total, 1))
    fold_net = np.zeros((total, 1))
    fold_stake = np.zeros((total, 1))
    largest = np.full(total, -np.inf)
    largest_stake = np.zeros(total)
    largest_issue = np.full(total, -1, dtype=np.int32)
    full_net = np.zeros((1, 1))
    full_stake = np.zeros((1, 1))
    issue = [np.zeros((total, 1)) for _ in range(6)]
    seed_net = np.zeros((1, 6, 2, 20, 100, 1))
    seed_stake = np.zeros_like(seed_net)
    lib.bj167_scientific_set_buffers(
        *(R.np_ptr(value) for value in tmp),
        R.np_ptr(mark, ctypes.c_ubyte), R.np_ptr(touched, ctypes.c_int),
        *(R.np_ptr(value) for value in totals),
        R.np_ptr(cumulative), R.np_ptr(peak), R.np_ptr(drawdown),
        R.np_ptr(miss, ctypes.c_int), R.np_ptr(longest, ctypes.c_int),
        R.np_ptr(year_net), R.np_ptr(year_stake),
        R.np_ptr(fold_net), R.np_ptr(fold_stake),
        R.np_ptr(largest), R.np_ptr(largest_stake),
        R.np_ptr(largest_issue, ctypes.c_int),
        R.np_ptr(full_net), R.np_ptr(full_stake), 1, 1, 1,
    )
    lib.bj193_set_seed_fold_buffers(
        R.np_ptr(seed_net), R.np_ptr(seed_stake), 1, 1
    )
    lib.bj193_set_action_issue_buffers(*(R.np_ptr(value) for value in issue))
    role = np.asarray(
        [
            0.51, 0.29, 0.20, 0.42, 0.31, 0.27, 0.48, 0.33, 0.19,
            0.38, 0.35, 0.27, 0.46, 0.28, 0.26, 0.41, 0.32, 0.27,
            0.44, 0.30, 0.26,
        ],
        dtype=float,
    )
    occurrence = np.asarray([0], dtype=np.int32)
    lib.bj193_begin_issue(0, 0, 0)
    lib.bj193_process_source(
        R.np_ptr(role), 0, b"fixture", 100.0,
        R.np_ptr(occurrence, ctypes.c_int), 1, 0,
    )
    lib.bj167_scientific_add_structural(0, 0, 0, 2, 1, 2, 100.0)
    lib.bj193_end_issue()
    assert issue[0][0, 0] == seed_net[0, 0, 0, 0, :, 0].sum()
    assert issue[1][0, 0] == seed_stake[0, 0, 0, 0, :, 0].sum()
    # The frozen M2187 WOR profile equals 100 identical FULL exposures.
    assert issue[1][39, 0] / 100 == issue[1][960, 0]
    assert issue[2][39, 0] / 100 == issue[2][960, 0]
